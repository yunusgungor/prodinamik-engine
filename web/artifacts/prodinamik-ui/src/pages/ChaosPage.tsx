import { useState, useCallback } from "react";
import {
  Zap, Play, AlertTriangle, CheckCircle2, Clock, RefreshCw,
  Skull, Wifi, HardDrive, Cpu, MemoryStick, Network,
  FlaskConical,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import { useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { cn } from "@/lib/utils";
import {
  useListChaosScenarios,
  useRunChaosScenario,
  type ChaosScenario,
} from "@workspace/api-client-react";

const FAULT_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  "network-partition": Wifi,
  "network-latency": Network,
  "disk-full": HardDrive,
  "disk-corruption": HardDrive,
  "memory-pressure": MemoryStick,
  "cpu-spike": Cpu,
  "random-crash": Skull,
  "degraded-mode": AlertTriangle,
  "wal-corruption": HardDrive,
  "event-flood": Zap,
};

const SEVERITY_COLORS: Record<string, string> = {
  low: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  medium: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  high: "text-orange-400 border-orange-500/30 bg-orange-500/10",
  critical: "text-red-400 border-red-500/30 bg-red-500/10",
};

interface RunResult {
  scenario: string;
  outcome: "success" | "failure";
  recovery_time_sec?: number | null;
  metrics_before?: Record<string, unknown> | null;
  metrics_after?: Record<string, unknown> | null;
  timestamp: string;
}

export default function ChaosPage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: scenarios = [], isLoading, isError, refetch } = useListChaosScenarios();
  const runScenarioMutation = useRunChaosScenario();

  const [runningScenario, setRunningScenario] = useState<string | null>(null);
  const [runResults, setRunResults] = useState<RunResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<RunResult | null>(null);

  const handleRunScenario = useCallback(
    async (scenarioId: string, duration?: number) => {
      setRunningScenario(scenarioId);
      try {
        const result = await runScenarioMutation.mutateAsync({
          data: { scenario_id: scenarioId, duration },
        });
        const runResult: RunResult = {
          scenario: result.scenario,
          outcome: result.outcome as "success" | "failure",
          recovery_time_sec: result.recovery_time_sec,
          metrics_before: result.metrics_before,
          metrics_after: result.metrics_after,
          timestamp: new Date().toISOString(),
        };
        setRunResults((prev) => [runResult, ...prev]);
        toast({
          description: `Scenario '${scenarioId}': ${result.outcome.toUpperCase()} (recovery: ${result.recovery_time_sec ?? "N/A"}s)`,
          variant: result.outcome === "success" ? "default" : "destructive",
        });
      } catch (err) {
        toast({
          variant: "destructive",
          description: `Scenario '${scenarioId}' failed: ${err instanceof Error ? err.message : "Unknown error"}`,
        });
      } finally {
        setRunningScenario(null);
      }
    },
    [runScenarioMutation, toast]
  );

  const getScenarioId = (scenario: ChaosScenario): string => {
    return scenario.id || scenario.name;
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FlaskConical className="w-5 h-5 text-muted-foreground" />
          <div>
            <h1 className="text-xl font-bold">Chaos Engineering</h1>
            <p className="text-sm text-muted-foreground">
              Fault injection, resilience testing, and self-healing verification
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          Reload Scenarios
        </Button>
      </div>

      {/* Scenario cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {isLoading ? (
          <div className="col-span-full p-8 text-center text-sm text-muted-foreground">
            Loading chaos scenarios...
          </div>
        ) : isError ? (
          <div className="col-span-full p-8 text-center text-sm text-red-400">
            Failed to load scenarios. Check engine connection.
          </div>
        ) : scenarios.length === 0 ? (
          <div className="col-span-full p-8 text-center text-sm text-muted-foreground">
            No chaos scenarios available.
          </div>
        ) : (
          scenarios.map((scenario) => {
            const sId = getScenarioId(scenario);
            const Icon = FAULT_ICONS[sId] || Zap;
            const isRunning = runningScenario === sId;
            return (
              <Card key={sId} className={cn("border-card-border", isRunning && "ring-2 ring-amber-500/30")}>
                <CardContent className="px-4 py-3 space-y-3">
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                      <Icon className="w-4 h-4 text-muted-foreground" />
                      <div>
                        <p className="text-sm font-medium">{scenario.name}</p>
                        <p className="text-xs text-muted-foreground mt-0.5">{scenario.description}</p>
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {scenario.severity && (
                        <span
                          className={cn(
                            "text-[10px] px-1.5 py-0.5 rounded border font-mono font-medium",
                            SEVERITY_COLORS[scenario.severity] ?? "text-slate-400 border-slate-500/30 bg-slate-500/10"
                          )}
                        >
                          {scenario.severity}
                        </span>
                      )}
                      {scenario.duration && (
                        <span className="text-xs text-muted-foreground font-mono">
                          {scenario.duration}s
                        </span>
                      )}
                      {scenario.dangerous && (
                        <span className="text-[10px] px-1.5 py-0.5 rounded border font-mono font-medium text-red-400 border-red-500/30 bg-red-500/10">
                          DANGEROUS
                        </span>
                      )}
                    </div>
                    <Button
                      size="sm"
                      variant={isRunning ? "secondary" : "default"}
                      className="h-7 text-xs shrink-0"
                      disabled={isRunning}
                      onClick={() => handleRunScenario(sId, scenario.duration)}
                      data-testid={`button-run-${sId}`}
                    >
                      {isRunning ? (
                        <>
                          <span className="animate-spin mr-1">⏳</span>
                          Running...
                        </>
                      ) : (
                        <>
                          <Play className="w-3 h-3 mr-1" />
                          Run
                        </>
                      )}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })
        )}
      </div>

      {/* Running progress */}
      {runningScenario && (
        <Card className="border-card-border ring-2 ring-amber-500/20">
          <CardContent className="px-4 py-3 space-y-2">
            <div className="flex items-center gap-2">
              <span className="animate-spin text-amber-400">⚡</span>
              <p className="text-sm font-medium">Running: {runningScenario}</p>
            </div>
            <Progress value={45} className="h-1" />
            <p className="text-xs text-muted-foreground">Injecting fault and measuring recovery...</p>
          </CardContent>
        </Card>
      )}

      {/* Results */}
      {runResults.length > 0 && (
        <Card className="border-card-border">
          <CardHeader className="pb-2 pt-4 px-4">
            <CardTitle className="text-sm font-medium">
              Recent Results ({runResults.length})
            </CardTitle>
          </CardHeader>
          <CardContent className="px-0 pb-0">
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-xs pl-4">Scenario</TableHead>
                  <TableHead className="text-xs">Outcome</TableHead>
                  <TableHead className="text-xs">Recovery</TableHead>
                  <TableHead className="text-xs">Timestamp</TableHead>
                  <TableHead className="text-xs"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runResults.map((result, i) => (
                  <TableRow key={`${result.scenario}-${i}`} className="border-border hover:bg-muted/30">
                    <TableCell className="text-xs font-mono pl-4">{result.scenario}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        {result.outcome === "success" ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
                        )}
                        <span
                          className={cn(
                            "text-xs font-mono font-medium",
                            result.outcome === "success" ? "text-emerald-400" : "text-red-400"
                          )}
                        >
                          {result.outcome.toUpperCase()}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs font-mono">
                      {result.recovery_time_sec != null
                        ? `${result.recovery_time_sec.toFixed(1)}s`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {format(new Date(result.timestamp), "HH:mm:ss")}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 text-xs"
                        onClick={() => setSelectedResult(result)}
                      >
                        Details
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Result details dialog */}
      {selectedResult && (
        <Dialog open onOpenChange={() => setSelectedResult(null)}>
          <DialogContent className="sm:max-w-lg">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                {selectedResult.outcome === "success" ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-red-400" />
                )}
                Chaos Result: {selectedResult.scenario}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <div className="border border-border rounded-md p-3">
                  <p className="text-xs text-muted-foreground">Outcome</p>
                  <p className="text-sm font-mono font-bold mt-1">{selectedResult.outcome.toUpperCase()}</p>
                </div>
                <div className="border border-border rounded-md p-3">
                  <p className="text-xs text-muted-foreground">Recovery Time</p>
                  <p className="text-sm font-mono font-bold mt-1">
                    {selectedResult.recovery_time_sec != null
                      ? `${selectedResult.recovery_time_sec.toFixed(1)}s`
                      : "N/A"}
                  </p>
                </div>
              </div>
              {selectedResult.metrics_before && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Health Before</p>
                  <pre className="text-[10px] font-mono bg-muted rounded p-2 overflow-auto max-h-24">
                    {JSON.stringify(selectedResult.metrics_before, null, 2)}
                  </pre>
                </div>
              )}
              {selectedResult.metrics_after && (
                <div>
                  <p className="text-xs text-muted-foreground mb-1">Health After</p>
                  <pre className="text-[10px] font-mono bg-muted rounded p-2 overflow-auto max-h-24">
                    {JSON.stringify(selectedResult.metrics_after, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
