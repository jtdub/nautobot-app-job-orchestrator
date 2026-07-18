"""Unit tests for the pure graph validation helpers (no database required)."""

from django.test import SimpleTestCase

from job_orchestrator.graph import GraphValidationError, WorkflowGraph
from job_orchestrator.tests._graph_helpers import _edge, _node


class WorkflowGraphValidateTest(SimpleTestCase):
    """Validation truth table for WorkflowGraph.validate()."""

    def test_valid_linear_graph(self):
        graph = {
            "nodes": [_node("s", "start"), _node("a", "job", job_id="x"), _node("end", "stop")],
            "edges": [_edge("e1", "s", "a"), _edge("e2", "a", "end", "on_success")],
        }
        # resolve_job always True -> should not raise.
        WorkflowGraph(graph).validate(resolve_job=lambda _id: True)

    def test_missing_start_node(self):
        graph = {"nodes": [_node("a", "job", job_id="x")], "edges": []}
        with self.assertRaises(GraphValidationError) as ctx:
            WorkflowGraph(graph).validate(resolve_job=lambda _id: True)
        self.assertTrue(any("start" in e for e in ctx.exception.errors))

    def test_two_start_nodes(self):
        graph = {"nodes": [_node("s1", "start"), _node("s2", "start")], "edges": []}
        with self.assertRaises(GraphValidationError):
            WorkflowGraph(graph).validate(resolve_job=lambda _id: True)

    def test_job_node_missing_job_id(self):
        graph = {"nodes": [_node("s", "start"), _node("a", "job")], "edges": [_edge("e1", "s", "a")]}
        with self.assertRaises(GraphValidationError) as ctx:
            WorkflowGraph(graph).validate(resolve_job=lambda _id: True)
        self.assertTrue(any("job_id" in e for e in ctx.exception.errors))

    def test_unknown_job_reference(self):
        graph = {"nodes": [_node("s", "start"), _node("a", "job", job_id="nope")], "edges": [_edge("e1", "s", "a")]}
        with self.assertRaises(GraphValidationError) as ctx:
            WorkflowGraph(graph).validate(resolve_job=lambda _id: False)
        self.assertTrue(any("unknown Job" in e for e in ctx.exception.errors))

    def test_edge_endpoint_missing(self):
        graph = {"nodes": [_node("s", "start")], "edges": [_edge("e1", "s", "ghost")]}
        with self.assertRaises(GraphValidationError):
            WorkflowGraph(graph).validate(resolve_job=lambda _id: True)

    def test_bad_condition(self):
        graph = {
            "nodes": [_node("s", "start"), _node("a", "job", job_id="x")],
            "edges": [_edge("e1", "s", "a", "whenever")],
        }
        with self.assertRaises(GraphValidationError):
            WorkflowGraph(graph).validate(resolve_job=lambda _id: True)

    def test_join_requires_two_incoming(self):
        graph = {
            "nodes": [_node("s", "start"), _node("a", "job", job_id="x"), _node("j", "join", join_rule="all")],
            "edges": [_edge("e1", "s", "a"), _edge("e2", "a", "j")],
        }
        with self.assertRaises(GraphValidationError) as ctx:
            WorkflowGraph(graph).validate(resolve_job=lambda _id: True)
        self.assertTrue(any("at least two incoming" in e for e in ctx.exception.errors))

    def test_cycle_rejected(self):
        graph = {
            "nodes": [_node("s", "start"), _node("a", "job", job_id="x"), _node("b", "job", job_id="y")],
            "edges": [_edge("e1", "s", "a"), _edge("e2", "a", "b"), _edge("e3", "b", "a")],
        }
        with self.assertRaises(GraphValidationError) as ctx:
            WorkflowGraph(graph).validate(resolve_job=lambda _id: True)
        self.assertTrue(any("acyclic" in e for e in ctx.exception.errors))

    def test_unreachable_node_rejected(self):
        # A disconnected job node would silently never run; runnable validation must reject it.
        graph = {
            "nodes": [_node("s", "start"), _node("a", "job", job_id="x"), _node("orphan", "job", job_id="y")],
            "edges": [_edge("e1", "s", "a")],
        }
        with self.assertRaises(GraphValidationError) as ctx:
            WorkflowGraph(graph).validate(resolve_job=lambda _id: True)
        self.assertTrue(any("not reachable" in e for e in ctx.exception.errors))

    def test_node_behind_stop_rejected(self):
        # The engine never propagates past a stop node, so nodes only reachable through one never run.
        graph = {
            "nodes": [_node("s", "start"), _node("end", "stop"), _node("after", "job", job_id="x")],
            "edges": [_edge("e1", "s", "end"), _edge("e2", "end", "after")],
        }
        with self.assertRaises(GraphValidationError) as ctx:
            WorkflowGraph(graph).validate(resolve_job=lambda _id: True)
        self.assertTrue(any("not reachable" in e for e in ctx.exception.errors))

    def test_draft_allows_unreachable_node(self):
        # Draft saves (require_runnable=False) tolerate not-yet-connected nodes.
        graph = {
            "nodes": [_node("s", "start"), _node("orphan", "job", job_id="y")],
            "edges": [],
        }
        WorkflowGraph(graph).validate(resolve_job=lambda _id: True, require_runnable=False)

    def test_draft_allows_missing_start(self):
        # require_runnable=False (draft save) tolerates a missing start node.
        graph = {"nodes": [_node("a", "job", job_id="x")], "edges": []}
        WorkflowGraph(graph).validate(resolve_job=lambda _id: True, require_runnable=False)

    def test_draft_still_rejects_two_starts(self):
        graph = {"nodes": [_node("s1", "start"), _node("s2", "start")], "edges": []}
        with self.assertRaises(GraphValidationError):
            WorkflowGraph(graph).validate(resolve_job=lambda _id: True, require_runnable=False)

    def test_helpers(self):
        graph = WorkflowGraph(
            {
                "nodes": [_node("s", "start"), _node("a", "job", job_id="x")],
                "edges": [_edge("e1", "s", "a")],
            }
        )
        self.assertEqual(graph.start_node_id, "s")
        self.assertEqual([e["id"] for e in graph.outgoing_edges("s")], ["e1"])
        self.assertEqual([e["id"] for e in graph.incoming_edges("a")], ["e1"])
        self.assertEqual(graph.node_type("a"), "job")
