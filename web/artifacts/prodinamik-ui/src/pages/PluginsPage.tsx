import { useState, useCallback } from "react";
import { Search, Package, Star, Download, RefreshCw, Power, PowerOff } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import {
  useListPlugins,
  useListMarketplacePlugins,
  useEnablePlugin,
  useDisablePlugin,
  type PluginInfo,
  type MarketplacePluginInfo,
} from "@workspace/api-client-react";

const TYPE_COLORS: Record<string, string> = {
  VALIDATOR: "text-purple-400 border-purple-500/30 bg-purple-500/10",
  ADAPTER: "text-blue-400 border-blue-500/30 bg-blue-500/10",
  HOOK: "text-orange-400 border-orange-500/30 bg-orange-500/10",
  TOOL: "text-green-400 border-green-500/30 bg-green-500/10",
  PROFILE: "text-teal-400 border-teal-500/30 bg-teal-500/10",
  STORE: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
  UI: "text-indigo-400 border-indigo-500/30 bg-indigo-500/10",
  INTEGRATION: "text-sky-400 border-sky-500/30 bg-sky-500/10",
  LLM_PROVIDER: "text-pink-400 border-pink-500/30 bg-pink-500/10",
  AGENT: "text-red-400 border-red-500/30 bg-red-500/10",
};

const STATUS_COLORS: Record<string, string> = {
  enabled: "bg-emerald-400",
  disabled: "bg-muted-foreground",
  error: "bg-red-400",
};

const CATEGORIES = ["all", "VALIDATOR", "ADAPTER", "HOOK", "TOOL", "INTEGRATION", "LLM_PROVIDER", "AGENT", "STORE"];

