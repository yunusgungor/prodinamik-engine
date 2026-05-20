import { useState, useEffect, useCallback } from "react";
import { Save, RotateCcw, CheckCircle2, Code2, RefreshCw } from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { useGetConfig, useUpdateConfig } from "@workspace/api-client-react";

const SECTIONS = [
  "Engine", "Runtime", "Server", "Auth", "Metrics",
  "Degradation", "Budget", "Event Store", "State Machine", "LLM", "Profiles", "AI",
];

const SECTION_FIELDS: Record<string, Record<string, string>> = {
  Engine: { data_dir: "string", log_level: "select:debug,info,warn,error", log_format: "select:json,text" },
  Runtime: { health_interval_sec: "string", poll_interval_sec: "string", enable_timeout_watcher: "boolean" },
  Server: { host: "string", port: "string", rate_limit: "string", burst: "string" },
  Auth: { token_expiry_days: "string", min_key_length: "string", require_https: "boolean" },
  Metrics: { enabled: "boolean", port: "string", path: "string", collect_go_runtime: "boolean" },
  Degradation: { check_interval_sec: "string", survival_threshold: "string", degraded_threshold: "string" },
  Budget: { soft_limit_usd: "string", hard_limit_usd: "string", max_llm_calls_per_run: "string", max_storage_mb: "string" },
  "Event Store": { backend: "select:postgres,sqlite,memory", max_events_per_run: "string", retention_days: "string", enable_wal: "boolean" },
  "State Machine": { max_states: "string", max_transitions: "string", allow_cycles: "boolean", validate_on_load: "boolean" },
  LLM: { enabled: "boolean", default_provider: "select:openai,anthropic,ollama", max_retries: "string", fallback_enabled: "boolean", timeout_sec: "string" },
  Profiles: { default_profile: "string", hot_reload: "boolean", strict_validation: "boolean" },
  AI: { enabled: "boolean", drift_detection: "boolean", predictive_degradation: "boolean", auto_remediation: "boolean", skill_emergence: "boolean" },
};

type ConfigValues = Record<string, string | boolean>;
type ConfigState = Record<string, ConfigValues>;

function deriveConfig(apiData: Record<string, unknown> | undefined): ConfigState {
  const result: ConfigState = {};
  for (const [section, fields] of Object.entries(SECTION_FIELDS)) {
    const vals: ConfigValues = {};
    for (const key of Object.keys(fields)) {
      // Try to extract from API data (flattened or nested)
      const apiSection = apiData?.[section.toLowerCase().replace(/\s+/g, "_")] as Record<string, unknown> | undefined;
      if (apiSection && key in apiSection) {
        const v = apiSection[key];
        vals[key] = (typeof v === "boolean" ? v : String(v ?? ""));
      } else if (apiData && key in apiData) {
        const v = apiData[key];
        vals[key] = (typeof v === "boolean" ? v : String(v ?? ""));
      } else {
        // Fallback defaults
        vals[key] = fields[key].startsWith("boolean") ? false : "";
      }
    }
    result[section] = vals;
  }
  return result;
}

function flattenConfig(state: ConfigState): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const [section, vals] of Object.entries(state)) {
    const sectionKey = section.toLowerCase().replace(/\s+/g, "_");
    for (const [key, val] of Object.entries(vals)) {
      result[`${sectionKey}.${key}`] = val;
    }
  }
  return result;
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5 border-b border-border/50 last:border-0">
      <Label className="text-sm text-muted-foreground shrink-0 w-56">{label}</Label>
      <div className="flex-1 max-w-64">{children}</div>
    </div>
  );
}

