"""Forms for the job_orchestrator app."""

from django import forms
from nautobot.apps.forms import NautobotBulkEditForm, NautobotFilterForm, NautobotModelForm

from job_orchestrator.models import Workflow, WorkflowExecution


class WorkflowForm(NautobotModelForm):
    """Create/edit form for Workflow.

    The ``graph`` is normally authored on the drag-and-drop canvas; it is exposed here as a hidden
    field so the standard object-edit view round-trips it without a raw JSON textarea.
    """

    class Meta:
        """Meta options for WorkflowForm."""

        model = Workflow
        fields = ("name", "description", "enabled", "version", "graph", "tags")
        widgets = {"graph": forms.HiddenInput()}


class WorkflowBulkEditForm(NautobotBulkEditForm):
    """Bulk-edit form for Workflow."""

    pk = forms.ModelMultipleChoiceField(queryset=Workflow.objects.all(), widget=forms.MultipleHiddenInput)
    enabled = forms.NullBooleanField(required=False)
    description = forms.CharField(required=False)

    class Meta:
        """Meta options for WorkflowBulkEditForm."""

        nullable_fields = ["description"]


class WorkflowFilterForm(NautobotFilterForm):
    """Filter form for Workflow."""

    model = Workflow
    q = forms.CharField(required=False, label="Search")
    enabled = forms.NullBooleanField(required=False)


class WorkflowExecutionFilterForm(NautobotFilterForm):
    """Filter form for WorkflowExecution."""

    model = WorkflowExecution
    q = forms.CharField(required=False, label="Search")
    workflow = forms.ModelChoiceField(queryset=Workflow.objects.all(), required=False)
