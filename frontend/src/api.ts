import type { components } from "./api.generated";

export type MatchCard = components["schemas"]["MatchCard"];
export type MatchSummary = components["schemas"]["MatchSummary"];
export type MatchList = components["schemas"]["MatchList"];
export type ShotLayer = components["schemas"]["ShotLayer"];
export type ShotPoint = components["schemas"]["ShotPoint"];
export type ShotEvidence = components["schemas"]["ShotEvidence"];

export const selectedLeague =
  new URLSearchParams(window.location.search).get("league") === "premier-league"
    ? "premier-league"
    : "wsl";
export const apiUrl = (path: string) =>
  `${selectedLeague === "premier-league" ? "/leagues/premier-league" : ""}/api/v1${path}`;

export async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try {
    response = await fetch(apiUrl(path), { signal });
  } catch (error) {
    if (signal?.aborted) throw error;
    const local = ["localhost", "127.0.0.1"].includes(window.location.hostname);
    throw new Error(
      local
        ? "Cannot reach the local TactiGraph server. Run Start-TactiGraph.cmd in the project folder, then refresh this page."
        : "Cannot reach the TactiGraph server. Check your connection and retry.",
    );
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(
      typeof payload.detail === "string"
        ? payload.detail
        : `Request failed (${response.status})`,
    );
  }
  return response.json();
}
