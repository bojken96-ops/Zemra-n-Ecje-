"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export interface AuthState {
  authenticated: boolean;
  setup_required: boolean;
  username: string | null;
}

export function useAuth() {
  return useQuery({ queryKey: ["auth"], queryFn: () => api<AuthState>("/api/auth/state"), staleTime: 60_000 });
}
