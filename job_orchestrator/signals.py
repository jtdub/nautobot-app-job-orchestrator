"""Signal receivers for the job_orchestrator app.

The orchestration engine reacts to Nautobot Jobs finishing. In Nautobot 3.x the Celery result
backend persists a JobResult's terminal status through a real ORM ``save()`` (via
``JobResultManager.store_result``), so Django's ``post_save`` fires for ``JobResult`` — including in
the worker process. We use that to advance any workflow waiting on the result.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from nautobot.extras.choices import JobResultStatusChoices
from nautobot.extras.models import JobResult

from job_orchestrator.choices import NodeExecutionStatusChoices

logger = logging.getLogger("nautobot.job_orchestrator.signals")


@receiver(post_save, sender=JobResult)
def advance_workflow_on_jobresult(sender, instance, **kwargs):  # pylint: disable=unused-argument
    """Dispatch a workflow advance when a JobResult reaches a terminal state.

    The actual graph traversal runs in a Celery task (not in the signal) so the worker thread that
    saved the JobResult is never blocked on workflow logic.
    """
    if instance.status not in JobResultStatusChoices.READY_STATES:
        return
    # Only bother if some workflow node is actually waiting on this result.
    from job_orchestrator.models import WorkflowNodeExecution

    has_waiter = WorkflowNodeExecution.objects.filter(
        job_result_id=instance.pk,
        status=NodeExecutionStatusChoices.STATUS_RUNNING,
    ).exists()
    if not has_waiter:
        return

    from job_orchestrator.tasks import advance_workflow_for_jobresult

    # Defer the dispatch until the saving transaction commits so the advance task cannot read a
    # stale, pre-terminal JobResult row (in autocommit mode on_commit runs immediately).
    transaction.on_commit(lambda: advance_workflow_for_jobresult.delay(str(instance.pk)))
