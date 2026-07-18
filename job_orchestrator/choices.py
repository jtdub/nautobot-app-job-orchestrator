"""ChoiceSets for the job_orchestrator app."""

from nautobot.apps.choices import ChoiceSet


class WorkflowNodeTypeChoices(ChoiceSet):
    """Types of nodes that can appear on a workflow canvas."""

    TYPE_START = "start"
    TYPE_JOB = "job"
    TYPE_JOIN = "join"
    TYPE_STOP = "stop"

    CHOICES = (
        (TYPE_START, "Start"),
        (TYPE_JOB, "Job"),
        (TYPE_JOIN, "Join"),
        (TYPE_STOP, "Stop"),
    )


class TransitionConditionChoices(ChoiceSet):
    """Condition under which an edge (transition) fires based on the source node outcome."""

    ON_SUCCESS = "on_success"
    ON_FAILURE = "on_failure"
    ON_COMPLETE = "on_complete"

    CHOICES = (
        (ON_SUCCESS, "On success"),
        (ON_FAILURE, "On failure"),
        (ON_COMPLETE, "On complete"),
    )


class JoinRuleChoices(ChoiceSet):
    """Firing rule for an explicit join (barrier) node once all incoming edges have resolved."""

    RULE_ANY = "any"
    RULE_ALL = "all"

    CHOICES = (
        (RULE_ANY, "Any (fire if at least one incoming edge activated)"),
        (RULE_ALL, "All (fire only if every incoming edge activated)"),
    )


class WorkflowExecutionStatusChoices(ChoiceSet):
    """Overall status of a workflow execution."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_TERMINATED = "terminated"

    CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_TERMINATED, "Terminated"),
    )

    #: Statuses after which an execution does no further work.
    TERMINAL_STATES = (STATUS_COMPLETED, STATUS_FAILED, STATUS_TERMINATED)


class NodeExecutionStatusChoices(ChoiceSet):
    """Status of a single node within a workflow execution."""

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    CHOICES = (
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    )

    #: Statuses after which a node will not transition again.
    TERMINAL_STATES = (STATUS_SUCCEEDED, STATUS_FAILED, STATUS_SKIPPED)


class EdgeActivationStateChoices(ChoiceSet):
    """Resolved state of an edge within a workflow execution.

    Each edge resolves exactly once per execution: ``ACTIVATED`` if the source node's outcome
    matched the edge condition, otherwise ``SKIPPED``.
    """

    STATE_ACTIVATED = "activated"
    STATE_SKIPPED = "skipped"

    CHOICES = (
        (STATE_ACTIVATED, "Activated"),
        (STATE_SKIPPED, "Skipped"),
    )
