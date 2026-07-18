"""Tests for the workflow execution engine.

These drive the engine without real Celery workers: ``engine._enqueue_job`` is patched to create a
JobResult in a running state, and completion is simulated by setting that JobResult's status and
calling ``advance_for_job_result`` directly. The JobResult ``post_save`` signal is disconnected so
only the explicit advance runs.
"""

from unittest import mock

from django.db.models.signals import post_save
from django.test import TestCase
from django.utils import timezone
from nautobot.extras.choices import JobResultStatusChoices
from nautobot.extras.models import JobResult

from job_orchestrator import engine
from job_orchestrator.choices import (
    NodeExecutionStatusChoices,
    WorkflowExecutionStatusChoices,
)
from job_orchestrator.models import Workflow, WorkflowNodeExecution
from job_orchestrator.signals import advance_workflow_on_jobresult
from job_orchestrator.tests._graph_helpers import _edge, _node


# pylint: disable-next=unused-argument
def _fake_enqueue(node_exec, job_id, job_kwargs, user):  # noqa: ARG001
    """Stand-in for engine._enqueue_job: create a running JobResult and link it to the node."""
    job_result = JobResult.objects.create(
        name=f"jr-{node_exec.node_id}",
        status=JobResultStatusChoices.STATUS_STARTED,
    )
    # Deliberately mirrors engine._enqueue_job's tail so the mock leaves the node in the same state.
    # pylint: disable=duplicate-code
    node_exec.job_result = job_result
    node_exec.kwargs = job_kwargs
    node_exec.status = NodeExecutionStatusChoices.STATUS_RUNNING
    node_exec.started_time = timezone.now()
    node_exec.save()


class EngineTestCase(TestCase):
    """Base helpers for engine scenarios."""

    def setUp(self):
        # Avoid double-driving via the real signal; we advance explicitly.
        post_save.disconnect(advance_workflow_on_jobresult, sender=JobResult)
        self.addCleanup(lambda: post_save.connect(advance_workflow_on_jobresult, sender=JobResult))
        # Skip Job-existence/structure validation so fake job ids are accepted.
        patcher_validate = mock.patch.object(Workflow, "validate_runnable", lambda self: None)
        patcher_validate.start()
        self.addCleanup(patcher_validate.stop)
        patcher_enqueue = mock.patch.object(engine, "_enqueue_job", _fake_enqueue)
        patcher_enqueue.start()
        self.addCleanup(patcher_enqueue.stop)

    def _start(self, nodes, edges):
        workflow = Workflow.objects.create(
            name=f"wf-{timezone.now().timestamp()}", graph={"nodes": nodes, "edges": edges}
        )
        return engine.start_workflow(workflow, None)

    def _complete(self, execution, node_id, success=True):
        node_exec = WorkflowNodeExecution.objects.get(
            workflow_execution=execution,
            node_id=node_id,
            status=NodeExecutionStatusChoices.STATUS_RUNNING,
        )
        job_result = node_exec.job_result
        job_result.status = JobResultStatusChoices.STATUS_SUCCESS if success else JobResultStatusChoices.STATUS_FAILURE
        job_result.save()
        engine.advance_for_job_result(str(job_result.pk))
        execution.refresh_from_db()

    def _node_status(self, execution, node_id):
        return WorkflowNodeExecution.objects.get(workflow_execution=execution, node_id=node_id).status

    def _is_running(self, execution, node_id):
        return WorkflowNodeExecution.objects.filter(
            workflow_execution=execution,
            node_id=node_id,
            status=NodeExecutionStatusChoices.STATUS_RUNNING,
        ).exists()


