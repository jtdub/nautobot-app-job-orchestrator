"""API views for the job_orchestrator app."""

from django.core.exceptions import ValidationError
from nautobot.apps.api import NautobotModelViewSet, ReadOnlyModelViewSet
from rest_framework import mixins
from rest_framework.decorators import action
from rest_framework.response import Response

from job_orchestrator.api.serializers import (
    WorkflowExecutionSerializer,
    WorkflowSerializer,
)
from job_orchestrator.engine import start_workflow
from job_orchestrator.filters import WorkflowExecutionFilterSet, WorkflowFilterSet
from job_orchestrator.models import Workflow, WorkflowExecution


class WorkflowViewSet(NautobotModelViewSet):
    """REST API viewset for Workflow, including a custom ``execute`` action."""

    queryset = Workflow.objects.all()
    serializer_class = WorkflowSerializer
    filterset_class = WorkflowFilterSet

    @action(detail=True, methods=["post"])
    def execute(self, request, pk=None):  # pylint: disable=unused-argument
        """Start a new execution of this workflow and return its serialized state."""
        workflow = self.get_object()
        try:
            execution = start_workflow(workflow, request.user)
        except ValidationError as exc:
            # DRF does not translate Django's ValidationError; do it here so an invalid or
            # disabled workflow yields a 400 with the messages instead of a 500.
            return Response(exc.message_dict if hasattr(exc, "message_dict") else exc.messages, status=400)
        serializer = WorkflowExecutionSerializer(execution, context={"request": request})
        return Response(serializer.data, status=201)


class WorkflowExecutionViewSet(mixins.DestroyModelMixin, ReadOnlyModelViewSet):
    """Read-mostly (list/retrieve/delete) REST API viewset for WorkflowExecution polling."""

    queryset = WorkflowExecution.objects.all().prefetch_related("node_executions", "edge_activations")
    serializer_class = WorkflowExecutionSerializer
    filterset_class = WorkflowExecutionFilterSet
