"""Deletion sensitivity of a fixed observed graph; no behavioural counterfactual."""

import networkx as nx


def summary(graph):
    players = len(graph)
    reachable = sum(len(nx.descendants(graph, node)) for node in graph)
    return {
        "players": players,
        "directed_edges": graph.number_of_edges(),
        "pass_weight": int(graph.size(weight="count")),
        "density": nx.density(graph),
        "isolated_players": len(list(nx.isolates(graph))),
        "weak_component_sizes": sorted(
            map(len, nx.weakly_connected_components(graph)), reverse=True
        ),
        "strong_component_sizes": sorted(
            map(len, nx.strongly_connected_components(graph)), reverse=True
        ),
        "reachable_ordered_pairs": reachable,
        "possible_ordered_pairs": players * (players - 1),
    }


def remove_player(network, player_id):
    graph = nx.DiGraph()
    graph.add_nodes_from(node.player_id for node in network.nodes)
    graph.add_weighted_edges_from(
        [(edge.sender, edge.recipient, edge.count) for edge in network.edges], weight="count"
    )
    if player_id not in graph:
        raise ValueError("Player is not in this observed network")
    before = summary(graph)
    graph.remove_node(player_id)
    after = summary(graph)
    return before, after
