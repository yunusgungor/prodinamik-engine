import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

/**
 * ResponsiveTable — wraps a table with horizontal scroll for mobile.
 * Use this instead of raw `overflow-hidden` divs so tables scroll on small screens.
 */
export function ResponsiveTable({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("w-full overflow-x-auto", className)}>
      {children}
    </div>
  );
}

/**
 * LoadingSkeleton — consistent loading placeholders.
 * Props:
 * - lines: number of skeleton rows (default 5)
 * - type: "table" (row layout) or "card" (card layout)
 */
export function LoadingSkeleton({
  lines = 5,
  type = "table",
}: {
  lines?: number;
  type?: "table" | "card" | "text";
}) {
  if (type === "card") {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="bg-card border border-card-border rounded-lg p-4 space-y-3">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-8 w-24" />
          </div>
        ))}
      </div>
    );
  }

  if (type === "text") {
    return (
      <div className="p-8 space-y-3">
        {Array.from({ length: lines }).map((_, i) => (
          <Skeleton key={i} className={cn("h-4", i % 2 === 0 ? "w-3/4" : "w-1/2")} />
        ))}
      </div>
    );
  }

  // Table skeleton
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border">
            {Array.from({ length: 4 }).map((_, i) => (
              <th key={i} className="p-3">
                <Skeleton className="h-3 w-16" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: lines }).map((_, i) => (
            <tr key={i} className="border-b border-border/50">
              {Array.from({ length: 4 }).map((_, j) => (
                <td key={j} className="p-3">
                  <Skeleton className={cn("h-4", j === 0 ? "w-32" : "w-20")} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * ConnectionStatusBanner — shown when WebSocket or API connection is lost.
 */
export function ConnectionStatusBanner({
  connected,
  checking,
}: {
  connected: boolean | null;
  checking: boolean;
}) {
  if (checking || connected === true || connected === null) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 animate-in slide-in-from-bottom-2 fade-in duration-200">
      <div className="bg-destructive/90 text-destructive-foreground text-xs px-4 py-2 rounded-lg shadow-lg backdrop-blur-sm flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-destructive-foreground animate-pulse" />
        Engine connection lost. Retrying...
      </div>
    </div>
  );
}
