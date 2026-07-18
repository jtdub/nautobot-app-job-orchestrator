// Thin REST client for the editor. All calls go through Nautobot's session-authenticated API.

import type { EditorConfig, ExecutionState, NautobotJob } from "./types";

function headers(config: EditorConfig): Record<string, string> {
  return {
    "Content-Type": "application/json",
    Accept: "application/json",
    "X-CSRFToken": config.csrfToken,
  };
}

export async function fetchJobs(config: EditorConfig): Promise<NautobotJob[]> {
  // Page through the job list; only enabled, runnable jobs are useful on the canvas.
  const results: NautobotJob[] = [];
  let url: string | null = `${config.urls.jobs}?limit=0`;
  while (url) {
    const resp = await fetch(url, { headers: headers(config), credentials: "same-origin" });
    if (!resp.ok) throw new Error(`Failed to load jobs (${resp.status})`);
    const page = await resp.json();
    results.push(...(page.results ?? []));
    url = page.next;
  }
  return results.filter(
    (j) => j.enabled !== false && !j.is_job_hook_receiver && !j.is_job_button_receiver,
  );
}

export async function fetchJobVariables(config: EditorConfig, jobId: string): Promise<any[]> {
  const url = `${config.urls.jobs}${jobId}/variables/`;
  const resp = await fetch(url, { headers: headers(config), credentials: "same-origin" });
  if (!resp.ok) throw new Error(`Failed to load job variables (${resp.status})`);
  return resp.json();
}

export async function fetchWorkflow(config: EditorConfig): Promise<any> {
  const resp = await fetch(config.urls.workflow, {
    headers: headers(config),
    credentials: "same-origin",
  });
  if (!resp.ok) throw new Error(`Failed to load workflow (${resp.status})`);
  return resp.json();
}

export async function saveGraph(config: EditorConfig, graph: unknown): Promise<void> {
  const resp = await fetch(config.urls.workflow, {
    method: "PATCH",
    headers: headers(config),
    credentials: "same-origin",
    body: JSON.stringify({ graph }),
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`Save failed (${resp.status}): ${detail}`);
  }
}

export async function executeWorkflow(config: EditorConfig): Promise<ExecutionState> {
  const resp = await fetch(config.urls.execute, {
    method: "POST",
    headers: headers(config),
    credentials: "same-origin",
    body: "{}",
  });
  if (!resp.ok) {
    const detail = await resp.text();
    throw new Error(`Execute failed (${resp.status}): ${detail}`);
  }
  return resp.json();
}

export async function fetchExecution(config: EditorConfig, executionId: string): Promise<ExecutionState> {
  const url = `${config.urls.executionBase}${executionId}/`;
  const resp = await fetch(url, { headers: headers(config), credentials: "same-origin" });
  if (!resp.ok) throw new Error(`Failed to poll execution (${resp.status})`);
  return resp.json();
}
