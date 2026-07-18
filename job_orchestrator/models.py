"""Models for the job_orchestrator app.

Storage is hybrid: the full React Flow document (nodes, edges, positions, visual metadata) lives in
the :class:`Workflow.graph` JSONField, while live execution state is normalized into the execution
models so it can be indexed, queried, and linked to real ``extras.JobResult`` records.
"""

from django.core.exceptions import ValidationError
from django.db import models
from nautobot.apps.models import OrganizationalModel, PrimaryModel

from job_orchestrator.choices import (
    EdgeActivationStateChoices,
    JoinRuleChoices,
    NodeExecutionStatusChoices,
    TransitionConditionChoices,
    WorkflowExecutionStatusChoices,
    WorkflowNodeTypeChoices,
)
from job_orchestrator.graph import GraphValidationError, WorkflowGraph


class Workflow(PrimaryModel):
    """A saved, drag-and-drop orchestration graph of Nautobot Jobs.

    The canonical graph document (React Flow nodes/edges plus visual metadata) is stored in
    :attr:`graph`; structural validity is enforced by :meth:`clean`.
    """

    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    graph = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        """Meta options for Workflow."""

        ordering = ["name"]

    def __str__(self):
        """Return the workflow name."""
        return self.name

    def as_graph(self):
        """Return a :class:`~job_orchestrator.graph.WorkflowGraph` view over :attr:`graph`."""
        return WorkflowGraph(self.graph)

    def _resolve_job(self):
        """Return a ``job_id -> bool`` existence check against the Job model."""
        # Imported here to keep module import-time free of the extras app registry.
        from nautobot.extras.models import Job as JobModel

        return lambda job_id: JobModel.objects.filter(pk=job_id).exists()

    def clean(self):
        """Validate the saved graph leniently (drafts allowed; executability checked at run time)."""
        super().clean()
        try:
            self.as_graph().validate(resolve_job=self._resolve_job(), require_runnable=False)
        except GraphValidationError as exc:
            raise ValidationError({"graph": exc.errors}) from exc

    def validate_runnable(self):
        """Strictly validate that the graph is executable; raise ``ValidationError`` otherwise."""
        try:
            self.as_graph().validate(resolve_job=self._resolve_job(), require_runnable=True)
        except GraphValidationError as exc:
            raise ValidationError({"graph": exc.errors}) from exc


class WorkflowExecution(PrimaryModel):
    """A single run of a :class:`Workflow`.

    ``graph_snapshot`` is a deep copy taken at start so that an in-flight run is immune to later
    edits of the source workflow.
    """

    workflow = models.ForeignKey(
        to=Workflow,
        on_delete=models.PROTECT,
        related_name="executions",
    )
    graph_snapshot = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=WorkflowExecutionStatusChoices,
        default=WorkflowExecutionStatusChoices.STATUS_PENDING,
    )
    started_by = models.ForeignKey(
        to="users.User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )
    started_time = models.DateTimeField(blank=True, null=True)
    completed_time = models.DateTimeField(blank=True, null=True)
    failure_reason = models.TextField(blank=True)

    class Meta:
        """Meta options for WorkflowExecution."""

        ordering = ["-created"]

    def __str__(self):
        """Return a human-readable label for this execution."""
        return f"{self.workflow.name} @ {self.created.isoformat() if self.created else self.pk}"

    def as_graph(self):
        """Return a :class:`~job_orchestrator.graph.WorkflowGraph` view over the snapshot."""
        return WorkflowGraph(self.graph_snapshot)

    @property
    def is_terminal(self):
        """Return ``True`` if this execution will do no further work."""
        return self.status in WorkflowExecutionStatusChoices.TERMINAL_STATES


class WorkflowNodeExecution(OrganizationalModel):
    """Tracks a single node within a :class:`WorkflowExecution`.

    For ``job`` nodes, :attr:`job_result` links to the ``extras.JobResult`` produced when the node's
    job was enqueued; the ``post_save`` signal on ``JobResult`` uses this FK to advance the workflow.
    """

    workflow_execution = models.ForeignKey(
        to=WorkflowExecution,
        on_delete=models.CASCADE,
        related_name="node_executions",
    )
    node_id = models.CharField(max_length=255)
    job = models.ForeignKey(
        to="extras.Job",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )
    job_result = models.ForeignKey(
        to="extras.JobResult",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="+",
    )
    status = models.CharField(
        max_length=20,
        choices=NodeExecutionStatusChoices,
        default=NodeExecutionStatusChoices.STATUS_PENDING,
    )
    kwargs = models.JSONField(default=dict, blank=True)
    attempt = models.PositiveSmallIntegerField(default=1)
    started_time = models.DateTimeField(blank=True, null=True)
    completed_time = models.DateTimeField(blank=True, null=True)

    class Meta:
        """Meta options for WorkflowNodeExecution."""

        ordering = ["created"]
        unique_together = [["workflow_execution", "node_id", "attempt"]]
        indexes = [
            models.Index(fields=["job_result"]),
            models.Index(fields=["workflow_execution", "status"]),
        ]

    def __str__(self):
        """Return a label combining execution and node id."""
        return f"{self.workflow_execution_id}:{self.node_id} ({self.status})"


class WorkflowEdgeActivation(OrganizationalModel):
    """Records the resolved state of an edge within a :class:`WorkflowExecution`.

    Each edge resolves exactly once per execution. The ``unique_together`` constraint both prevents
    double-resolution under concurrent fan-out and lets the engine atomically ask whether all of a
    join node's incoming edges have resolved yet.
    """

    workflow_execution = models.ForeignKey(
        to=WorkflowExecution,
        on_delete=models.CASCADE,
        related_name="edge_activations",
    )
    edge_id = models.CharField(max_length=255)
    state = models.CharField(max_length=20, choices=EdgeActivationStateChoices)

    class Meta:
        """Meta options for WorkflowEdgeActivation."""

        ordering = ["created"]
        unique_together = [["workflow_execution", "edge_id"]]

    def __str__(self):
        """Return a label combining execution, edge id, and state."""
        return f"{self.workflow_execution_id}:{self.edge_id} ({self.state})"


# Re-export choice/enum-style helpers that callers commonly need alongside the models.
__all__ = [
    "Workflow",
    "WorkflowExecution",
    "WorkflowNodeExecution",
    "WorkflowEdgeActivation",
    "JoinRuleChoices",
    "TransitionConditionChoices",
    "WorkflowNodeTypeChoices",
]
