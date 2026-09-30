from copy import deepcopy
from uuid import UUID

import pytest

from tactigraph.models.graph_features import EDGE_DIM, NODE_DIM, graph_at_cutoff


def fixture():
    def event(index, kind, seconds=0, player=None):
        return {
            "id": str(UUID(int=index)),
            "index": index,
            "period": 1,
            "timestamp": f"00:00:{seconds:06.3f}",
            "type": {"name": kind},
            "team": {"id": 10},
            "player": {"id": player} if player else {},
            "play_pattern": {"name": "Regular Play"},
            "location": [40, 40],
        }

    lineup = event(1, "Starting XI")
    lineup["tactics"] = {
        "lineup": [{"player": {"id": p}, "position": {"id": p - 10}} for p in range(11, 22)]
    }
    raw = [lineup]
    for index, sender, recipient in [(2, 11, 12), (3, 12, 11), (4, 11, 12)]:
        e = event(index, "Pass", index * 2, sender)
        e["duration"] = 1.0
        e["pass"] = {
            "recipient": {"id": recipient},
            "end_location": [50 + index, 42],
            "length": 15,
            "height": {"name": "Ground Pass"},
        }
        raw.append(e)
    shot = event(5, "Shot", 12, 12)
    shot["shot"] = {"outcome": {"name": "Goal"}}
    raw.append(shot)
    return raw


def build(raw):
    return graph_at_cutoff(raw, 4, [str(UUID(int=i)) for i in (2, 3, 4)], 10, 1)


def test_prefix_graph_preserves_repeated_edges_and_known_recipient():
    result = build(fixture())
    assert len(result["nodes"]) == 11
    assert len(result["nodes"][0]) == NODE_DIM
    assert len(result["edge_attributes"][0]) == EDGE_DIM
    assert result["edges"] == [[0, 1], [1, 0], [0, 1]]
    assert result["holder"] == 1
    assert result["cutoff_ms"] == 9000  # Includes the third pass's duration.
    assert result["nodes"][1][-1] == 1
    assert result["nodes"][1][-5:-3] == [54 / 120, 42 / 80]
    assert result["globals"][5] == 0  # The later goal is not score state.


def test_graph_parquet_roundtrip_preserves_mixed_numeric_features(tmp_path):
    import polars as pl

    from tactigraph.models.graph_features import save_samples

    row = {**build(fixture()), "label": True, "sample_id": "synthetic"}
    path = tmp_path / "samples.parquet"
    save_samples(path, [row])
    restored = pl.read_parquet(path).to_dicts()[0]
    assert restored == row
    assert pl.read_parquet_schema(path)["nodes"] == pl.List(pl.List(pl.Float64))


def test_every_future_record_and_future_assist_flag_are_inaccessible():
    raw = fixture()
    expected = build(raw)
    changed = deepcopy(raw)
    changed[-1] = {"index": 5, "unparseable_future": object()}
    changed.append({"index": 6, "type": {"name": "Substitution"}, "player": {"id": 12}})
    for e in changed[:4]:
        if "pass" in e:
            e["pass"].update(shot_assist=True, goal_assist=True, assisted_shot_id="future")
    assert build(changed) == expected


def test_identity_is_metadata_not_a_numeric_feature():
    raw = fixture()
    before = build(raw)
    changed = deepcopy(raw)
    for entry in changed[0]["tactics"]["lineup"]:
        entry["player"]["id"] += 1000
    for e in changed:
        if e.get("player", {}).get("id"):
            e["player"]["id"] += 1000
        if "pass" in e:
            e["pass"]["recipient"]["id"] += 1000
    after = build(changed)
    for field in ("nodes", "edges", "edge_attributes", "globals", "tabular", "holder"):
        assert after[field] == before[field]


@pytest.mark.parametrize("change", ["missing_duration", "out", "unknown_holder", "prior_shot"])
def test_invalid_cutoff_is_excluded(change):
    raw = fixture()
    if change == "missing_duration":
        del raw[3]["duration"]
    elif change == "out":
        raw[3]["out"] = True
    elif change == "unknown_holder":
        raw[3]["pass"]["recipient"]["id"] = 999
    else:
        raw[1]["type"] = {"name": "Shot"}
    with pytest.raises(ValueError):
        build(raw)


def test_gine_forward_batching_and_all_ablations():
    torch = pytest.importorskip("torch")
    pytest.importorskip("torch_geometric")
    from torch_geometric.data import Batch

    from tactigraph.models.graph_network import ShotAfterThirdPass, graph_data

    row = {**build(fixture()), "label": True, "sample_id": "synthetic"}
    for variant in (
        "gine",
        "no_message",
        "episode_edges",
        "no_edge_time_space",
        "random_connectivity",
    ):
        graph = graph_data(row, variant)
        assert graph.num_nodes == 11
        assert graph.edge_index.shape[1] == 3
        batch = Batch.from_data_list([graph, graph])
        model = ShotAfterThirdPass(variant).eval()
        result = model(batch)
        assert result.shape == (2,)
        assert torch.isfinite(result).all()
        torch.nn.functional.binary_cross_entropy_with_logits(result, batch.y).backward()
    random_a = graph_data(row, "random_connectivity", 2026)
    random_b = graph_data(row, "random_connectivity", 2026)
    assert torch.equal(random_a.edge_index, random_b.edge_index)
    assert torch.equal(random_a.x, graph_data(row).x)
    assert torch.equal(random_a.edge_attr, graph_data(row).edge_attr)


def test_gine_is_invariant_to_node_order_and_pooling_ignores_connectivity():
    torch = pytest.importorskip("torch")
    pytest.importorskip("torch_geometric")
    from torch_geometric.data import Batch

    from tactigraph.models.graph_network import ShotAfterThirdPass, graph_data

    row = {**build(fixture()), "label": False, "sample_id": "synthetic"}
    original = graph_data(row)
    permutation = torch.arange(10, -1, -1)
    changed = original.clone()
    changed.x = original.x[permutation]
    changed.holder_mask = original.holder_mask[permutation]
    changed.edge_index = 10 - original.edge_index
    model = ShotAfterThirdPass().eval()
    with torch.no_grad():
        assert torch.allclose(
            model(Batch.from_data_list([original])),
            model(Batch.from_data_list([changed])),
            atol=1e-6,
        )
    pooled = ShotAfterThirdPass("no_message").eval()
    changed = original.clone()
    changed.edge_index = original.edge_index.flip(0)
    with torch.no_grad():
        assert torch.equal(
            pooled(Batch.from_data_list([original])), pooled(Batch.from_data_list([changed]))
        )
