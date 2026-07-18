"""API URL routing for the job_orchestrator app."""

from nautobot.apps.api import OrderedDefaultRouter

from job_orchestrator.api.views import WorkflowExecutionViewSet, WorkflowViewSet

router = OrderedDefaultRouter()
router.register("workflows", WorkflowViewSet)
router.register("workflow-executions", WorkflowExecutionViewSet)

app_name = "job_orchestrator-api"
urlpatterns = router.urls
