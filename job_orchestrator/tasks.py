"""Celery tasks for the job_orchestrator app.

``advance_workflow_for_jobresult`` is the reactive worker dispatched by the JobResult ``post_save``
signal. ``reconcile_workflow_executions`` is the safety-net sweep that recovers from a missed signal,
a worker crash, or a hung job; it is exposed to operators as the schedulable ``WorkflowReconciler``
Nautobot Job in ``jobs.py`` and can also be called directly.
"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger("nautobot.job_orchestrator.tasks")

#: Default cap on how long a single node may stay RUNNING before the reconciler fails it.
DEFAULT_MAX_NODE_RUNTIME_SECONDS = 24 * 60 * 60


@shared_task
def advance_workflow_for_jobresult(job_result_id):
    """Advance any workflow node waiting on the given JobResult. Idempotent."""
    from job_orchestrator.engine import advance_for_job_result

    advance_for_job_result(job_result_id)


def reconcile_workflow_executions(max_node_runtime_seconds=DEFAULT_MAX_NODE_RUNTIME_SECONDS):
    """Recover stuck executions.

    Two cases are handled:

    1. **Missed advance** — a RUNNING node whose JobResult is already in a terminal state (the signal
       was lost or fired before our FK committed). Re-drive it through the normal advance path.
    2. **Hung node** — a RUNNING node whose JobResult never reached a terminal state and has exceeded
       ``max_node_runtime_seconds``. Mark its JobResult-less progress as failed and advance.

    Returns a summary dict for logging/Job output.
    """
    from nautobot.extras.choices import JobResultStatusChoices

    from job_orchestrator.choices import NodeExecutionStatusChoices
    from job_orchestrator.engine import advance_for_job_result, fail_stuck_node
    from job_orchestrator.models import WorkflowNodeExecution

    summary = {"readvanced": 0, "timed_out": 0}
    cutoff = timezone.now() - timezone.timedelta(seconds=max_node_runtime_seconds)

    # Any RUNNING node is fair game — including one inside an already-terminated execution (e.g. a
    # stop node ended the run while this node's job was in flight); it still needs finalizing.
    running_nodes = WorkflowNodeExecution.objects.filter(
        status=NodeExecutionStatusChoices.STATUS_RUNNING,
    ).select_related("job_result")

    for node_exec in running_nodes:
        job_result = node_exec.job_result
        if job_result is not None and job_result.status in JobResultStatusChoices.READY_STATES:
            # Terminal JobResult but the node never advanced — re-drive it.
            advance_for_job_result(str(job_result.pk))
            summary["readvanced"] += 1
        elif node_exec.started_time and node_exec.started_time < cutoff:
            # Hung node past the runtime cap — fail it and advance the workflow. This goes through
            # the engine (not a bare status save) so on-failure edges resolve and completion runs.
            if fail_stuck_node(node_exec.pk):
                summary["timed_out"] += 1

    if summary["readvanced"] or summary["timed_out"]:
        logger.info("Workflow reconciler: %s", summary)
    return summary
