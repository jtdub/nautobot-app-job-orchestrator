"""UI views for the job_orchestrator app."""

from django.contrib.auth.mixins import PermissionRequiredMixin
from django.shortcuts import get_object_or_404, render
from django.views.generic import View
from nautobot.apps.views import (
    NautobotUIViewSet,
    ObjectBulkDestroyViewMixin,
    ObjectChangeLogViewMixin,
    ObjectDestroyViewMixin,
    ObjectDetailViewMixin,
    ObjectListViewMixin,
    ObjectNotesViewMixin,
)

from job_orchestrator.api.serializers import WorkflowExecutionSerializer, WorkflowSerializer
from job_orchestrator.filters import WorkflowExecutionFilterSet, WorkflowFilterSet
from job_orchestrator.forms import (
    WorkflowBulkEditForm,
    WorkflowExecutionFilterForm,
    WorkflowFilterForm,
    WorkflowForm,
)
from job_orchestrator.models import Workflow, WorkflowExecution
from job_orchestrator.tables import WorkflowExecutionTable, WorkflowTable


class WorkflowUIViewSet(NautobotUIViewSet):
    """UI viewset (list/detail/edit/delete) for Workflow."""

    queryset = Workflow.objects.all()
    serializer_class = WorkflowSerializer
    table_class = WorkflowTable
    form_class = WorkflowForm
    bulk_update_form_class = WorkflowBulkEditForm
    filterset_class = WorkflowFilterSet
    filterset_form_class = WorkflowFilterForm


class WorkflowExecutionUIViewSet(
    ObjectListViewMixin,
    ObjectDetailViewMixin,
    ObjectDestroyViewMixin,
    ObjectBulkDestroyViewMixin,
    ObjectChangeLogViewMixin,
    ObjectNotesViewMixin,
):
    """UI viewset (list/detail/delete only) for WorkflowExecution.

    Executions are created and mutated exclusively by the engine, so no add/edit routes are
    composed in — hand-editing an execution's status would corrupt engine state.
    """

    queryset = WorkflowExecution.objects.all()
    serializer_class = WorkflowExecutionSerializer
    table_class = WorkflowExecutionTable
    filterset_class = WorkflowExecutionFilterSet
    filterset_form_class = WorkflowExecutionFilterForm


class WorkflowEditorView(PermissionRequiredMixin, View):
    """Full-page drag-and-drop canvas for authoring/running a workflow graph."""

    permission_required = "job_orchestrator.change_workflow"

    def get(self, request, pk):
        """Render the React Flow editor mounted on the given workflow."""
        # restrict() enforces constraint-scoped ObjectPermissions; PermissionRequiredMixin alone
        # only checks that the "change_workflow" codename exists for the user.
        workflow = get_object_or_404(Workflow.objects.restrict(request.user, "change"), pk=pk)
        return render(
            request,
            "job_orchestrator/workflow_editor.html",
            {"object": workflow, "workflow": workflow},
        )
