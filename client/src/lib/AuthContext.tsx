import { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { api, clearTokens, getAccessToken, setTokens, apiErrorMessage } from "./api";
import { Parish, Role, User } from "./types";

interface AuthContextValue {
  user: User | null;
  parish: Parish | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  loginWithGoogle: (idToken: string) => Promise<void>;
  register: (data: { name: string; email: string; password: string; parishName: string }) => Promise<void>;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [parish, setParish] = useState<Parish | null>(null);
  const [loading, setLoading] = useState(true);

  const loadMe = useCallback(async () => {
    try {
      const res = await api.get("/auth/me");
      setUser(res.data.user);
      setParish(res.data.parish);
    } catch {
      setUser(null);
      setParish(null);
      clearTokens();
    }
  }, []);

  useEffect(() => {
    (async () => {
      if (getAccessToken()) {
        await loadMe();
      }
      setLoading(false);
    })();
  }, [loadMe]);

  useEffect(() => {
    const handler = () => {
      setUser(null);
      setParish(null);
      clearTokens();
    };
    window.addEventListener("auth:logout", handler);
    return () => window.removeEventListener("auth:logout", handler);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.post("/auth/login", { email, password });
    setTokens(res.data.accessToken, res.data.refreshToken);
    setUser(res.data.user);
    const parishRes = await api.get("/settings/parish");
    setParish(parishRes.data);
  }, []);

  const loginWithGoogle = useCallback(async (idToken: string) => {
    const res = await api.post("/auth/google", { idToken });
    setTokens(res.data.accessToken, res.data.refreshToken);
    setUser(res.data.user);
    const parishRes = await api.get("/settings/parish");
    setParish(parishRes.data);
  }, []);

  const register = useCallback(
    async (data: { name: string; email: string; password: string; parishName: string }) => {
      const res = await api.post("/auth/register", data);
      setTokens(res.data.accessToken, res.data.refreshToken);
      setUser(res.data.user);
      const parishRes = await api.get("/settings/parish");
      setParish(parishRes.data);
    },
    []
  );

  const logout = useCallback(async () => {
    try {
      await api.post("/auth/logout");
    } catch {
      // ignore
    }
    clearTokens();
    setUser(null);
    setParish(null);
  }, []);

  const hasRole = useCallback((...roles: Role[]) => !!user && roles.includes(user.role), [user]);

  const value = useMemo(
    () => ({ user, parish, loading, login, loginWithGoogle, register, logout, refreshMe: loadMe, hasRole }),
    [user, parish, loading, login, loginWithGoogle, register, logout, loadMe, hasRole]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth deve essere usato dentro AuthProvider");
  return ctx;
}

export { apiErrorMessage };
