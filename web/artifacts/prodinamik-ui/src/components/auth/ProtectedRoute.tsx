import { useEffect, useState } from "react";
import { Redirect } from "wouter";
import { useAuthStore } from "@/store/auth";
import { Loader2 } from "lucide-react";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const hasHydrated = useAuthStore((s) => s.hasHydrated);
  const [checking, setChecking] = useState(false);
  const [sessionOk, setSessionOk] = useState<boolean | null>(null);

  // Wait for zustand persist to rehydrate before checking auth
  useEffect(() => {
    if (!hasHydrated) return;
    if (!isAuthenticated) {
      setSessionOk(false);
      return;
    }
    // Optional: verify session with backend (silent)
    const verify = async () => {
      setChecking(true);
      const ok = await useAuthStore.getState().checkSession();
      setSessionOk(ok);
      setChecking(false);
    };
    verify();
  }, [hasHydrated, isAuthenticated]);

  // Not hydrated yet — show loading
  if (!hasHydrated) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <div className="text-center">
          <Loader2 className="w-6 h-6 animate-spin mx-auto text-primary" />
          <p className="text-xs text-muted-foreground mt-2">Restoring session...</p>
        </div>
      </div>
    );
  }

  // Checking session validity
  if (checking || sessionOk === null) {
    if (!isAuthenticated) return <Redirect to="/login" />;
    // Session is being verified in background — show children anyway
    return <>{children}</>;
  }

  if (!sessionOk) {
    return <Redirect to="/login" />;
  }

  if (!isAuthenticated) {
    return <Redirect to="/login" />;
  }

  return <>{children}</>;
}