class LinearAndConditionalTest(EngineTestCase):
    """Sequential and conditional routing."""

    def test_linear_success(self):
        ex = self._start(
            [_node("s", "start"), _node("a", "job", job_id="x"), _node("b", "job", job_id="y")],
            [_edge("e1", "s", "a"), _edge("e2", "a", "b", "on_success")],
        )
        self.assertTrue(self._is_running(ex, "a"))
        self._complete(ex, "a", success=True)
        self.assertTrue(self._is_running(ex, "b"))
        self._complete(ex, "b", success=True)
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_COMPLETED)

    def test_failure_routes_to_handler(self):
        ex = self._start(
            [
                _node("s", "start"),
                _node("a", "job", job_id="x"),
                _node("b", "job", job_id="y"),
                _node("c", "job", job_id="z"),
            ],
            [_edge("e1", "s", "a"), _edge("e2", "a", "b", "on_success"), _edge("e3", "a", "c", "on_failure")],
        )
        self._complete(ex, "a", success=False)
        self.assertEqual(self._node_status(ex, "b"), NodeExecutionStatusChoices.STATUS_SKIPPED)
        self.assertTrue(self._is_running(ex, "c"))
        self._complete(ex, "c", success=True)
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_COMPLETED)

    def test_stop_node_terminates(self):
        ex = self._start(
            [_node("s", "start"), _node("a", "job", job_id="x"), _node("end", "stop")],
            [_edge("e1", "s", "a"), _edge("e2", "a", "end", "on_failure")],
        )
        self._complete(ex, "a", success=False)
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_TERMINATED)

    def test_unhandled_failure_fails_execution(self):
        ex = self._start(
            [_node("s", "start"), _node("a", "job", job_id="x"), _node("b", "job", job_id="y")],
            [_edge("e1", "s", "a"), _edge("e2", "a", "b", "on_success")],
        )
        self._complete(ex, "a", success=False)
        self.assertEqual(self._node_status(ex, "b"), NodeExecutionStatusChoices.STATUS_SKIPPED)
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_FAILED)


class FanOutJoinTest(EngineTestCase):
    """Parallel fan-out and join (barrier) behaviour."""

    def test_fan_out(self):
        ex = self._start(
            [
                _node("s", "start"),
                _node("a", "job", job_id="x"),
                _node("b", "job", job_id="y"),
                _node("c", "job", job_id="z"),
            ],
            [_edge("e1", "s", "a"), _edge("e2", "a", "b", "on_complete"), _edge("e3", "a", "c", "on_complete")],
        )
        self._complete(ex, "a", success=True)
        self.assertTrue(self._is_running(ex, "b"))
        self.assertTrue(self._is_running(ex, "c"))

    def test_join_all_waits_for_both(self):
        nodes = [
            _node("s", "start"),
            _node("b", "job", job_id="y"),
            _node("c", "job", job_id="z"),
            _node("j", "join", join_rule="all"),
            _node("d", "job", job_id="w"),
        ]
        edges = [
            _edge("e1", "s", "b"),
            _edge("e2", "s", "c"),
            _edge("e3", "b", "j", "on_success"),
            _edge("e4", "c", "j", "on_success"),
            _edge("e5", "j", "d", "on_complete"),
        ]
        ex = self._start(nodes, edges)
        self.assertTrue(self._is_running(ex, "b"))
        self.assertTrue(self._is_running(ex, "c"))
        self._complete(ex, "b", success=True)
        # Join must NOT fire until c also resolves.
        self.assertFalse(WorkflowNodeExecution.objects.filter(workflow_execution=ex, node_id="d").exists())
        self._complete(ex, "c", success=True)
        self.assertTrue(self._is_running(ex, "d"))
        self._complete(ex, "d", success=True)
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_COMPLETED)

    def test_join_all_skips_when_one_branch_fails(self):
        nodes = [
            _node("s", "start"),
            _node("b", "job", job_id="y"),
            _node("c", "job", job_id="z"),
            _node("j", "join", join_rule="all"),
            _node("d", "job", job_id="w"),
        ]
        edges = [
            _edge("e1", "s", "b"),
            _edge("e2", "s", "c"),
            _edge("e3", "b", "j", "on_success"),
            _edge("e4", "c", "j", "on_success"),
            _edge("e5", "j", "d", "on_complete"),
        ]
        ex = self._start(nodes, edges)
        self._complete(ex, "b", success=True)
        self._complete(ex, "c", success=False)  # c's on_success edge to join is SKIPPED
        # ALL rule: not every incoming activated -> join skips -> d skipped.
        self.assertEqual(self._node_status(ex, "j"), NodeExecutionStatusChoices.STATUS_SKIPPED)
        self.assertEqual(self._node_status(ex, "d"), NodeExecutionStatusChoices.STATUS_SKIPPED)
        # c failed with no activated outgoing edge -> unhandled -> execution FAILED.
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_FAILED)

    def test_stop_terminates_but_inflight_sibling_still_finalizes(self):
        # Fan-out: a reaches a stop while b is still running; b must still reach a terminal
        # node status when its job finishes, even though the execution is already TERMINATED.
        ex = self._start(
            [
                _node("s", "start"),
                _node("a", "job", job_id="x"),
                _node("b", "job", job_id="y"),
                _node("end", "stop"),
            ],
            [_edge("e1", "s", "a"), _edge("e2", "s", "b"), _edge("e3", "a", "end", "on_success")],
        )
        self._complete(ex, "a", success=True)
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_TERMINATED)
        self.assertTrue(self._is_running(ex, "b"))
        self._complete(ex, "b", success=True)
        self.assertEqual(self._node_status(ex, "b"), NodeExecutionStatusChoices.STATUS_SUCCEEDED)
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_TERMINATED)

    def test_join_any_fires_with_one_branch(self):
        nodes = [
            _node("s", "start"),
            _node("b", "job", job_id="y"),
            _node("c", "job", job_id="z"),
            _node("j", "join", join_rule="any"),
            _node("d", "job", job_id="w"),
        ]
        edges = [
            _edge("e1", "s", "b"),
            _edge("e2", "s", "c"),
            _edge("e3", "b", "j", "on_success"),
            _edge("e4", "c", "j", "on_success"),
            _edge("e5", "j", "d", "on_complete"),
        ]
        ex = self._start(nodes, edges)
        self._complete(ex, "b", success=True)
        self._complete(ex, "c", success=False)
        # ANY rule: at least one activated -> join fires -> d runs.
        self.assertTrue(self._is_running(ex, "d"))


