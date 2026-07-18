"""Shared builders for constructing React-Flow-style graph dicts in tests."""


def _node(node_id, node_type, **data):
    """Build a node dict; extra kwargs become its ``data`` payload."""
    node = {"id": node_id, "type": node_type, "position": {"x": 0, "y": 0}}
    if data:
        node["data"] = data
    return node


def _edge(edge_id, source, target, condition="on_complete"):
    """Build an edge dict with a transition ``condition``."""
    return {"id": edge_id, "source": source, "target": target, "data": {"condition": condition}}
