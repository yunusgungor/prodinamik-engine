import { useState, useEffect, useCallback } from "react";
import { Link, useLocation } from "wouter";
import {
  LayoutDashboard, Play, GitBranch, Activity, FileText, Brain, Puzzle,
  Users, Settings, Shield, Network, Zap, ChevronLeft, ChevronRight,
  LogOut, Sun, Moon, Menu, X, CircleDot, Wifi, WifiOff, Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useAuthStore } from "@/store/auth";
import { useUIStore } from "@/store/ui";
import { cn } from "@/lib/utils";
import { useGetMetrics } from "@workspace/api-client-react";
import { MOCK_METRICS } from "@/lib/mock-data";
import { EngineStatusDot } from "@/components/engine/EngineStatus";
import { ConnectionStatusBanner } from "@/components/shared/ResponsiveTable";
import { useEngineConnection } from "@/hooks/use-websocket";

interface NavItem {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

const NAV_GROUPS: { group: string; items: NavItem[] }[] = [
  {
    group: "Main",
    items: [
      { label: "Dashboard", href: "/", icon: LayoutDashboard },
      { label: "Runs", href: "/runs", icon: Play },
    ],
  },
  {
    group: "Engine",
    items: [
      { label: "State Machine", href: "/state-machine", icon: GitBranch, adminOnly: true },
      { label: "Observability", href: "/observability", icon: Activity },
      { label: "Audit Log", href: "/audit", icon: FileText },
    ],
  },
  {
    group: "Intelligence",
    items: [
      { label: "AI Dashboard", href: "/ai", icon: Brain },
      { label: "Plugins", href: "/plugins", icon: Puzzle },
    ],
  },
  {
    group: "Operations",
    items: [
      { label: "Human Loop", href: "/human-loop", icon: Users },
      { label: "Config", href: "/config", icon: Settings, adminOnly: true },
      { label: "Security", href: "/security", icon: Shield, adminOnly: true },
      { label: "Distribution", href: "/distribution", icon: Network, adminOnly: true },
      { label: "Chaos", href: "/chaos", icon: Zap, adminOnly: true },
    ],
  },
];

function DegradationBadge({ level }: { level?: string }) {
  const colors: Record<string, string> = {
    FULL: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    DEGRADED: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    SURVIVAL: "bg-red-500/20 text-red-400 border-red-500/30",
  };
  const lvl = level ?? "FULL";
  return (
    <span
      className={cn(
        "text-xs px-2 py-0.5 rounded border font-mono font-medium",
        colors[lvl] ?? colors.FULL
      )}
    >
      {lvl}
    </span>
  );
}

function HealthDot({ score }: { score?: number }) {
  const s = score ?? 100;
  const color =
    s >= 80 ? "text-emerald-400" : s >= 50 ? "text-amber-400" : "text-red-400";
  return <CircleDot className={cn("w-3.5 h-3.5", color)} />;
}

/**
 * Responsive table wrapper — horizontal scroll on mobile.
 * Wrap any <Table> with this component.
 */
export function ResponsiveTableWrapper({
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
 * Mobile drawer overlay for sidebar
 */
function MobileNavOverlay({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [location] = useLocation();
  const { logout, baseUrl, role } = useAuthStore();
  const { theme, setTheme } = useUIStore();
  const { data: metrics } = useGetMetrics({
    query: { refetchInterval: 30_000 } as any,
  });
  const displayMetrics = metrics ?? MOCK_METRICS;

  const isActive = (href: string) =>
    href === "/" ? location === "/" : location.startsWith(href);

  // Close on navigation
  useEffect(() => {
    onClose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location]);

  return (
    <>
      {/* Backdrop */}
      {open && (
        <div
          className="fixed inset-0 bg-black/50 z-40 md:hidden"
          onClick={onClose}
        />
      )}
      {/* Drawer */}
      <aside
        className={cn(
          "fixed top-0 left-0 h-full w-64 z-50 bg-sidebar border-r border-sidebar-border",
          "flex flex-col transition-transform duration-200 ease-in-out md:hidden",
          open ? "translate-x-0" : "-translate-x-full"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between h-12 px-3 border-b border-sidebar-border shrink-0">
          <span className="text-sidebar-foreground font-semibold text-sm tracking-tight">
            Prodinamik
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-sidebar-foreground/60 hover:text-sidebar-foreground"
            onClick={onClose}
          >
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Nav */}
        <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.group}>
              <p className="text-sidebar-foreground/40 text-[10px] font-semibold uppercase tracking-wider px-2 mb-1">
                {group.group}
              </p>
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(item.href);
                  return (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        className={cn(
                          "flex items-center gap-2.5 px-2 py-1.5 rounded text-sm font-medium transition-colors",
                          active
                            ? "bg-sidebar-primary text-sidebar-primary-foreground"
                            : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground"
                        )}
                      >
                        <Icon className="w-4 h-4 shrink-0" />
                        <span className="truncate">{item.label}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* Bottom */}
        <div className="border-t border-sidebar-border p-2 space-y-0.5 shrink-0">
          <div className="px-2 py-1.5 flex items-center gap-2 text-xs text-sidebar-foreground/60">
            <HealthDot score={displayMetrics.health_score} />
            <DegradationBadge level={displayMetrics.degradation_level} />
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start gap-2 text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent"
            onClick={logout}
          >
            <LogOut className="w-4 h-4 shrink-0" />
            Sign out
          </Button>
        </div>
      </aside>
    </>
  );
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [location, setLocation] = useLocation();
  const { logout, baseUrl, role } = useAuthStore();
  const { theme, setTheme, sidebarCollapsed, toggleSidebar } = useUIStore();
  const { data: metrics } = useGetMetrics({
    query: { refetchInterval: 30_000 } as any,
  });
  const displayMetrics = metrics ?? MOCK_METRICS;

  const { connected, checking } = useEngineConnection();

  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  // Track keyboard shortcut dialog
  const [shortcutsOpen, setShortcutsOpen] = useState(false);

  const isActive = (href: string) =>
    href === "/" ? location === "/" : location.startsWith(href);

  // ── Keyboard shortcuts ──
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't trigger when typing in inputs
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      // Ctrl+K or Cmd+K → search (navigate to /runs)
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setLocation("/runs");
        return;
      }
      // ? → show shortcuts
      if (e.key === "?" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        setShortcutsOpen((p) => !p);
        return;
      }
      // g then d → dashboard
      if (e.key === "d" && !e.metaKey && !e.ctrlKey && !e.shiftKey) {
        // Only if no other modifier pressed
        return;
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [setLocation]);

  // ── Dynamic document title ──
  useEffect(() => {
    const path = location || "/";
    const titles: Record<string, string> = {
      "/": "Dashboard",
      "/runs": "Runs",
      "/observability": "Observability",
      "/audit": "Audit Log",
      "/state-machine": "State Machine",
      "/ai": "AI Dashboard",
      "/plugins": "Plugins",
      "/human-loop": "Human Loop",
      "/config": "Configuration",
      "/security": "Security",
      "/distribution": "Distribution",
      "/chaos": "Chaos Engineering",
    };
    const title = titles[path] || "Prodinamik Engine";
    document.title = `${title} · Prodinamik Engine v1.3`;
  }, [location]);

  /* ... */
  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Desktop sidebar */}
      <aside
        className={cn(
          "hidden md:flex flex-col bg-sidebar border-r border-sidebar-border transition-all duration-200 shrink-0",
          sidebarCollapsed ? "w-14" : "w-56"
        )}
      >
        {/* Logo / header */}
        <div
          className={cn(
            "flex items-center border-b border-sidebar-border h-12 px-3 shrink-0",
            sidebarCollapsed ? "justify-center" : "justify-between"
          )}
        >
          {!sidebarCollapsed && (
            <span className="text-sidebar-foreground font-semibold text-sm tracking-tight">
              Prodinamik
            </span>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent"
            onClick={toggleSidebar}
            data-testid="button-toggle-sidebar"
          >
            {sidebarCollapsed ? (
              <ChevronRight className="w-4 h-4" />
            ) : (
              <ChevronLeft className="w-4 h-4" />
            )}
          </Button>
        </div>

        {/* Nav groups */}
        <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-4">
          {NAV_GROUPS.map((group) => (
            <div key={group.group}>
              {!sidebarCollapsed && (
                <p className="text-sidebar-foreground/40 text-[10px] font-semibold uppercase tracking-wider px-2 mb-1">
                  {group.group}
                </p>
              )}
              <ul className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(item.href);
                  const navLink = (
                    <Link
                      href={item.href}
                      className={cn(
                        "flex items-center gap-2.5 px-2 py-1.5 rounded text-sm font-medium transition-colors",
                        active
                          ? "bg-sidebar-primary text-sidebar-primary-foreground"
                          : "text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground",
                        sidebarCollapsed && "justify-center px-2"
                      )}
                      data-testid={`nav-${item.href.replace("/", "").replace("-", "") || "dashboard"}`}
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
                    </Link>
                  );
                  return (
                    <li key={item.href}>
                      {sidebarCollapsed ? (
                        <Tooltip>
                          <TooltipTrigger asChild>{navLink}</TooltipTrigger>
                          <TooltipContent side="right">
                            {item.label}
                          </TooltipContent>
                        </Tooltip>
                      ) : (
                        navLink
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        {/* Bottom actions */}
        <div
          className={cn(
            "border-t border-sidebar-border p-2 space-y-0.5 shrink-0",
            sidebarCollapsed && "flex flex-col items-center"
          )}
        >
          <Button
            variant="ghost"
            size={sidebarCollapsed ? "icon" : "sm"}
            className={cn(
              "text-sidebar-foreground/60 hover:text-sidebar-foreground hover:bg-sidebar-accent",
              !sidebarCollapsed && "w-full justify-start gap-2"
            )}
            onClick={logout}
            data-testid="button-logout"
          >
            <LogOut className="w-4 h-4 shrink-0" />
            {!sidebarCollapsed && "Sign out"}
          </Button>
        </div>
      </aside>

      {/* Mobile nav overlay */}
      <MobileNavOverlay open={mobileNavOpen} onClose={() => setMobileNavOpen(false)} />

      {/* Main */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Top bar */}
        <header className="h-12 border-b border-border flex items-center px-4 gap-3 shrink-0 bg-background">
          {/* Mobile menu button */}
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 md:hidden text-muted-foreground hover:text-foreground"
            onClick={() => setMobileNavOpen(true)}
            data-testid="button-mobile-menu"
          >
            <Menu className="w-4 h-4" />
          </Button>

          <EngineStatusDot />

          <div className="flex items-center gap-2 flex-1 min-w-0">
            <HealthDot score={displayMetrics.health_score} />
            <DegradationBadge level={displayMetrics.degradation_level} />
            <span className="text-xs text-muted-foreground font-mono hidden sm:inline truncate max-w-32 lg:max-w-48">
              {useAuthStore.getState().baseUrl}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {/* Keyboard shortcut hint */}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 text-muted-foreground/50 hover:text-muted-foreground hidden sm:inline-flex"
                  onClick={() => setShortcutsOpen((p) => !p)}
                >
                  <kbd className="text-[10px] font-mono font-bold border border-border rounded px-1">
                    ?
                  </kbd>
                </Button>
              </TooltipTrigger>
              <TooltipContent>Keyboard shortcuts</TooltipContent>
            </Tooltip>

            <Badge
              variant="outline"
              className="text-xs font-mono capitalize hidden xs:inline-flex"
            >
              {role ?? "readonly"}
            </Badge>

            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              data-testid="button-theme-toggle"
            >
              {theme === "dark" ? (
                <Sun className="w-4 h-4" />
              ) : (
                <Moon className="w-4 h-4" />
              )}
            </Button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>

      {/* Keyboard shortcuts dialog */}
      {shortcutsOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
          onClick={() => setShortcutsOpen(false)}
        >
          <div
            className="bg-card border border-card-border rounded-lg p-6 max-w-sm w-full mx-4 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-sm font-bold mb-4">Keyboard Shortcuts</h3>
            <div className="space-y-2 text-sm">
              {[
                { keys: "Ctrl+K", action: "Search / Go to Runs" },
                { keys: "?", action: "Toggle shortcuts" },
                { keys: "Esc", action: "Close dialogs" },
              ].map(({ keys, action }) => (
                <div
                  key={keys}
                  className="flex items-center justify-between"
                >
                  <kbd className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded border border-border">
                    {keys}
                  </kbd>
                  <span className="text-xs text-muted-foreground">
                    {action}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Connection status banner */}
      <ConnectionStatusBanner connected={connected} checking={checking} />
    </div>
  );
}