class EngineGuardsTest(EngineTestCase):
    """Guards and recovery paths: enabled flag, stuck nodes, non-terminal results, failure reason."""

    def test_disabled_workflow_cannot_start(self):
        from django.core.exceptions import ValidationError

        workflow = Workflow.objects.create(
            name=f"wf-{timezone.now().timestamp()}",
            graph={"nodes": [_node("s", "start")], "edges": []},
            enabled=False,
        )
        with self.assertRaises(ValidationError):
            engine.start_workflow(workflow, None)

    def test_advance_defers_on_nonterminal_job_result(self):
        ex = self._start(
            [_node("s", "start"), _node("a", "job", job_id="x")],
            [_edge("e1", "s", "a")],
        )
        node_exec = WorkflowNodeExecution.objects.get(workflow_execution=ex, node_id="a")
        # JobResult is still STARTED; the advance must defer, not stamp the node FAILED.
        engine.advance_for_job_result(str(node_exec.job_result.pk))
        self.assertTrue(self._is_running(ex, "a"))
        ex.refresh_from_db()
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_RUNNING)

    def test_fail_stuck_node_propagates_and_completes(self):
        ex = self._start(
            [_node("s", "start"), _node("a", "job", job_id="x"), _node("c", "job", job_id="z")],
            [_edge("e1", "s", "a"), _edge("e2", "a", "c", "on_failure")],
        )
        node_exec = WorkflowNodeExecution.objects.get(workflow_execution=ex, node_id="a")
        self.assertTrue(engine.fail_stuck_node(node_exec.pk))
        self.assertEqual(self._node_status(ex, "a"), NodeExecutionStatusChoices.STATUS_FAILED)
        # The on_failure handler fired, so the workflow keeps going instead of deadlocking.
        self.assertTrue(self._is_running(ex, "c"))
        # Idempotent: a second call is a no-op.
        self.assertFalse(engine.fail_stuck_node(node_exec.pk))
        self._complete(ex, "c", success=True)
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_COMPLETED)

    def test_unhandled_failure_records_failure_reason(self):
        ex = self._start(
            [_node("s", "start"), _node("a", "job", job_id="x")],
            [_edge("e1", "s", "a")],
        )
        self._complete(ex, "a", success=False)
        self.assertEqual(ex.status, WorkflowExecutionStatusChoices.STATUS_FAILED)
        self.assertIn("a", ex.failure_reason)
