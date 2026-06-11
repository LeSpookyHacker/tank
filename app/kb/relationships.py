"""Graph traversal helpers."""
from __future__ import annotations

from app.storage import entities_store, relationships_store


def traverse(entity_id: str, *, direction: str = "both",
             kind: str | None = None, hops: int = 1) -> dict:
    """Return neighbors of `entity_id` up to `hops` away.

    direction ∈ {out, in, both}. Returns:
        {"start": <card>,
         "edges": [{src, dst, kind, ...}, ...],
         "neighbors": [<card>, ...]}
    """
    start = entities_store.get_entity(entity_id)
    if not start:
        return {"start": None, "edges": [], "neighbors": []}

    visited: set[str] = {entity_id}
    frontier: list[str] = [entity_id]
    edges_out: list[dict] = []
    for _ in range(max(1, hops)):
        next_frontier: list[str] = []
        for src in frontier:
            for edge in relationships_store.list_for_entity(
                src, direction=direction, kind=kind,
            ):
                edges_out.append(edge)
                for other in (edge["src_id"], edge["dst_id"]):
                    if other not in visited:
                        visited.add(other)
                        next_frontier.append(other)
        frontier = next_frontier
        if not frontier:
            break

    neighbor_ids = visited - {entity_id}
    neighbors = []
    for nid in neighbor_ids:
        n = entities_store.get_entity(nid)
        if n:
            neighbors.append({
                "id": n["id"], "type": n["type"], "name": n["name"],
                "description": n["description"],
                "provenance": n["provenance"],
            })
    return {
        "start": {
            "id": start["id"], "type": start["type"], "name": start["name"],
            "description": start["description"],
        },
        "edges": edges_out,
        "neighbors": neighbors,
    }


def graph_for_type(type_: str, depth: int = 2,
                   limit_nodes: int = 80) -> dict:
    """Return a small graph slice for visualization.

    BFS from seed nodes of `type_` up to `depth` hops, capped at
    `limit_nodes` total nodes.
    """
    nodes_by_id: dict[str, dict] = {}
    edges_out: list[dict] = []

    def _add_node(ent: dict) -> None:
        nodes_by_id[ent["id"]] = {
            "id": ent["id"], "type": ent["type"], "name": ent["name"],
        }

    seed = entities_store.list_entities(type_=type_, limit=limit_nodes)
    for ent in seed:
        _add_node(ent)

    frontier = list(nodes_by_id.keys())
    for _ in range(max(1, depth)):
        if not frontier or len(nodes_by_id) >= limit_nodes:
            break
        next_frontier: list[str] = []
        for ent_id in frontier:
            for edge in relationships_store.list_for_entity(ent_id):
                edges_out.append({
                    "src_id": edge["src_id"],
                    "dst_id": edge["dst_id"],
                    "kind": edge["kind"],
                })
                for other_id in (edge["src_id"], edge["dst_id"]):
                    if other_id not in nodes_by_id and len(nodes_by_id) < limit_nodes:
                        other = entities_store.get_entity(other_id)
                        if other:
                            _add_node(other)
                            next_frontier.append(other_id)
        frontier = next_frontier

    # Drop edges whose endpoints didn't make it into the node set (cap was hit).
    # D3 forceLink throws "node not found" for any dangling edge reference.
    node_ids = set(nodes_by_id.keys())
    edges_out = [e for e in edges_out
                 if e["src_id"] in node_ids and e["dst_id"] in node_ids]

    return {"nodes": list(nodes_by_id.values()), "edges": edges_out}


def graph_for_all_types(depth: int = 1, limit_nodes: int = 150) -> dict:
    """Return a graph slice spanning all entity types for the knowledge graph view."""
    nodes_by_id: dict[str, dict] = {}
    edges_out: list[dict] = []
    seen_edges: set[tuple] = set()

    def _add_node(ent: dict) -> None:
        nodes_by_id[ent["id"]] = {
            "id": ent["id"], "type": ent["type"], "name": ent["name"],
        }

    all_ents = entities_store.list_entities(type_=None, limit=limit_nodes)
    for ent in all_ents:
        _add_node(ent)

    for ent_id in list(nodes_by_id.keys()):
        if len(edges_out) >= limit_nodes * 3:
            break
        for edge in relationships_store.list_for_entity(ent_id):
            key = (edge["src_id"], edge["dst_id"], edge["kind"])
            if key not in seen_edges:
                seen_edges.add(key)
                edges_out.append({
                    "src_id": edge["src_id"],
                    "dst_id": edge["dst_id"],
                    "kind": edge["kind"],
                })
                for other_id in (edge["src_id"], edge["dst_id"]):
                    if other_id not in nodes_by_id and len(nodes_by_id) < limit_nodes:
                        other = entities_store.get_entity(other_id)
                        if other:
                            _add_node(other)

    # Drop edges whose endpoints didn't make it into the node set (cap was hit).
    # D3 forceLink throws "node not found" for any dangling edge reference.
    node_ids = set(nodes_by_id.keys())
    edges_out = [e for e in edges_out
                 if e["src_id"] in node_ids and e["dst_id"] in node_ids]

    return {"nodes": list(nodes_by_id.values()), "edges": edges_out}
