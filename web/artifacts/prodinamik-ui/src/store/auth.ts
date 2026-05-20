import { create } from "zustand";
import { persist } from "zustand/middleware";
import { setBaseUrl, setAuthTokenGetter } from "@workspace/api-client-react";

export type Role = "admin" | "user" | "readonly";

interface AuthState {
  apiKey: string | null;
  baseUrl: string;
  role: Role | null;
  isAuthenticated: boolean;
  login: (key: string, url: string, role: Role) => void;
  logout: () => void;
}

const DEFAULT_BASE_URL = "http://localhost:8000";

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      apiKey: null,
      baseUrl: DEFAULT_BASE_URL,
      role: null,
      isAuthenticated: false,
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
    }),
    {
      name: "pdmk-auth",
      onRehydrateStorage: () => (state) => {
        if (state?.apiKey) {
          setBaseUrl(state.baseUrl ?? DEFAULT_BASE_URL);
          setAuthTokenGetter(() => state.apiKey!);
        }
      },
    }
  )
);
