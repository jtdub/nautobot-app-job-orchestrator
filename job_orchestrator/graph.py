"""Helpers for parsing and validating a workflow graph document.

The graph is the React Flow document persisted on ``Workflow.graph`` (and snapshotted onto
``WorkflowExecution.graph_snapshot``). This module provides a thin, dependency-free wrapper so the
same parsing/validation logic is shared by model ``clean()`` and the execution engine.

Expected shape::

    {
        "nodes": [
            {"id": "n1", "type": "start", "position": {"x": 0, "y": 0}, "data": {...}},
            {"id": "n2", "type": "job", "position": {...},
             "data": {"job_id": "<uuid>", "kwargs": {...}, "label": "..."}},
            {"id": "n3", "type": "join", "data": {"join_rule": "all"}},
            {"id": "n4", "type": "stop"},
        ],
        "edges": [
            {"id": "e1", "source": "n1", "target": "n2", "data": {"condition": "on_complete"}},
        ],
    }
"""

from job_orchestrator.choices import (
    JoinRuleChoices,
    TransitionConditionChoices,
    WorkflowNodeTypeChoices,
)


class GraphValidationError(Exception):
    """Raised when a workflow graph is structurally invalid.

    Carries a list of human-readable error messages.
    """

    def __init__(self, errors):
        """Store the list of error strings."""
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


