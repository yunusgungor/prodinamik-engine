import { useState, useEffect, useCallback } from "react";
import {
  ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer,
  AreaChart, Area, CartesianGrid, BarChart, Bar, Legend, LineChart, Line
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  AlertCircle, Brain, RefreshCw, Activity, TrendingUp,
  Shield, Zap, Clock, CheckCircle2, XCircle, Play,
  Download, FileText, Cpu
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useWebSocket } from "@/hooks/use-websocket";
import { cn } from "@/lib/utils";

// ── Types ──

interface DriftItem {
  id: string; type: string; severity: string; description: string;
  timestamp: string; run_slug?: string; confidence?: number;
}

interface EmergenceItem {
  id: string; type: string; description: string;
  occurrences: number; affected_runs: number; confidence: number;
  suggested_name?: string;
}

interface RemediPlan {
  id: string; name: string; pattern: string;
  status: string; success_rate: number; cooldown?: number;
}

interface ForecastPoint {
  hour: string; baseline: number; lower: number; upper: number;
}

interface AgentTaskItem {
  task_id: string; task_type: string; interval_seconds: number;
  last_run?: string; next_run?: string; status: string; run_count?: number;
}

// ── Constants ──

const DRIFT_COLORS: Record<string, string> = {
  semantic: "#3b82f6", behavioral: "#f59e0b",
  temporal: "#10b981", structural: "#8b5cf6",
};
const SEVERITY_COLORS: Record<string, string> = {
  low: "text-slate-400 border-slate-500/30 bg-slate-500/10",
  medium: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  high: "text-orange-400 border-orange-500/30 bg-orange-500/10",
  critical: "text-red-400 border-red-500/30 bg-red-500/10",
};

const FORECAST_DATA = Array.from({ length: 24 }, (_, i) => ({
  hour: `+${i}h`,
  baseline: Math.max(0, 70 + Math.sin(i * 0.5) * 15 + Math.random() * 5),
  lower: Math.max(0, 60 + Math.sin(i * 0.5) * 10),
  upper: Math.min(100, 80 + Math.sin(i * 0.5) * 20),
}));

