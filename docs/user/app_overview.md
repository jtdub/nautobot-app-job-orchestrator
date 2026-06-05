# App Overview

This document provides an overview of the Job Orchestrator App including critical information and
important considerations when applying it to your Nautobot environment.

!!! note
    Throughout this documentation, the terms "app" and "plugin" will be used interchangeably.

## Description

Job Orchestrator lets you compose existing Nautobot Jobs into **visual workflows**. On a
drag-and-drop canvas you add Jobs as nodes, connect them with **conditional transitions**, and run
the resulting graph while watching live per-node status.

Each connection (edge) carries a condition that decides when it fires based on the source node's
outcome:

- **on success** — fire when the source Job succeeds
- **on failure** — fire when the source Job fails
- **on complete** — fire when the source Job finishes, regardless of outcome

The graph supports:

- **Fan-out** — one node triggering several successors in parallel.
- **Fan-in / join** — a barrier node that waits for multiple branches and then fires using an
  `ANY` (at least one branch succeeded) or `ALL` (every branch succeeded) rule.
- **Stop** — terminate the whole run from any branch.

## How it works

- A **Workflow** stores the canvas graph (nodes, edges, positions) as a single JSON document.
- Running a workflow creates a **WorkflowExecution** with an immutable snapshot of the graph, so
  in-flight runs are unaffected by later edits.
- The engine reacts to each Job finishing (via a `JobResult` signal) and advances the graph using
  **edge-activation propagation** — every edge resolves exactly once, which keeps fan-in joins
  deadlock-free.
- A schedulable **Workflow Reconciler** job is provided as a safety net to recover any run that
  missed an advance (e.g. a worker restart) or whose node hung.

## Nautobot Features Used

- **Jobs / JobResult / Celery** — the orchestrator runs existing Nautobot Jobs and reacts to their
  completion; it adds the *Workflow Reconciler* job.
- **Models** — `Workflow`, `WorkflowExecution`, `WorkflowNodeExecution`, `WorkflowEdgeActivation`
  (change logging, custom fields, GraphQL, and REST API come from the standard base classes).
- **UI** — a custom React Flow canvas embedded in a Nautobot page, plus standard list/detail views
  and an "Automation › Job Orchestrator" navigation group.
- **REST API** — `workflows` (with an `execute` action) and `workflow-executions` (for status
  polling). The canvas reuses core `extras/jobs/<id>/variables/` to render per-Job input forms.

## First-run / build steps

Two artifacts are generated rather than committed by hand:

1. **Database migrations** — generate them once after install:
   ```bash
   invoke makemigrations
   ```
2. **The editor bundle** — build the React Flow canvas (requires Node.js/npm on the host):
   ```bash
   invoke build-ui      # or: cd ui && npm install && npm run build
   ```
   This writes `job_orchestrator/static/job_orchestrator/js/editor.bundle.{js,css}`.

## Authors and Maintainers

- James Williams (@jtdub)
