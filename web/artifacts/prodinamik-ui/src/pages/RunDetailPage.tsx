import { useState, useEffect } from "react";
import { Link } from "wouter";
import { ArrowLeft, CheckCircle2, XCircle, AlertTriangle, ChevronDown, ChevronRight, Clock, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
import { useGetRun, getGetRunQueryKey } from "@workspace/api-client-react";
import { useWebSocket } from "@/hooks/use-websocket";
import { useQueryClient } from "@tanstack/react-query";
import { MOCK_RUN_DETAIL } from "@/lib/mock-data";
import { formatDistanceToNow, format } from "date-fns";
import TransitionDialog from "@/components/runs/TransitionDialog";
import { PipelineVisualizer, PipelineProgress } from "@/components/pipeline/PipelineVisualizer";
import { HITLDialog } from "@/components/hitl/HITLDialog";
import { cn } from "@/lib/utils";

const STATE_COLORS: Record<string, string> = {
  initial: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  spec: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  captured: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  development: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  iteration: "text-violet-400 border-violet-500/30 bg-violet-500/10",
  drafting: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  review: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  draft_review: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  deploy: "text-orange-400 border-orange-500/30 bg-orange-500/10",
  release: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  done: "text-slate-400 border-slate-500/30 bg-slate-500/10",
  published: "text-slate-400 border-slate-500/30 bg-slate-500/10",
  error: "text-red-400 border-red-500/30 bg-red-500/10",
  paused: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  blocked: "text-red-400 border-red-500/30 bg-red-500/10",
  correction_needed: "text-red-400 border-red-500/30 bg-red-500/10",
};

const PROFILE_COLORS: Record<string, string> = {
  software: "text-violet-400 border-violet-500/30 bg-violet-500/10",
  content: "text-sky-400 border-sky-500/30 bg-sky-500/10",
  research: "text-teal-400 border-teal-500/30 bg-teal-500/10",
  design: "text-pink-400 border-pink-500/30 bg-pink-500/10",
  haber: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  devcycle: "text-red-400 border-red-500/30 bg-red-500/10",
};

// PAUSE states that trigger HITL dialog
const PAUSE_STATES = new Set([
  "draft_review", "review", "published", "correction_needed",
  "peer_review", "blocked", "pause",
]);

function JsonViewer({ data }: { data: unknown }) {
  return (
    <pre className="text-xs font-mono bg-muted/50 rounded-md p-3 overflow-auto max-h-64 text-muted-foreground">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

function ExpandableEvent({ event }: { event: { event_type: string; timestamp: string; data?: unknown } }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-border rounded-md overflow-hidden">
      <button
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-muted/30 text-left"
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground shrink-0" /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground shrink-0" />}
        <span className="text-xs font-mono text-primary">{event.event_type}</span>
        <span className="text-xs text-muted-foreground ml-auto shrink-0">
          {format(new Date(event.timestamp), "HH:mm:ss")}
        </span>
      </button>
      {open && event.data != null && (
        <div className="px-3 pb-3 border-t border-border">
          <JsonViewer data={event.data} />
        </div>
      )}
    </div>
  );
}

export default function RunDetailPage({ slug }: { slug: string }) {
  const [transitionOpen, setTransitionOpen] = useState(false);
  const [hitlOpen, setHitlOpen] = useState(false);
  const [wsUpdate, setWsUpdate] = useState<any>(null);
  const [hitlQuestions, setHitlQuestions] = useState<any[]>([]);
  const queryClient = useQueryClient();

  const { data: run, isLoading, refetch } = useGetRun(slug, {
    query: { refetchInterval: 15000 } as any,
  });

  // WebSocket live updates for this run
  useWebSocket({
    channel: "runs",
    slug,
    onMessage: (data) => {
      if (data.type === "state.transition" || data.type === "run.updated") {
        setWsUpdate(data);
        refetch();
      }
    },
  });

  const display = run ?? MOCK_RUN_DETAIL;
  const isRealData = run != null;
  const isPauseState = PAUSE_STATES.has(display.state);

  // Auto-show HITL dialog when entering PAUSE state
  useEffect(() => {
    if (isPauseState && isRealData && display.state) {
      setHitlQuestions([
        {
          question: `Run "${slug}" is in PAUSE state "${display.state}". What would you like to do?`,
          type: "yes_no",
          choices: [],
          timeout: 300,
        },
      ]);
      setHitlOpen(true);
    }
  }, [display.state, isPauseState, isRealData]);

  const handleHitlResolved = () => {
    refetch();
    queryClient.invalidateQueries({ queryKey: getGetRunQueryKey(slug) });
  };

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-start gap-3">
        <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0 mt-0.5" asChild>
          <Link href="/runs"><ArrowLeft className="w-4 h-4" /></Link>
        </Button>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono font-bold text-lg">{display.slug}</span>
            <span className={cn("text-xs px-2 py-0.5 rounded border font-mono", PROFILE_COLORS[display.profile] ?? "text-muted-foreground border-border bg-muted")}>
              {display.profile}
            </span>
            <span className={cn("text-xs px-2 py-0.5 rounded border font-mono", STATE_COLORS[display.state] ?? "text-muted-foreground border-border bg-muted")}>
              {display.state}
            </span>
            {isPauseState && (
              <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-500/30 bg-amber-500/10 animate-pulse">
                ⏸ PAUSE
              </Badge>
            )}
            {isRealData && <span className="text-[10px] text-emerald-400">● live</span>}
          </div>
          {display.title && <p className="text-sm text-muted-foreground mt-0.5">{display.title}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Refresh
          </Button>
          <Button size="sm" onClick={() => setTransitionOpen(true)}>
            Transition
          </Button>
        </div>
      </div>

      {/* Pipeline Progress Bar */}
      <PipelineProgress profile={display.profile} currentState={display.state} className="px-1" />

      {/* Pipeline Visualizer */}
      <div className="bg-card border border-card-border rounded-lg p-4">
        <PipelineVisualizer
          profile={display.profile}
          currentState={display.state}
          compact
        />
      </div>

      {/* PAUSE state banner */}
      {isPauseState && (
        <div className="flex items-center gap-3 bg-amber-500/10 border border-amber-500/20 rounded-md px-4 py-3">
          <Clock className="w-5 h-5 text-amber-400 shrink-0 animate-pulse" />
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-400">Human Input Required</p>
            <p className="text-xs text-amber-300/80">
              Run is in <span className="font-mono">{display.state}</span> PAUSE state. 
              Provide your decision to continue the pipeline.
            </p>
          </div>
          <Button
            size="sm"
            className="bg-amber-500/20 text-amber-400 border border-amber-500/30 hover:bg-amber-500/30 shrink-0"
            onClick={() => setHitlOpen(true)}
          >
            Respond Now
          </Button>
        </div>
      )}

      {/* WebSocket live notification */}
      {wsUpdate && (
        <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-md px-4 py-2 text-xs text-emerald-400 flex items-center gap-2 animate-pulse">
          <Clock className="w-3 h-3" />
          Live update: {wsUpdate.type} — {format(new Date(), "HH:mm:ss")}
        </div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="overview">
        <TabsList className="h-8">
          <TabsTrigger value="overview" className="text-xs">Overview</TabsTrigger>
          <TabsTrigger value="events" className="text-xs">Events ({display.events?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="validation" className="text-xs">Validation</TabsTrigger>
          <TabsTrigger value="context" className="text-xs">Context</TabsTrigger>
          <TabsTrigger value="debug" className="text-xs">Debug</TabsTrigger>
        </TabsList>

        {/* Overview */}
        <TabsContent value="overview" className="mt-4 space-y-4">
          {isLoading ? <Skeleton className="h-48" /> : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: "Status", value: display.status },
                  { label: "Iteration", value: display.iteration ?? 0 },
                  { label: "Created", value: formatDistanceToNow(new Date(display.created_at), { addSuffix: true }) },
                  { label: "Elapsed", value: display.elapsed_seconds ? `${Math.floor(display.elapsed_seconds / 3600)}h ${Math.floor((display.elapsed_seconds % 3600) / 60)}m` : "—" },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-card border border-card-border rounded-md px-4 py-3">
                    <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</p>
                    <p className="text-sm font-medium font-mono mt-0.5">{String(value)}</p>
                  </div>
                ))}
              </div>

              {/* State timeline */}
              <div className="bg-card border border-card-border rounded-md p-4">
                <h3 className="text-sm font-medium mb-3">
                  State History
                  {isRealData && <span className="text-emerald-400 text-[10px] ml-1">● live</span>}
                </h3>
                <div className="space-y-0">
                  {(display.state_history ?? []).length === 0 ? (
                    <p className="text-xs text-muted-foreground">No state history.</p>
                  ) : (
                    (display.state_history ?? []).map((entry: any, i: number) => (
                      <div key={i} className="flex gap-3 pb-4 last:pb-0">
                        <div className="flex flex-col items-center">
                          <div className={cn("w-2.5 h-2.5 rounded-full mt-0.5 shrink-0", entry.exited_at ? "bg-muted-foreground" : "bg-primary animate-pulse")} />
                          {i < (display.state_history?.length ?? 0) - 1 && <div className="w-px flex-1 bg-border mt-1" />}
                        </div>
                        <div className="flex-1 pb-1">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-mono font-medium">{entry.state}</span>
                            {!entry.exited_at && <span className="text-[10px] text-primary bg-primary/10 px-1.5 py-0.5 rounded">current</span>}
                          </div>
                          <div className="text-[11px] text-muted-foreground mt-0.5">
                            {format(new Date(entry.entered_at), "MMM d HH:mm:ss")}
                            {entry.duration_seconds && ` · ${Math.round(entry.duration_seconds / 60)}m`}
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </TabsContent>

        {/* Events */}
        <TabsContent value="events" className="mt-4 space-y-2">
          {(display.events ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">No events recorded.</p>
          ) : (
            (display.events ?? []).map((event: any, i: number) => (
              <ExpandableEvent key={i} event={event} />
            ))
          )}
        </TabsContent>

        {/* Validation */}
        <TabsContent value="validation" className="mt-4 space-y-3">
          {(display.validation_results ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">No validation results.</p>
          ) : (
            (display.validation_results ?? []).map((result: any, i: number) => (
              <div key={i} className="bg-card border border-card-border rounded-md p-4">
                <div className="flex items-center gap-2 mb-2">
                  {result.passed ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <XCircle className="w-4 h-4 text-red-400" />}
                  <span className="text-sm font-semibold font-mono">{result.tier}</span>
                  <Badge variant="outline" className={cn("text-xs ml-auto", result.passed ? "text-emerald-400 border-emerald-500/30" : "text-red-400 border-red-500/30")}>
                    {result.passed ? "PASS" : "FAIL"}
                  </Badge>
                </div>
                {(result.errors ?? []).map((err: string, j: number) => (
                  <p key={j} className="text-xs text-red-400 flex items-start gap-1.5 mt-1"><XCircle className="w-3 h-3 mt-0.5 shrink-0" />{err}</p>
                ))}
                {(result.warnings ?? []).map((w: string, j: number) => (
                  <p key={j} className="text-xs text-amber-400 flex items-start gap-1.5 mt-1"><AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />{w}</p>
                ))}
              </div>
            ))
          )}
        </TabsContent>

        {/* Context */}
        <TabsContent value="context" className="mt-4">
          <div className="bg-card border border-card-border rounded-md p-4">
            <h3 className="text-sm font-medium mb-3">Run Context</h3>
            <JsonViewer data={display.context ?? {}} />
          </div>
        </TabsContent>

        {/* Debug */}
        <TabsContent value="debug" className="mt-4 space-y-3">
          <div className="bg-card border border-card-border rounded-md p-4">
            <h3 className="text-sm font-medium mb-2">Possible Transitions</h3>
            <div className="flex flex-wrap gap-2">
              {(display.possible_transitions ?? []).length === 0 ? (
                <p className="text-xs text-muted-foreground">No transitions available.</p>
              ) : (
                (display.possible_transitions ?? []).map((t: string) => (
                  <button
                    key={t}
                    className="text-xs font-mono px-2 py-1 border border-border rounded hover:bg-muted/50 text-primary"
                    onClick={() => setTransitionOpen(true)}
                  >
                    {t}
                  </button>
                ))
              )}
            </div>
          </div>
          <div className="bg-card border border-card-border rounded-md p-4">
            <h3 className="text-sm font-medium mb-2">Raw Run Data</h3>
            <JsonViewer data={display} />
          </div>
        </TabsContent>
      </Tabs>

      {/* Transition Dialog */}
      {transitionOpen && (
        <TransitionDialog
          slug={slug}
          transitions={display.possible_transitions ?? ["approve", "reject", "pause"]}
          onClose={() => setTransitionOpen(false)}
        />
      )}

      {/* HITL Dialog */}
      {hitlOpen && (
        <HITLDialog
          open={hitlOpen}
          onClose={() => setHitlOpen(false)}
          slug={slug}
          state={display.state}
          questions={hitlQuestions}
          onResolved={handleHitlResolved}
        />
      )}
    </div>
  );
}
