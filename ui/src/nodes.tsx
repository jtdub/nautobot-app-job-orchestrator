// Custom React Flow node renderers for the workflow canvas.
import React from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { NodeData } from "./types";

// Map a runtime node-execution status to a border colour for live highlighting.
const STATUS_COLORS: Record<string, string> = {
  pending: "#b0b0b0",
  running: "#2b8cef",
  succeeded: "#3abc54",
  failed: "#d9534f",
  skipped: "#999999",
};

function statusColor(status?: string): string | undefined {
  return status ? STATUS_COLORS[status] : undefined;
}

function baseStyle(data: NodeData, fallback: string): React.CSSProperties {
  const color = statusColor(data.status);
  return {
    padding: "8px 12px",
    borderRadius: 6,
    border: `2px solid ${color ?? fallback}`,
    background: "#ffffff",
    color: "#222222", // explicit: Nautobot dark theme would otherwise make text white-on-white
    fontSize: 12,
    minWidth: 120,
    textAlign: "center",
    boxShadow: data.status === "running" ? "0 0 0 3px rgba(43,140,239,0.25)" : undefined,
  };
}

export function JobNode({ data }: NodeProps) {
  const d = data as NodeData;
  return (
    <div style={baseStyle(d, "#5b9bd5")}>
      <Handle type="target" position={Position.Top} />
      <strong>{d.label || "Job"}</strong>
      {d.status ? <div style={{ color: "#666", marginTop: 4 }}>{d.status}</div> : null}
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export function StartNode({ data }: NodeProps) {
  const d = data as NodeData;
  return (
    <div style={{ ...baseStyle(d, "#5cb85c"), borderRadius: 20 }}>
      <strong>Start</strong>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export function JoinNode({ data }: NodeProps) {
  const d = data as NodeData;
  return (
    <div style={{ ...baseStyle(d, "#f0ad4e") }}>
      <Handle type="target" position={Position.Top} />
      <strong>Join</strong>
      <div style={{ color: "#666", marginTop: 4 }}>{(d.join_rule || "any").toUpperCase()}</div>
      <Handle type="source" position={Position.Bottom} />
    </div>
  );
}

export function StopNode({ data }: NodeProps) {
  const d = data as NodeData;
  return (
    <div style={{ ...baseStyle(d, "#d9534f"), borderRadius: 20 }}>
      <Handle type="target" position={Position.Top} />
      <strong>Stop</strong>
    </div>
  );
}

export const nodeTypes = {
  start: StartNode,
  job: JobNode,
  join: JoinNode,
  stop: StopNode,
};
