// Main drag-and-drop workflow editor built on @xyflow/react.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  addEdge,
  Background,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";

import { nodeTypes } from "./nodes";
import { ConfigDrawer } from "./ConfigDrawer";
import {
  executeWorkflow,
  fetchExecution,
  fetchJobs,
  fetchWorkflow,
  saveGraph,
} from "./api";
import type { Condition, EditorConfig, NautobotJob } from "./types";

const CONDITION_LABELS: Record<Condition, string> = {
  on_success: "success",
  on_failure: "failure",
  on_complete: "complete",
};
const CONDITION_COLORS: Record<Condition, string> = {
  on_success: "#5cb85c",
  on_failure: "#d9534f",
  on_complete: "#777777",
};

let idCounter = 1;
const nextId = (prefix: string) => `${prefix}_${Date.now().toString(36)}_${idCounter++}`;

// React Flow's built-in widgets (Controls, MiniMap) ship light-themed CSS; pick a colorMode that
// matches the active Nautobot theme by reading the page background luminance.
function detectColorMode(): "light" | "dark" {
  try {
    const match = getComputedStyle(document.body).backgroundColor.match(/\d+/g);
    if (match && match.length >= 3) {
      const [r, g, b] = match.map(Number);
      const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
      return luminance < 0.5 ? "dark" : "light";
    }
  } catch {
    /* fall through */
  }
  return "light";
}

function styleEdge(edge: Edge): Edge {
  const condition = ((edge.data?.condition as Condition) || "on_success") as Condition;
  return {
    ...edge,
    label: CONDITION_LABELS[condition],
    labelStyle: { fill: CONDITION_COLORS[condition], fontWeight: 600 },
    style: { stroke: CONDITION_COLORS[condition] },
    animated: condition === "on_failure",
    data: { ...edge.data, condition },
  };
}

function Editor({ config }: { config: EditorConfig }) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [jobs, setJobs] = useState<NautobotJob[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [status, setStatus] = useState<string>("");
  const [executionId, setExecutionId] = useState<string | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const rfRef = useRef<any>(null);
  const colorMode = useMemo(detectColorMode, []);

  // -- Initial load --------------------------------------------------------------------------
  useEffect(() => {
    (async () => {
      try {
        const [jobList, workflow] = await Promise.all([fetchJobs(config), fetchWorkflow(config)]);
        setJobs(jobList);
        const graph = workflow.graph || {};
        setNodes((graph.nodes || []) as Node[]);
        setEdges(((graph.edges || []) as Edge[]).map(styleEdge));
      } catch (err: any) {
        setStatus(`Error: ${err.message}`);
      }
    })();
  }, [config, setNodes, setEdges]);

  const selectedNode = useMemo(
    () => nodes.find((n) => n.id === selectedNodeId) || null,
    [nodes, selectedNodeId],
  );

  // -- Connecting nodes ----------------------------------------------------------------------
  const onConnect = useCallback(
    (connection: Connection) => {
      const edge: Edge = styleEdge({
        ...connection,
        id: nextId("e"),
        data: { condition: "on_success" },
      } as Edge);
      setEdges((eds) => addEdge(edge, eds));
    },
    [setEdges],
  );

  // Cycle an edge's condition on click: success -> failure -> complete -> success.
  const onEdgeClick = useCallback(
    (_: React.MouseEvent, edge: Edge) => {
      const order: Condition[] = ["on_success", "on_failure", "on_complete"];
      const current = (edge.data?.condition as Condition) || "on_success";
      const next = order[(order.indexOf(current) + 1) % order.length];
      setEdges((eds) =>
        eds.map((e) => (e.id === edge.id ? styleEdge({ ...e, data: { ...e.data, condition: next } }) : e)),
      );
    },
    [setEdges],
  );

  // -- Drag-and-drop from the palette --------------------------------------------------------
  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const raw = event.dataTransfer.getData("application/job-orchestrator");
      if (!raw || !rfRef.current) return;
      const payload = JSON.parse(raw);
      const position = rfRef.current.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const id = nextId("n");
      const node: Node =
        payload.kind === "job"
          ? {
              id,
              type: "job",
              position,
              data: { label: payload.name, job_id: payload.jobId, kwargs: {} },
            }
          : {
              id,
              type: payload.kind,
              position,
              data: payload.kind === "join" ? { join_rule: "any" } : {},
            };
      setNodes((nds) => nds.concat(node));
    },
    [setNodes],
  );

  // -- Persisting node config from the drawer ------------------------------------------------
  const updateNodeData = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      setNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, ...patch } } : n)),
      );
    },
    [setNodes],
  );

  // Delete a node and any edges connected to it.
  const deleteNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== nodeId));
      setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
      setSelectedNodeId(null);
    },
    [setNodes, setEdges],
  );

  // Keep the drawer in sync if the selected node is removed via the keyboard.
  const onNodesDelete = useCallback(
    (deleted: Node[]) => {
      if (selectedNodeId && deleted.some((n) => n.id === selectedNodeId)) {
        setSelectedNodeId(null);
      }
    },
    [selectedNodeId],
  );

  // -- Save / Run ----------------------------------------------------------------------------
  const toGraph = useCallback(
    () => ({
      nodes: nodes.map((n) => ({ id: n.id, type: n.type, position: n.position, data: stripRuntime(n.data) })),
      edges: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        data: { condition: (e.data?.condition as Condition) || "on_success" },
      })),
    }),
    [nodes, edges],
  );

  const onSave = useCallback(async () => {
    setStatus("Saving…");
    try {
      await saveGraph(config, toGraph());
      setStatus("Saved.");
    } catch (err: any) {
      setStatus(`Save failed: ${err.message}`);
    }
  }, [config, toGraph]);

  const onRun = useCallback(async () => {
    setStatus("Saving & starting…");
    try {
      await saveGraph(config, toGraph());
      const execution = await executeWorkflow(config);
      setExecutionId(execution.id);
      setStatus(`Running (${execution.status})…`);
    } catch (err: any) {
      setStatus(`Run failed: ${err.message}`);
    }
  }, [config, toGraph]);

  // -- Poll execution for live highlighting --------------------------------------------------
  useEffect(() => {
    if (!executionId) return;
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return; // don't issue another request after the run finished
      try {
        const exec = await fetchExecution(config, executionId);
        if (cancelled) return;
        const byNode = new Map(exec.node_executions.map((ne) => [ne.node_id, ne.status]));
        setNodes((nds) =>
          nds.map((n) => {
            const nodeStatus = byNode.get(n.id);
            // Preserve object identity when nothing changed so memoized nodes skip re-rendering.
            return n.data.status === nodeStatus ? n : { ...n, data: { ...n.data, status: nodeStatus } };
          }),
        );
        setStatus(`Execution: ${exec.status}`);
        if (exec.is_terminal) {
          cancelled = true;
          window.clearInterval(handle);
        }
      } catch {
        /* transient; keep polling */
      }
    };
    const handle = window.setInterval(tick, 2500);
    tick();
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [executionId, config, setNodes]);

  return (
    <div style={{ display: "flex", height: "100%" }}>
      <Palette jobs={jobs} />
      <div ref={wrapperRef} style={{ flex: 1, position: "relative" }}>
        <Toolbar status={status} onSave={onSave} onRun={onRun} />
        <ReactFlow
          colorMode={colorMode}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onEdgeClick={onEdgeClick}
          onNodeClick={(_, node) => setSelectedNodeId(node.id)}
          onNodesDelete={onNodesDelete}
          onInit={(instance) => (rfRef.current = instance)}
          onDrop={onDrop}
          onDragOver={onDragOver}
          deleteKeyCode={["Backspace", "Delete"]}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
      {selectedNode ? (
        <ConfigDrawer
          config={config}
          node={selectedNode}
          onClose={() => setSelectedNodeId(null)}
          onChange={updateNodeData}
          onDelete={deleteNode}
        />
      ) : null}
    </div>
  );
}

