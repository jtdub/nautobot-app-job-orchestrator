"""Nautobot Jobs provided by the job_orchestrator app."""

from nautobot.apps.jobs import IntegerVar, Job, register_jobs

from job_orchestrator.tasks import DEFAULT_MAX_NODE_RUNTIME_SECONDS, reconcile_workflow_executions


class WorkflowReconciler(Job):
    """Safety-net sweep that recovers stuck workflow executions.

    Schedule this (e.g. every minute) via Nautobot's native job scheduling so that workflows still
    make progress if an advance signal is ever lost, a worker crashes mid-advance, or a node hangs.
    """

    max_node_runtime_seconds = IntegerVar(
        label="Max node runtime (seconds)",
        description="A node RUNNING longer than this is considered hung and is failed.",
        default=DEFAULT_MAX_NODE_RUNTIME_SECONDS,
        required=False,
    )

    class Meta:
        """Metadata for the WorkflowReconciler job."""

        name = "Workflow Reconciler"
        description = "Recover stuck Job Orchestrator workflow executions."

    def run(self, max_node_runtime_seconds=DEFAULT_MAX_NODE_RUNTIME_SECONDS):  # pylint: disable=arguments-differ
        """Run the reconciliation sweep and log a summary."""
        if max_node_runtime_seconds is None:  # `is None`, not falsy: an explicit 0 means "time out now".
            max_node_runtime_seconds = DEFAULT_MAX_NODE_RUNTIME_SECONDS
        summary = reconcile_workflow_executions(max_node_runtime_seconds=max_node_runtime_seconds)
        self.logger.info("Reconciler summary: %s", summary)
        return summary


register_jobs(WorkflowReconciler)
