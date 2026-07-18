"""Workflow execution engine.

The engine drives a :class:`~job_orchestrator.models.WorkflowExecution` forward using
**edge-activation propagation**: when a node completes, each of its outgoing edges resolves exactly
once to ``ACTIVATED`` (its condition matched the node's outcome) or ``SKIPPED``. A node fires when
its join rule over its incoming edges is satisfied — an implicit OR-join for ordinary nodes, an
explicit barrier for ``join`` nodes. This is what makes fan-out and fan-in deadlock-free.

Concurrency model: every entry point takes a ``select_for_update`` lock on the ``WorkflowExecution``
row, so all advances for a single execution are fully serialized while different executions still
run in parallel. The unique constraints on node/edge rows are a backstop, not the primary guard.
"""

import copy
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from job_orchestrator.choices import (
    EdgeActivationStateChoices,
    JoinRuleChoices,
    NodeExecutionStatusChoices,
    TransitionConditionChoices,
    WorkflowExecutionStatusChoices,
    WorkflowNodeTypeChoices,
)
from job_orchestrator.models import (
    WorkflowEdgeActivation,
    WorkflowExecution,
    WorkflowNodeExecution,
)

logger = logging.getLogger("nautobot.job_orchestrator.engine")

# Outcomes used internally when completing a node and resolving its outgoing edges.
OUTCOME_SUCCEEDED = NodeExecutionStatusChoices.STATUS_SUCCEEDED
OUTCOME_FAILED = NodeExecutionStatusChoices.STATUS_FAILED
OUTCOME_SKIPPED = NodeExecutionStatusChoices.STATUS_SKIPPED


def start_workflow(workflow, user):
    """Create and begin a :class:`WorkflowExecution` for ``workflow``.

    Validates the workflow, snapshots its graph, then resolves the ``start`` node (a pass-through),
    which schedules the first real nodes. Returns the created execution.
    """
    if not workflow.enabled:
        raise ValidationError({"enabled": ["Workflow is disabled and cannot be executed."]})
    workflow.validate_runnable()
    # Create the execution inside the same transaction as the initial propagation so a failure
    # during propagation rolls the RUNNING execution back instead of stranding a node-less phantom.
    with transaction.atomic():
        execution = WorkflowExecution.objects.create(
            workflow=workflow,
            graph_snapshot=copy.deepcopy(workflow.graph),
            status=WorkflowExecutionStatusChoices.STATUS_RUNNING,
            started_by=user,
            started_time=timezone.now(),
        )
        graph = execution.as_graph()
        start_id = graph.start_node_id
        # The start node is a pass-through: completing it (succeeded) resolves its outgoing edges.
        _propagate(execution, graph, user, [(start_id, OUTCOME_SUCCEEDED)])
        _check_completion(execution, graph)
    execution.refresh_from_db()
    return execution


def advance_for_job_result(job_result_id):
    """Advance any workflow waiting on the ``extras.JobResult`` with ``job_result_id``.

    This is the reactive entry point invoked (via a Celery task) from the ``post_save`` signal when a
    JobResult reaches a terminal Celery state. It is idempotent: duplicate deliveries no-op.
    """
    # Resolve outside the per-execution lock so we know which execution to lock.
    node_exec = (
        WorkflowNodeExecution.objects.filter(
            job_result_id=job_result_id,
            status=NodeExecutionStatusChoices.STATUS_RUNNING,
        )
        .select_related("workflow_execution", "job_result")
        .first()
    )
    if node_exec is None:
        return  # No workflow node is waiting on this JobResult (or already advanced).

    execution_id = node_exec.workflow_execution_id
    with transaction.atomic():
        execution = WorkflowExecution.objects.select_for_update().get(pk=execution_id)
        # Re-read the node under the execution lock and re-check it's still RUNNING (idempotency).
        node_exec = (
            WorkflowNodeExecution.objects.select_related("job_result")
            .filter(pk=node_exec.pk, status=NodeExecutionStatusChoices.STATUS_RUNNING)
            .first()
        )
        if node_exec is None:
            return

        outcome = _outcome_from_job_result(node_exec.job_result)
        if outcome is None:
            return  # JobResult not terminal yet (e.g. a stale read); a later delivery will advance.
        node_exec.status = outcome
        node_exec.completed_time = timezone.now()
        node_exec.save()

        if execution.is_terminal:
            return  # e.g. a stop node already ended the run; just finalize the node, no propagation.

        graph = execution.as_graph()
        user = execution.started_by
        _propagate(execution, graph, user, [(node_exec.node_id, outcome)])
        _check_completion(execution, graph)


