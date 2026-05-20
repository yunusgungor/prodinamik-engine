import { useState, useEffect } from "react";
import { Link } from "wouter";
import { Plus, Search, X, MoreHorizontal, RefreshCw, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useListRuns, useListProfiles } from "@workspace/api-client-react";
import { useWebSocket } from "@/hooks/use-websocket";
import { MOCK_RUNS, MOCK_PROFILES } from "@/lib/mock-data";
import { formatDistanceToNow } from "date-fns";
import CreateRunDialog from "@/components/runs/CreateRunDialog";
import TransitionDialog from "@/components/runs/TransitionDialog";
import { cn } from "@/lib/utils";

const STATE_COLORS: Record<string, string> = {
  initial: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  spec: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  captured: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  development: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  prototyping: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  iteration: "text-violet-400 border-violet-500/30 bg-violet-500/10",
  drafting: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  planning: "text-indigo-400 border-indigo-500/30 bg-indigo-500/10",
  testing: "text-violet-400 border-violet-500/30 bg-violet-500/10",
  review: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  draft_review: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  idea_review: "text-pink-400 border-pink-500/30 bg-pink-500/10",
  brief_ready: "text-teal-400 border-teal-500/30 bg-teal-500/10",
  verification: "text-violet-400 border-violet-500/30 bg-violet-500/10",
  deploy: "text-orange-400 border-orange-500/30 bg-orange-500/10",
  release: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  approved: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
  done: "text-slate-400 border-slate-500/30 bg-slate-500/10",
  published: "text-slate-400 border-slate-500/30 bg-slate-500/10",
  archived: "text-slate-400 border-slate-500/30 bg-slate-500/10",
  analysis: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
  feedback: "text-purple-400 border-purple-500/30 bg-purple-500/10",
  error: "text-red-400 border-red-500/30 bg-red-500/10",
  paused: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  fact_checking: "text-orange-400 border-orange-500/30 bg-orange-500/10",
  cross_verified: "text-teal-400 border-teal-500/30 bg-teal-500/10",
  correction_needed: "text-red-400 border-red-500/30 bg-red-500/10",
  peer_review: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  blocked: "text-red-400 border-red-500/30 bg-red-500/10",
};

const PROFILE_COLORS: Record<string, string> = {
  software: "text-violet-400 border-violet-500/30 bg-violet-500/10",
  content: "text-sky-400 border-sky-500/30 bg-sky-500/10",
  research: "text-teal-400 border-teal-500/30 bg-teal-500/10",
  design: "text-pink-400 border-pink-500/30 bg-pink-500/10",
  haber: "text-amber-400 border-amber-500/30 bg-amber-500/10",
  devcycle: "text-red-400 border-red-500/30 bg-red-500/10",
};

function safeDate(dateStr: string | null | undefined): Date | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  return isNaN(d.getTime()) ? null : d;
}

function safeFormatDistance(dateStr: string | null | undefined): string {
  const d = safeDate(dateStr);
  return d ? formatDistanceToNow(d, { addSuffix: true }) : "—";
}

function safeFormatDate(dateStr: string | null | undefined): string {
  const d = safeDate(dateStr);
  return d ? format(d, "MMM d HH:mm:ss") : "—";
}

function StateBadge({ state }: { state: string }) {
  return (
    <span className={cn("text-[11px] px-2 py-0.5 rounded border font-mono font-medium", STATE_COLORS[state] ?? "text-muted-foreground border-border bg-muted")}>
      {state}
    </span>
  );
}

function ProfileBadge({ profile }: { profile: string }) {
  return (
    <span className={cn("text-[11px] px-2 py-0.5 rounded border font-mono font-medium capitalize", PROFILE_COLORS[profile] ?? "text-muted-foreground border-border bg-muted")}>
      {profile}
    </span>
  );
}

const PAGE_SIZE = 20;

