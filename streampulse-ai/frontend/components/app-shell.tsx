"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Bell, Clapperboard, LayoutDashboard, LogOut, Radio, Send, Settings, Users, Zap } from "lucide-react";
import { api, post } from "@/lib/api";
import { cn, timeAgo } from "@/lib/utils";
import { useAuth } from "@/hooks/use-auth";
import { useLiveEvents } from "@/hooks/use-live-events";
import type { Notification } from "@/types";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/streams", label: "Streams", icon: Radio },
  { href: "/clips", label: "Clips", icon: Clapperboard },
  { href: "/publishing", label: "Publishing", icon: Send },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/accounts", label: "Accounts", icon: Users },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const qc = useQueryClient();
  const auth = useAuth();
  const isLogin = pathname.startsWith("/login");
  const authed = !!auth.data?.authenticated;
  const live = useLiveEvents(authed && !isLogin);

  useEffect(() => {
    if (auth.data && !auth.data.authenticated && !isLogin) router.replace("/login");
  }, [auth.data, isLogin, router]);

  const logout = useMutation({
    mutationFn: () => post("/api/auth/logout"),
    onSuccess: () => {
      qc.clear();
      router.replace("/login");
    },
  });

  if (isLogin) return <>{children}</>;
  if (!authed) return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">Loading…</div>;

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r bg-card/40 p-4 md:flex">
        <Link href="/dashboard" className="mb-8 flex items-center gap-2 px-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary"><Zap className="h-4 w-4 text-white" /></span>
          <span className="font-semibold tracking-tight">StreamPulse AI</span>
        </Link>
        <nav className="flex flex-1 flex-col gap-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link key={href} href={href} className={cn("flex items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground", pathname.startsWith(href) && "bg-accent text-foreground")}>
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="space-y-3 border-t pt-4 text-xs text-muted-foreground">
          <div className="flex items-center gap-2 px-2">
            <span className={cn("h-2 w-2 rounded-full", live ? "bg-success" : "bg-muted-foreground")} />
            {live ? "Live updates connected" : "Live updates offline"}
          </div>
          <button onClick={() => logout.mutate()} className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 hover:bg-accent hover:text-foreground">
            <LogOut className="h-3.5 w-3.5" /> Sign out ({auth.data?.username})
          </button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b bg-background/80 px-6 backdrop-blur">
          <div className="flex gap-1 overflow-x-auto md:hidden">
            {NAV.map(({ href, icon: Icon }) => (
              <Link key={href} href={href} className={cn("rounded-md p-2 text-muted-foreground", pathname.startsWith(href) && "bg-accent text-foreground")}><Icon className="h-4 w-4" /></Link>
            ))}
          </div>
          <div className="hidden text-xs text-muted-foreground md:block">Paste a livestream URL → StreamPulse monitors it → AI finds moments → clips are generated → clips are published.</div>
          <NotificationBell />
        </header>
        <main className="mx-auto w-full max-w-[1400px] flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}

function NotificationBell() {
  const [open, setOpen] = useState(false);
  const qc = useQueryClient();
  const { data = [] } = useQuery({ queryKey: ["notifications"], queryFn: () => api<Notification[]>("/api/notifications?limit=30"), refetchInterval: 60_000 });
  const unread = data.filter((n) => !n.read).length;
  const markRead = useMutation({ mutationFn: () => post("/api/notifications/read"), onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }) });
  return (
    <div className="relative">
      <button onClick={() => { setOpen(!open); if (!open && unread) markRead.mutate(); }} className="relative rounded-md p-2 hover:bg-accent" aria-label="Notifications">
        <Bell className="h-4 w-4" />
        {unread > 0 && <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-live px-1 text-[10px] font-semibold text-white">{unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 top-11 z-50 max-h-[420px] w-96 overflow-y-auto rounded-lg border bg-card p-2 shadow-xl scrollbar-thin">
          {data.length === 0 && <p className="p-4 text-center text-xs text-muted-foreground">No notifications yet</p>}
          {data.map((n) => (
            <div key={n.id} className="rounded-md p-2.5 text-xs hover:bg-accent">
              <div className="flex items-center gap-2">
                <span className={cn("h-1.5 w-1.5 rounded-full", n.level === "error" ? "bg-destructive" : n.level === "warning" ? "bg-warning" : "bg-primary")} />
                <span className="font-medium capitalize">{n.category}</span>
                <span className="ml-auto text-muted-foreground">{timeAgo(n.created_at)}</span>
              </div>
              <p className="mt-1 text-muted-foreground">{n.message}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