class WorkflowGraph:
    """Read-only view over a workflow graph dictionary."""

    def __init__(self, graph):
        """Wrap a graph ``dict`` (the React Flow document) and precompute lookup maps."""
        self.graph = graph or {}
        self.nodes = list(self.graph.get("nodes", []))
        self.edges = list(self.graph.get("edges", []))
        # The wrapper is read-only, so lookups are computed once instead of per access — the
        # engine hits these repeatedly on every propagation step.
        self.nodes_by_id = {node["id"]: node for node in self.nodes if "id" in node}
        self._outgoing = {}
        self._incoming = {}
        for edge in self.edges:
            self._outgoing.setdefault(edge.get("source"), []).append(edge)
            self._incoming.setdefault(edge.get("target"), []).append(edge)

    # -- Lookups ---------------------------------------------------------------------------------

    def node(self, node_id):
        """Return the node dict for ``node_id`` (or ``None``)."""
        return self.nodes_by_id.get(node_id)

    def node_type(self, node_id):
        """Return the ``type`` of ``node_id`` (or ``None``)."""
        node = self.node(node_id)
        return node.get("type") if node else None

    def outgoing_edges(self, node_id):
        """Return edges whose ``source`` is ``node_id``."""
        return self._outgoing.get(node_id, [])

    def incoming_edges(self, node_id):
        """Return edges whose ``target`` is ``node_id``."""
        return self._incoming.get(node_id, [])

    @property
    def start_node_id(self):
        """Return the id of the single ``start`` node (or ``None``)."""
        for node in self.nodes:
            if node.get("type") == WorkflowNodeTypeChoices.TYPE_START:
                return node.get("id")
        return None

    # -- Validation ------------------------------------------------------------------------------

    def validate(self, resolve_job=None, require_runnable=True):
        """Validate the graph structure, raising :class:`GraphValidationError` on failure.

        Args:
            resolve_job: optional callable ``job_id -> bool`` returning whether a Job exists.
                When provided, every ``job`` node's ``job_id`` is checked. Kept injectable so this
                module stays free of Django/ORM imports and remains unit-testable in isolation.
            require_runnable: when ``True`` (the default, used at execution time) the graph must be
                executable — exactly one ``start`` node and every ``join`` with at least two incoming
                edges. When ``False`` (used for draft saves) those executability checks are skipped so
                a partially-built canvas can still be persisted.
        """
        errors = []
        node_ids = [node.get("id") for node in self.nodes]

        self._validate_node_ids_and_types(errors)
        self._validate_start_node(errors, require_runnable)
        self._validate_job_nodes(errors, resolve_job)
        self._validate_join_nodes(errors, require_runnable)
        self._validate_edges(errors, node_ids)

        # The graph must be a DAG (loops are deferred to a later phase).
        if not errors and self._has_cycle():
            errors.append("Workflow graph must be acyclic (no loops).")

        # Every node must be reachable, otherwise it would silently never run.
        if require_runnable and not errors:
            self._validate_reachability(errors)

        if errors:
            raise GraphValidationError(errors)

    def _validate_node_ids_and_types(self, errors):
        """Every node needs a unique id and a known type."""
        valid_types = set(WorkflowNodeTypeChoices.values())
        seen_ids = set()
        for node in self.nodes:
            node_id = node.get("id")
            if not node_id:
                errors.append("Every node must have an 'id'.")
                continue
            if node_id in seen_ids:
                errors.append(f"Duplicate node id '{node_id}'.")
            seen_ids.add(node_id)
            node_type = node.get("type")
            if node_type not in valid_types:
                errors.append(f"Node '{node_id}' has unknown type '{node_type}'.")

    def _validate_start_node(self, errors, require_runnable):
        """Enforce the single-``start``-node rule (relaxed for drafts)."""
        start_nodes = [n for n in self.nodes if n.get("type") == WorkflowNodeTypeChoices.TYPE_START]
        if require_runnable:
            if len(start_nodes) == 0:
                errors.append("Workflow must contain exactly one 'start' node (found none).")
            elif len(start_nodes) > 1:
                errors.append(f"Workflow must contain exactly one 'start' node (found {len(start_nodes)}).")
        elif len(start_nodes) > 1:
            # More than one start is always wrong, even for a draft.
            errors.append(f"Workflow must contain at most one 'start' node (found {len(start_nodes)}).")

    def _validate_job_nodes(self, errors, resolve_job):
        """Job nodes need a ``job_id`` (and optionally an existence check)."""
        for node in self.nodes:
            if node.get("type") != WorkflowNodeTypeChoices.TYPE_JOB:
                continue
            job_id = (node.get("data") or {}).get("job_id")
            if not job_id:
                errors.append(f"Job node '{node.get('id')}' is missing 'data.job_id'.")
            elif resolve_job is not None and not resolve_job(job_id):
                errors.append(f"Job node '{node.get('id')}' references unknown Job '{job_id}'.")

    def _validate_join_nodes(self, errors, require_runnable):
        """Join nodes need a valid rule and (when runnable) at least two incoming edges."""
        valid_rules = set(JoinRuleChoices.values())
        for node in self.nodes:
            if node.get("type") != WorkflowNodeTypeChoices.TYPE_JOIN:
                continue
            rule = (node.get("data") or {}).get("join_rule", JoinRuleChoices.RULE_ANY)
            if rule not in valid_rules:
                errors.append(f"Join node '{node.get('id')}' has invalid join_rule '{rule}'.")
            if require_runnable and len(self.incoming_edges(node.get("id"))) < 2:
                errors.append(f"Join node '{node.get('id')}' must have at least two incoming edges.")

    def _validate_edges(self, errors, node_ids):
        """Edge endpoints must exist; conditions must be valid; ids unique."""
        valid_conditions = set(TransitionConditionChoices.values())
        seen_edge_ids = set()
        for edge in self.edges:
            edge_id = edge.get("id")
            if not edge_id:
                errors.append("Every edge must have an 'id'.")
            elif edge_id in seen_edge_ids:
                errors.append(f"Duplicate edge id '{edge_id}'.")
            else:
                seen_edge_ids.add(edge_id)
            for endpoint in ("source", "target"):
                if edge.get(endpoint) not in node_ids:
                    errors.append(f"Edge '{edge_id}' {endpoint} '{edge.get(endpoint)}' does not match any node.")
            condition = (edge.get("data") or {}).get("condition")
            if condition not in valid_conditions:
                errors.append(f"Edge '{edge_id}' has invalid condition '{condition}'.")

    def _validate_reachability(self, errors):
        """Every node must be reachable from the start node, or it will never execute.

        Traversal does not continue past ``stop`` nodes because the engine never propagates
        beyond them.
        """
        start_id = self.start_node_id
        reachable = set()
        frontier = [start_id]
        while frontier:
            node_id = frontier.pop()
            if node_id in reachable:
                continue
            reachable.add(node_id)
            if self.node_type(node_id) == WorkflowNodeTypeChoices.TYPE_STOP:
                continue
            frontier.extend(edge.get("target") for edge in self.outgoing_edges(node_id))

        unreachable = sorted(node_id for node_id in self.nodes_by_id if node_id not in reachable)
        for node_id in unreachable:
            errors.append(f"Node '{node_id}' is not reachable from the start node and would never run.")

    def _has_cycle(self):
        """Return ``True`` if the directed graph contains a cycle (DFS three-color)."""
        white, gray, black = 0, 1, 2
        color = {node_id: white for node_id in self.nodes_by_id}
        adjacency = {node_id: [] for node_id in self.nodes_by_id}
        for edge in self.edges:
            source, target = edge.get("source"), edge.get("target")
            if source in adjacency and target in adjacency:
                adjacency[source].append(target)

        def visit(node_id):
            color[node_id] = gray
            for neighbor in adjacency[node_id]:
                if color[neighbor] == gray:
                    return True
                if color[neighbor] == white and visit(neighbor):
                    return True
            color[node_id] = black
            return False

        return any(color[node_id] == white and visit(node_id) for node_id in color)