function stripRuntime(data: Record<string, unknown>): Record<string, unknown> {
  const { status, ...rest } = data; // never persist the runtime-only status field
  void status;
  return rest;
}

// A draggable palette entry rendered with Nautobot's themed list-group styling.
function PaletteItem({
  label,
  payload,
  title,
  onDragStart,
}: {
  label: React.ReactNode;
  payload: unknown;
  title?: string;
  onDragStart: (event: React.DragEvent, payload: unknown) => void;
}) {
  return (
    // eslint-disable-next-line jsx-a11y/anchor-is-valid
    <a
      href="#"
      className="list-group-item"
      style={{ cursor: "grab" }}
      draggable
      title={title}
      onClick={(e) => e.preventDefault()}
      onDragStart={(e) => onDragStart(e, payload)}
    >
      {label}
    </a>
  );
}

function Palette({ jobs }: { jobs: NautobotJob[] }) {
  const onDragStart = (event: React.DragEvent, payload: unknown) => {
    event.dataTransfer.setData("application/job-orchestrator", JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "move";
  };
  return (
    <div style={{ width: 260, overflowY: "auto", padding: 10 }}>
      <div className="panel panel-default">
        <div className="panel-heading"><strong>Control</strong></div>
        <div className="list-group" style={{ marginBottom: 0 }}>
          <PaletteItem label="● Start" payload={{ kind: "start" }} onDragStart={onDragStart} />
          <PaletteItem label="◆ Join" payload={{ kind: "join" }} onDragStart={onDragStart} />
          <PaletteItem label="■ Stop" payload={{ kind: "stop" }} onDragStart={onDragStart} />
        </div>
      </div>
      <div className="panel panel-default">
        <div className="panel-heading"><strong>Jobs</strong> <span className="badge">{jobs.length}</span></div>
        <div className="list-group" style={{ marginBottom: 0 }}>
          {jobs.map((job) => (
            <PaletteItem
              key={job.id}
              label={job.name}
              title={job.grouping || job.module_name}
              payload={{ kind: "job", jobId: job.id, name: job.name }}
              onDragStart={onDragStart}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function Toolbar({ status, onSave, onRun }: { status: string; onSave: () => void; onRun: () => void }) {
  return (
    <div style={{ position: "absolute", zIndex: 5, top: 8, right: 8, display: "flex", gap: 8, alignItems: "center" }}>
      {status ? <span className="label label-default" style={{ fontSize: 12 }}>{status}</span> : null}
      <button className="btn btn-default btn-sm" onClick={onSave}>Save</button>
      <button className="btn btn-primary btn-sm" onClick={onRun}>Save &amp; Run</button>
    </div>
  );
}

export function WorkflowEditor({ config }: { config: EditorConfig }) {
  return (
    <ReactFlowProvider>
      <Editor config={config} />
    </ReactFlowProvider>
  );
}
