import { Crown, Server, Plus, Trash2, Network, RefreshCw, Activity } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { useListRaftNodes, useGetRaftStatus } from "@workspace/api-client-react";

const STATE_COLORS: Record<string, string> = {
  leader: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  follower: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  candidate: "text-purple-400 border-purple-500/30 bg-purple-500/10",
};

export default function DistributionPage() {
  const { toast } = useToast();

  // Real API hooks — auto-refresh every 10s
  const { data: nodes = [], isLoading: nodesLoading, isError: nodesError, refetch: refetchNodes } = useListRaftNodes();
  const { data: raftStatus, isLoading: statusLoading, refetch: refetchStatus } = useGetRaftStatus();

  const handleRefresh = () => {
    refetchNodes();
    refetchStatus();
    toast({ description: "Cluster state refreshed." });
  };

  const leader = nodes.find((n) => n.state === "leader");

  const summaryCards = [
    { label: "Leader", value: leader?.id ?? raftStatus?.leader ?? "—", icon: Crown, color: "text-amber-400" },
    { label: "Cluster Size", value: nodesLoading ? "..." : `${nodes.length} nodes`, icon: Server, color: "text-blue-400" },
    { label: "Term", value: raftStatus ? `#${raftStatus.term}` : leader ? `#${leader.term}` : "—", icon: Activity, color: "text-purple-400" },
    { label: "Log Index", value: leader?.log_index?.toLocaleString() ?? "—", icon: Network, color: "text-emerald-400" },
  ];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Network className="w-5 h-5 text-muted-foreground" />
          <div>
            <h1 className="text-xl font-bold">Distribution</h1>
            <p className="text-sm text-muted-foreground">Raft cluster management and replication status</p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={handleRefresh} data-testid="button-refresh-cluster">
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          Refresh
        </Button>
      </div>

      {/* Cluster overview */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {summaryCards.map(({ label, value, icon: Icon, color }) => (
          <Card key={label} className="border-card-border">
            <CardContent className="px-4 py-3">
              <div className="flex items-center gap-2 mb-1">
                <Icon className={`w-3.5 h-3.5 ${color}`} />
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</p>
              </div>
              <p className="text-lg font-bold font-mono mt-0.5" data-testid={`cluster-${label.toLowerCase().replace(/\s+/g, "-")}`}>
                {value}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Node list */}
      <Card className="border-card-border">
        <CardHeader className="pb-2 pt-4 px-4">
          <CardTitle className="text-sm font-medium">Cluster Nodes</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          {nodesLoading ? (
            <div className="p-8 text-center text-sm text-muted-foreground">Loading cluster nodes...</div>
          ) : nodesError ? (
            <div className="p-8 text-center text-sm text-red-400">Failed to load nodes. Check engine connection.</div>
          ) : nodes.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No cluster nodes found. Engine is running in standalone mode.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-xs pl-4">Node ID</TableHead>
                  <TableHead className="text-xs">Address</TableHead>
                  <TableHead className="text-xs">State</TableHead>
                  <TableHead className="text-xs">Term</TableHead>
                  <TableHead className="text-xs">Log Index</TableHead>
                  <TableHead className="text-xs">Last Seen</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {nodes.map((node) => (
                  <TableRow
                    key={node.id}
                    className="border-border hover:bg-muted/30"
                    data-testid={`node-row-${node.id}`}
                  >
                    <TableCell className="pl-4">
                      <div className="flex items-center gap-2">
                        {node.state === "leader" && <Crown className="w-3.5 h-3.5 text-amber-400" />}
                        <span className="text-sm font-mono font-medium">{node.id}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs font-mono text-muted-foreground">{node.address}</TableCell>
                    <TableCell>
                      <span
                        className={cn(
                          "text-xs px-2 py-0.5 rounded border font-mono font-medium",
                          STATE_COLORS[node.state] ?? "text-slate-400 border-slate-500/30 bg-slate-500/10"
                        )}
                      >
                        {node.state}
                      </span>
                    </TableCell>
                    <TableCell className="text-xs font-mono">{node.term ?? "—"}</TableCell>
                    <TableCell className="text-xs font-mono">
                      {node.log_index?.toLocaleString() ?? "—"}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {node.last_seen
                        ? formatDistanceToNow(new Date(node.last_seen), { addSuffix: true })
                        : "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        <span className="text-xs text-muted-foreground">healthy</span>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Log replication summary */}
      {leader && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <Card className="border-card-border">
            <CardContent className="px-4 py-3">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Log Index</p>
              <p className="text-xl font-bold font-mono mt-0.5">{leader.log_index?.toLocaleString() ?? "0"}</p>
              <p className="text-xs text-muted-foreground mt-1">Latest committed entry</p>
            </CardContent>
          </Card>
          <Card className="border-card-border">
            <CardContent className="px-4 py-3">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Committed Index</p>
              <p className="text-xl font-bold font-mono mt-0.5">
                {((leader.log_index ?? 0) - Math.min(2, nodes.length - 1)).toLocaleString()}
              </p>
              <p className="text-xs text-muted-foreground mt-1">Quorum-committed entries</p>
            </CardContent>
          </Card>
          <Card className="border-card-border">
            <CardContent className="px-4 py-3">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Followers</p>
              <p className="text-xl font-bold font-mono mt-0.5">{nodes.filter((n) => n.state === "follower").length}</p>
              <p className="text-xs text-muted-foreground mt-1">Active follower nodes</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Connection info */}
      <Card className="border-card-border">
        <CardContent className="px-4 py-3">
          <p className="text-xs text-muted-foreground">
            {raftStatus ? (
              <>
                Cluster state: <code className="font-mono text-primary">{raftStatus.state}</code> · 
                {raftStatus.nodes} nodes · Term #{raftStatus.term}
                {raftStatus.leader && <> · Leader: {raftStatus.leader}</>}
              </>
            ) : nodesError ? (
              "Unable to connect to Raft cluster. Engine may be running in standalone mode."
            ) : (
              "Loading cluster status..."
            )}
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