def fail_stuck_node(node_exec_id):
    """Fail a RUNNING node (e.g. hung past a runtime cap) and advance its workflow.

    Unlike :func:`advance_for_job_result` this does not require a JobResult: the node is failed
    directly (under the execution lock, idempotently) and its outgoing edges are resolved so
    on-failure paths fire and the execution can reach a terminal status. Returns ``True`` if the
    node was failed by this call.
    """
    node_exec = WorkflowNodeExecution.objects.filter(
        pk=node_exec_id,
        status=NodeExecutionStatusChoices.STATUS_RUNNING,
    ).first()
    if node_exec is None:
        return False

    with transaction.atomic():
        execution = WorkflowExecution.objects.select_for_update().get(pk=node_exec.workflow_execution_id)
        node_exec = WorkflowNodeExecution.objects.filter(
            pk=node_exec_id,
            status=NodeExecutionStatusChoices.STATUS_RUNNING,
        ).first()
        if node_exec is None:
            return False

        node_exec.status = NodeExecutionStatusChoices.STATUS_FAILED
        node_exec.completed_time = timezone.now()
        node_exec.save()

        if execution.is_terminal:
            return True  # Node finalized; the execution already ended (e.g. via a stop node).

        graph = execution.as_graph()
        _propagate(execution, graph, execution.started_by, [(node_exec.node_id, OUTCOME_FAILED)])
        _check_completion(execution, graph)
    return True


# -- Propagation ---------------------------------------------------------------------------------


def _propagate(execution, graph, user, completions):
    """Process a worklist of completed nodes, cascading through pass-through nodes and skips.

    ``completions`` is a list of ``(node_id, outcome)`` tuples. Resolving a node's outgoing edges may
    fire downstream job nodes (async — no further completion now) or resolve pass-through/skip nodes
    synchronously, which appends more completions to the worklist.
    """
    while completions:
        node_id, outcome = completions.pop()
        for edge in graph.outgoing_edges(node_id):
            state, created = _resolve_edge(execution, edge, outcome)
            if not created:
                continue  # Already resolved (duplicate); avoid double-processing the target.
            follow_up = _process_target(execution, graph, user, edge, state)
            if follow_up is not None:
                completions.append(follow_up)


def _resolve_edge(execution, edge, outcome):
    """Record an edge as ACTIVATED or SKIPPED for this execution; return ``(state, created)``."""
    if outcome == OUTCOME_SKIPPED:
        state = EdgeActivationStateChoices.STATE_SKIPPED
    else:
        condition = (edge.get("data") or {}).get("condition")
        activated = (
            (condition == TransitionConditionChoices.ON_SUCCESS and outcome == OUTCOME_SUCCEEDED)
            or (condition == TransitionConditionChoices.ON_FAILURE and outcome == OUTCOME_FAILED)
            or (condition == TransitionConditionChoices.ON_COMPLETE)
        )
        state = EdgeActivationStateChoices.STATE_ACTIVATED if activated else EdgeActivationStateChoices.STATE_SKIPPED
    _, created = WorkflowEdgeActivation.objects.get_or_create(
        workflow_execution=execution,
        edge_id=edge["id"],
        defaults={"state": state},
    )
    return state, created


