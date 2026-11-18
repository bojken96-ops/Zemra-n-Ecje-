"use client";
import Link from "next/link";
import { useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Download, Pencil, Trash2 } from "lucide-react";
import { del, post } from "@/lib/api";
import type { Clip } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ClipStatusBadge, ScorePill } from "@/components/streams/status";
import { formatDuration, humanize } from "@/lib/utils";

export function ClipCard({ clip }: { clip: Clip }) {
  const qc = useQueryClient();
  const video = useRef<HTMLVideoElement>(null);
  const done = () => { qc.invalidateQueries({ queryKey: ["clips"] }); qc.invalidateQueries({ queryKey: ["analytics"] }); qc.invalidateQueries({ queryKey: ["jobs"] }); };
  const approve = useMutation({ mutationFn: () => post(`/api/clips/${clip.id}/approve`), onSuccess: done });
  const remove = useMutation({ mutationFn: () => del(`/api/clips/${clip.id}`), onSuccess: done });
  const err = approve.error || remove.error;

  return (
    <Card className="overflow-hidden">
      <div className="relative aspect-[9/16] max-h-[420px] w-full bg-black" onMouseEnter={() => video.current?.play().catch(() => {})} onMouseLeave={() => { if (video.current) { video.current.pause(); video.current.currentTime = 0; } }}>
        {clip.file_url ? (
          <video ref={video} src={clip.file_url} poster={clip.thumbnail_url || undefined} muted loop playsInline preload="none" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">{clip.status === "processing" ? "Rendering…" : clip.error_message || "No video"}</div>
        )}
        <div className="absolute left-2 top-2 rounded-full bg-black/80"><ClipStatusBadge status={clip.status} /></div>
        <div className="absolute right-2 top-2 rounded-full bg-black/70 px-2 py-0.5"><ScorePill score={clip.viral_score} /></div>
        <div className="absolute bottom-2 right-2 rounded bg-black/70 px-1.5 text-[11px]">{formatDuration(clip.duration)}</div>
      </div>
      <div className="space-y-2 p-3">
        <p className="line-clamp-2 text-sm font-medium">{clip.title || "Untitled clip"}</p>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          <span>{clip.creator_name || "Unknown creator"}</span>·<Badge variant="secondary">{humanize(clip.moment_type)}</Badge>
          {clip.language && <Badge variant="outline">{clip.language.toUpperCase()}</Badge>}
        </div>
        {clip.publications.length > 0 && (
          <div className="flex flex-wrap gap-1">{clip.publications.map((p) => (
            <Badge key={p.job_id} variant={p.status === "published" ? "success" : p.status === "failed" ? "destructive" : "secondary"}>
              {p.post_url ? <a href={p.post_url} target="_blank" rel="noreferrer">{p.platform}</a> : p.platform}: {p.status}
            </Badge>
          ))}</div>
        )}
        {err && <p className="text-[11px] text-destructive">{(err as Error).message}</p>}
        <div className="flex gap-1 pt-1">
          {clip.status === "ready" && <Button size="sm" variant="success" onClick={() => approve.mutate()} disabled={approve.isPending}><Check /> Approve</Button>}
          <Button size="sm" variant="outline" asChild><Link href={`/clips/${clip.id}`}><Pencil /> Edit</Link></Button>
          {clip.file_url && <Button size="icon" variant="ghost" asChild><a href={`${clip.file_url}?download=true`} aria-label="Download"><Download /></a></Button>}
          <Button size="icon" variant="ghost" className="ml-auto" onClick={() => confirm("Delete this clip and its files?") && remove.mutate()} aria-label="Delete"><Trash2 /></Button>
        </div>
      </div>
    </Card>
  );
}