function fmtTime(d: string | undefined): string {
  if (!d) return "—";
  const diff = Date.now() - new Date(d).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

// ── Helpers ──

function getAuth() {
  try {
    const s = localStorage.getItem("pdmk-auth");
    if (!s) return { apiBase: "http://localhost:8000", apiKey: "" };
    const p = JSON.parse(s)?.state;
    return { apiBase: p?.baseUrl || "http://localhost:8000", apiKey: p?.apiKey || "" };
  } catch { return { apiBase: "http://localhost:8000", apiKey: "" }; }
}

async function api(path: string, opts?: RequestInit) {
  const { apiBase, apiKey } = getAuth();
  const h: Record<string, string> = { ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}), ...opts?.headers as Record<string, string> };
  const res = await fetch(`${apiBase}${path}`, { ...opts, headers: { ...h, ...(opts?.body ? { "Content-Type": "application/json" } : {}) } });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text().catch(() => "Unknown")}`);
  return res.json();
}

// ── Component ──

export default function AIDashboardPage() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [driftEvents, setDriftEvents] = useState<DriftItem[]>([]);
  const [driftStats, setDriftStats] = useState<any>(null);
  const [emergenceCandidates, setEmergenceCandidates] = useState<EmergenceItem[]>([]);
  const [remediationPlans, setRemediationPlans] = useState<RemediPlan[]>([]);
  const [agentStatus, setAgentStatus] = useState<any>(null);
  const [agentTasks, setAgentTasks] = useState<AgentTaskItem[]>([]);
  const [forecast, setForecast] = useState<ForecastPoint[]>(FORECAST_DATA);
  const [driftFilter, setDriftFilter] = useState<string>("all");
  const [features, setFeatures] = useState({
    driftDetection: true, predictiveDegradation: true,
    autoRemediation: true, skillEmergence: true, runRecommender: true,
  });

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [drift, stats, emerge, remed, agent, tasks, forecastRes] = await Promise.allSettled([
        api("/api/v1/ai/drift?limit=50"),
        api("/api/v1/ai/drift/stats"),
        api("/api/v1/ai/emergence"),
        api("/api/v1/ai/remediation"),
        api("/api/v1/ai/agent"),
        api("/api/v1/ai/agent/tasks"),
        api("/api/v1/ai/forecast?horizon=24"),
      ]);
      if (drift.status === "fulfilled") setDriftEvents(drift.value);
      if (stats.status === "fulfilled") setDriftStats(stats.value);
      if (emerge.status === "fulfilled") setEmergenceCandidates(emerge.value);
      if (remed.status === "fulfilled") setRemediationPlans(remed.value);
      if (agent.status === "fulfilled") setAgentStatus(agent.value);
      if (tasks.status === "fulfilled") setAgentTasks(tasks.value);
      if (forecastRes.status === "fulfilled") {
        const data = forecastRes.value;
        if (data.points) setForecast(data.points);
      }
    } catch (e) { console.log("AI fetch:", e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  useWebSocket({
    channel: "events",
    onMessage: (data) => {
      if (data.type === "drift" || data.type === "emergence") fetchAll();
    },
  });

  const hasData = driftEvents.length > 0;
  const filteredDrift = driftFilter === "all" ? driftEvents : driftEvents.filter(d => d.type === driftFilter);

  const toggle = (key: keyof typeof features) => {
    setFeatures(f => ({ ...f, [key]: !f[key] }));
    toast({ description: `Feature ${features[key] ? "disabled" : "enabled"}` });
  };

  const seedDrift = async () => {
    try {
      const res = await api("/api/v1/ai/drift/seed?count=5", { method: "POST" });
      toast({ title: "Drift events seeded", description: `${res.seeded} events created` });
      fetchAll();
    } catch { toast({ title: "Failed", variant: "destructive" }); }
  };

  const testRemediation = async (pattern: string) => {
    try {
      await api("/api/v1/ai/remediation/test", {
        method: "POST",
        body: JSON.stringify({ pattern }),
      });
      toast({ title: "Test triggered", description: `Pattern: ${pattern}` });
    } catch { toast({ title: "Failed", variant: "destructive" }); }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <h1 className="text-xl font-bold">AI Grid</h1>
            <Badge variant="outline" className={`text-xs ${hasData ? "text-emerald-400 border-emerald-500/30" : "text-amber-400 border-amber-500/30"}`}>
              {hasData ? "Live" : "Demo"}
            </Badge>
            {hasData && <span className="text-emerald-400 text-[10px]">● {driftEvents.length} events</span>}
          </div>
          <p className="text-sm text-muted-foreground">
            Drift detection · Skill emergence · Auto-remediation · Warm agent · Degradation forecast
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={seedDrift}>
            <Zap className="w-3.5 h-3.5 mr-1.5" />Seed Drift
          </Button>
          <Button variant="outline" size="sm" onClick={fetchAll}>
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Refresh
          </Button>
        </div>
      </div>

      {/* Feature Toggles */}
      <Card className="border-card-border">
        <CardHeader className="pb-2 pt-4 px-4">
          <CardTitle className="text-sm font-medium">AI Grid Modules</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4 grid grid-cols-2 md:grid-cols-5 gap-4">
          {([
            ["driftDetection", "Drift Detection", Activity],
            ["predictiveDegradation", "Degradation Forecast", TrendingUp],
            ["autoRemediation", "Auto-Remediation", Shield],
            ["skillEmergence", "Skill Emergence", Brain],
            ["runRecommender", "Run Recommender", Zap],
          ] as const).map(([key, label, Icon]) => (
            <div key={key} className="flex items-center justify-between gap-2 p-2 rounded-md border border-border/50">
              <div className="flex items-center gap-2">
                <Icon className="w-3.5 h-3.5 text-muted-foreground" />
                <Label className="text-xs text-muted-foreground">{label}</Label>
              </div>
              <Switch
                checked={features[key as keyof typeof features]}
                onCheckedChange={() => toggle(key as keyof typeof features)}
                data-testid={`toggle-${key}`}
              />
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Warm Agent + Task Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Agent Status */}
        <Card className="border-card-border lg:col-span-1">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Cpu className="w-4 h-4 text-muted-foreground" />
              Warm Agent Coordinator
              {agentStatus?.is_running && <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="bg-muted/30 rounded p-2">
                <p className="text-muted-foreground">Status</p>
                <Badge variant="outline" className={`mt-1 text-xs ${agentStatus?.is_running ? "text-emerald-400 border-emerald-500/30" : "text-muted-foreground"}`}>
                  {agentStatus?.is_running ? "Running" : "Stopped"}
                </Badge>
              </div>
              <div className="bg-muted/30 rounded p-2">
                <p className="text-muted-foreground">Uptime</p>
                <p className="font-mono mt-1">{Math.floor((agentStatus?.uptime || 0) / 60)}m</p>
              </div>
              <div className="bg-muted/30 rounded p-2">
                <p className="text-muted-foreground">Success Rate</p>
                <p className="font-mono mt-1 text-emerald-400">{Math.round((agentStatus?.success_rate || 0) * 100)}%</p>
              </div>
              <div className="bg-muted/30 rounded p-2">
                <p className="text-muted-foreground">Failed Tasks</p>
                <p className="font-mono mt-1 text-red-400">{agentStatus?.failed_tasks || 0}</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Agent Tasks */}
        <Card className="border-card-border lg:col-span-2">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-medium">Background Tasks</CardTitle>
          </CardHeader>
          <CardContent className="px-0 pb-0">
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-xs pl-4">Task</TableHead>
                  <TableHead className="text-xs">Type</TableHead>
                  <TableHead className="text-xs">Interval</TableHead>
                  <TableHead className="text-xs">Last</TableHead>
                  <TableHead className="text-xs">Count</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(agentTasks.length > 0 ? agentTasks : [
                  { task_id: "skill-emergence", task_type: "SKILL_EMERGENCE", interval_seconds: 300, last_run: undefined, run_count: 142, status: "running" },
                  { task_id: "health-monitor", task_type: "HEALTH_CHECK", interval_seconds: 60, last_run: undefined, run_count: 4231, status: "running" },
                  { task_id: "drift-persist", task_type: "DRIFT_PERSIST", interval_seconds: 600, last_run: undefined, run_count: 712, status: "idle" },
                  { task_id: "data-collection", task_type: "DATA_COLLECTION", interval_seconds: 1800, last_run: undefined, run_count: 237, status: "idle" },
                ]).map((t: any) => (
                  <TableRow key={t.task_id} className="border-border hover:bg-muted/30">
                    <TableCell className="text-xs font-mono pl-4 text-primary">{t.task_id}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{t.task_type}</TableCell>
                    <TableCell className="text-xs font-mono">{t.interval_seconds < 120 ? `${t.interval_seconds}s` : `${Math.floor(t.interval_seconds / 60)}m`}</TableCell>
                    <TableCell className="text-xs text-muted-foreground">{fmtTime(t.last_run)}</TableCell>
                    <TableCell className="text-xs font-mono">{t.run_count?.toLocaleString()}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <div className={cn("w-1.5 h-1.5 rounded-full", t.status === "running" ? "bg-emerald-400 animate-pulse" : "bg-muted-foreground")} />
                        <span className="text-xs capitalize">{t.status}</span>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      {/* Drift + Forecast */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Drift Events */}
        <Card className="border-card-border">
          <CardHeader className="pb-2 pt-4 px-4">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <Activity className="w-4 h-4 text-muted-foreground" />
                Drift Events
                {driftStats && <Badge variant="outline" className="text-[10px]">{driftStats.total_events} total</Badge>}
              </CardTitle>
              <Select value={driftFilter} onValueChange={setDriftFilter}>
                <SelectTrigger className="h-7 w-28 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all" className="text-xs">All Types</SelectItem>
                  {Object.keys(DRIFT_COLORS).map(t => <SelectItem key={t} value={t} className="text-xs">{t}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </CardHeader>
          <CardContent className="px-2 pb-4">
            {/* Trend chart */}
            {driftStats?.trend_windows && (
              <ResponsiveContainer width="100%" height={60}>
                <BarChart data={driftStats.trend_windows} margin={{ top: 0, right: 10, bottom: 0, left: 10 }}>
                  <Bar dataKey="count" fill="#3b82f6" radius={[2, 2, 0, 0]} />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 11 }} />
                </BarChart>
              </ResponsiveContainer>
            )}
            {/* Drift list */}
            <div className="space-y-0.5 max-h-52 overflow-y-auto mt-1">
              {filteredDrift.slice(0, 15).map((d) => (
                <div key={d.id} className="flex items-center gap-2 px-2 py-1 text-xs border-b border-border/30 last:border-0 hover:bg-muted/20">
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ background: DRIFT_COLORS[d.type] || "#6b7280" }} />
                  <span className="font-mono text-[10px] text-muted-foreground w-16 shrink-0">{d.type}</span>
                  <span className="flex-1 truncate">{d.description}</span>
                  <span className={cn("text-[9px] px-1 py-0.5 rounded border font-medium shrink-0", SEVERITY_COLORS[d.severity] || "text-muted-foreground")}>
                    {d.severity}
                  </span>
                  <span className="text-[9px] text-muted-foreground w-12 text-right shrink-0">{fmtTime(d.timestamp)}</span>
                </div>
              ))}
            </div>
            {/* Type distribution */}
            {driftStats?.type_distribution && (
              <div className="flex flex-wrap gap-2 mt-2 px-2">
                {Object.entries(driftStats.type_distribution).map(([type, count]) => (
                  <div key={type} className="flex items-center gap-1 text-[10px]">
                    <div className="w-2 h-2 rounded-full" style={{ background: DRIFT_COLORS[type] || "#6b7280" }} />
                    <span className="text-muted-foreground">{type}:</span>
                    <span className="font-mono font-medium">{count as number}</span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Forecast */}
        <Card className="border-card-border">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-muted-foreground" />
              Health Score Forecast (24h)
            </CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-4">
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={forecast}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="hour" tick={{ fontSize: 10 }} tickLine={false} interval={5} />
                <YAxis tick={{ fontSize: 10 }} tickLine={false} domain={[0, 100]} />
                <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 11 }} />
                <Area type="monotone" dataKey="upper" stroke="transparent" fill="#3b82f620" name="Upper" />
                <Area type="monotone" dataKey="baseline" stroke="#3b82f6" fill="#3b82f610" strokeWidth={2} name="Forecast" />
                <Area type="monotone" dataKey="lower" stroke="transparent" fill="#ef444420" name="Lower" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Emergence Candidates */}
      <Card className="border-card-border">
        <CardHeader className="pb-2 pt-4 px-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Brain className="w-4 h-4 text-muted-foreground" />
              Skill Emergence Candidates
              {emergenceCandidates.length > 0 && <Badge variant="outline" className="text-xs">{emergenceCandidates.length}</Badge>}
            </CardTitle>
            <Button variant="outline" size="sm" className="h-7 text-xs" onClick={fetchAll}>
              <RefreshCw className="w-3 h-3 mr-1" />Scan
            </Button>
          </div>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          {emergenceCandidates.length === 0 ? (
            <div className="text-center py-8 text-sm text-muted-foreground">
              <Brain className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p>No emergence candidates yet. Run more pipeline iterations to discover patterns.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-xs pl-4">Pattern</TableHead>
                  <TableHead className="text-xs">Type</TableHead>
                  <TableHead className="text-xs">Description</TableHead>
                  <TableHead className="text-xs w-20">Runs</TableHead>
                  <TableHead className="text-xs w-32">Confidence</TableHead>
                  <TableHead className="text-xs w-40">Skill Name</TableHead>
                  <TableHead className="text-xs w-28"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {emergenceCandidates.map((c) => (
                  <TableRow key={c.id} className="border-border hover:bg-muted/30">
                    <TableCell className="text-xs font-mono pl-4 text-primary">{c.id}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px]" style={{ color: DRIFT_COLORS[c.type], borderColor: `${DRIFT_COLORS[c.type]}50` }}>
                        {c.type}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground max-w-64">{c.description}</TableCell>
                    <TableCell className="text-xs text-center font-mono">{c.occurrences} / {c.affected_runs}r</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Progress value={c.confidence * 100} className="h-1.5 flex-1" />
                        <span className={cn("text-xs font-mono w-8", c.confidence >= 0.7 ? "text-emerald-400" : c.confidence >= 0.5 ? "text-amber-400" : "text-muted-foreground")}>
                          {Math.round(c.confidence * 100)}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs font-mono text-muted-foreground">{c.suggested_name ?? "—"}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button variant="ghost" size="sm" className="h-6 text-[10px] px-2 text-emerald-400"
                          onClick={() => toast({ title: "Generate", description: `Generating skill: ${c.suggested_name}` })}>
                          <Download className="w-3 h-3 mr-1" />Generate
                        </Button>
                        <Button variant="ghost" size="sm" className="h-6 text-[10px] px-2" onClick={() => toast({ title: "Promote", description: "Promoted to Tier 2" })}>
                          <TrendingUp className="w-3 h-3 mr-1" />Promote
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Auto-Remediation */}
      <Card className="border-card-border">
        <CardHeader className="pb-2 pt-4 px-4">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <Shield className="w-4 h-4 text-muted-foreground" />
              Auto-Remediation Monitor
              {remediationPlans.length > 0 && <Badge variant="outline" className="text-xs">{remediationPlans.length} plans</Badge>}
            </CardTitle>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-4 space-y-2">
          {(remediationPlans.length === 0 ? [
            { id: "plan-001", name: "LLM Fallback Cascade", pattern: "consecutive_llm_failures", status: "active", success_rate: 0.83 },
            { id: "plan-002", name: "Memory Pressure Relief", pattern: "memory_pressure", status: "standby", success_rate: 0.91, cooldown: 1800 },
            { id: "plan-003", name: "Rejection Loop Breaker", pattern: "hitl_repeated_rejection", status: "active", success_rate: 0.76 },
            { id: "plan-004", name: "Event Store Compaction", pattern: "event_store_full", status: "cooldown", success_rate: 0.97, cooldown: 600 },
          ] : remediationPlans).map((plan) => (
            <div key={plan.id} className="flex items-center gap-3 border border-border rounded-md px-3 py-2.5 hover:bg-muted/20">
              <div className={cn("w-2 h-2 rounded-full shrink-0",
                plan.status === "active" ? "bg-emerald-400 animate-pulse" :
                plan.status === "cooldown" ? "bg-amber-400" : "bg-muted-foreground"
              )} />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium">{plan.name}</p>
                <p className="text-xs text-muted-foreground font-mono">{plan.pattern}</p>
              </div>
              <Badge variant="outline" className="text-xs capitalize">{plan.status}</Badge>
              {plan.cooldown ? (
                <div className="text-right w-20">
                  <p className="text-[10px] text-muted-foreground">Cooldown</p>
                  <p className="text-xs font-mono">{Math.floor(plan.cooldown / 60)}m</p>
                </div>
              ) : (
                <div className="text-right w-20">
                  <p className="text-[10px] text-muted-foreground">Success rate</p>
                  <p className="text-sm font-mono font-medium">{Math.round(plan.success_rate * 100)}%</p>
                </div>
              )}
              <Button variant="ghost" size="sm" className="h-7 text-[10px] px-2"
                onClick={() => testRemediation(plan.pattern)}>
                <Play className="w-3 h-3 mr-1" />Test
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Drift Stats Summary */}
      {driftStats && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="bg-card border border-card-border rounded-md p-3">
            <p className="text-[10px] text-muted-foreground uppercase">Total Drift Events</p>
            <p className="text-xl font-bold font-mono">{driftStats.total_events}</p>
          </div>
          <div className="bg-card border border-card-border rounded-md p-3">
            <p className="text-[10px] text-muted-foreground uppercase">Unique Runs</p>
            <p className="text-xl font-bold font-mono">{driftStats.unique_runs || "—"}</p>
          </div>
          <div className="bg-card border border-card-border rounded-md p-3">
            <p className="text-[10px] text-muted-foreground uppercase">Agent Status</p>
            <p className="text-xl font-bold font-mono">{agentStatus?.is_running ? "Running" : "Idle"}</p>
          </div>
          <div className="bg-card border border-card-border rounded-md p-3">
            <p className="text-[10px] text-muted-foreground uppercase">Forecast Trend</p>
            <p className="text-xl font-bold font-mono">{forecast.length > 0 ? `${forecast[forecast.length-1].baseline.toFixed(0)}%` : "—"}</p>
          </div>
        </div>
      )}
    </div>
  );
}
