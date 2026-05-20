import { useState, useEffect } from "react";
import { FileUp, FileDown, CheckCircle2, Save, Plus, GitBranch } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/hooks/use-toast";
import { cn } from "@/lib/utils";

interface ProfileState {
  name: string;
  type: string;
  x?: number;
  y?: number;
}

interface ProfileTransition {
  from_state: string;
  to_state: string;
  label?: string;
}

const PROFILE_STATES: Record<string, { name: string; type: string }[]> = {
  software: [
    { name: "spec", type: "initial" },
    { name: "prototyping", type: "intermediate" },
    { name: "iteration", type: "intermediate" },
    { name: "review", type: "pause" },
    { name: "release", type: "terminal" },
  ],
  content: [
    { name: "captured", type: "initial" },
    { name: "decide_route", type: "intermediate" },
    { name: "idea_review", type: "intermediate" },
    { name: "brief_ready", type: "intermediate" },
    { name: "drafting", type: "intermediate" },
    { name: "verification", type: "intermediate" },
    { name: "draft_review", type: "pause" },
    { name: "approved", type: "intermediate" },
    { name: "published", type: "pause" },
    { name: "archived", type: "terminal" },
  ],
  haber: [
    { name: "captured", type: "initial" },
    { name: "fact_checking", type: "intermediate" },
    { name: "cross_verified", type: "intermediate" },
    { name: "published", type: "pause" },
    { name: "correction_needed", type: "pause" },
  ],
  devcycle: [
    { name: "brief", type: "initial" },
    { name: "prototyping", type: "intermediate" },
    { name: "development", type: "intermediate" },
    { name: "drift_resolution", type: "intermediate" },
    { name: "review", type: "pause" },
    { name: "blocked", type: "pause" },
  ],
  research: [
    { name: "topic_selected", type: "initial" },
    { name: "literature_review", type: "intermediate" },
    { name: "hypothesis", type: "intermediate" },
    { name: "experiment_design", type: "intermediate" },
    { name: "paper_draft", type: "intermediate" },
    { name: "peer_review", type: "pause" },
  ],
  design: [
    { name: "brief", type: "initial" },
    { name: "research", type: "intermediate" },
    { name: "sketch", type: "intermediate" },
    { name: "wireframe", type: "intermediate" },
    { name: "mockup", type: "intermediate" },
    { name: "prototype", type: "intermediate" },
    { name: "review", type: "pause" },
  ],
};

const PROFILE_EDGES: Record<string, { from: string; to: string; label: string }[]> = {
  software: [
    { from: "spec", to: "prototyping", label: "start" },
    { from: "prototyping", to: "iteration", label: "ready" },
    { from: "iteration", to: "iteration", label: "iterate" },
    { from: "iteration", to: "review", label: "done" },
    { from: "review", to: "release", label: "approved" },
    { from: "review", to: "iteration", label: "changes" },
  ],
  content: [
    { from: "captured", to: "decide_route", label: "captured" },
    { from: "decide_route", to: "idea_review", label: "route" },
    { from: "idea_review", to: "brief_ready", label: "approved" },
    { from: "brief_ready", to: "drafting", label: "brief_ok" },
    { from: "drafting", to: "verification", label: "draft_done" },
    { from: "verification", to: "draft_review", label: "verified" },
    { from: "draft_review", to: "approved", label: "approved" },
    { from: "draft_review", to: "drafting", label: "changes" },
    { from: "approved", to: "published", label: "publish" },
    { from: "published", to: "archived", label: "archive" },
  ],
  haber: [
    { from: "captured", to: "fact_checking", label: "check" },
    { from: "fact_checking", to: "cross_verified", label: "verified" },
    { from: "cross_verified", to: "published", label: "publish" },
    { from: "published", to: "correction_needed", label: "error" },
    { from: "correction_needed", to: "fact_checking", label: "recheck" },
  ],
  devcycle: [
    { from: "brief", to: "prototyping", label: "brief_ok" },
    { from: "prototyping", to: "development", label: "prototype" },
    { from: "development", to: "drift_resolution", label: "drift" },
    { from: "drift_resolution", to: "development", label: "fixed" },
    { from: "development", to: "review", label: "done" },
    { from: "review", to: "blocked", label: "block" },
    { from: "review", to: "development", label: "changes" },
  ],
};

