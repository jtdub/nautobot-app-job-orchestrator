"""Django urlpatterns declaration for job_orchestrator app."""

from django.templatetags.static import static
from django.urls import path
from django.views.generic import RedirectView
from nautobot.apps.urls import NautobotUIViewSetRouter


# Uncomment the following line if you have views to import
# from job_orchestrator import views


app_name = "job_orchestrator"
router = NautobotUIViewSetRouter()

# Here is an example of how to register a viewset, you will want to replace views.JobOrchestratorUIViewSet with your viewset
# router.register("job_orchestrator", views.JobOrchestratorUIViewSet)


urlpatterns = [
    path("docs/", RedirectView.as_view(url=static("job_orchestrator/docs/index.html")), name="docs"),
]

urlpatterns += router.urls
