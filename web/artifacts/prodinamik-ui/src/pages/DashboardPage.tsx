import { useEffect, useState } from "react";
import { Link } from "wouter";
import {
  Activity, AlertTriangle, CheckCircle2, Info, Play, TrendingUp,
  DollarSign, Clock, Zap, RefreshCw, Plus, Wifi, WifiOff,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { useGetMetrics, useHealthCheck } from "@workspace/api-client-react";
import { useWebSocket } from "@/hooks/use-websocket";
import { useAuthStore } from "@/store/auth";
import { MOCK_METRICS, MOCK_BUDGET, MOCK_ALERTS } from "@/lib/mock-data";
import { formatDistanceToNow } from "date-fns";
import CreateRunDialog from "@/components/runs/CreateRunDialog";
import { cn } from "@/lib/utils";

const STATE_COLORS: Record<string, string> = {
  initial: "#10b981",
  development: "#3b82f6",
  planning: "#6366f1",
  testing: "#8b5cf6",
  review: "#f59e0b",
  deploy: "#f97316",
  done: "#6b7280",
  error: "#ef4444",
  paused: "#f59e0b",
  cancelled: "#6b7280",
  spec: "#6366f1",
  prototyping: "#3b82f6",
  iteration: "#8b5cf6",
  release: "#10b981",
  captured: "#f59e0b",
  decide_route: "#f97316",
  idea_review: "#ec4899",
  brief_ready: "#14b8a6",
  drafting: "#3b82f6",
  verification: "#8b5cf6",
  draft_review: "#f59e0b",
  approved: "#10b981",
  published: "#6b7280",
  archived: "#6b7280",
  fact_checking: "#f97316",
  cross_verified: "#14b8a6",
  correction_needed: "#ef4444",
  blocked: "#ef4444",
  peer_review: "#f59e0b",
};

const PROFILE_COLORS: Record<string, string> = {
  software: "#8b5cf6",
  content: "#0ea5e9",
  research: "#14b8a6",
  design: "#ec4899",
  haber: "#f59e0b",
  devcycle: "#ef4444",
};

function AlertIcon({ level }: { level: string }) {
  if (level === "error") return <AlertTriangle className="w-3.5 h-3.5 text-red-400 shrink-0" />;
  if (level === "warning") return <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />;
  return <Info className="w-3.5 h-3.5 text-blue-400 shrink-0" />;
}

function CircularProgress({ value, size = 80 }: { value: number; size?: number }) {
  const r = (size / 2) - 8;
  const circ = 2 * Math.PI * r;
  const offset = circ - (value / 100) * circ;
  const color = value >= 80 ? "#10b981" : value >= 50 ? "#f59e0b" : "#ef4444";
  return (
    <svg width={size} height={size}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth={6} />
      <circle
        cx={size / 2} cy={size / 2} r={r}
        fill="none" stroke={color} strokeWidth={6}
        strokeDasharray={circ} strokeDashoffset={offset}
        strokeLinecap="round" transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x={size / 2} y={size / 2 + 5} textAnchor="middle" fontSize={14} fontWeight="bold" fill={color}>
        {value}
      </text>
    </svg>
  );
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (d > 0) return `${d}d ${h}h ${m}m`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m`;
}

function EngineConnectionBadge({ connected }: { connected: boolean | null }) {
  if (connected === null) return <Badge variant="outline" className="text-xs"><Clock className="w-3 h-3 mr-1 animate-pulse" />Connecting</Badge>;
  if (connected) return <Badge variant="outline" className="text-xs text-emerald-400 border-emerald-500/30"><Wifi className="w-3 h-3 mr-1" />Engine Online</Badge>;
  return <Badge variant="outline" className="text-xs text-amber-400 border-amber-500/30"><WifiOff className="w-3 h-3 mr-1" />Using Mock Data</Badge>;
}

export default function DashboardPage({ initialCreateRun }: { initialCreateRun?: boolean }) {
  const [createOpen, setCreateOpen] = useState(initialCreateRun ?? false);
  const [wsMetrics, setWsMetrics] = useState<any>(null);
  const [engineConnected, setEngineConnected] = useState<boolean | null>(null);
  const { data: metrics, isLoading, refetch } = useGetMetrics({ query: { refetchInterval: 15000 } as any });
  const { data: health } = useHealthCheck({ query: { refetchInterval: 15000 } as any });

  // WebSocket live metrics
  useWebSocket({
    channel: "metrics",
    onMessage: (data) => {
      if (data.type === "metrics") {
        setWsMetrics(data);
      }
    },
    onConnect: () => setEngineConnected(true),
    onDisconnect: () => setEngineConnected(false),
  });

  // Determine engine connection status
  useEffect(() => {
    if (metrics || health) setEngineConnected(true);
  }, [metrics, health]);

  // Merge: WS data takes priority, then API, then mock fallback
  const mergedMetrics = wsMetrics || metrics || null;
  const displayMetrics = mergedMetrics ?? MOCK_METRICS;
  const isRealData = mergedMetrics != null;

  const stateData = Object.entries(displayMetrics.runs_by_state ?? {})
    .map(([name, value]) => ({ name, value }))
    .filter((d) => d.value > 0)
    .sort((a, b) => b.value - a.value);

  const profileData = Object.entries(displayMetrics.runs_by_profile ?? {})
    .map(([name, value]) => ({ name, value }));

  const budgetPct = Math.round((displayMetrics.budget_usage_ratio ?? 0) * 100);
  const costs = displayMetrics.total_cost_usd != null
    ? { LLM: (displayMetrics.total_cost_usd || 0) * 0.65, Compute: (displayMetrics.total_cost_usd || 0) * 0.25, Storage: (displayMetrics.total_cost_usd || 0) * 0.06, Network: (displayMetrics.total_cost_usd || 0) * 0.04 }
    : (MOCK_BUDGET.cost_by_category ?? {});
  const costData = Object.entries(costs).map(([name, value]) => ({ name, value: Number(value) }));

  const alerts = displayMetrics.alerts ?? MOCK_ALERTS;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-xl font-bold">Dashboard</h1>
            <p className="text-sm text-muted-foreground">Engine overview and live metrics</p>
          </div>
          <EngineConnectionBadge connected={engineConnected} />
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} data-testid="button-refresh">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Refresh
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)} data-testid="button-new-run">
            <Plus className="w-3.5 h-3.5 mr-1.5" />New Run
          </Button>
        </div>
      </div>

      {/* Top row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {/* Health */}
        <Card className="border-card-border">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Engine Health {isRealData && <span className="text-emerald-400 text-[10px] ml-1">● live</span>}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 flex items-center gap-4">
            {isLoading ? (
              <Skeleton className="w-20 h-20 rounded-full" />
            ) : (
              <CircularProgress value={displayMetrics.health_score ?? 0} />
            )}
            <div>
              <p className="text-xs text-muted-foreground">Degradation</p>
              <span className={cn("text-sm font-semibold font-mono",
                displayMetrics.degradation_level === "FULL" ? "text-emerald-400" :
                displayMetrics.degradation_level === "DEGRADED" ? "text-amber-400" : "text-red-400"
              )}>
                {displayMetrics.degradation_level}
              </span>
              <p className="text-xs text-muted-foreground mt-1">Uptime</p>
              <p className="text-sm font-medium font-mono">{formatUptime(displayMetrics.uptime_seconds ?? 0)}</p>
            </div>
          </CardContent>
        </Card>

        {/* Active runs */}
        <Card className="border-card-border">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Run Activity {isRealData && <span className="text-emerald-400 text-[10px] ml-1">● live</span>}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            {isLoading ? <Skeleton className="h-16" /> : (
              <>
                <div className="flex items-end gap-3">
                  <span className="text-4xl font-bold tabular-nums">{displayMetrics.active_runs}</span>
                  <span className="text-sm text-muted-foreground pb-1">active</span>
                </div>
                <p className="text-xs text-muted-foreground">{displayMetrics.total_runs} total runs</p>
                <p className="text-xs text-muted-foreground">{displayMetrics.throughput_per_minute?.toFixed(1)}/min throughput</p>
              </>
            )}
          </CardContent>
        </Card>

        {/* Budget */}
        <Card className="border-card-border">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Budget</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-2">
            {isLoading ? <Skeleton className="h-16" /> : (
              <>
                <div className="flex items-end gap-2">
                  <span className="text-2xl font-bold tabular-nums">${displayMetrics.total_cost_usd?.toFixed(2)}</span>
                </div>
                <Progress value={budgetPct} className="h-1.5" />
                <p className="text-xs text-muted-foreground">{budgetPct}% of budget used</p>
              </>
            )}
          </CardContent>
        </Card>

        {/* Latency */}
        <Card className="border-card-border">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Transitions</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-1">
            {isLoading ? <Skeleton className="h-16" /> : (
              <>
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">P50</span>
                  <span className="font-mono">{displayMetrics.transition_latency_p50 ?? "—"}ms</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">P95</span>
                  <span className="font-mono">{displayMetrics.transition_latency_p95 ?? "—"}ms</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-muted-foreground">P99</span>
                  <span className="font-mono text-amber-400">{displayMetrics.transition_latency_p99 ?? "—"}ms</span>
                </div>
                <div className="flex justify-between text-xs pt-1 border-t border-border">
                  <span className="text-muted-foreground">Transitions</span>
                  <span className="font-mono">{displayMetrics.total_transitions?.toLocaleString() ?? "—"}</span>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charts row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* State distribution */}
        <Card className="border-card-border">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-medium">
              State Distribution
              {isRealData && stateData.length > 0 && <span className="text-emerald-400 text-[10px] ml-1">● {stateData.length} states</span>}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            {stateData.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-44 text-muted-foreground">
                <Activity className="w-8 h-8 mb-2 opacity-30" />
                <p className="text-xs">No runs yet. Create a run to see state distribution.</p>
              </div>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie data={stateData} cx="50%" cy="50%" innerRadius={45} outerRadius={75} dataKey="value" paddingAngle={2}>
                      {stateData.map((entry) => (
                        <Cell key={entry.name} fill={STATE_COLORS[entry.name] ?? "#6b7280"} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 12 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
                  {stateData.slice(0, 6).map((d) => (
                    <div key={d.name} className="flex items-center gap-1 text-xs text-muted-foreground">
                      <div className="w-2 h-2 rounded-full shrink-0" style={{ background: STATE_COLORS[d.name] ?? "#6b7280" }} />
                      {d.name} ({d.value})
                    </div>
                  ))}
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* Profile distribution */}
        <Card className="border-card-border">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-medium">
              Profile Distribution
              {isRealData && profileData.length > 0 && <span className="text-emerald-400 text-[10px] ml-1">● {profileData.length} profiles</span>}
            </CardTitle>
          </CardHeader>
          <CardContent className="px-2 pb-4">
            {profileData.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-44 text-muted-foreground">
                <Activity className="w-8 h-8 mb-2 opacity-30" />
                <p className="text-xs">No profile data yet.</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={profileData} margin={{ left: -10 }}>
                  <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 12 }}
                  />
                  <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                    {profileData.map((entry) => (
                      <Cell key={entry.name} fill={PROFILE_COLORS[entry.name] ?? "#6b7280"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Cost breakdown */}
        <Card className="border-card-border">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-medium">Cost Breakdown</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4">
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={costData} cx="50%" cy="50%" innerRadius={45} outerRadius={75} dataKey="value" paddingAngle={2}>
                  {costData.map((_, i) => (
                    <Cell key={i} fill={["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"][i % 4]} />
                  ))}
                </Pie>
                <Tooltip
                  formatter={(v: number) => `$${v.toFixed(2)}`}
                  contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 12 }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
              {costData.map((d, i) => (
                <div key={d.name} className="flex items-center gap-1 text-xs text-muted-foreground">
                  <div className="w-2 h-2 rounded-full shrink-0" style={{ background: ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"][i % 4] }} />
                  {d.name} (${d.value.toFixed(0)})
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Recent alerts */}
      <Card className="border-card-border">
        <CardHeader className="pb-2 pt-4 px-4 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium">Recent Alerts</CardTitle>
          <Link href="/observability" className="text-xs text-primary hover:underline">View all</Link>
        </CardHeader>
        <CardContent className="px-4 pb-4 space-y-2">
          {alerts.length === 0 ? (
            <p className="text-xs text-muted-foreground text-center py-4">No alerts.</p>
          ) : (
            alerts.slice(0, 5).map((alert, i) => (
              <div key={i} className="flex items-start gap-2.5 py-1.5 border-b border-border/50 last:border-0">
                <AlertIcon level={alert.level} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs">{alert.message}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {formatDistanceToNow(new Date(alert.timestamp), { addSuffix: true })}
                  </p>
                </div>
                <Badge variant="outline" className="text-[10px] shrink-0 capitalize">{alert.level}</Badge>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <CreateRunDialog open={createOpen} onClose={() => setCreateOpen(false)} />
    </div>
  );
}