export default function PluginsPage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  // Real API hooks
  const { data: plugins = [], isLoading, isError, refetch } = useListPlugins();
  const { data: marketplace = [] } = useListMarketplacePlugins();
  const enablePluginMutation = useEnablePlugin();
  const disablePluginMutation = useDisablePlugin();

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [selectedPlugin, setSelectedPlugin] = useState<PluginInfo | null>(null);

  const installedFiltered = plugins.filter(
    (p) =>
      (!search || p.name.toLowerCase().includes(search.toLowerCase()) || p.id.includes(search)) &&
      (category === "all" || p.type === category)
  );

  const marketplaceFiltered = marketplace.filter(
    (p) =>
      (!search || p.name.toLowerCase().includes(search.toLowerCase())) &&
      (category === "all" || p.type === category)
  );

  const handleTogglePlugin = useCallback(
    async (plugin: PluginInfo) => {
      try {
        if (plugin.status === "enabled") {
          await disablePluginMutation.mutateAsync({ pluginId: plugin.id });
          toast({ description: `Plugin "${plugin.name}" disabled.` });
        } else {
          await enablePluginMutation.mutateAsync({ pluginId: plugin.id });
          toast({ description: `Plugin "${plugin.name}" enabled.` });
        }
        queryClient.invalidateQueries({ queryKey: ["listPlugins"] });
      } catch (err) {
        toast({
          variant: "destructive",
          description: `Failed to toggle plugin: ${err instanceof Error ? err.message : "Unknown error"}`,
        });
      }
    },
    [enablePluginMutation, disablePluginMutation, queryClient, toast]
  );

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Plugins</h1>
          <p className="text-sm text-muted-foreground">Manage installed plugins and browse the marketplace</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()}>
          <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative flex-1 min-w-48 max-w-72">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
          <Input
            placeholder="Search plugins..."
            className="pl-8 h-8 text-sm"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            data-testid="input-search-plugins"
          />
        </div>
        <div className="flex items-center gap-1 flex-wrap">
          {CATEGORIES.map((c) => (
            <button
              key={c}
              className={cn(
                "text-xs px-2.5 py-1 rounded border transition-colors",
                category === c
                  ? "border-primary text-primary bg-primary/10"
                  : "border-border text-muted-foreground hover:border-muted-foreground"
              )}
              onClick={() => setCategory(c)}
              data-testid={`filter-${c}`}
            >
              {c === "all" ? "All" : c}
            </button>
          ))}
        </div>
      </div>

      <Tabs defaultValue="installed">
        <TabsList className="h-8">
          <TabsTrigger value="installed" className="text-xs">
            Installed ({isLoading ? "..." : plugins.length})
          </TabsTrigger>
          <TabsTrigger value="marketplace" className="text-xs">
            Marketplace ({marketplace.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="installed" className="mt-4">
          {isLoading ? (
            <div className="p-8 text-center text-sm text-muted-foreground">Loading installed plugins...</div>
          ) : isError ? (
            <div className="p-8 text-center text-sm text-red-400">Failed to load plugins. Check engine connection.</div>
          ) : installedFiltered.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">No plugins found.</div>
          ) : (
            <div className="border border-border rounded-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow className="border-border hover:bg-transparent">
                    <TableHead className="text-xs pl-4">Name</TableHead>
                    <TableHead className="text-xs">Version</TableHead>
                    <TableHead className="text-xs">Type</TableHead>
                    <TableHead className="text-xs">Status</TableHead>
                    <TableHead className="text-xs w-36"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {installedFiltered.map((plugin) => (
                    <TableRow
                      key={plugin.id}
                      className="border-border hover:bg-muted/30"
                      data-testid={`plugin-row-${plugin.id}`}
                    >
                      <TableCell className="pl-4">
                        <p className="text-sm font-medium">{plugin.name}</p>
                        <p className="text-xs text-muted-foreground font-mono">{plugin.id}</p>
                      </TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">
                        v{plugin.version}
                      </TableCell>
                      <TableCell>
                        <span
                          className={cn(
                            "text-[10px] px-1.5 py-0.5 rounded border font-mono font-medium",
                            TYPE_COLORS[plugin.type] ?? "text-muted-foreground border-border"
                          )}
                        >
                          {plugin.type}
                        </span>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5">
                          <div
                            className={cn(
                              "w-1.5 h-1.5 rounded-full",
                              STATUS_COLORS[plugin.status] ?? "bg-muted-foreground"
                            )}
                          />
                          <span className="text-xs text-muted-foreground capitalize">{plugin.status}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 text-xs px-2"
                            onClick={() => setSelectedPlugin(plugin)}
                          >
                            Info
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className={cn(
                              "h-6 text-xs px-2",
                              plugin.status === "enabled"
                                ? "text-amber-400 hover:text-amber-300"
                                : "text-emerald-400 hover:text-emerald-300"
                            )}
                            onClick={() => handleTogglePlugin(plugin)}
                            disabled={
                              (plugin.status === "enabled" && disablePluginMutation.isPending) ||
                              (plugin.status !== "enabled" && enablePluginMutation.isPending)
                            }
                            data-testid={`button-toggle-plugin-${plugin.id}`}
                          >
                            {plugin.status === "enabled" ? (
                              <>
                                <PowerOff className="w-3 h-3 mr-1" />
                                Disable
                              </>
                            ) : (
                              <>
                                <Power className="w-3 h-3 mr-1" />
                                Enable
                              </>
                            )}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>

        <TabsContent value="marketplace" className="mt-4">
          {marketplaceFiltered.length === 0 ? (
            <div className="p-8 text-center text-sm text-muted-foreground">No marketplace plugins found.</div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {marketplaceFiltered.map((plugin) => (
                <div
                  key={plugin.id}
                  className="bg-card border border-card-border rounded-lg p-4 space-y-3"
                  data-testid={`marketplace-plugin-${plugin.id}`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold">{plugin.name}</p>
                      <span
                        className={cn(
                          "text-[10px] px-1.5 py-0.5 rounded border font-mono font-medium",
                          TYPE_COLORS[plugin.type] ?? "text-muted-foreground border-border"
                        )}
                      >
                        {plugin.type}
                      </span>
                    </div>
                    <span className="text-xs text-muted-foreground font-mono">v{plugin.version}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{plugin.description}</p>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1">
                        <Star className="w-3 h-3 text-amber-400" />
                        {plugin.rating}
                      </div>
                      <div className="flex items-center gap-1">
                        <Download className="w-3 h-3" />
                        {plugin.downloads.toLocaleString()}
                      </div>
                    </div>
                    <Button
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => toast({ description: `Installing ${plugin.name}...` })}
                      data-testid={`button-install-${plugin.id}`}
                    >
                      Install
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Plugin info modal */}
      {selectedPlugin && (
        <Dialog open onOpenChange={() => setSelectedPlugin(null)}>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Package className="w-4 h-4" />
                {selectedPlugin.name}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <p className="text-muted-foreground">ID</p>
                  <p className="font-mono">{selectedPlugin.id}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Version</p>
                  <p className="font-mono">v{selectedPlugin.version}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Type</p>
                  <p className="font-mono">{selectedPlugin.type}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Status</p>
                  <p className="font-mono capitalize">{selectedPlugin.status}</p>
                </div>
              </div>
              {selectedPlugin.description && (
                <div>
                  <p className="text-xs text-muted-foreground">Description</p>
                  <p className="text-sm mt-1">{selectedPlugin.description}</p>
                </div>
              )}
              {selectedPlugin.author && (
                <div>
                  <p className="text-xs text-muted-foreground">Author</p>
                  <p className="text-sm font-mono">{selectedPlugin.author}</p>
                </div>
              )}
              {selectedPlugin.dependencies && selectedPlugin.dependencies.length > 0 && (
                <div>
                  <p className="text-xs text-muted-foreground">Dependencies</p>
                  <div className="flex gap-1 flex-wrap mt-1">
                    {selectedPlugin.dependencies.map((d) => (
                      <span
                        key={d}
                        className="text-xs font-mono px-2 py-0.5 border border-border rounded text-muted-foreground"
                      >
                        {d}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex items-center justify-between pt-2 border-t border-border">
                <span className="text-xs text-muted-foreground">Health check</span>
                <div className="flex items-center gap-1.5">
                  <div
                    className={cn(
                      "w-2 h-2 rounded-full",
                      STATUS_COLORS[selectedPlugin.status] ?? "bg-muted-foreground"
                    )}
                  />
                  <span className="text-xs">
                    {selectedPlugin.status === "enabled" ? "Passing" : "Not running"}
                  </span>
                </div>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
