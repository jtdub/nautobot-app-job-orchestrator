// Side panel for configuring a selected node:
//  - job nodes: render input fields from the Job's /variables/ schema, bound to data.kwargs
//  - join nodes: pick the join rule (ANY/ALL)
import React, { useEffect, useState } from "react";
import type { Node } from "@xyflow/react";
import { fetchJobVariables } from "./api";
import type { EditorConfig, JoinRule, NodeData } from "./types";

interface JobVar {
  name: string;
  type: string;
  label?: string;
  help_text?: string;
  required?: boolean;
  default?: unknown;
  choices?: Array<[string, string]>;
}

interface Props {
  config: EditorConfig;
  node: Node;
  onClose: () => void;
  onChange: (nodeId: string, patch: Record<string, unknown>) => void;
  onDelete: (nodeId: string) => void;
}

export function ConfigDrawer({ config, node, onClose, onChange, onDelete }: Props) {
  const data = node.data as NodeData;
  const [vars, setVars] = useState<JobVar[] | null>(null);
  const [error, setError] = useState<string>("");

  useEffect(() => {
    setVars(null);
    setError("");
    if (node.type === "job" && data.job_id) {
      fetchJobVariables(config, data.job_id)
        .then((v) => setVars(v as JobVar[]))
        .catch((e) => setError(e.message));
    }
  }, [config, node.id, node.type, data.job_id]);

  const setKwarg = (name: string, value: unknown) => {
    onChange(node.id, { kwargs: { ...(data.kwargs || {}), [name]: value } });
  };

  const drawer: React.CSSProperties = {
    width: 340,
    overflowY: "auto",
    padding: 10,
    // theme-neutral divider; no hardcoded background/text so it inherits the active Nautobot theme
    borderLeft: "1px solid rgba(128,128,128,0.3)",
  };

  return (
    <div style={drawer}>
      <div className="panel panel-default" style={{ marginBottom: 0 }}>
        <div
          className="panel-heading"
          style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}
        >
          <strong style={{ textTransform: "capitalize" }}>{data.label || node.type}</strong>
          <button className="btn btn-default btn-xs" onClick={onClose} title="Close">✕</button>
        </div>
        <div className="panel-body">
          {node.type === "join" ? (
            <div className="form-group">
              <label className="control-label">Join rule</label>
              <select
                className="form-control"
                value={(data.join_rule as JoinRule) || "any"}
                onChange={(e) => onChange(node.id, { join_rule: e.target.value })}
              >
                <option value="any">Any — fire if at least one branch activated</option>
                <option value="all">All — fire only if every branch activated</option>
              </select>
            </div>
          ) : null}

          {node.type === "job" ? (
            <>
              <div className="form-group">
                <label className="control-label">Label</label>
                <input
                  className="form-control"
                  value={data.label || ""}
                  onChange={(e) => onChange(node.id, { label: e.target.value })}
                />
              </div>
              <h5>Job inputs</h5>
              {error ? <div className="text-danger">{error}</div> : null}
              {vars === null && !error ? <div className="text-muted">Loading…</div> : null}
              {vars?.length === 0 ? <div className="text-muted">This job has no inputs.</div> : null}
              {vars?.map((v) => (
                <div key={v.name} className="form-group">
                  <label className="control-label">
                    {v.label || v.name}
                    {v.required ? <span className="text-danger"> *</span> : null}
                  </label>
                  <VarInput
                    variable={v}
                    value={(data.kwargs || {})[v.name]}
                    onChange={(value) => setKwarg(v.name, value)}
                  />
                  {v.help_text ? <p className="help-block" style={{ marginTop: 4 }}>{v.help_text}</p> : null}
                </div>
              ))}
            </>
          ) : null}

          <hr />
          <button className="btn btn-danger btn-sm btn-block" onClick={() => onDelete(node.id)}>
            <span className="mdi mdi-trash-can-outline" aria-hidden="true" /> Delete node
          </button>
          <p className="help-block" style={{ marginTop: 8 }}>
            Tip: you can also select any node or connection on the canvas and press Delete / Backspace.
          </p>
        </div>
      </div>
    </div>
  );
}

function VarInput({
  variable,
  value,
  onChange,
}: {
  variable: JobVar;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const multiValued = variable.type === "MultiChoiceVar" || variable.type === "MultiObjectVar";
  if (variable.choices && variable.choices.length) {
    if (multiValued) {
      const selected = Array.isArray(value) ? (value as string[]) : value ? [String(value)] : [];
      const toggle = (val: string, checked: boolean) =>
        onChange(checked ? [...selected, val] : selected.filter((v) => v !== val));
      return (
        <div>
          {variable.choices.map(([val, label]) => (
            <div className="checkbox" key={val} style={{ marginTop: 2, marginBottom: 2 }}>
              <label>
                <input
                  type="checkbox"
                  checked={selected.includes(val)}
                  onChange={(e) => toggle(val, e.target.checked)}
                />{" "}
                {label}
              </label>
            </div>
          ))}
        </div>
      );
    }
    return (
      <select className="form-control" value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
        <option value="">—</option>
        {variable.choices.map(([val, label]) => (
          <option key={val} value={val}>{label}</option>
        ))}
      </select>
    );
  }
  if (variable.type === "BooleanVar") {
    return <input type="checkbox" checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />;
  }
  if (variable.type === "IntegerVar") {
    return (
      <input
        type="number"
        className="form-control"
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
    );
  }
  // ObjectVar/MultiObjectVar are stored as PK strings entered by the user for the MVP;
  // a future enhancement is a model-aware picker driven by variable.model.
  if (multiValued) {
    return <MultiValueTextInput value={value} onChange={onChange} />;
  }
  return (
    <input
      className="form-control"
      value={value === undefined || value === null ? "" : String(value)}
      onChange={(e) => onChange(e.target.value)}
      placeholder={variable.type === "ObjectVar" ? "object UUID/PK" : ""}
    />
  );
}

// Free-text entry for MultiObjectVar without choices: comma-separated PKs, stored as a list.
// Local text state so typing a trailing comma isn't eaten by the split/join round-trip.
function MultiValueTextInput({
  value,
  onChange,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const [text, setText] = useState(() =>
    Array.isArray(value) ? (value as string[]).join(", ") : String(value ?? ""),
  );
  return (
    <input
      className="form-control"
      value={text}
      onChange={(e) => {
        setText(e.target.value);
        onChange(
          e.target.value
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        );
      }}
      placeholder="comma-separated UUIDs/PKs"
    />
  );
}
