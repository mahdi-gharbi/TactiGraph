"""Resumable official Qwen3 4B download for unreliable connections.

No inference runs here. Stop Ollama pulls for this tag before invoking this helper.
Every layer is verified against the pinned official manifest before installation.
"""

import hashlib
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "artifacts/ollama-download"
STORE = ROOT / "artifacts/ollama-models"
REGISTRY = "https://registry.ollama.ai/v2/library/qwen3"
MODEL = "sha256:3e4cb14174460404e7a233e531675303b2fbf7749c02f91864fe311ab6344e4f"
CHUNK = 4 * 1024 * 1024


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    (STORE / "blobs").mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 7200
    timeout = httpx.Timeout(60, connect=20)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        manifest_path = CACHE / "manifest.json"
        if not manifest_path.exists():
            response = client.get(REGISTRY + "/manifests/4b")
            response.raise_for_status()
            candidate = response.json()
            model = next(x for x in candidate["layers"] if x["mediaType"].endswith(".model"))
            if model["digest"] != MODEL or model["size"] != 2497280480:
                raise ValueError("The upstream tag changed; review a new model version explicitly")
            manifest_path.write_bytes(response.content)
        raw = manifest_path.read_bytes()
        pin = json.loads((ROOT / "configs/ollama-runtime-v1.json").read_text(encoding="utf-8"))
        if hashlib.sha256(raw).hexdigest() != pin["expected_manifest_sha256"]:
            raise ValueError("Manifest checksum differs from the reviewed model version")
        manifest = json.loads(raw)
        model = next(x for x in manifest["layers"] if x["mediaType"].endswith(".model"))
        if model["digest"] != MODEL or model["size"] != 2497280480:
            raise ValueError("Cached manifest does not describe the pinned model")
        print("Pinned manifest:", hashlib.sha256(raw).hexdigest(), flush=True)
        for layer in [*manifest["layers"], manifest["config"]]:
            digest = layer["digest"]
            if not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
                raise ValueError("Invalid blob digest")
            size = layer["size"]
            if not isinstance(size, int) or not 0 < size <= 3_000_000_000:
                raise ValueError("Invalid blob size")
            destination = STORE / "blobs" / digest.replace(":", "-")
            if destination.exists():
                if checksum(destination) != digest[7:]:
                    raise ValueError("Existing installed blob fails verification")
                continue
            pieces = CACHE / digest[7:]
            pieces.mkdir(exist_ok=True)

            def fetch(start):
                end = min(start + CHUNK, size) - 1
                path = pieces / f"{start:012d}.chunk"
                if path.exists() and path.stat().st_size == end - start + 1:
                    return path
                for attempt in range(8):
                    if time.monotonic() > deadline:
                        raise TimeoutError(
                            "Two-hour budget exhausted; completed chunks are retained"
                        )
                    try:
                        with client.stream(
                            "GET",
                            REGISTRY + "/blobs/" + digest,
                            headers={"Range": f"bytes={start}-{end}"},
                        ) as response:
                            response.raise_for_status()
                            full_blob = (
                                response.status_code == 200 and start == 0 and end == size - 1
                            )
                            valid_range = (
                                response.status_code == 206
                                and response.headers.get("content-range")
                                == f"bytes {start}-{end}/{size}"
                            )
                            if not (full_blob or valid_range):
                                raise ValueError("Server did not honor the requested byte range")
                            content = bytearray()
                            for data in response.iter_bytes():
                                content.extend(data)
                                if len(content) > end - start + 1:
                                    raise ValueError("Oversized range response")
                        if len(content) != end - start + 1:
                            raise ValueError("Incomplete byte range")
                        pending = path.with_suffix(".pending")
                        pending.write_bytes(content)
                        os.replace(pending, path)
                        return path
                    except (httpx.HTTPError, ValueError):
                        if attempt == 7:
                            raise
                        time.sleep(min(2**attempt, 20))

            offsets = list(range(0, size, CHUNK))
            with ThreadPoolExecutor(max_workers=2) as workers:
                for count, _ in enumerate(workers.map(fetch, offsets), 1):
                    if count % 8 == 0 or count == len(offsets):
                        print(f"{digest[7:19]}: {count}/{len(offsets)} chunks complete", flush=True)
            assembled = CACHE / (digest[7:] + ".verified-pending")
            with assembled.open("wb") as output:
                for start in offsets:
                    output.write((pieces / f"{start:012d}.chunk").read_bytes())
            if assembled.stat().st_size != size or checksum(assembled) != digest[7:]:
                raise ValueError("Full-layer SHA-256 verification failed; nothing installed")
            os.replace(assembled, destination)
            print("Verified layer", digest, flush=True)
        target = STORE / "manifests/registry.ollama.ai/library/qwen3/4b"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        print(
            "Installed verified qwen3:4b. Model digest:",
            hashlib.sha256(raw).hexdigest(),
            flush=True,
        )


if __name__ == "__main__":
    main()
