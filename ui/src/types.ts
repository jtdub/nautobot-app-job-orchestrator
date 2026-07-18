// Shared types for the workflow editor.

export type NodeType = "start" | "job" | "join" | "stop";
export type Condition = "on_success" | "on_failure" | "on_complete";
export type JoinRule = "any" | "all";

export interface EditorConfig {
  workflowId: string;
  workflowName: string;
  csrfToken: string;
  urls: {
    jobs: string;
    workflow: string;
    execute: string;
    executionBase: string;
  };
}

// A Nautobot Job as returned by /api/extras/jobs/.
export interface NautobotJob {
  id: string;
  name: string;
  grouping?: string;
  module_name?: string;
  job_class_name?: string;
  enabled?: boolean;
  // Receivers are not free-form runnable; we filter them out of the palette.
  is_job_hook_receiver?: boolean;
  is_job_button_receiver?: boolean;
}

// Node `data` payload persisted in the graph document.
export interface NodeData {
  label?: string;
  job_id?: string;
  kwargs?: Record<string, unknown>;
  join_rule?: JoinRule;
  // Runtime-only, populated while polling an execution (not persisted).
  status?: string;
  [key: string]: unknown;
}

export interface EdgeData {
  condition: Condition;
  [key: string]: unknown;
}

// Execution state returned by /workflow-executions/<id>/.
export interface ExecutionState {
  id: string;
  status: string;
  // Authoritative terminal flag from the backend (WorkflowExecution.is_terminal).
  is_terminal: boolean;
  node_executions: Array<{ node_id: string; status: string; job_result: string | null }>;
}
