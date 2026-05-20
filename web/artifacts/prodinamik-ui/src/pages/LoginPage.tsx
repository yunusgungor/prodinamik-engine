import { useState, useEffect } from "react";
import { useLocation } from "wouter";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { KeyRound, Server, AlertCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useAuthStore, type Role } from "@/store/auth";

const schema = z.object({
  apiKey: z.string().min(1, "API key is required").startsWith("pdmk_", "API key must start with pdmk_"),
  baseUrl: z.string().url("Must be a valid URL"),
  remember: z.boolean(),
});

type FormData = z.infer<typeof schema>;

export default function LoginPage() {
  const [, setLocation] = useLocation();
  const login = useAuthStore((s) => s.login);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const hasHydrated = useAuthStore((s) => s.hasHydrated);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Redirect if already authenticated (useEffect to avoid render-time setLocation)
  useEffect(() => {
    if (isAuthenticated && hasHydrated) {
      setLocation("/");
    }
  }, [isAuthenticated, hasHydrated, setLocation]);

  // Still hydrating — show loading
  if (!hasHydrated) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center p-4">
        <Loader2 className="w-6 h-6 animate-spin text-primary" />
      </div>
    );
  }

  if (isAuthenticated) {
    return null; // useEffect will handle navigation
  }

  const { register, handleSubmit, formState: { errors }, setValue } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      apiKey: "",
      baseUrl: typeof window !== 'undefined' ? window.location.origin : "http://localhost:8000",
      remember: true,
    },
  });

  const onSubmit = async (data: FormData) => {
    setError(null);
    setLoading(true);
    try {
      // Temporarily set base URL and key for the profile check
      const { setBaseUrl, setAuthTokenGetter } = await import("@workspace/api-client-react");
      setBaseUrl(data.baseUrl);
      setAuthTokenGetter(() => data.apiKey);

      // Try to detect role from /auth/me endpoint
      let role: Role = "user";
      try {
        const meRes = await fetch(`${data.baseUrl}/api/v1/auth/me`, {
          headers: { Authorization: `Bearer ${data.apiKey}` },
        });
        if (!meRes.ok) {
          if (meRes.status === 401 || meRes.status === 403) {
            setError("Invalid API key or insufficient permissions.");
            setLoading(false);
            return;
          }
        } else {
          const meData = await meRes.json();
          role = (meData.role as Role) || "user";
        }
      } catch {
        // Offline mode — still log in with default role
        role = "admin";
      }

      login(data.apiKey, data.baseUrl, role);
      setLocation("/");
    } catch (err) {
      setError("Connection failed. Check your API base URL and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="mb-8 text-center">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-primary/10 border border-primary/20 mb-4">
            <div className="w-6 h-6 rounded bg-primary" />
          </div>
          <h1 className="text-xl font-bold tracking-tight">Prodinamik Engine</h1>
          <p className="text-sm text-muted-foreground mt-1">v1.3 Control Plane</p>
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="bg-card border border-card-border rounded-lg p-5 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="apiKey" className="text-xs font-medium">API Key</Label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <Input
                  id="apiKey"
                  type="password"
                  placeholder="pdmk_xxxxxxxxxxxxxxxxxx"
                  className="pl-9 font-mono text-sm"
                  data-testid="input-api-key"
                  {...register("apiKey")}
                />
              </div>
              {errors.apiKey && (
                <p className="text-xs text-destructive">{errors.apiKey.message}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="baseUrl" className="text-xs font-medium">Engine Base URL</Label>
              <div className="relative">
                <Server className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                <Input
                  id="baseUrl"
                  type="text"
                  placeholder="http://localhost:8000"
                  className="pl-9 font-mono text-sm"
                  data-testid="input-base-url"
                  {...register("baseUrl")}
                />
              </div>
              {errors.baseUrl && (
                <p className="text-xs text-destructive">{errors.baseUrl.message}</p>
              )}
            </div>

            <div className="flex items-center gap-2">
              <Checkbox
                id="remember"
                defaultChecked
                data-testid="checkbox-remember"
                onCheckedChange={(v) => setValue("remember", !!v)}
              />
              <Label htmlFor="remember" className="text-xs text-muted-foreground cursor-pointer">
                Remember credentials
              </Label>
            </div>
          </div>

          {error && (
            <Alert variant="destructive" className="py-2.5">
              <AlertCircle className="w-4 h-4" />
              <AlertDescription className="text-xs">{error}</AlertDescription>
            </Alert>
          )}

          <Button
            type="submit"
            className="w-full"
            disabled={loading}
            data-testid="button-login"
          >
            {loading ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Connecting...</>
            ) : (
              "Connect to Engine"
            )}
          </Button>
        </form>

        <p className="text-center text-xs text-muted-foreground mt-4">
          API key auth via <code className="font-mono">Authorization: Bearer</code>
        </p>
      </div>
    </div>
  );
}