export default function RunsPage() {
  const [search, setSearch] = useState("");
  const [profileFilter, setProfileFilter] = useState("all");
  const [stateFilter, setStateFilter] = useState("all");
  const [page, setPage] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [transitionSlug, setTransitionSlug] = useState<string | null>(null);
  const [liveUpdates, setLiveUpdates] = useState<any[]>([]);

  const { data: runs, isLoading, refetch } = useListRuns();
  const { data: profiles } = useListProfiles();

  // WebSocket live updates
  useWebSocket({
    channel: "events",
    onMessage: (data) => {
      if (data.type === "run.created" || data.type === "state.transition") {
        refetch(); // Auto-refresh on run changes
      }
    },
  });

  const displayRuns = runs && runs.length > 0 ? runs : MOCK_RUNS;
  const displayProfiles = profiles && profiles.length > 0 ? profiles : MOCK_PROFILES;
  const isRealData = runs && runs.length > 0;

  const filtered = displayRuns.filter((r: any) => {
    if (search && !r.slug?.includes(search) && !r.title?.toLowerCase().includes(search.toLowerCase())) return false;
    if (profileFilter !== "all" && r.profile !== profileFilter) return false;
    if (stateFilter !== "all" && r.state !== stateFilter) return false;
    return true;
  });

  const pageCount = Math.ceil(filtered.length / PAGE_SIZE);
  const pageData = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const allStates = [...new Set(displayRuns.map((r: any) => r.state))];

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div>
            <h1 className="text-xl font-bold">Runs</h1>
            <p className="text-sm text-muted-foreground">
              {filtered.length} runs found
              {isRealData && <span className="text-emerald-400 ml-1">● live</span>}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()} data-testid="button-refresh-runs">
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />Refresh
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)} data-testid="button-create-run">
            <Plus className="w-3.5 h-3.5 mr-1.5" />New Run
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-48 max-w-72">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder="Search by slug or title..."
            className="pl-8 h-8 text-sm"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            data-testid="input-search-runs"
          />
        </div>
        <Select value={profileFilter} onValueChange={(v) => { setProfileFilter(v); setPage(0); }}>
          <SelectTrigger className="h-8 w-36 text-xs" data-testid="select-filter-profile">
            <SelectValue placeholder="All profiles" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All profiles</SelectItem>
            {displayProfiles.map((p: any) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={stateFilter} onValueChange={(v) => { setStateFilter(v); setPage(0); }}>
          <SelectTrigger className="h-8 w-36 text-xs" data-testid="select-filter-state">
            <SelectValue placeholder="All states" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All states</SelectItem>
            {allStates.map((s: string) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
          </SelectContent>
        </Select>
        {(search || profileFilter !== "all" || stateFilter !== "all") && (
          <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => { setSearch(""); setProfileFilter("all"); setStateFilter("all"); setPage(0); }}>
            <X className="w-3.5 h-3.5 mr-1" />Reset
          </Button>
        )}
      </div>

      {/* Table */}
      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="border-border hover:bg-transparent">
              <TableHead className="text-xs font-medium w-48">Slug</TableHead>
              <TableHead className="text-xs font-medium">Title</TableHead>
              <TableHead className="text-xs font-medium w-28">Profile</TableHead>
              <TableHead className="text-xs font-medium w-28">State</TableHead>
              <TableHead className="text-xs font-medium w-24">Status</TableHead>
              <TableHead className="text-xs font-medium w-36">Created</TableHead>
              <TableHead className="text-xs font-medium w-24">Elapsed</TableHead>
              <TableHead className="text-xs font-medium w-12"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading ? (
              Array.from({ length: 8 }).map((_, i) => (
                <TableRow key={i} className="border-border">
                  {Array.from({ length: 8 }).map((_, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : pageData.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center text-sm text-muted-foreground py-12">
                  No runs found matching your filters.
                </TableCell>
              </TableRow>
            ) : (
              pageData.map((run: any) => (
                <TableRow key={run.slug} className="border-border hover:bg-muted/30" data-testid={`row-run-${run.slug}`}>
                  <TableCell className="font-mono text-xs">
                    <Link href={`/runs/${run.slug}`} className="text-primary hover:underline">
                      {run.slug}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground truncate max-w-48">{run.title ?? "—"}</TableCell>
                  <TableCell><ProfileBadge profile={run.profile} /></TableCell>
                  <TableCell><StateBadge state={run.state} /></TableCell>
                  <TableCell>
                    <span className={cn("text-xs font-medium", run.status === "active" ? "text-emerald-400" : run.status === "error" ? "text-red-400" : "text-muted-foreground")}>
                      {run.status}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {safeFormatDistance(run.created_at)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground font-mono">
                    {run.elapsed_seconds ? `${Math.floor(run.elapsed_seconds / 3600)}h ${Math.floor((run.elapsed_seconds % 3600) / 60)}m` : "—"}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-7 w-7" data-testid={`button-actions-${run.slug}`}>
                          <MoreHorizontal className="w-3.5 h-3.5" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem asChild>
                          <Link href={`/runs/${run.slug}`}>View details</Link>
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setTransitionSlug(run.slug)}>
                          Transition state
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-muted-foreground">Archive</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination */}
      {pageCount > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>Page {page + 1} of {pageCount} ({filtered.length} total)</span>
          <div className="flex items-center gap-1">
            <Button variant="outline" size="icon" className="h-7 w-7" disabled={page === 0} onClick={() => setPage(p => p - 1)}>
              <ChevronLeft className="w-3.5 h-3.5" />
            </Button>
            <Button variant="outline" size="icon" className="h-7 w-7" disabled={page >= pageCount - 1} onClick={() => setPage(p => p + 1)}>
              <ChevronRight className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      )}

      <CreateRunDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      {transitionSlug && (
        <TransitionDialog slug={transitionSlug} transitions={["approve", "reject", "pause", "escalate"]} onClose={() => setTransitionSlug(null)} />
      )}
    </div>
  );
}