def _process_target(execution, graph, user, edge, state):
    """Given a freshly resolved ``edge``, decide what its target node should do.

    Returns a ``(node_id, outcome)`` follow-up completion when the target resolves synchronously
    (pass-through fire or skip), otherwise ``None``.
    """
    target_id = edge["target"]
    target_type = graph.node_type(target_id)
    activated = state == EdgeActivationStateChoices.STATE_ACTIVATED

    if target_type == WorkflowNodeTypeChoices.TYPE_STOP:
        if activated:
            execution.status = WorkflowExecutionStatusChoices.STATUS_TERMINATED
            execution.completed_time = timezone.now()
            execution.save()
        return None

    if target_type == WorkflowNodeTypeChoices.TYPE_JOIN:
        return _process_join(execution, graph, user, target_id)

    # Ordinary job node (implicit OR-join).
    if activated:
        return _fire_node(execution, graph, user, target_id)
    # Skipped edge: the node is skipped only once every incoming edge has resolved as SKIPPED.
    incoming_ids, states = _incoming_states(execution, graph, target_id)
    all_resolved = all(edge_id in states for edge_id in incoming_ids)
    any_activated = any(state == EdgeActivationStateChoices.STATE_ACTIVATED for state in states.values())
    if all_resolved and not any_activated:
        return _skip_node(execution, target_id)
    return None


def _process_join(execution, graph, user, join_id):
    """Resolve a join (barrier) node once all of its incoming edges have resolved."""
    incoming_ids, states = _incoming_states(execution, graph, join_id)
    if any(edge_id not in states for edge_id in incoming_ids):
        return None  # Still waiting on at least one upstream branch.

    activated_count = sum(1 for s in states.values() if s == EdgeActivationStateChoices.STATE_ACTIVATED)

    node = graph.node(join_id)
    rule = (node.get("data") or {}).get("join_rule", JoinRuleChoices.RULE_ANY)
    if rule == JoinRuleChoices.RULE_ALL:
        should_fire = activated_count == len(incoming_ids)
    else:  # RULE_ANY
        should_fire = activated_count >= 1

    if not should_fire:
        return _skip_node(execution, join_id)

    # A join with a job behaves like a job node; a job-less join is a pass-through.
    if (node.get("data") or {}).get("job_id"):
        return _fire_node(execution, graph, user, join_id)
    return _fire_passthrough(execution, join_id)


def _fire_node(execution, graph, user, node_id):
    """Enqueue the Job for ``node_id`` (first-writer-wins). Returns ``None`` (async)."""
    node = graph.node(node_id)
    node_exec, created = WorkflowNodeExecution.objects.get_or_create(
        workflow_execution=execution,
        node_id=node_id,
        attempt=1,
        defaults={"status": NodeExecutionStatusChoices.STATUS_PENDING},
    )
    if not created:
        return None  # Another activated edge already fired this node.

    data = node.get("data") or {}
    job_id = data.get("job_id")
    job_kwargs = data.get("kwargs") or {}
    try:
        _enqueue_job(node_exec, job_id, job_kwargs, user)
    # pylint: disable-next=broad-exception-caught
    except Exception as exc:  # noqa: BLE001 — surface any enqueue/validation error as a node failure.
        logger.exception("Failed to enqueue job for node %s: %s", node_id, exc)
        node_exec.status = NodeExecutionStatusChoices.STATUS_FAILED
        node_exec.completed_time = timezone.now()
        node_exec.save()
        return (node_id, OUTCOME_FAILED)
    return None


def _coerce_multi_values(job_class, job_kwargs):
    """Wrap scalar values in a list for MultiChoiceVar/MultiObjectVar inputs.

    Workflows saved by older editor builds stored a single string for
    multi-valued variables; the job form rejects those with "Enter a list of
    values."
    """
    from nautobot.extras.jobs import MultiChoiceVar, MultiObjectVar

    coerced = dict(job_kwargs)
    for name, var in job_class._get_vars().items():
        value = coerced.get(name)
        if (
            isinstance(var, (MultiChoiceVar, MultiObjectVar))
            and value is not None
            and not isinstance(value, (list, tuple))
        ):
            coerced[name] = [value]
    return coerced


def _enqueue_job(node_exec, job_id, job_kwargs, user):
    """Validate inputs and enqueue the Job, recording the JobResult on ``node_exec``."""
    from nautobot.extras.models import Job as JobModel
    from nautobot.extras.models import JobResult

    job_model = JobModel.objects.get(pk=job_id)
    job_class = job_model.job_class
    job_kwargs = _coerce_multi_values(job_class, job_kwargs)
    cleaned = job_class.validate_data(job_kwargs)
    job_result = JobResult.enqueue_job(job_model, user, **job_class.serialize_data(cleaned))

    node_exec.job = job_model
    node_exec.job_result = job_result
    node_exec.kwargs = job_kwargs
    node_exec.status = NodeExecutionStatusChoices.STATUS_RUNNING
    node_exec.started_time = timezone.now()
    node_exec.save()


