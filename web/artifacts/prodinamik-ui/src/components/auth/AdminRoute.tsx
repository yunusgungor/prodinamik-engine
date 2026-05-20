import { useAuthStore } from "@/store/auth";
import { ShieldX } from "lucide-react";

export function AdminRoute({ children }: { children: React.ReactNode }) {
  const role = useAuthStore((s) => s.role);
  if (role !== "admin") {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-muted-foreground">
        <ShieldX className="w-12 h-12" />
        <p className="text-lg font-medium">Insufficient permissions</p>
        <p className="text-sm">This page requires admin access.</p>
      </div>
    );
  }
  return <>{children}</>;
}
