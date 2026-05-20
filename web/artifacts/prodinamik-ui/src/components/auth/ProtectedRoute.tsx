import { Redirect } from "wouter";
import { useAuthStore } from "@/store/auth";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  if (!isAuthenticated) return <Redirect to="/login" />;
  return <>{children}</>;
}