def _fire_passthrough(execution, node_id):
    """Fire a job-less node (e.g. a pure join) as immediately succeeded; returns a follow-up."""
    _, created = WorkflowNodeExecution.objects.get_or_create(
        workflow_execution=execution,
        node_id=node_id,
        attempt=1,
        defaults={
            "status": NodeExecutionStatusChoices.STATUS_SUCCEEDED,
            "started_time": timezone.now(),
            "completed_time": timezone.now(),
        },
    )
    if not created:
        return None
    return (node_id, OUTCOME_SUCCEEDED)


def _skip_node(execution, node_id):
    """Mark ``node_id`` as skipped (first-writer-wins); returns a follow-up to cascade the skip."""
    _, created = WorkflowNodeExecution.objects.get_or_create(
        workflow_execution=execution,
        node_id=node_id,
        attempt=1,
        defaults={
            "status": NodeExecutionStatusChoices.STATUS_SKIPPED,
            "completed_time": timezone.now(),
        },
    )
    if not created:
        return None
    return (node_id, OUTCOME_SKIPPED)


# -- Helpers -------------------------------------------------------------------------------------


def _activations_for(execution, edge_ids):
    """Return ``{edge_id: state}`` for the given edge ids within this execution."""
    rows = WorkflowEdgeActivation.objects.filter(workflow_execution=execution, edge_id__in=edge_ids).values_list(
        "edge_id", "state"
    )
    return dict(rows)


def _incoming_states(execution, graph, node_id):
    """Return ``(incoming_edge_ids, {edge_id: state})`` for ``node_id``'s incoming edges."""
    incoming_ids = [e["id"] for e in graph.incoming_edges(node_id)]
    return incoming_ids, _activations_for(execution, incoming_ids)


def _outcome_from_job_result(job_result):
    """Map a ``JobResult`` status onto a node outcome, or ``None`` if the result is not terminal.

    Returning ``None`` makes the caller defer instead of stamping a still-running job as failed
    (e.g. when a stale row is read before the terminal status committed).
    """
    from nautobot.extras.choices import JobResultStatusChoices

    if job_result is None:
        return OUTCOME_FAILED  # The result row vanished; the node can never succeed.
    if job_result.status not in JobResultStatusChoices.READY_STATES:
        return None
    if job_result.status == JobResultStatusChoices.STATUS_SUCCESS:
        return OUTCOME_SUCCEEDED
    # FAILURE and REVOKED both count as a node failure.
    return OUTCOME_FAILED


def _check_completion(execution, graph):
    """Set the execution's final status once no node remains pending or running."""
    if execution.is_terminal:
        return  # e.g. a stop node already TERMINATED it.

    in_flight = execution.node_executions.filter(
        status__in=[
            NodeExecutionStatusChoices.STATUS_PENDING,
            NodeExecutionStatusChoices.STATUS_RUNNING,
        ]
    ).exists()
    if in_flight:
        return

    # No work remains. A FAILED node with no activated outgoing edge is an unhandled failure.
    states = dict(execution.edge_activations.values_list("edge_id", "state"))
    unhandled = []
    for node_exec in execution.node_executions.filter(status=NodeExecutionStatusChoices.STATUS_FAILED):
        outgoing_ids = [e["id"] for e in graph.outgoing_edges(node_exec.node_id)]
        if not any(states.get(edge_id) == EdgeActivationStateChoices.STATE_ACTIVATED for edge_id in outgoing_ids):
            unhandled.append(node_exec.node_id)

    if unhandled:
        execution.status = WorkflowExecutionStatusChoices.STATUS_FAILED
        if not execution.failure_reason:
            execution.failure_reason = "Node(s) failed with no activated on-failure/on-complete path: " + ", ".join(
                sorted(unhandled)
            )
    else:
        execution.status = WorkflowExecutionStatusChoices.STATUS_COMPLETED
    execution.completed_time = timezone.now()
    execution.save()
