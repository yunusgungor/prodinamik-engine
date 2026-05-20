import { useState, useEffect, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell, Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useGetMetrics, useListAuditLog } from "@workspace/api-client-react";
import { useWebSocket } from "@/hooks/use-websocket";
import { MOCK_METRICS, MOCK_LATENCY_DATA, MOCK_THROUGHPUT_DATA, MOCK_AUDIT_ENTRIES } from "@/lib/mock-data";
import { RefreshCw, Activity, TrendingDown, DollarSign, AlertTriangle, FileText, Server, Cpu } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";

// ── Helpers ──

function getAuth() {
  try {
    const s = localStorage.getItem("pdmk-auth");
    if (!s) return { apiBase: "http://localhost:8000", apiKey: "" };
    const p = JSON.parse(s)?.state;
    return { apiBase: p?.baseUrl || "http://localhost:8000", apiKey: p?.apiKey || "" };
  } catch { return { apiBase: "http://localhost:8000", apiKey: "" }; }
}

async function api(path: string) {
  const { apiBase, apiKey } = getAuth();
  const h: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}` } : {};
  const res = await fetch(`${apiBase}${path}`, { headers: h });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

function fmtTime(d: string): string {
  const diff = Date.now() - new Date(d).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

function formatUptime(seconds: number): string {
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h`;
  return `${Math.floor(seconds / 60)}m`;
}

const DEGRADATION_COLORS: Record<string, string> = {
  FULL: "#10b981", DEGRADED: "#f59e0b", SURVIVAL: "#ef4444",
};

const TIME_RANGES = ["1h", "6h", "24h", "7d"] as const;

