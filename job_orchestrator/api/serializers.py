"""API serializers for the job_orchestrator app."""

from nautobot.apps.api import NautobotModelSerializer
from rest_framework import serializers

from job_orchestrator.models import (
    Workflow,
    WorkflowEdgeActivation,
    WorkflowExecution,
    WorkflowNodeExecution,
)


class WorkflowSerializer(NautobotModelSerializer):
    """Serializer for the Workflow model."""

    class Meta:
        """Meta options for WorkflowSerializer."""

        model = Workflow
        fields = "__all__"


class WorkflowNodeExecutionSerializer(NautobotModelSerializer):
    """Serializer for a single node within an execution (used for live canvas highlighting)."""

    class Meta:
        """Meta options for WorkflowNodeExecutionSerializer."""

        model = WorkflowNodeExecution
        fields = [
            "id",
            "node_id",
            "status",
            "job",
            "job_result",
            "started_time",
            "completed_time",
        ]


class WorkflowEdgeActivationSerializer(NautobotModelSerializer):
    """Serializer for an edge activation within an execution."""

    class Meta:
        """Meta options for WorkflowEdgeActivationSerializer."""

        model = WorkflowEdgeActivation
        fields = ["id", "edge_id", "state"]


class WorkflowExecutionSerializer(NautobotModelSerializer):
    """Serializer for a workflow execution, with nested node/edge state for polling."""

    node_executions = WorkflowNodeExecutionSerializer(many=True, read_only=True)
    edge_activations = WorkflowEdgeActivationSerializer(many=True, read_only=True)
    # Exposed so API consumers (e.g. the editor's poll loop) don't hardcode the terminal-state list.
    is_terminal = serializers.BooleanField(read_only=True)

    class Meta:
        """Meta options for WorkflowExecutionSerializer."""

        model = WorkflowExecution
        fields = [
            "id",
            "url",
            "workflow",
            "status",
            "is_terminal",
            "started_by",
            "started_time",
            "completed_time",
            "failure_reason",
            "node_executions",
            "edge_activations",
        ]


class WorkflowExecuteInputSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Empty input serializer for the ``execute`` action (kwargs come from the saved graph)."""
