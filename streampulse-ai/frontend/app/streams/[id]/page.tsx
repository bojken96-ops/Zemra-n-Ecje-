"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Pause, Play, RefreshCw, Trash2 } from "lucide-react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, del, patch, post } from "@/lib/api";
import type { ActivityWindow, ChatEvent, Clip, Creator, Stream } from "@/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/input";
import { ErrorNote, PageHeader, Skeleton } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { CaptureStatusBadge, StreamStatusBadge } from "@/components/streams/status";
import { ClipCard } from "@/components/clips/clip-card";
import { formatDuration, humanize, timeAgo } from "@/lib/utils";

const SERIES = [
  { key: "combined_score", name: "Combined", color: "hsl(262 83% 64%)", width: 2.5 },
  { key: "chat_score", name: "Chat", color: "hsl(199 89% 55%)", width: 1.5 },
  { key: "audio_score", name: "Audio", color: "hsl(38 92% 55%)", width: 1.5 },
  { key: "visual_score", name: "Visual", color: "hsl(152 62% 45%)", width: 1.5 },
  { key: "emoji_score", name: "Emoji", color: "hsl(330 81% 60%)", width: 1 },
];

export default function StreamDetail() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const stream = useQuery({ queryKey: ["stream", id], queryFn: () => api<Stream>(`/api/streams/${id}`), refetchInterval: 10_000 });
  const activity = useQuery({ queryKey: ["activity", id], queryFn: () => api<ActivityWindow[]>(`/api/streams/${id}/activity?minutes=30`), refetchInterval: 10_000 });
  const chat = useQuery({ queryKey: ["chat", id], queryFn: () => api<ChatEvent[]>(`/api/streams/${id}/chat?limit=80`), refetchInterval: 5_000 });
  const clips = useQuery({ queryKey: ["clips", "stream", id], queryFn: () => api<Clip[]>(`/api/clips?stream_id=${id}&limit=8`) });
  const creators = useQuery({ queryKey: ["creators"], queryFn: () => api<Creator[]>("/api/creators") });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["stream", id] }); qc.invalidateQueries({ queryKey: ["streams"] }); };
  const action = useMutation({ mutationFn: (a: "start" | "stop" | "refresh") => post(`/api/streams/${id}/${a}`), onSettled: refresh });
  const update = useMutation({ mutationFn: (body: object) => patch(`/api/streams/${id}`, body), onSuccess: refresh });
  const remove = useMutation({ mutationFn: () => del(`/api/streams/${id}`), onSuccess: () => router.push("/streams") });

  const s = stream.data;
  if (!s) return <Skeleton className="h-96" />;
  const health = (s.capture?.health || {}) as Record<string, unknown>;
  const data = (activity.data || []).map((w) => ({ ...w, t: new Date(w.start_time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) }));

  return (
    <div>
      <Link href="/streams" className="mb-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3 w-3" /> Streams</Link>
      <PageHeader title={s.title || "Untitled stream"} description={s.creator_name || "Unassigned creator"}>
        <Button variant="outline" size="sm" asChild><a href={s.youtube_url} target="_blank" rel="noreferrer"><ExternalLink /> YouTube</a></Button>
        <Button variant="outline" size="sm" onClick={() => action.mutate("refresh")}><RefreshCw /> Check now</Button>
        {s.monitoring_enabled ? <Button variant="secondary" size="sm" onClick={() => action.mutate("stop")}><Pause /> Pause monitoring</Button> : <Button size="sm" onClick={() => action.mutate("start")}><Play /> Resume monitoring</Button>}
        <Button variant="ghost" size="icon" onClick={() => confirm("Remove this stream?") && remove.mutate()}><Trash2 /></Button>
      </PageHeader>
      <div className="mb-4 space-y-2"><ErrorNote error={action.error || update.error || remove.error} />{s.last_error && <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">{s.last_error}</p>}</div>

      <div className="grid gap-4 lg:grid-cols-4">
        <Card className="p-4"><p className="text-xs text-muted-foreground">Stream</p><div className="mt-2"><StreamStatusBadge status={s.status} /></div><p className="mt-2 text-[11px] text-muted-foreground">{s.status === "upcoming" && s.scheduled_start_at ? `Scheduled ${new Date(s.scheduled_start_at).toLocaleString()}` : `Checked ${timeAgo(s.last_checked_at)}`}</p></Card>
        <Card className="p-4"><p className="text-xs text-muted-foreground">Capture</p><div className="mt-2"><CaptureStatusBadge status={s.capture?.status} /></div><p className="mt-2 text-[11px] text-muted-foreground">{s.capture?.capture_method || "—"} · {formatDuration(s.recording_seconds)} recorded</p></Card>
        <Card className="p-4"><p className="text-xs text-muted-foreground">Chat</p><p className="mt-2 text-lg font-semibold">{s.chat_messages_last_minute}<span className="text-xs font-normal text-muted-foreground"> msg/min</span></p><p className="text-[11px] text-muted-foreground">{humanize(s.chat_status)}</p></Card>
        <Card className="p-4"><p className="text-xs text-muted-foreground">Current viral score</p><p className="mt-2 text-lg font-semibold">{Math.round(s.current_viral_score)}</p><p className="text-[11px] text-muted-foreground">combined signal, 0–100</p></Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Live signals (last 30 min)</CardTitle><CardDescription>Chat spikes alone never create clips — audio or visual evidence is required.</CardDescription></CardHeader>
          <CardContent className="h-72">
            <ResponsiveContainer>
              <LineChart data={data} margin={{ left: -20, right: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(240 5% 16%)" />
                <XAxis dataKey="t" tick={{ fontSize: 10, fill: "hsl(240 5% 62%)" }} minTickGap={40} />
                <YAxis domain={[0, 1]} tick={{ fontSize: 10, fill: "hsl(240 5% 62%)" }} />
                <Tooltip contentStyle={{ background: "hsl(240 8% 7%)", border: "1px solid hsl(240 5% 16%)", borderRadius: 8, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                {SERIES.map((x) => <Line key={x.key} type="monotone" dataKey={x.key} name={x.name} stroke={x.color} strokeWidth={x.width} dot={false} connectNulls isAnimationActive={false} />)}
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
        <Card className="flex flex-col">
          <CardHeader><CardTitle>Live chat</CardTitle></CardHeader>
          <CardContent className="h-72 flex-1 space-y-1.5 overflow-y-auto text-xs scrollbar-thin">
            {(chat.data || []).map((m) => (
              <p key={m.id}><span className="font-medium text-primary">{m.metadata?.author_name || "viewer"}</span> <span className="text-muted-foreground">{m.message}</span>{m.metadata?.super_chat && <span className="ml-1 text-warning">{m.metadata.super_chat}</span>}</p>
            ))}
            {!chat.data?.length && <p className="text-muted-foreground">No chat messages captured yet.</p>}
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader><CardTitle>Stream settings</CardTitle></CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="space-y-1.5"><p className="text-xs text-muted-foreground">Creator</p>
              <Select value={s.creator_id || ""} onChange={(e) => update.mutate({ creator_id: e.target.value || null })}>
                <option value="">Unassigned</option>{(creators.data || []).map((c) => <option key={c.id} value={c.id}>{c.name}{c.authorised ? "" : " (not authorised)"}</option>)}
              </Select>
            </div>
            <div className="flex items-center justify-between"><span>Monitoring</span><Switch checked={s.monitoring_enabled} onCheckedChange={(v) => update.mutate({ monitoring_enabled: v })} /></div>
            <div className="flex items-center justify-between"><span>Auto-capture when live</span><Switch checked={s.auto_capture} onCheckedChange={(v) => update.mutate({ auto_capture: v })} /></div>
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Capture health</CardTitle><CardDescription>Reported by the Windows capture agent{s.capture?.last_heartbeat_at ? ` · last heartbeat ${timeAgo(s.capture.last_heartbeat_at)}` : ""}</CardDescription></CardHeader>
          <CardContent>
            {s.capture ? (
              <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs md:grid-cols-3">
                {["fps", "frames", "dropped_frames", "drop_ratio", "speed", "disk_free_gb", "player", "ad_showing", "black_alert", "frozen_alert"].map((k) => (
                  <div key={k} className="flex justify-between border-b border-border/50 py-1"><span className="text-muted-foreground">{humanize(k)}</span><span className="font-mono">{String(health[k] ?? "—")}</span></div>
                ))}
                {Array.isArray(health.problems) && health.problems.length > 0 && <p className="col-span-full mt-2 text-warning">Problems: {(health.problems as string[]).join(", ")}</p>}
                {s.capture.error_message && <p className="col-span-full mt-2 text-destructive">{s.capture.error_message}</p>}
              </div>
            ) : <p className="text-xs text-muted-foreground">No capture session yet. Capture starts when the YouTube API reports the stream as live and the creator is authorised.</p>}
          </CardContent>
        </Card>
      </div>

      {!!clips.data?.length && (
        <section className="mt-6"><h2 className="mb-3 text-sm font-semibold">Clips from this stream</h2><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{clips.data.map((c) => <ClipCard key={c.id} clip={c} />)}</div></section>
      )}
    </div>
  );
}
