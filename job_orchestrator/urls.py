"""Django urlpatterns declaration for job_orchestrator app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from nautobot.apps.urls import NautobotUIViewSetRouter

from job_orchestrator import views

app_name = "job_orchestrator"
router = NautobotUIViewSetRouter()
router.register("workflows", views.WorkflowUIViewSet)
router.register("workflow-executions", views.WorkflowExecutionUIViewSet)


urlpatterns = [
    path(
        "workflows/<uuid:pk>/editor/",
        views.WorkflowEditorView.as_view(),
        name="workflow_editor",
    ),
    path("docs/", RedirectView.as_view(url=static("job_orchestrator/docs/index.html")), name="docs"),
]

urlpatterns += router.urls