const NODE_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  initial: { fill: "#052e16", stroke: "#10b981", text: "#10b981" },
  intermediate: { fill: "#0f172a", stroke: "#3b82f6", text: "#3b82f6" },
  terminal: { fill: "#1e1b1b", stroke: "#6b7280", text: "#9ca3af" },
  pause: { fill: "#261200", stroke: "#f59e0b", text: "#fbbf24" },
};

const SVG_W = 800;
const SVG_H = 400;
const NODE_W = 105;
const NODE_H = 34;

// Calculate node positions based on grid
function getNodePositions(states: ProfileState[]): ProfileState[] {
  const cols = Math.ceil(Math.sqrt(states.length));
  const spacingX = 130;
  const spacingY = 80;
  const startX = 40;
  const startY = 60;

  return states.map((s, i) => ({
    ...s,
    x: startX + (i % cols) * spacingX,
    y: startY + Math.floor(i / cols) * spacingY,
  }));
}

function getCenter(node: { x?: number; y?: number }) {
  return { x: (node.x ?? 0) + NODE_W / 2, y: (node.y ?? 0) + NODE_H / 2 };
}

function Arrow({ from, to, label }: { from: { x: number; y: number }; to: { x: number; y: number }; label: string }) {
  const mx = (from.x + to.x) / 2;
  const my = (from.y + to.y) / 2;
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const len = Math.sqrt(dx * dx + dy * dy) || 1;
  const nx = dx / len;
  const ny = dy / len;
  const ex = to.x - nx * (NODE_W / 2 + 4);
  const ey = to.y - ny * (NODE_H / 2 + 4);
  const sx = from.x + nx * (NODE_W / 2 + 4);
  const sy = from.y + ny * (NODE_H / 2 + 4);

  return (
    <g>
      <defs>
        <marker id={`ah-${label}`} markerWidth="6" markerHeight="4" refX="5" refY="2" orient="auto">
          <polygon points="0 0, 6 2, 0 4" fill="#475569" />
        </marker>
      </defs>
      <line x1={sx} y1={sy} x2={ex} y2={ey} stroke="#334155" strokeWidth={1.5} markerEnd={`url(#ah-${label})`} />
      <text x={mx} y={my - 6} textAnchor="middle" fontSize={9} fill="#64748b">{label}</text>
    </g>
  ) as any;
}

