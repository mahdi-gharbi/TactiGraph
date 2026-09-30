import hashlib
import json

from fastapi import APIRouter, HTTPException, Path, Request

from tactigraph.analytics.sensitivity import remove_player
from tactigraph.api.schemas import BaseModel, Provenance
from tactigraph.api.tactics import evidence

router = APIRouter(prefix="/api/v1", tags=["network structural sensitivity"])


class Structure(BaseModel):
    players: int
    directed_edges: int
    pass_weight: int
    density: float
    isolated_players: int
    weak_component_sizes: list[int]
    strong_component_sizes: list[int]
    reachable_ordered_pairs: int
    possible_ordered_pairs: int


class SensitivityResponse(BaseModel):
    result_id: str
    metric_version: str = "network-removal-v1"
    evidence_id: str
    player_id: int
    player_name: str
    before: Structure
    after: Structure
    removed_pass_weight: int
    source_sha256: str | None
    provenance: Provenance
    limitation: str = (
        "Structural sensitivity of a fixed historical passing graph. The selected node and "
        "its incident edges are deleted; every other observed edge and isolated player "
        "is retained. This does not predict replacement behaviour, goals or what would "
        "have happened without the player. "
        "Reachability counts ordered pairs connected by a directed path, excluding self-pairs; "
        "weak components ignore direction, strong components require paths both ways."
    )


@router.get(
    "/tactical-evidence/{result_id}/remove-player/{player_id}", response_model=SensitivityResponse
)
def sensitivity(result_id: str, request: Request, player_id: int = Path(gt=0)):
    original = evidence(result_id, request, offset=0, limit=1)
    if original.network is None:
        raise HTTPException(422, "Removal requires a passing-network evidence reference")
    try:
        before, after = remove_player(original.network, player_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    result = SensitivityResponse(
        result_id="pending",
        evidence_id=result_id,
        player_id=player_id,
        player_name=next(n.name for n in original.network.nodes if n.player_id == player_id),
        before=Structure(**before),
        after=Structure(**after),
        removed_pass_weight=before["pass_weight"] - after["pass_weight"],
        source_sha256=original.source_sha256,
        provenance=original.provenance,
    )
    result.result_id = (
        "removal-"
        + hashlib.sha256(json.dumps(result.model_dump(), sort_keys=True).encode()).hexdigest()[:24]
    )
    return result
