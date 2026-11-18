"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Download, RefreshCw, Save, Send, Sparkles } from "lucide-react";
import { api, patch, post } from "@/lib/api";
import type { Clip, SocialAccount, TranscriptSegment } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { ErrorNote, PageHeader, Skeleton } from "@/components/ui/misc";
import { ClipStatusBadge, ScorePill } from "@/components/streams/status";
import { formatDuration, humanize } from "@/lib/utils";

const STYLES = [
  { value: "clean", label: "Clean white" },
  { value: "highlight", label: "Highlighted keywords" },
  { value: "animated", label: "Creator-style animated" },
  { value: "minimal", label: "Minimal" },
];

export default function ClipEditor() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const clip = useQuery({ queryKey: ["clip", id], queryFn: () => api<Clip>(`/api/clips/${id}`), refetchInterval: (q) => (q.state.data?.status === "processing" ? 3000 : false) });
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => api<SocialAccount[]>("/api/accounts") });
  const [title, setTitle] = useState("");
  const [content, setContent] = useState({ youtube_title: "", tiktok_description: "", instagram_caption: "", hashtags: "" });
  const [segments, setSegments] = useState<TranscriptSegment[]>([]);
  const [style, setStyle] = useState("clean");
  const [selected, setSelected] = useState<string[]>([]);
  const [when, setWhen] = useState("");

  useEffect(() => {
    const c = clip.data;
    if (!c) return;
    setTitle(c.title || "");
    setContent({ youtube_title: c.content?.youtube_title || "", tiktok_description: c.content?.tiktok_description || "", instagram_caption: c.content?.instagram_caption || "", hashtags: (c.content?.hashtags || []).join(" ") });
    setSegments(c.transcript?.segments || []);
    setStyle(c.subtitle_style);
  }, [clip.data?.id, clip.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => { qc.invalidateQueries({ queryKey: ["clip", id] }); qc.invalidateQueries({ queryKey: ["clips"] }); qc.invalidateQueries({ queryKey: ["jobs"] }); };
  const save = useMutation({
    mutationFn: (withSubs: boolean) => patch(`/api/clips/${id}`, {
      title,
      content: { ...content, hashtags: content.hashtags.split(/\s+/).filter(Boolean) },
      ...(withSubs ? { transcript_segments: segments.map(({ start, end, text }) => ({ start, end, text })) } : {}),
    }),
    onSuccess: refresh,
  });
  const regenerate = useMutation({ mutationFn: (regenerate_content: boolean) => post(`/api/clips/${id}/regenerate`, { subtitle_style: style, regenerate_content }), onSuccess: refresh });
  const approve = useMutation({ mutationFn: () => post(`/api/clips/${id}/approve?publish=false`), onSuccess: refresh });
  const publish = useMutation({
    mutationFn: () => post("/api/publishing/jobs", { clip_id: id, account_ids: selected.length ? selected : null, scheduled_at: when ? new Date(when).toISOString() : null }),
    onSuccess: refresh,
  });

  const c = clip.data;
  if (!c) return <Skeleton className="h-[600px]" />;
  const busy = c.status === "processing" || c.status === "publishing";

  return (
    <div>
      <Link href="/clips" className="mb-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"><ArrowLeft className="h-3 w-3" /> Clips</Link>
      <PageHeader title={c.title || "Untitled clip"} description={`${c.creator_name || "Unknown creator"} · ${humanize(c.moment_type)} · ${formatDuration(c.duration)}`}>
        <ClipStatusBadge status={c.status} />
        <span className="rounded-full bg-secondary px-2 py-0.5 text-xs">Viral <ScorePill score={c.viral_score} /></span>
        {c.status === "ready" && <Button size="sm" variant="success" onClick={() => approve.mutate()}><Check /> Approve</Button>}
        {c.file_url && <Button size="sm" variant="outline" asChild><a href={`${c.file_url}?download=true`}><Download /> Download</a></Button>}
      </PageHeader>
      <div className="mb-4"><ErrorNote error={save.error || regenerate.error || approve.error || publish.error} />{c.error_message && <ErrorNote error={c.error_message} />}</div>

      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <div className="space-y-4">
          <div className="overflow-hidden rounded-lg border bg-black">
            {c.status === "processing" ? <div className="flex aspect-[9/16] items-center justify-center text-sm text-muted-foreground"><RefreshCw className="mr-2 h-4 w-4 animate-spin" /> Rendering…</div>
              : c.file_url ? <video key={c.file_url + c.subtitle_style} src={`${c.file_url}?v=${encodeURIComponent(c.subtitle_style)}`} poster={c.thumbnail_url || undefined} controls playsInline className="aspect-[9/16] w-full" /> : null}
          </div>
          <Card>
            <CardHeader><CardTitle>Subtitle style</CardTitle><CardDescription>Fonts, colours and position are set in Settings → Subtitles.</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-2">{STYLES.map((s) => (
                <button key={s.value} onClick={() => setStyle(s.value)} className={`rounded-md border px-2 py-2 text-xs ${style === s.value ? "border-primary bg-primary/10" : "hover:bg-accent"}`}>{s.label}</button>
              ))}</div>
              <Button className="w-full" variant="secondary" disabled={busy || regenerate.isPending} onClick={() => regenerate.mutate(false)}><RefreshCw /> Re-render with this style</Button>
              <Button className="w-full" variant="outline" disabled={busy || regenerate.isPending} onClick={() => regenerate.mutate(true)}><Sparkles /> Re-render + regenerate AI captions</Button>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Titles & captions</CardTitle><CardDescription>Generated by AI from the transcript only{c.content?.language ? ` · ${c.content.language === "sq" ? "Albanian" : "English"}` : ""}. Edit freely.</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <div className="space-y-1.5"><Label>Clip title</Label><Input value={title} maxLength={100} onChange={(e) => setTitle(e.target.value)} /></div>
              <div className="space-y-1.5"><Label>YouTube Shorts title</Label><Input value={content.youtube_title} maxLength={100} onChange={(e) => setContent({ ...content, youtube_title: e.target.value })} /></div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1.5"><Label>TikTok description</Label><Textarea rows={4} value={content.tiktok_description} onChange={(e) => setContent({ ...content, tiktok_description: e.target.value })} /></div>
                <div className="space-y-1.5"><Label>Instagram caption</Label><Textarea rows={4} value={content.instagram_caption} onChange={(e) => setContent({ ...content, instagram_caption: e.target.value })} /></div>
              </div>
              <div className="space-y-1.5"><Label>Hashtags</Label><Input value={content.hashtags} onChange={(e) => setContent({ ...content, hashtags: e.target.value })} placeholder="#shorts #gaming" /></div>
              {c.content?.hook && <p className="text-xs text-muted-foreground">Hook: <span className="text-foreground">{c.content.hook}</span></p>}
              <Button size="sm" onClick={() => save.mutate(false)} disabled={save.isPending || busy}><Save /> Save text</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Subtitles</CardTitle><CardDescription>Edit the transcribed text; saving re-renders the video with your corrections.</CardDescription></CardHeader>
            <CardContent className="max-h-80 space-y-2 overflow-y-auto scrollbar-thin">
              {segments.length === 0 && <p className="text-xs text-muted-foreground">No speech was transcribed for this clip.</p>}
              {segments.map((s, i) => (
                <div key={i} className="flex items-start gap-2">
                  <span className="mt-2 w-20 shrink-0 font-mono text-[11px] text-muted-foreground">{s.start.toFixed(1)}–{s.end.toFixed(1)}s</span>
                  <Input value={s.text} onChange={(e) => setSegments(segments.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} />
                </div>
              ))}
            </CardContent>
            {segments.length > 0 && <CardContent><Button size="sm" variant="secondary" disabled={busy || save.isPending} onClick={() => save.mutate(true)}><Save /> Save subtitles & re-render</Button></CardContent>}
          </Card>

          <Card>
            <CardHeader><CardTitle>Publish</CardTitle><CardDescription>Jobs are created once per account — duplicates are prevented. A post is only marked published after the platform confirms it.</CardDescription></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap gap-2">
                {(accounts.data || []).filter((a) => a.connected && a.enabled).map((a) => (
                  <button key={a.id} onClick={() => setSelected(selected.includes(a.id) ? selected.filter((x) => x !== a.id) : [...selected, a.id])} className={`rounded-md border px-3 py-1.5 text-xs ${selected.includes(a.id) ? "border-primary bg-primary/10" : "hover:bg-accent"}`}>
                    {humanize(a.platform)} · {a.account_name}
                  </button>
                ))}
                {!accounts.data?.some((a) => a.connected) && <p className="text-xs text-muted-foreground">No connected accounts. <Link className="text-primary" href="/accounts">Connect platforms</Link>.</p>}
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <div className="space-y-1.5"><Label>Schedule (optional)</Label><Input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} /></div>
                <Button disabled={busy || publish.isPending || !["ready", "approved", "published"].includes(c.status)} onClick={() => publish.mutate()}><Send /> {selected.length ? `Publish to ${selected.length} selected` : "Publish to all enabled"}</Button>
              </div>
              {Array.isArray(publish.data) && <p className="text-xs text-success">{publish.data.length} new job(s) queued.</p>}
              <div className="flex flex-wrap gap-1.5">{c.publications.map((p) => (
                <Badge key={p.job_id} variant={p.status === "published" ? "success" : p.status === "failed" ? "destructive" : "secondary"}>{p.platform}: {p.status}{p.post_url && <a className="ml-1 underline" href={p.post_url} target="_blank" rel="noreferrer">open</a>}</Badge>
              ))}</div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