export default function ObservabilityPage() {
  const [timeRange, setTimeRange] = useState<string>("24h");
  const [tab, setTab] = useState("overview");
  const [degradation, setDegradation] = useState<any>(null);
  const [costs, setCosts] = useState<any>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [events, setEvents] = useState<any[]>([]);
  const [alertSummary, setAlertSummary] = useState<any>(null);
  const [wsMetrics, setWsMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const { data: metrics } = useGetMetrics({ query: { refetchInterval: 15000 } as any });
  const { data: auditLog } = useListAuditLog({ limit: 10 });

  useWebSocket({
    channel: "metrics",
    onMessage: (data) => {
      if (data.type === "metrics") setWsMetrics(data);
    },
  });

  const fetchObservability = useCallback(async () => {
    setLoading(true);
    try {
      const [deg, cst, alrt, evts] = await Promise.allSettled([
        api("/api/v1/observability/degradation?days=1"),
        api("/api/v1/observability/costs?days=30"),
        api("/api/v1/observability/alerts"),
        api("/api/v1/observability/events"),
      ]);
      if (deg.status === "fulfilled") setDegradation(deg.value);
      if (cst.status === "fulfilled") setCosts(cst.value);
      if (alrt.status === "fulfilled") setAlerts(alrt.value);
      if (evts.status === "fulfilled") setEvents(evts.value);
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchObservability(); }, [fetchObservability]);

  useEffect(() => {
    api("/api/v1/observability/alerts/summary").then(setAlertSummary).catch(() => {});
  }, []);

  const merged = wsMetrics || metrics || null;
  const displayMetrics = merged ?? MOCK_METRICS;
  const displayAudit = auditLog ?? MOCK_AUDIT_ENTRIES;
  const isRealData = merged != null;

  const degData = degradation?.history?.slice(-24) || [];
  const costData = costs?.history || [];
  const costSummary = costs?.summary;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Observability</h1>
          <p className="text-sm text-muted-foreground">
            Metrics, degradation, costs, alerts, and event store
            {isRealData && <span className="text-emerald-400 ml-1">● live</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-muted rounded-md p-0.5">
            {TIME_RANGES.map((r) => (
              <button key={r} className={cn("px-3 py-1 text-xs rounded transition-colors font-medium", timeRange === r ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}
                onClick={() => setTimeRange(r)}>{r}</button>
            ))}
          </div>
          <Button variant="outline" size="sm" onClick={fetchObservability}>
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Refresh
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="h-8">
          <TabsTrigger value="overview" className="text-xs"><Activity className="w-3 h-3 mr-1" />Overview</TabsTrigger>
          <TabsTrigger value="degradation" className="text-xs"><TrendingDown className="w-3 h-3 mr-1" />Degradation</TabsTrigger>
          <TabsTrigger value="costs" className="text-xs"><DollarSign className="w-3 h-3 mr-1" />Costs</TabsTrigger>
          <TabsTrigger value="alerts" className="text-xs"><AlertTriangle className="w-3 h-3 mr-1" />Alerts ({alerts.length})</TabsTrigger>
          <TabsTrigger value="events" className="text-xs"><FileText className="w-3 h-3 mr-1" />Events</TabsTrigger>
        </TabsList>

        {/* ── Overview Tab ── */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          {/* Metric cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              { label: "Active Runs", value: displayMetrics.active_runs, icon: Activity },
              { label: "Health Score", value: `${displayMetrics.health_score}/100`, icon: Server },
              { label: "Uptime", value: formatUptime(displayMetrics.uptime_seconds ?? 0), icon: Cpu },
              { label: "Degradation", value: displayMetrics.degradation_level, icon: TrendingDown,
                color: displayMetrics.degradation_level === "FULL" ? "text-emerald-400" : displayMetrics.degradation_level === "DEGRADED" ? "text-amber-400" : "text-red-400" },
            ].map(({ label, value, icon: Icon, color }) => (
              <Card key={label} className="border-card-border">
                <CardHeader className="pb-2 pt-4 px-4">
                  <CardTitle className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{label}</CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4 flex items-center gap-3">
                  <Icon className="w-5 h-5 text-muted-foreground/40" />
                  <p className={cn("text-xl font-bold font-mono", color)}>{value ?? "—"}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Latency chart */}
          <Card className="border-card-border">
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm font-medium">Transition Latency (last 24h)</CardTitle>
            </CardHeader>
            <CardContent className="px-2 pb-4">
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={MOCK_LATENCY_DATA}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="time" tick={{ fontSize: 10 }} tickLine={false} interval={5} />
                  <YAxis tick={{ fontSize: 10 }} tickLine={false} unit="ms" />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 11 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="p50" stroke="#3b82f6" strokeWidth={2} dot={false} name="P50" />
                  <Line type="monotone" dataKey="p95" stroke="#f59e0b" strokeWidth={2} dot={false} name="P95" />
                  <Line type="monotone" dataKey="p99" stroke="#ef4444" strokeWidth={2} dot={false} name="P99" />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Quick stats row */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            <Card className="border-card-border">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-medium">Degradation Uptime</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                <div className="flex items-center gap-3">
                  <div className={cn("text-2xl font-bold font-mono", degradation?.uptime_pct > 90 ? "text-emerald-400" : "text-amber-400")}>
                    {degradation?.uptime_pct ?? "—"}%
                  </div>
                  <p className="text-xs text-muted-foreground">FULL level uptime (24h)</p>
                </div>
              </CardContent>
            </Card>
            <Card className="border-card-border">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-medium">Daily Cost</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                <div className="text-2xl font-bold font-mono">${costs?.daily_avg?.toFixed(2) ?? "—"}</div>
                <p className="text-xs text-muted-foreground">
                  {costSummary?.llm_percentage ? `${costSummary.llm_percentage}% from LLM` : "No cost data"}
                </p>
              </CardContent>
            </Card>
            <Card className="border-card-border">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-medium">Active Alerts</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                <div className="flex items-center gap-3">
                  <div className="text-2xl font-bold font-mono">{alertSummary?.unacknowledged ?? 0}</div>
                  <div className="flex gap-2 text-xs">
                    <Badge variant="outline" className="text-red-400 border-red-500/30">{alertSummary?.by_level?.error ?? 0} errors</Badge>
                    <Badge variant="outline" className="text-amber-400 border-amber-500/30">{alertSummary?.by_level?.warning ?? 0} warnings</Badge>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* ── Degradation Tab ── */}
        <TabsContent value="degradation" className="mt-4 space-y-4">
          <Card className="border-card-border">
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm font-medium">Degradation Timeline (24h)</CardTitle>
            </CardHeader>
            <CardContent className="px-2 pb-4">
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={degData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                  <XAxis dataKey="timestamp" tick={{ fontSize: 9 }} tickFormatter={(v) => new Date(v).getHours() + ":00"} interval={5} />
                  <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} />
                  <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 11 }}
                    labelFormatter={(v) => new Date(v).toLocaleString()} />
                  <Area type="monotone" dataKey="health_score" stroke="#3b82f6" fill="#3b82f610" strokeWidth={2} name="Health Score" />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Current Level", value: degradation?.current_level, color: DEGRADATION_COLORS[degradation?.current_level || "FULL"] },
              { label: "Total Changes", value: degradation?.total_changes },
              { label: "Uptime (FULL)", value: `${degradation?.uptime_pct ?? 0}%` },
              { label: "Data Points", value: degData.length },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-card border border-card-border rounded-md p-3">
                <p className="text-[10px] text-muted-foreground uppercase">{label}</p>
                <p className={cn("text-lg font-bold font-mono mt-0.5", color && `text-[${color}]`)}>{value ?? "—"}</p>
              </div>
            ))}
          </div>
        </TabsContent>

        {/* ── Costs Tab ── */}
        <TabsContent value="costs" className="mt-4 space-y-4">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card className="border-card-border">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-medium">Daily Cost Breakdown (30 days)</CardTitle>
              </CardHeader>
              <CardContent className="px-2 pb-4">
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={costData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                    <XAxis dataKey="date" tick={{ fontSize: 9 }} tickFormatter={(v) => v?.slice(5) || ""} interval={6} />
                    <YAxis tick={{ fontSize: 10 }} unit="$" />
                    <Tooltip contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 6, fontSize: 11 }} />
                    <Area type="monotone" dataKey="llm" stackId="1" stroke="#3b82f6" fill="#3b82f640" name="LLM" />
                    <Area type="monotone" dataKey="compute" stackId="1" stroke="#8b5cf6" fill="#8b5cf640" name="Compute" />
                    <Area type="monotone" dataKey="storage" stackId="1" stroke="#10b981" fill="#10b98140" name="Storage" />
                    <Area type="monotone" dataKey="network" stackId="1" stroke="#f59e0b" fill="#f59e0b40" name="Network" />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card className="border-card-border">
              <CardHeader className="pb-2 pt-4 px-4">
                <CardTitle className="text-sm font-medium">Cost Distribution</CardTitle>
              </CardHeader>
              <CardContent className="px-4 pb-4">
                {costSummary ? (
                  <div className="flex flex-col items-center gap-4">
                    <ResponsiveContainer width="100%" height={150}>
                      <PieChart>
                        <Pie data={Object.entries(costSummary).filter(([k]) => k !== "total").map(([k, v]) => ({ name: k, value: v as number }))}
                          cx="50%" cy="50%" innerRadius={40} outerRadius={65} dataKey="value" paddingAngle={2}>
                          {[["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"]].map((colors, _) =>
                            Object.keys(costSummary).filter(k => k !== "total").map((k, i) => (
                              <Cell key={k} fill={["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"][i]} />
                            ))
                          )}
                        </Pie>
                        <Tooltip formatter={(v: number) => `$${v.toFixed(2)}`} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
                      {Object.entries(costSummary).filter(([k]) => k !== "total").map(([k, v], i) => (
                        <div key={k} className="flex items-center gap-2">
                          <div className="w-2.5 h-2.5 rounded" style={{ background: ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b"][i] }} />
                          <span className="capitalize text-muted-foreground">{k}</span>
                          <span className="font-mono">${(v as number).toFixed(2)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground text-center py-8">No cost data available.</p>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: "Total (30d)", value: `$${costSummary?.total?.toFixed(2) ?? "—"}`, color: "text-foreground" },
              { label: "Daily Avg", value: `$${costs?.daily_avg?.toFixed(2) ?? "—"}` },
              { label: "LLM %", value: `${costSummary?.llm_percentage ?? "—"}%`, color: costSummary?.llm_percentage > 70 ? "text-amber-400" : "text-emerald-400" },
              { label: "Cost/Run", value: `$${costs?.cost_per_run?.toFixed(2) ?? "—"}` },
            ].map(({ label, value, color }) => (
              <div key={label} className="bg-card border border-card-border rounded-md p-3">
                <p className="text-[10px] text-muted-foreground uppercase">{label}</p>
                <p className={cn("text-lg font-bold font-mono mt-0.5", color)}>{value}</p>
              </div>
            ))}
          </div>
        </TabsContent>

        {/* ── Alerts Tab ── */}
        <TabsContent value="alerts" className="mt-4 space-y-4">
          {alerts.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">No alerts.</p>
            </div>
          ) : (
            <div className="space-y-2">
              {alerts.map((alert) => (
                <div key={alert.id} className="flex items-start gap-3 px-4 py-3 bg-card border border-card-border rounded-lg">
                  <div className={cn("w-2 h-2 rounded-full mt-1.5 shrink-0",
                    alert.level === "error" ? "bg-red-400" : alert.level === "warning" ? "bg-amber-400" : "bg-blue-400")} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={cn("text-[10px]",
                        alert.level === "error" ? "text-red-400 border-red-500/30" :
                        alert.level === "warning" ? "text-amber-400 border-amber-500/30" : "text-blue-400 border-blue-500/30")}>
                        {alert.level}
                      </Badge>
                      <span className="text-xs text-muted-foreground font-mono">{alert.source || "system"}</span>
                    </div>
                    <p className="text-xs mt-1">{alert.message}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">{fmtTime(alert.timestamp)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        {/* ── Events Tab ── */}
        <TabsContent value="events" className="mt-4 space-y-4">
          <Card className="border-card-border">
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm font-medium">Event Store Browser</CardTitle>
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <Table>
                <TableHeader>
                  <TableRow className="border-border hover:bg-transparent">
                    <TableHead className="text-xs pl-4">Event Type</TableHead>
                    <TableHead className="text-xs">Summary</TableHead>
                    <TableHead className="text-xs w-28">Time</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {events.slice(0, 20).map((e, i) => (
                    <TableRow key={e.id || i} className="border-border hover:bg-muted/30">
                      <TableCell className="text-xs font-mono pl-4 text-primary">{e.event_type}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{e.summary || e.event_type}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{fmtTime(e.timestamp)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card className="border-card-border">
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm font-medium">Audit Log</CardTitle>
            </CardHeader>
            <CardContent className="px-0 pb-0">
              <Table>
                <TableHeader>
                  <TableRow className="border-border hover:bg-transparent">
                    <TableHead className="text-xs pl-4">Event</TableHead>
                    <TableHead className="text-xs">Summary</TableHead>
                    <TableHead className="text-xs w-32">Actor</TableHead>
                    <TableHead className="text-xs w-28">Time</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {displayAudit.slice(0, 10).map((entry: any, i: number) => (
                    <TableRow key={entry.id ?? i} className="border-border hover:bg-muted/30">
                      <TableCell className="text-xs font-mono pl-4 text-primary">{entry.event_type}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{entry.summary ?? "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground font-mono">{entry.actor ?? "system"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">{formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true })}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
