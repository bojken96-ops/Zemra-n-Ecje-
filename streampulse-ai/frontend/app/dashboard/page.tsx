"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clapperboard, Clock, Radio, Scissors, Tv } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import type { Analytics, Clip, Stream } from "@/types";
import { StatCard } from "@/components/dashboard/stat-card";
import { StorageCard } from "@/components/dashboard/storage-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/misc";
import { StreamCard } from "@/components/streams/stream-card";
import { ClipCard } from "@/components/clips/clip-card";
import { Button } from "@/components/ui/button";

export default function DashboardPage() {
  const analytics = useQuery({ queryKey: ["analytics", 14], queryFn: () => api<Analytics>("/api/analytics?days=14"), refetchInterval: 30_000 });
  const streams = useQuery({ queryKey: ["streams"], queryFn: () => api<Stream[]>("/api/streams"), refetchInterval: 15_000 });
  const clips = useQuery({ queryKey: ["clips", "recent"], queryFn: () => api<Clip[]>("/api/clips?limit=4") });
  const o = analytics.data?.overview;
  const active = (streams.data || []).filter((s) => s.status === "live" || s.status === "reconnecting");

  return (
    <div>
      <PageHeader title="Overview" description="Everything StreamPulse is watching, clipping and publishing right now.">
        <Button asChild><Link href="/streams"><Radio /> Add livestream</Link></Button>
      </PageHeader>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-7">
        {o ? (
          <>
            <StatCard label="Active livestreams" value={o.active_streams} icon={Radio} tone="live" hint={`${o.active_captures} recording`} />
            <StatCard label="Streams monitored" value={o.total_streams} icon={Tv} />
            <StatCard label="Clips today" value={o.clips_today} icon={Scissors} hint={`${o.candidates_today} moments detected`} />
            <StatCard label="Awaiting approval" value={o.clips_awaiting_approval} icon={Clock} tone="warning" />
            <StatCard label="Published clips" value={o.published_clips} icon={CheckCircle2} tone="success" />
            <StatCard label="Failed publishing" value={o.failed_jobs} icon={AlertTriangle} tone={o.failed_jobs ? "destructive" : undefined} />
            <StatCard label="Avg viral score" value={analytics.data?.average_viral_score ?? "—"} icon={Clapperboard} />
          </>
        ) : (
          Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="h-[92px]" />)
        )}
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Clips generated vs published (14 days)</CardTitle></CardHeader>
          <CardContent className="h-56">
            <ResponsiveContainer>
              <AreaChart data={analytics.data?.series || []} margin={{ left: -20, right: 8 }}>
                <defs>
                  <linearGradient id="gc" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="hsl(262 83% 64%)" stopOpacity={0.4} /><stop offset="100%" stopColor="hsl(262 83% 64%)" stopOpacity={0} /></linearGradient>
                  <linearGradient id="gp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="hsl(152 62% 45%)" stopOpacity={0.4} /><stop offset="100%" stopColor="hsl(152 62% 45%)" stopOpacity={0} /></linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(240 5% 16%)" />
                <XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} tick={{ fontSize: 11, fill: "hsl(240 5% 62%)" }} />
                <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "hsl(240 5% 62%)" }} />
                <Tooltip contentStyle={{ background: "hsl(240 8% 7%)", border: "1px solid hsl(240 5% 16%)", borderRadius: 8, fontSize: 12 }} />
                <Area type="monotone" dataKey="clips" stroke="hsl(262 83% 64%)" fill="url(#gc)" strokeWidth={2} />
                <Area type="monotone" dataKey="published" stroke="hsl(152 62% 45%)" fill="url(#gp)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        {analytics.data ? <StorageCard storage={analytics.data.storage} /> : <Skeleton className="h-64" />}
      </div>

      <section className="mt-8">
        <h2 className="mb-3 text-sm font-semibold">Active livestreams</h2>
        {active.length ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{active.map((s) => <StreamCard key={s.id} stream={s} />)}</div>
        ) : (
          <EmptyState icon={Radio} title="No livestreams are live right now">StreamPulse checks your streams every minute and starts capturing automatically when one goes live.</EmptyState>
        )}
      </section>

      <section className="mt-8">
        <div className="mb-3 flex items-center justify-between"><h2 className="text-sm font-semibold">Latest clips</h2><Link href="/clips" className="text-xs text-primary hover:underline">View all</Link></div>
        {clips.data?.length ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{clips.data.map((c) => <ClipCard key={c.id} clip={c} />)}</div>
        ) : (
          <EmptyState icon={Clapperboard} title="No clips yet">Clips appear here when the AI finds an interesting moment in a captured stream.</EmptyState>
        )}
      </section>
    </div>
  );
}
