"""Tables for the job_orchestrator app."""

import django_tables2 as tables
from nautobot.apps.tables import BaseTable, ButtonsColumn, ToggleColumn

from job_orchestrator.models import Workflow, WorkflowExecution


class WorkflowTable(BaseTable):
    """Table for listing Workflow records."""

    pk = ToggleColumn()
    name = tables.Column(linkify=True)
    actions = ButtonsColumn(Workflow)

    class Meta(BaseTable.Meta):
        """Meta options for WorkflowTable."""

        model = Workflow
        fields = ("pk", "name", "description", "enabled", "version")
        default_columns = ("pk", "name", "enabled", "version")


class WorkflowExecutionTable(BaseTable):
    """Table for listing WorkflowExecution records."""

    pk = ToggleColumn()
    workflow = tables.Column(linkify=True)
    status = tables.Column()
    created = tables.DateTimeColumn(linkify=True)
    # No edit button: executions are engine-owned and the viewset composes no edit route.
    actions = ButtonsColumn(WorkflowExecution, buttons=("changelog", "delete"))

    class Meta(BaseTable.Meta):
        """Meta options for WorkflowExecutionTable."""

        model = WorkflowExecution
        fields = ("pk", "workflow", "status", "started_by", "started_time", "completed_time", "created")
        default_columns = ("pk", "workflow", "status", "started_time", "completed_time")
