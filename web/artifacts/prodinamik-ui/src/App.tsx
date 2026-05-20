import { Switch, Route, Router as WouterRouter } from "wouter";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AppLayout } from "@/components/layout/AppLayout";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { AdminRoute } from "@/components/auth/AdminRoute";
import { useUIStore } from "@/store/ui";

import LoginPage from "@/pages/LoginPage";
import DashboardPage from "@/pages/DashboardPage";
import RunsPage from "@/pages/RunsPage";
import RunDetailPage from "@/pages/RunDetailPage";
import StateMachinePage from "@/pages/StateMachinePage";
import ObservabilityPage from "@/pages/ObservabilityPage";
import AuditPage from "@/pages/AuditPage";
import AIDashboardPage from "@/pages/AIDashboardPage";
import PluginsPage from "@/pages/PluginsPage";
import HumanLoopPage from "@/pages/HumanLoopPage";
import ConfigPage from "@/pages/ConfigPage";
import SecurityPage from "@/pages/SecurityPage";
import DistributionPage from "@/pages/DistributionPage";
import ChaosPage from "@/pages/ChaosPage";
import NotFoundPage from "@/pages/not-found";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 10000,
      refetchOnWindowFocus: false,
    },
  },
});

function AppInitializer({ children }: { children: React.ReactNode }) {
  const { theme, setTheme } = useUIStore();
  useEffect(() => {
    // Apply stored theme on mount
    setTheme(theme);
  }, []);
  return <>{children}</>;
}

function ProtectedLayout({ children }: { children: React.ReactNode }) {
  return (
    <ProtectedRoute>
      <AppLayout>{children}</AppLayout>
    </ProtectedRoute>
  );
}

function Router() {
  return (
    <Switch>
      <Route path="/login" component={LoginPage} />
      <Route path="/new-run">
        <ProtectedLayout><DashboardPage initialCreateRun /></ProtectedLayout>
      </Route>
      <Route path="/">
        <ProtectedLayout><DashboardPage /></ProtectedLayout>
      </Route>
      <Route path="/runs">
        <ProtectedLayout><RunsPage /></ProtectedLayout>
      </Route>
      <Route path="/runs/:slug">
        {(params) => (
          <ProtectedLayout><RunDetailPage slug={params.slug} /></ProtectedLayout>
        )}
      </Route>
      <Route path="/state-machine">
        <ProtectedLayout><AdminRoute><StateMachinePage /></AdminRoute></ProtectedLayout>
      </Route>
      <Route path="/observability">
        <ProtectedLayout><ObservabilityPage /></ProtectedLayout>
      </Route>
      <Route path="/audit">
        <ProtectedLayout><AuditPage /></ProtectedLayout>
      </Route>
      <Route path="/ai">
        <ProtectedLayout><AIDashboardPage /></ProtectedLayout>
      </Route>
      <Route path="/plugins">
        <ProtectedLayout><PluginsPage /></ProtectedLayout>
      </Route>
      <Route path="/human-loop">
        <ProtectedLayout><HumanLoopPage /></ProtectedLayout>
      </Route>
      <Route path="/config">
        <ProtectedLayout><AdminRoute><ConfigPage /></AdminRoute></ProtectedLayout>
      </Route>
      <Route path="/security">
        <ProtectedLayout><AdminRoute><SecurityPage /></AdminRoute></ProtectedLayout>
      </Route>
      <Route path="/distribution">
        <ProtectedLayout><AdminRoute><DistributionPage /></AdminRoute></ProtectedLayout>
      </Route>
      <Route path="/chaos">
        <ProtectedLayout><AdminRoute><ChaosPage /></AdminRoute></ProtectedLayout>
      </Route>
      {/* Catch-all: 404 */}
      <Route>
        <ProtectedLayout><NotFoundPage /></ProtectedLayout>
      </Route>
    </Switch>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <AppInitializer>
            <Router />
          </AppInitializer>
        </WouterRouter>
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
