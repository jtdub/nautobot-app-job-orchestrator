"""Tests for the reactive JobResult -> workflow advance signal path."""

from unittest import mock

from django.test import TestCase
from nautobot.extras.choices import JobResultStatusChoices
from nautobot.extras.models import JobResult

from job_orchestrator.choices import NodeExecutionStatusChoices, WorkflowExecutionStatusChoices
from job_orchestrator.models import Workflow, WorkflowExecution, WorkflowNodeExecution


class JobResultSignalTest(TestCase):
    """The signal should dispatch an advance only for terminal results with a waiting node."""

    def _execution(self):
        workflow = Workflow.objects.create(name="sig-wf", graph={"nodes": [], "edges": []})
        return WorkflowExecution.objects.create(
            workflow=workflow,
            graph_snapshot={"nodes": [], "edges": []},
            status=WorkflowExecutionStatusChoices.STATUS_RUNNING,
        )

    @mock.patch("job_orchestrator.tasks.advance_workflow_for_jobresult.delay")
    def test_no_dispatch_for_nonterminal_status(self, mock_delay):
        JobResult.objects.create(name="jr1", status=JobResultStatusChoices.STATUS_STARTED)
        mock_delay.assert_not_called()

    @mock.patch("job_orchestrator.tasks.advance_workflow_for_jobresult.delay")
    def test_no_dispatch_without_waiting_node(self, mock_delay):
        jr = JobResult.objects.create(name="jr2", status=JobResultStatusChoices.STATUS_STARTED)
        jr.status = JobResultStatusChoices.STATUS_SUCCESS
        jr.save()
        mock_delay.assert_not_called()

    @mock.patch("job_orchestrator.tasks.advance_workflow_for_jobresult.delay")
    def test_dispatch_for_terminal_with_waiting_node(self, mock_delay):
        execution = self._execution()
        jr = JobResult.objects.create(name="jr3", status=JobResultStatusChoices.STATUS_STARTED)
        WorkflowNodeExecution.objects.create(
            workflow_execution=execution,
            node_id="a",
            job_result=jr,
            status=NodeExecutionStatusChoices.STATUS_RUNNING,
        )
        jr.status = JobResultStatusChoices.STATUS_SUCCESS
        # The dispatch is deferred via transaction.on_commit so the task can never read a
        # pre-commit JobResult row; capture and run the callbacks as a commit would.
        with self.captureOnCommitCallbacks(execute=True):
            jr.save()
        mock_delay.assert_called_once_with(str(jr.pk))
