from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tactigraph.analytics.sensitivity import remove_player
from tactigraph.api.app import create_app
from tactigraph.config import Settings
from tactigraph.data.ingest import ingest_payload


def graph(nodes, edges):
    return SimpleNamespace(
        nodes=[SimpleNamespace(player_id=n) for n in nodes],
        edges=[SimpleNamespace(sender=a, recipient=b, count=c) for a, b, c in edges],
    )


def test_bridge_removal_preserves_isolates_and_counts_directed_reachability():
    network = graph([1, 2, 3, 4], [(1, 2, 3), (2, 1, 2), (2, 3, 5)])
    original = deepcopy(network)
    before, after = remove_player(network, 2)
    assert before["pass_weight"] == 10
    assert before["weak_component_sizes"] == [3, 1]
    assert before["strong_component_sizes"] == [2, 1, 1]
    assert before["reachable_ordered_pairs"] == 4
    assert before["possible_ordered_pairs"] == 12
    assert after["players"] == 3
    assert after["pass_weight"] == 0
    assert after["weak_component_sizes"] == [1, 1, 1]
    assert after["isolated_players"] == 3
    assert after["reachable_ordered_pairs"] == 0
    assert after["possible_ordered_pairs"] == 6
    assert network == original


def test_isolate_and_last_node_removal_are_well_defined():
    before, after = remove_player(graph([1, 2, 3], [(1, 2, 7)]), 3)
    assert before["pass_weight"] == after["pass_weight"] == 7
    assert after["density"] == 0.5
    _, empty = remove_player(graph([1], []), 1)
    assert empty["players"] == empty["possible_ordered_pairs"] == 0
    assert empty["weak_component_sizes"] == []
    assert empty["density"] == 0
    with pytest.raises(ValueError, match="not in"):
        remove_player(graph([1], []), 99)


def test_endpoint_resolves_source_network_and_rejects_unknown_player(database, payload):
    engine, sessions = database
    ingest_payload(sessions, *payload)
    reference = "tactics-1-10-1-0-600000-network"
    with TestClient(create_app(Settings(mode="public"), engine)) as client:
        response = client.get(f"/api/v1/tactical-evidence/{reference}/remove-player/11")
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["before"]["pass_weight"] == result["removed_pass_weight"] == 1
        assert result["after"]["pass_weight"] == 0
        assert result["evidence_id"] == reference
        assert "does not predict" in result["limitation"]
        assert (
            client.get(f"/api/v1/tactical-evidence/{reference}/remove-player/999").status_code
            == 422
        )
        wrong_metric = reference.replace("network", "shots")
        assert (
            client.get(f"/api/v1/tactical-evidence/{wrong_metric}/remove-player/11").status_code
            == 422
        )
        assert (
            client.get(f"/api/v1/tactical-evidence/{reference}/remove-player/0").status_code == 422
        )
