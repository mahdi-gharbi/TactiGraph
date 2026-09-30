import numpy as np
import pytest

from tactigraph.models.xt import Action, Episode, close_actions, fit, predict, solve, zone


def test_terminal_actions_are_counted_once_and_moves_get_explicit_loss():
    move = Action("move", 10, 20, 30, 40)
    assert close_actions([move])[-1] == Action("loss", 30, 40)
    for terminal in (Action("loss", 30, 40), Action("shot", 30, 40, goal=True)):
        assert len(close_actions([move, terminal])) == 2
        with pytest.raises(ValueError, match="after terminal"):
            close_actions([terminal, move])


def test_spatial_boundary_and_missingness_are_not_clipped():
    assert zone(120, 80, (12, 8)) == 95
    assert zone(0, 0, (12, 8)) == 0
    assert zone(80, 40, (12, 8)) == 56
    with pytest.raises(ValueError):
        close_actions([Action("move", 10, 20, 120.1, 40)])
    with pytest.raises(ValueError):
        close_actions([Action("shot", None, 20)])


def test_one_zone_solution_matches_hand_calculation_and_baselines():
    # Four actions: retained move, goal shot, non-goal shot, loss.
    episodes = [
        Episode("1", 1, (Action("move", 10, 20, 30, 40), Action("shot", 30, 40, goal=True))),
        Episode("2", 1, (Action("shot", 30, 40),)),
        Episode("3", 2, (Action("loss", 10, 20),)),
    ]
    model = fit(episodes, (1, 1))
    # Priors centered on this single zone leave probabilities unchanged:
    # reward = .5 * .5 = .25; V = .25 + .25 V => 1/3.
    assert model["values"][0] == pytest.approx(1 / 3, abs=1e-8)
    assert model["no_transition"] == [0.25]
    assert model["terminal_count"] == model["episodes"] == 3
    assert model["row_probability_error"] < 1e-12
    assert model["maximum_delta"] < 1e-8
    assert predict(episodes, model)["global"].tolist() == [1 / 3] * 3


def test_nonconvergence_fails_instead_of_publishing_partial_values():
    with pytest.raises(ValueError, match="converge"):
        solve(np.array([0.1]), np.array([[0.8]]), max_iterations=1)


def test_terminal_only_fixture_has_no_transition_inflation():
    episodes = [
        Episode("a", 1, (Action("shot", 100, 40, goal=True),)),
        Episode("b", 1, (Action("shot", 100, 40),)),
        Episode("c", 2, (Action("loss", 20, 40),)),
    ]
    model = fit(episodes, (2, 1))
    assert model["values"] == model["no_transition"]
    assert all(0 <= p <= 1 for p in model["values"])


def test_unseen_zone_uses_fitting_global_prior():
    model = fit(
        [
            Episode("a", 1, (Action("shot", 100, 40, goal=True),)),
            Episode("b", 1, (Action("loss", 100, 40),)),
        ],
        (2, 1),
    )
    assert model["action_counts"] == [0, 2]
    assert model["values"] == [0.5, 0.5]


def test_serving_signed_values_never_credit_shots():
    from types import SimpleNamespace as NS

    from tactigraph.models.xt_serving import movement_value

    xt = {"model": {"grid": [2, 1], "values": [0.1, 0.4]}}
    event = NS(type="Pass", x=10, y=20)
    assert movement_value(event, NS(completed=True, end_x=100, end_y=20), None, xt) == (
        True,
        pytest.approx(0.3),
    )
    assert movement_value(event, NS(completed=False), None, xt) == (True, -0.1)
    assert movement_value(NS(type="Shot", x=100, y=20), None, None, xt) == (False, None)


def test_test_label_mutation_cannot_change_fitted_surface(database, payload):
    from copy import deepcopy
    from uuid import UUID

    from tactigraph.data.ingest import ingest_payload
    from tactigraph.db import Shot
    from tactigraph.models.xt_data import extract

    _, factory = database
    ingest_payload(factory, *payload)
    match, events, lineups = deepcopy(payload)
    match["match_id"] = 2
    for event in events:
        event["id"] = str(UUID(int=100 + event["index"]))
    ingest_payload(factory, match, events, lineups)
    with factory() as session:
        before, _ = extract(session, [1])
        artifact = fit(before, (2, 1))
        for event in events:
            shot = session.get(Shot, event["id"])
            if shot:
                shot.goal = not shot.goal
        session.commit()
        after, _ = extract(session, [1])
        assert fit(after, (2, 1)) == artifact
        assert all(e.match_id == 1 for e in after)
