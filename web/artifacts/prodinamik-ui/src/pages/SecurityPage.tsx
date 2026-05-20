import { useState, useCallback } from "react";
import { KeyRound, Copy, Trash2, Shield, Plus, RefreshCw } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  useListAuthKeys,
  useCreateAuthKey,
  useRevokeAuthKey,
  useGetRateLimitStats,
  type APIKeyInfo,
} from "@workspace/api-client-react";

const ROLE_COLORS: Record<string, string> = {
  admin: "text-red-400 border-red-500/30 bg-red-500/10",
  user: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  readonly: "text-slate-400 border-slate-500/30 bg-slate-500/10",
};

const STATUS_COLORS: Record<string, string> = {
  active: "bg-emerald-400",
  expired: "bg-red-400",
  revoked: "bg-slate-400",
};

function copyToClipboard(text: string): Promise<boolean> {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).then(() => true).catch(() => false);
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand("copy");
    return Promise.resolve(true);
  } catch {
    return Promise.resolve(false);
  } finally {
    document.body.removeChild(ta);
  }
}

export default function SecurityPage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Real API hooks
  const { data: keys = [], isLoading, isError, refetch } = useListAuthKeys();
  const { data: rateLimitStats } = useGetRateLimitStats();
  const createAuthKeyMutation = useCreateAuthKey();
  const revokeAuthKeyMutation = useRevokeAuthKey();

  // Form state
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyRole, setNewKeyRole] = useState("user");
  const [newKeyExpiry, setNewKeyExpiry] = useState("365");
  const [createdKeyResult, setCreatedKeyResult] = useState<{
    name: string;
    role: string;
    key: string;
    id: string;
  } | null>(null);

  const handleCreateKey = useCallback(async () => {
    if (!newKeyName.trim()) return;
    try {
      const result = await createAuthKeyMutation.mutateAsync({
        data: {
          name: newKeyName.trim(),
          role: newKeyRole,
          expires_in_days: Number(newKeyExpiry),
        },
      });
      setCreatedKeyResult({
        name: result.name,
        role: result.role,
        key: result.key,
        id: result.id,
      });
      setNewKeyName("");
      queryClient.invalidateQueries({ queryKey: ["listAuthKeys"] });
    } catch (err) {
      toast({
        variant: "destructive",
        description: `Failed to create key: ${err instanceof Error ? err.message : "Unknown error"}`,
      });
    }
  }, [newKeyName, newKeyRole, newKeyExpiry, createAuthKeyMutation, queryClient, toast]);

  const handleRevokeKey = useCallback(
    async (keyId: string) => {
      try {
        await revokeAuthKeyMutation.mutateAsync({ keyId });
        toast({ description: "API key revoked." });
        queryClient.invalidateQueries({ queryKey: ["listAuthKeys"] });
      } catch (err) {
        toast({
          variant: "destructive",
          description: `Failed to revoke key: ${err instanceof Error ? err.message : "Unknown error"}`,
        });
      }
    },
    [revokeAuthKeyMutation, queryClient, toast]
  );

  const handleCopyKey = useCallback(
    async (text: string, label: string) => {
      const ok = await copyToClipboard(text);
      if (ok) {
        toast({ description: `${label} copied to clipboard.` });
      } else {
        toast({ variant: "destructive", description: "Failed to copy." });
      }
    },
    [toast]
  );

  const getKeyStatus = (key: APIKeyInfo): "active" | "expired" | "revoked" => {
    if (!key.enabled) return "revoked";
    if (key.expires_at && new Date(key.expires_at) < new Date()) return "expired";
    return "active";
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-2">
        <Shield className="w-5 h-5 text-muted-foreground" />
        <div>
          <h1 className="text-xl font-bold">Security</h1>
          <p className="text-sm text-muted-foreground">API key management, RBAC, and rate limits</p>
        </div>
      </div>

      {/* Create key */}
      <Card className="border-card-border">
        <CardHeader className="pb-2 pt-4 px-4">
          <CardTitle className="text-sm font-medium">Create API Key</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <div className="flex gap-2 flex-wrap">
            <Input
              placeholder="Key name (e.g. CI/CD Pipeline)"
              className="h-8 text-sm flex-1 min-w-48"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              data-testid="input-new-key-name"
            />
            <Select value={newKeyRole} onValueChange={setNewKeyRole}>
              <SelectTrigger className="h-8 w-32 text-xs" data-testid="select-key-role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">admin</SelectItem>
                <SelectItem value="user">user</SelectItem>
                <SelectItem value="readonly">readonly</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex items-center gap-2">
              <Label className="text-xs text-muted-foreground whitespace-nowrap">Expires in</Label>
              <Select value={newKeyExpiry} onValueChange={setNewKeyExpiry}>
                <SelectTrigger className="h-8 w-24 text-xs" data-testid="select-key-expiry">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {[7, 30, 90, 180, 365].map((d) => (
                    <SelectItem key={d} value={String(d)}>
                      {d}d
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              size="sm"
              className="h-8 shrink-0"
              disabled={!newKeyName.trim() || createAuthKeyMutation.isPending}
              onClick={handleCreateKey}
              data-testid="button-create-key"
            >
              <Plus className="w-3.5 h-3.5 mr-1.5" />
              {createAuthKeyMutation.isPending ? "Creating..." : "Create Key"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Keys table */}
      <Card className="border-card-border">
        <CardHeader className="pb-2 pt-4 px-4 flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-medium">
            API Keys ({isLoading ? "..." : keys.length})
          </CardTitle>
          <Button variant="ghost" size="sm" className="h-7 text-xs" onClick={() => refetch()}>
            <RefreshCw className="w-3 h-3 mr-1" />
            Refresh
          </Button>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          {isLoading ? (
            <div className="p-8 text-center text-sm text-muted-foreground">Loading API keys...</div>
          ) : isError ? (
            <div className="p-8 text-center text-sm text-red-400">Failed to load API keys. Check connection.</div>
          ) : keys.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No API keys found. Create one above.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-border hover:bg-transparent">
                  <TableHead className="text-xs pl-4">Name</TableHead>
                  <TableHead className="text-xs">ID</TableHead>
                  <TableHead className="text-xs">Role</TableHead>
                  <TableHead className="text-xs">Created</TableHead>
                  <TableHead className="text-xs">Expires</TableHead>
                  <TableHead className="text-xs">Last Used</TableHead>
                  <TableHead className="text-xs">Status</TableHead>
                  <TableHead className="text-xs w-24"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.map((key) => {
                  const status = getKeyStatus(key);
                  return (
                    <TableRow
                      key={key.id}
                      className="border-border hover:bg-muted/30"
                      data-testid={`key-row-${key.id}`}
                    >
                      <TableCell className="text-sm font-medium pl-4">{key.name}</TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        {key.id}
                      </TableCell>
                      <TableCell>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded border font-mono font-medium ${ROLE_COLORS[key.role] ?? ""}`}
                        >
                          {key.role}
                        </span>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {format(new Date(key.created_at), "MMM d, yyyy")}
                      </TableCell>
                      <TableCell
                        className={`text-xs font-mono ${status === "expired" ? "text-red-400" : "text-muted-foreground"}`}
                      >
                        {key.expires_at
                          ? format(new Date(key.expires_at), "MMM d, yyyy")
                          : "—"}
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {key.last_used
                          ? format(new Date(key.last_used), "MMM d, HH:mm")
                          : "—"}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <div
                            className={`w-1.5 h-1.5 rounded-full ${STATUS_COLORS[status] ?? "bg-slate-400"}`}
                          />
                          <span className="text-xs text-muted-foreground capitalize">{status}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={() => handleCopyKey(key.id, "Key ID")}
                            data-testid={`button-copy-${key.id}`}
                          >
                            <Copy className="w-3 h-3" />
                          </Button>
                          {status === "active" && (
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6 text-red-400 hover:text-red-300"
                              onClick={() => handleRevokeKey(key.id)}
                              data-testid={`button-revoke-${key.id}`}
                            >
                              <Trash2 className="w-3 h-3" />
                            </Button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Rate limits */}
      <Card className="border-card-border">
        <CardHeader className="pb-2 pt-4 px-4">
          <CardTitle className="text-sm font-medium">Rate Limits</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4 grid grid-cols-2 md:grid-cols-4 gap-3">
          {rateLimitStats ? (
            <>
              <div className="border border-border rounded-md p-3">
                <p className="text-xs text-muted-foreground">Rate</p>
                <p className="text-xl font-mono font-bold">{rateLimitStats.rate}/s</p>
                <p className="text-xs text-muted-foreground mt-1">Tokens per second</p>
              </div>
              <div className="border border-border rounded-md p-3">
                <p className="text-xs text-muted-foreground">Burst</p>
                <p className="text-xl font-mono font-bold">{rateLimitStats.burst}</p>
                <p className="text-xs text-muted-foreground mt-1">Max burst size</p>
              </div>
              <div className="border border-border rounded-md p-3">
                <p className="text-xs text-muted-foreground">Allowed</p>
                <p className="text-xl font-mono font-bold text-emerald-400">
                  {rateLimitStats.total_allowed.toLocaleString()}
                </p>
                <p className="text-xs text-muted-foreground mt-1">Total allowed requests</p>
              </div>
              <div className="border border-border rounded-md p-3">
                <p className="text-xs text-muted-foreground">Denied</p>
                <p className="text-xl font-mono font-bold text-red-400">
                  {rateLimitStats.total_denied.toLocaleString()}
                </p>
                <p className="text-xs text-muted-foreground mt-1">Total rate-limited</p>
              </div>
            </>
          ) : (
            <>
              <div className="border border-border rounded-md p-3">
                <p className="text-xs text-muted-foreground">Rate</p>
                <p className="text-xl font-mono font-bold">—</p>
                <p className="text-xs text-muted-foreground mt-1">Connect to engine</p>
              </div>
              <div className="border border-border rounded-md p-3">
                <p className="text-xs text-muted-foreground">Burst</p>
                <p className="text-xl font-mono font-bold">—</p>
                <p className="text-xs text-muted-foreground mt-1">Connect to engine</p>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Generated key modal */}
      {createdKeyResult && (
        <Dialog open onOpenChange={() => setCreatedKeyResult(null)}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <KeyRound className="w-4 h-4" />
                New API Key Generated
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-md p-3">
                <p className="text-xs text-amber-400">
                  Copy this key now — it will not be shown again.
                </p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Name</p>
                <p className="text-sm font-medium">{createdKeyResult.name}</p>
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Key</p>
                <code className="block text-xs font-mono bg-muted rounded-md p-3 break-all select-all">
                  {createdKeyResult.key}
                </code>
              </div>
              <Button
                className="w-full"
                onClick={() => {
                  handleCopyKey(createdKeyResult.key, "API Key");
                  setCreatedKeyResult(null);
                }}
                data-testid="button-copy-generated-key"
              >
                <Copy className="w-4 h-4 mr-2" />
                Copy and Close
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
