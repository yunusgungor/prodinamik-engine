import { useState } from "react";
import { ChevronRight, ChevronDown, Download, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useListAuditLog } from "@workspace/api-client-react";
import { MOCK_AUDIT_ENTRIES } from "@/lib/mock-data";
import { format } from "date-fns";

const EVENT_TYPES = [
  "all", "run.created", "run.archived", "run.error",
  "state.transition", "human.approved", "human.rejected",
  "plugin.enabled", "budget.warning", "auth.login", "config.updated",
];

function ExpandableRow({ entry }: { entry: typeof MOCK_AUDIT_ENTRIES[0] }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <TableRow
        className="border-border hover:bg-muted/30 cursor-pointer"
        onClick={() => setOpen(!open)}
        data-testid={`audit-row-${entry.id}`}
      >
        <TableCell className="text-xs font-mono text-muted-foreground pl-4">
          {format(new Date(entry.timestamp), "MMM d HH:mm:ss")}
        </TableCell>
        <TableCell className="text-xs font-mono text-primary">{entry.event_type}</TableCell>
        <TableCell className="text-xs text-muted-foreground">{entry.actor ?? "system"}</TableCell>
        <TableCell className="text-xs text-muted-foreground">{entry.summary}</TableCell>
        <TableCell className="text-xs">
          {open ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
        </TableCell>
      </TableRow>
      {open && (
        <TableRow className="border-border">
          <TableCell colSpan={5} className="bg-muted/20 pl-4 pr-4 pb-3">
            <pre className="text-[11px] font-mono text-muted-foreground overflow-auto max-h-40 pt-2">
              {JSON.stringify(entry.data, null, 2)}
            </pre>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

export default function AuditPage() {
  const [search, setSearch] = useState("");
  const [eventType, setEventType] = useState("all");
  const [limit, setLimit] = useState(50);

  const { data: auditLog } = useListAuditLog({
    event_type: eventType !== "all" ? eventType : undefined,
    limit,
    search: search || undefined,
  });
  const display = auditLog ?? MOCK_AUDIT_ENTRIES;

  const filtered = display.filter((e) => {
    if (search && !e.event_type.includes(search) && !e.summary?.toLowerCase().includes(search.toLowerCase()) && !e.actor?.includes(search)) return false;
    if (eventType !== "all" && e.event_type !== eventType) return false;
    return true;
  });

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(filtered, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "audit-log.json"; a.click();
    URL.revokeObjectURL(url);
  };

  const exportCsv = () => {
    const headers = "timestamp,event_type,actor,summary";
    const rows = filtered.map((e) =>
      [e.timestamp, e.event_type, e.actor ?? "system", `"${(e.summary ?? "").replace(/"/g, '""')}"`].join(",")
    );
    const blob = new Blob([[headers, ...rows].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "audit-log.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Audit Log</h1>
          <p className="text-sm text-muted-foreground">{filtered.length} entries</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={exportJson} data-testid="button-export-json">
            <Download className="w-3.5 h-3.5 mr-1.5" />Export JSON
          </Button>
          <Button variant="outline" size="sm" onClick={exportCsv} data-testid="button-export-csv">
            <Download className="w-3.5 h-3.5 mr-1.5" />Export CSV
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-48 max-w-72">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder="Search events..."
            className="pl-8 h-8 text-sm"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            data-testid="input-search-audit"
          />
        </div>
        <Select value={eventType} onValueChange={setEventType}>
          <SelectTrigger className="h-8 w-44 text-xs" data-testid="select-event-type">
            <SelectValue placeholder="Event type" />
          </SelectTrigger>
          <SelectContent>
            {EVENT_TYPES.map((t) => <SelectItem key={t} value={t}>{t === "all" ? "All events" : t}</SelectItem>)}
          </SelectContent>
        </Select>
        <div className="flex items-center gap-1.5">
          <Label className="text-xs text-muted-foreground">Limit</Label>
          <Select value={String(limit)} onValueChange={(v) => setLimit(Number(v))}>
            <SelectTrigger className="h-8 w-20 text-xs"><SelectValue /></SelectTrigger>
            <SelectContent>
              {[10, 25, 50, 100].map((n) => <SelectItem key={n} value={String(n)}>{n}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        {(search || eventType !== "all") && (
          <Button variant="ghost" size="sm" className="h-8 text-xs" onClick={() => { setSearch(""); setEventType("all"); }}>
            <X className="w-3.5 h-3.5 mr-1" />Reset
          </Button>
        )}
      </div>

      {/* Table */}
      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow className="border-border hover:bg-transparent">
              <TableHead className="text-xs pl-4 w-44">Timestamp</TableHead>
              <TableHead className="text-xs w-48">Event Type</TableHead>
              <TableHead className="text-xs w-40">Actor</TableHead>
              <TableHead className="text-xs">Summary</TableHead>
              <TableHead className="text-xs w-8"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-12">
                  No audit entries found.
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((entry, i) => <ExpandableRow key={i} entry={entry} />)
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
