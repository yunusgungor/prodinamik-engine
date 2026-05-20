/**
 * Engine bağlantı durumu göstergesi bileşeni.
 * Sidebar'da ve üst çubukta kullanılır.
 */

import { useEngineConnection } from "@/hooks/use-websocket";
import { cn } from "@/lib/utils";
import { useEffect, useState } from "react";

export function EngineStatusDot({ className }: { className?: string }) {
  const { connected, checking, healthCheck } = useEngineConnection();
  const [label, setLabel] = useState("Connecting...");

  useEffect(() => {
    if (checking) setLabel("Checking...");
    else if (connected) setLabel("Engine Online");
    else setLabel("Engine Offline (Mock)");
  }, [connected, checking]);

  return (
    <div
      className={cn("flex items-center gap-1.5 cursor-help", className)}
      onClick={healthCheck}
      title={`Engine status: ${label}`}
    >
      <div
        className={cn(
          "w-2 h-2 rounded-full transition-colors duration-300",
          checking && "bg-muted-foreground animate-pulse",
          !checking && connected && "bg-emerald-400",
          !checking && !connected && "bg-amber-400"
        )}
      />
      <span className="text-[11px] text-muted-foreground font-mono hidden sm:inline">
        {checking ? "..." : connected ? "Online" : "Mock"}
      </span>
    </div>
  );
}
