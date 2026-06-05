"""App declaration for job_orchestrator."""

# Metadata is inherited from Nautobot. If not including Nautobot in the environment, this should be added
from importlib import metadata

from nautobot.apps import NautobotAppConfig

__version__ = metadata.version(__name__)


class JobOrchestratorConfig(NautobotAppConfig):
    """App configuration for the job_orchestrator app."""

    name = "job_orchestrator"
    verbose_name = "Job Orchestrator"
    version = __version__
    author = "James Williams"
    description = "Job Orchestrator."
    base_url = "job-orchestrator"
    required_settings = []
    default_settings = {}
    docs_view_name = "plugins:job_orchestrator:docs"
    searchable_models = ["job_orchestrator.Workflow"]

    def ready(self):
        """Register signal receivers once the app registry is ready."""
        super().ready()
        # Importing connects the post_save receiver that drives workflow advancement.
        from job_orchestrator import signals  # noqa: F401  pylint:disable=import-outside-toplevel,unused-import


config = JobOrchestratorConfig  # pylint:disable=invalid-name
