"""Navigation menu items for the job_orchestrator app."""

from nautobot.apps.ui import NavMenuAddButton, NavMenuGroup, NavMenuItem, NavMenuTab

menu_items = (
    NavMenuTab(
        name="Automation",
        weight=600,
        groups=(
            NavMenuGroup(
                name="Job Orchestrator",
                weight=100,
                items=(
                    NavMenuItem(
                        link="plugins:job_orchestrator:workflow_list",
                        name="Workflows",
                        permissions=["job_orchestrator.view_workflow"],
                        buttons=(
                            NavMenuAddButton(
                                link="plugins:job_orchestrator:workflow_add",
                                permissions=["job_orchestrator.add_workflow"],
                            ),
                        ),
                    ),
                    NavMenuItem(
                        link="plugins:job_orchestrator:workflowexecution_list",
                        name="Executions",
                        permissions=["job_orchestrator.view_workflowexecution"],
                    ),
                ),
            ),
        ),
    ),
)