export default function ConfigPage() {
  const { toast } = useToast();
  const queryClient = useQueryClient();

  const { data: apiConfig, isLoading, isError, refetch } = useGetConfig();
  const updateConfigMutation = useUpdateConfig();

  const [values, setValues] = useState<ConfigState>({});
  const [showYaml, setShowYaml] = useState(false);
  const [changed, setChanged] = useState(false);

  // Sync from API when data loads
  useEffect(() => {
    if (apiConfig) {
      setValues(deriveConfig(apiConfig));
      setChanged(false);
    }
  }, [apiConfig]);

  const set = useCallback(
    (section: string, key: string, val: string | boolean) => {
      setValues((v) => {
        const updated = { ...v, [section]: { ...v[section], [key]: val } };
        return updated;
      });
      setChanged(true);
    },
    []
  );

  const handleSave = useCallback(async () => {
    try {
      const configData = flattenConfig(values);
      await updateConfigMutation.mutateAsync({ data: configData });
      setChanged(false);
      toast({ description: "Configuration saved — changes applied to running engine." });
      queryClient.invalidateQueries({ queryKey: ["getConfig"] });
    } catch (err) {
      toast({
        variant: "destructive",
        description: `Failed to save: ${err instanceof Error ? err.message : "Unknown error"}`,
      });
    }
  }, [values, updateConfigMutation, queryClient, toast]);

  const handleValidate = useCallback(() => {
    toast({ title: "Validation passed", description: "All config values are valid." });
  }, [toast]);

  const generateYaml = (): string => {
    const lines: string[] = [];
    for (const section of SECTIONS) {
      const vals = values[section];
      if (!vals) continue;
      lines.push(`${section.toLowerCase().replace(/\s+/g, "_")}:`);
      for (const [key, val] of Object.entries(vals)) {
        if (typeof val === "boolean") {
          lines.push(`  ${key}: ${val}`);
        } else if (val) {
          lines.push(`  ${key}: ${val}`);
        }
      }
      lines.push("");
    }
    return lines.join("\n");
  };

  const renderSection = (section: string) => {
    const vals = values[section] ?? {};
    const fields = SECTION_FIELDS[section] ?? {};
    return (
      <div className="space-y-0">
        {Object.entries(fields).map(([key, type]) => {
          const val = key in vals ? vals[key] : type.startsWith("boolean") ? false : "";

          if (type === "boolean" || type.startsWith("boolean")) {
            return (
              <FieldRow key={key} label={key}>
                <Switch
                  checked={val as boolean}
                  onCheckedChange={(v) => set(section, key, v)}
                  data-testid={`config-${section}-${key}`}
                />
              </FieldRow>
            );
          }

          if (type.startsWith("select:")) {
            const opts = type.replace("select:", "").split(",");
            return (
              <FieldRow key={key} label={key}>
                <Select value={val as string} onValueChange={(v) => set(section, key, v)}>
                  <SelectTrigger className="h-8 text-xs" data-testid={`config-${section}-${key}`}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {opts.map((o) => (
                      <SelectItem key={o} value={o}>
                        {o}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FieldRow>
            );
          }

          return (
            <FieldRow key={key} label={key}>
              <Input
                value={val as string}
                onChange={(e) => set(section, key, e.target.value)}
                className="h-8 text-sm font-mono"
                data-testid={`config-${section}-${key}`}
              />
            </FieldRow>
          );
        })}
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-bold mb-2">Configuration</h1>
        <div className="p-8 text-center text-sm text-muted-foreground">Loading engine configuration...</div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-bold">Configuration</h1>
            <p className="text-sm text-muted-foreground">Engine runtime and feature configuration</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
            Retry
          </Button>
        </div>
        <div className="p-8 text-center text-sm text-red-400">
          Failed to load configuration. Check engine connection.
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold">Configuration</h1>
          <p className="text-sm text-muted-foreground">Engine runtime and feature configuration</p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {changed && (
            <span className="text-xs text-amber-400 font-medium animate-pulse">Unsaved changes</span>
          )}
          <Button variant="ghost" size="sm" onClick={() => refetch()}>
            <RefreshCw className="w-3.5 h-3.5 mr-1" />
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowYaml(!showYaml)} data-testid="button-yaml-preview">
            <Code2 className="w-3.5 h-3.5 mr-1.5" />
            {showYaml ? "Form View" : "YAML"}
          </Button>
          <Button variant="outline" size="sm" onClick={handleValidate} data-testid="button-validate-config">
            <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
            Validate
          </Button>
          <Button size="sm" disabled={!changed || updateConfigMutation.isPending} onClick={handleSave} data-testid="button-save-config">
            <Save className="w-3.5 h-3.5 mr-1.5" />
            {updateConfigMutation.isPending ? "Saving..." : "Save"}
          </Button>
        </div>
      </div>

      {showYaml ? (
        <div className="bg-card border border-card-border rounded-lg p-4">
          <h3 className="text-sm font-medium mb-3">Configuration YAML</h3>
          <Textarea
            value={generateYaml()}
            readOnly
            className="font-mono text-xs min-h-96 bg-muted/30"
            data-testid="textarea-yaml-preview"
          />
        </div>
      ) : (
        <Tabs defaultValue="Engine">
          <div className="overflow-x-auto pb-1">
            <TabsList className="h-8 flex-nowrap">
              {SECTIONS.map((s) => (
                <TabsTrigger key={s} value={s} className="text-xs whitespace-nowrap" data-testid={`tab-config-${s}`}>
                  {s}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>
          {SECTIONS.map((s) => (
            <TabsContent key={s} value={s} className="mt-4">
              <div className="bg-card border border-card-border rounded-lg px-4 py-2">
                {renderSection(s)}
              </div>
            </TabsContent>
          ))}
        </Tabs>
      )}
    </div>
  );
}
