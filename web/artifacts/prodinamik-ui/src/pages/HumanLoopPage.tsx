import { useState, useEffect } from "react";
import { Clock, CheckCircle2, XCircle, PauseCircle, Users, DollarSign, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { useWebSocket } from "@/hooks/use-websocket";
import { MOCK_APPROVALS, MOCK_BUDGET, MOCK_AUDIT_ENTRIES } from "@/lib/mock-data";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { Link } from "wouter";

const PAUSE_REASONS = ["human_review", "budget_exceeded", "error_threshold", "manual", "security"];

const PRIORITY_COLORS: Record<string, string> = {
  critical: "text-red-400 border-red-500/30 bg-red-500/10",
  high: "text-orange-400 border-orange-500/30 bg-orange-500/10",
  medium: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  low: "text-slate-400 border-slate-500/30 bg-slate-500/10",
};

interface ApprovalItem {
  task_id: string;
  description: string;
  created_at: string;
  run_slug?: string;
  priority?: string;
}

function ApprovalCard({ task, onApprove, onReject }: {
  task: ApprovalItem;
  onApprove: (taskId: string, feedback: string) => void;
  onReject: (taskId: string, feedback: string) => void;
}) {
  const [feedback, setFeedback] = useState("");

  return (
    <div className="bg-card border border-card-border rounded-lg p-4 space-y-3" data-testid={`approval-card-${task.task_id}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-xs font-mono text-primary">{task.task_id}</span>
            <span className={cn("text-[10px] px-1.5 py-0.5 rounded border font-medium capitalize", PRIORITY_COLORS[task.priority ?? "medium"])}>
              {task.priority}
            </span>
          </div>
          <p className="text-sm">{task.description}</p>
          <div className="flex items-center gap-3 mt-1.5 text-xs text-muted-foreground">
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatDistanceToNow(new Date(task.created_at), { addSuffix: true })}
            </div>
            {task.run_slug && (
              <Link href={`/runs/${task.run_slug}`} className="font-mono hover:text-primary transition-colors">
                {task.run_slug}
              </Link>
            )}
          </div>
        </div>
      </div>
      <Textarea
        placeholder="Feedback or reason (optional)..."
        className="text-sm min-h-16 resize-none"
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        data-testid={`textarea-feedback-${task.task_id}`}
      />
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          className="flex-1 text-emerald-400 border-emerald-500/30 hover:bg-emerald-500/10"
          onClick={() => onApprove(task.task_id, feedback)}
          data-testid={`button-approve-${task.task_id}`}
        >
          <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />Approve
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="flex-1 text-red-400 border-red-500/30 hover:bg-red-500/10"
          onClick={() => onReject(task.task_id, feedback)}
          data-testid={`button-reject-${task.task_id}`}
        >
          <XCircle className="w-3.5 h-3.5 mr-1.5" />Reject
        </Button>
      </div>
    </div>
  );
}

export default function HumanLoopPage() {
  const { toast } = useToast();
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [budget, setBudget] = useState<any>(null);
  const [pauseTaskId, setPauseTaskId] = useState("");
  const [pauseReason, setPauseReason] = useState("human_review");
  const [loading, setLoading] = useState(true);

  const apiBase = (() => {
    try {
      const stored = localStorage.getItem("pdmk-auth");
      return stored ? JSON.parse(stored)?.state?.baseUrl || "http://localhost:8000" : "http://localhost:8000";
    } catch { return "http://localhost:8000"; }
  })();
  const apiKey = (() => {
    try {
      const stored = localStorage.getItem("pdmk-auth");
      return stored ? JSON.parse(stored)?.state?.apiKey || "" : "";
    } catch { return ""; }
  })();
  const headers: Record<string, string> = apiKey ? { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" } : { "Content-Type": "application/json" };

  const fetchData = async () => {
    setLoading(true);
    try {
      const [approvalsRes, budgetRes] = await Promise.allSettled([
        fetch(`${apiBase}/api/v1/human/approvals`, { headers }),
        fetch(`${apiBase}/api/v1/human/budget`, { headers }),
      ]);
      if (approvalsRes.status === "fulfilled") setApprovals(await approvalsRes.value.json());
      if (budgetRes.status === "fulfilled") setBudget(await budgetRes.value.json());
    } catch (e) {
      console.log("Human loop fetch (will use mock):", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  // WebSocket for live HITL updates
  useWebSocket({
    channel: "human",
    onMessage: (data) => {
      if (data.type === "approval" || data.type === "hitl") {
        fetchData();
      }
    },
  });

  const displayApprovals = approvals.length > 0 ? approvals : MOCK_APPROVALS;
  const displayBudget = budget ?? MOCK_BUDGET;
  const isRealData = approvals.length > 0;

  const handleApprove = async (taskId: string, feedback: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/human/approve`, {
        method: "POST", headers, body: JSON.stringify({ task_id: taskId, feedback }),
      });
      if (res.ok) {
        toast({ title: "Approved", description: taskId });
        fetchData();
      } else {
        toast({ title: "Failed to approve", variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to approve", variant: "destructive" });
    }
  };

  const handleReject = async (taskId: string, feedback: string) => {
    try {
      const res = await fetch(`${apiBase}/api/v1/human/reject`, {
        method: "POST", headers, body: JSON.stringify({ task_id: taskId, feedback }),
      });
      if (res.ok) {
        toast({ title: "Rejected", description: taskId });
        fetchData();
      } else {
        toast({ title: "Failed to reject", variant: "destructive" });
      }
    } catch {
      toast({ title: "Failed to reject", variant: "destructive" });
    }
  };

  const handlePause = async () => {
    if (!pauseTaskId) return;
    try {
      const res = await fetch(`${apiBase}/api/v1/human/pause`, {
        method: "POST", headers, body: JSON.stringify({ task_id: pauseTaskId, reason: pauseReason }),
      });
      if (res.ok) {
        toast({ title: "Task paused", description: pauseTaskId });
        setPauseTaskId("");
        fetchData();
      }
    } catch {
      toast({ title: "Failed to pause task", variant: "destructive" });
    }
  };

  const budgetPct = Math.round((displayBudget.budget_usage_ratio ?? 0) * 100);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Human Loop Oversight</h1>
          <p className="text-sm text-muted-foreground">
            Pending approvals, budget management, and task control
            {isRealData && <span className="text-emerald-400 ml-1">● live</span>}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={fetchData}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Refresh
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Approvals column */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold flex items-center gap-2">
              <Users className="w-4 h-4 text-muted-foreground" />
              Pending Approvals
              <Badge variant="outline" className="text-xs">{displayApprovals.length}</Badge>
            </h2>
          </div>
          {displayApprovals.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-32 text-muted-foreground border border-dashed border-border rounded-lg">
              <CheckCircle2 className="w-8 h-8 mb-2 text-emerald-400" />
              <p className="text-sm">No pending approvals</p>
            </div>
          ) : (
            displayApprovals.map((task) => (
              <ApprovalCard key={task.task_id} task={task} onApprove={handleApprove} onReject={handleReject} />
            ))
          )}

          {/* Pause task form */}
          <div className="bg-card border border-card-border rounded-lg p-4 space-y-3">
            <h3 className="text-sm font-semibold flex items-center gap-2">
              <PauseCircle className="w-4 h-4 text-muted-foreground" />
              Pause Task
            </h3>
            <div className="flex gap-2">
              <Input
                placeholder="Task ID (e.g., hitl-run-slug)..."
                className="text-sm font-mono h-8"
                value={pauseTaskId}
                onChange={(e) => setPauseTaskId(e.target.value)}
                data-testid="input-pause-task-id"
              />
              <Select value={pauseReason} onValueChange={setPauseReason}>
                <SelectTrigger className="h-8 w-44 text-xs" data-testid="select-pause-reason">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PAUSE_REASONS.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                </SelectContent>
              </Select>
              <Button size="sm" className="h-8 shrink-0" disabled={!pauseTaskId} onClick={handlePause} data-testid="button-pause-task">
                Pause
              </Button>
            </div>
          </div>
        </div>

        {/* Budget + audit column */}
        <div className="space-y-4">
          {/* Budget card */}
          <Card className="border-card-border">
            <CardHeader className="pb-2 pt-4 px-4">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                  <DollarSign className="w-4 h-4 text-muted-foreground" />
                  Budget Status
                  {isRealData && <span className="text-emerald-400 text-[10px]">●</span>}
                </CardTitle>
                <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => {
                  fetch(`${apiBase}/api/v1/human/budget/reset`, { method: "POST", headers })
                    .then(() => { toast({ title: "Budget reset" }); fetchData(); })
                    .catch(() => toast({ title: "Failed to reset", variant: "destructive" }));
                }}>
                  Reset
                </Button>
              </div>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-3">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-muted-foreground">Usage</span>
                  <span className="font-mono">${displayBudget.total_cost_usd?.toFixed(2)} / ${displayBudget.soft_limit_usd}</span>
                </div>
                <Progress value={budgetPct} className={`h-2 ${budgetPct > 90 ? "[&>div]:bg-red-500" : budgetPct > 70 ? "[&>div]:bg-amber-500" : ""}`} />
                <p className="text-xs text-muted-foreground mt-1">{budgetPct}% of soft limit</p>
              </div>
              <div className="space-y-1 text-xs">
                {[
                  { label: "Soft limit", value: `$${displayBudget.soft_limit_usd}` },
                  { label: "Hard limit", value: `$${displayBudget.hard_limit_usd}` },
                  { label: "LLM calls", value: displayBudget.llm_calls?.toLocaleString() },
                  { label: "Tool calls", value: displayBudget.tool_calls?.toLocaleString() },
                  { label: "Hourly rate", value: `$${displayBudget.hourly_cost_usd?.toFixed(2)}/h` },
                ].map(({ label, value }) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-muted-foreground">{label}</span>
                    <span className="font-mono">{value}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Audit trail */}
          <Card className="border-card-border">
            <CardHeader className="pb-2 pt-4 px-4">
              <CardTitle className="text-sm font-medium">Approval Audit Trail</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-4 space-y-2">
              {MOCK_AUDIT_ENTRIES.filter((e) => e.event_type === "human.approved" || e.event_type === "human.rejected")
                .slice(0, 5).map((entry, i) => (
                <div key={i} className="text-xs border-b border-border/50 last:border-0 pb-1.5 last:pb-0">
                  <p className="font-mono text-primary">{entry.event_type}</p>
                  <p className="text-muted-foreground">{entry.summary}</p>
                  <p className="text-muted-foreground/60">{formatDistanceToNow(new Date(entry.timestamp), { addSuffix: true })}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
