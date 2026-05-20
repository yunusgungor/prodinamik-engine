import { create } from "zustand";
import { persist } from "zustand/middleware";
import { setBaseUrl, setAuthTokenGetter } from "@workspace/api-client-react";

export type Role = "admin" | "user" | "readonly";

interface AuthState {
  apiKey: string | null;
  baseUrl: string;
  role: Role | null;
  isAuthenticated: boolean;
  hasHydrated: boolean;
  login: (key: string, url: string, role: Role) => void;
  logout: () => void;
  checkSession: () => Promise<boolean>;
}

const DEFAULT_BASE_URL = typeof window !== 'undefined' ? window.location.origin : "http://localhost:8000";

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      apiKey: null,
      baseUrl: DEFAULT_BASE_URL,
      role: null,
      isAuthenticated: false,
      hasHydrated: false,
      login: (key, url, role) => {
        setBaseUrl(url);
        setAuthTokenGetter(() => key);
        set({ apiKey: key, baseUrl: url, role, isAuthenticated: true });
      },
      logout: () => {
        setBaseUrl(null);
        setAuthTokenGetter(null);
        set({ apiKey: null, role: null, isAuthenticated: false });
      },
      checkSession: async () => {
        const { apiKey, baseUrl, isAuthenticated } = get();
        if (!apiKey || !isAuthenticated) return false;
        try {
          const res = await fetch(`${baseUrl}/api/v1/auth/me`, {
            headers: { Authorization: `Bearer ${apiKey}` },
            signal: AbortSignal.timeout(3000),
          });
          return res.ok;
        } catch {
          // Network error — keep session active, don't force re-login
          return true;
        }
      },
    }),
    {
      name: "pdmk-auth",
      onRehydrateStorage: () => (state) => {
        // After hydration completes, restore API client config
        if (state?.apiKey) {
          setBaseUrl(state.baseUrl ?? DEFAULT_BASE_URL);
          setAuthTokenGetter(() => state.apiKey!);
        }
        // Signal that hydration is complete (next tick for React rendering)
        setTimeout(() => {
          useAuthStore.setState({ hasHydrated: true });
        }, 0);
      },
    }
  )
);
