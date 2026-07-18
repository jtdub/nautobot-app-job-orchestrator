// Entry point: read the server-rendered config and mount the editor.
import { createRoot } from "react-dom/client";
import "@xyflow/react/dist/style.css";

import { WorkflowEditor } from "./WorkflowEditor";
import type { EditorConfig } from "./types";

function boot() {
  const mount = document.getElementById("job-orchestrator-editor");
  const configEl = document.getElementById("job-orchestrator-config");
  if (!mount || !configEl?.textContent) return;
  const config = JSON.parse(configEl.textContent) as EditorConfig;
  createRoot(mount).render(<WorkflowEditor config={config} />);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
