"""FilterSets for the job_orchestrator app."""

import django_filters
from nautobot.apps.filters import NautobotFilterSet, SearchFilter

from job_orchestrator.models import Workflow, WorkflowExecution


class WorkflowFilterSet(NautobotFilterSet):
    """FilterSet for Workflow."""

    q = SearchFilter(filter_predicates={"name": "icontains", "description": "icontains"})

    class Meta:
        """Meta options for WorkflowFilterSet."""

        model = Workflow
        fields = ["id", "name", "enabled", "version"]


class WorkflowExecutionFilterSet(NautobotFilterSet):
    """FilterSet for WorkflowExecution."""

    q = SearchFilter(filter_predicates={"workflow__name": "icontains"})
    workflow = django_filters.ModelMultipleChoiceFilter(
        field_name="workflow",
        queryset=Workflow.objects.all(),
    )

    class Meta:
        """Meta options for WorkflowExecutionFilterSet."""

        model = WorkflowExecution
        fields = ["id", "workflow", "status"]