export default function StateMachinePage() {
  const { toast } = useToast();
  const [profile, setProfile] = useState("software");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const states = (PROFILE_STATES[profile] || []).map((s) => ({ ...s }));
  const edges = (PROFILE_EDGES[profile] || []);
  const positioned = getNodePositions(states);
  const nodeMap = Object.fromEntries(positioned.map((n) => [n.name, n]));

  const selectedNode = positioned.find((n) => n.name === selectedId);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-xl font-bold">State Machine Editor</h1>
            <p className="text-sm text-muted-foreground">Visual pipeline editor — select a profile</p>
          </div>
          <Select value={profile} onValueChange={(v) => { setProfile(v); setSelectedId(null); }}>
            <SelectTrigger className="w-36 h-8 text-xs" data-testid="select-profile">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.keys(PROFILE_STATES).map((p) => (
                <SelectItem key={p} value={p} className="text-xs capitalize">{p}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => toast({ description: "Export YAML — available with engine connection." })}>
            <FileDown className="w-3.5 h-3.5 mr-1.5" />Export
          </Button>
          <Button size="sm" onClick={() => toast({ description: "Save — available with engine connection." })}>
            <Save className="w-3.5 h-3.5 mr-1.5" />Save
          </Button>
        </div>
      </div>

      <div className="flex gap-4">
        {/* Canvas */}
        <div className="flex-1 bg-card border border-card-border rounded-lg overflow-hidden">
          <div className="border-b border-border px-3 py-2 flex items-center gap-2 text-xs text-muted-foreground">
            <GitBranch className="w-3.5 h-3.5" />
            <span>{profile} profile — {positioned.length} states, {edges.length} transitions</span>
            {edges.filter(e => e.from === e.to).length > 0 && (
              <Badge variant="outline" className="text-[10px]">self-loop</Badge>
            )}
          </div>
          <div className="overflow-auto">
            <svg width={SVG_W} height={SVG_H} className="select-none">
              {/* Edges */}
              {edges.map((edge, i) => {
                const fromNode = nodeMap[edge.from];
                const toNode = nodeMap[edge.to];
                if (!fromNode || !toNode) return null;

                // Self-loop rendering
                if (edge.from === edge.to) {
                  const cx = (fromNode.x ?? 0) + NODE_W / 2;
                  const cy = (fromNode.y ?? 0);
                  return (
                    <g key={i}>
                      <ellipse cx={cx} cy={cy - 8} rx={22} ry={12} fill="none" stroke="#334155" strokeWidth={1.5} />
                      <text x={cx + 28} y={cy - 14} fontSize={9} fill="#64748b">{edge.label}</text>
                    </g>
                  ) as any;
                }

                const from = getCenter(fromNode);
                const to = getCenter(toNode);
                return <Arrow key={i} from={from} to={to} label={edge.label} />;
              })}
              {/* Nodes */}
              {positioned.map((node) => {
                const colors = NODE_COLORS[node.type] ?? NODE_COLORS.intermediate;
                const isSelected = selectedId === node.name;
                return (
                  <g key={node.name} onClick={() => setSelectedId(node.name === selectedId ? null : node.name)} className="cursor-pointer">
                    <rect
                      x={node.x} y={node.y}
                      width={NODE_W} height={NODE_H}
                      rx={node.type === "initial" ? 17 : 6}
                      fill={colors.fill}
                      stroke={isSelected ? "#f8fafc" : colors.stroke}
                      strokeWidth={isSelected ? 2 : 1.5}
                    />
                    <text
                      x={(node.x ?? 0) + NODE_W / 2} y={(node.y ?? 0) + NODE_H / 2 + 4}
                      textAnchor="middle" fontSize={11} fontFamily="monospace"
                      fill={colors.text} fontWeight={isSelected ? "bold" : "normal"}
                    >
                      {node.name}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>
        </div>

        {/* Properties panel */}
        <div className="w-64 bg-card border border-card-border rounded-lg p-4 shrink-0">
          <h3 className="text-sm font-semibold mb-3">
            {selectedNode ? "State Properties" : "Properties"}
          </h3>
          {!selectedNode ? (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">Click a state node to view its properties.</p>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Profile Info</p>
                <p className="text-sm font-mono capitalize mt-1">{profile}</p>
                <p className="text-xs text-muted-foreground mt-1">{positioned.length} states · {edges.length} transitions</p>
              </div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">State Types</p>
                {["initial", "intermediate", "pause", "terminal"].map((t) => {
                  const c = NODE_COLORS[t];
                  return (
                    <div key={t} className="flex items-center gap-2 mt-1 text-xs">
                      <div className="w-3 h-3 rounded-sm border" style={{ background: c.fill, borderColor: c.stroke }} />
                      <span className="capitalize text-muted-foreground">{t}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Name</p>
                <p className="text-sm font-mono font-medium">{selectedNode.name}</p>
              </div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Type</p>
                <Badge variant="outline" className="text-xs capitalize">{selectedNode.type}</Badge>
              </div>
              <div>
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Outgoing Transitions</p>
                <div className="space-y-1 mt-1">
                  {edges.filter((e) => e.from === selectedNode.name).map((e, i) => (
                    <div key={i} className="text-xs flex items-center gap-1 text-muted-foreground">
                      <span className="font-mono text-primary">{e.label}</span>
                      <span>→</span>
                      <span className="font-mono">{e.to}</span>
                    </div>
                  ))}
                  {edges.filter((e) => e.from === selectedNode.name).length === 0 && (
                    <p className="text-xs text-muted-foreground">None (terminal state)</p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
