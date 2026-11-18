"use client";
import Link from "next/link";
import { MessageSquare, Timer, TrendingUp } from "lucide-react";
import { Card } from "@/components/ui/card";
import { formatDuration } from "@/lib/utils";
import type { Stream } from "@/types";
import { CaptureStatusBadge, StreamStatusBadge } from "./status";

export function StreamCard({ stream }: { stream: Stream }) {
  return (
    <Link href={`/streams/${stream.id}`}>
      <Card className="group overflow-hidden transition-colors hover:border-primary/50">
        <div className="relative aspect-video bg-muted">
          {stream.thumbnail_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={stream.thumbnail_url} alt="" className="h-full w-full object-cover opacity-90 transition-opacity group-hover:opacity-100" />
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">No thumbnail</div>
          )}
          <div className="absolute left-2 top-2 flex gap-1.5 rounded-full bg-black/80"><StreamStatusBadge status={stream.status} /></div>
          <div className="absolute right-2 top-2 rounded-full bg-black/80"><CaptureStatusBadge status={stream.capture?.status} /></div>
        </div>
        <div className="space-y-3 p-4">
          <div className="flex items-center gap-2">
            {stream.creator_image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={stream.creator_image} alt="" className="h-6 w-6 rounded-full" />
            ) : (
              <span className="flex h-6 w-6 items-center justify-center rounded-full bg-secondary text-[10px]">{(stream.creator_name || "?")[0]}</span>
            )}
            <span className="text-xs text-muted-foreground">{stream.creator_name || "Unassigned creator"}</span>
          </div>
          <p className="line-clamp-2 text-sm font-medium">{stream.title || stream.youtube_url}</p>
          <div className="grid grid-cols-3 gap-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1"><MessageSquare className="h-3 w-3" />{stream.chat_messages_last_minute}/min</span>
            <span className="flex items-center gap-1"><TrendingUp className="h-3 w-3" />{Math.round(stream.current_viral_score)}</span>
            <span className="flex items-center gap-1"><Timer className="h-3 w-3" />{formatDuration(stream.recording_seconds)}</span>
          </div>
          {stream.last_error && <p className="line-clamp-2 text-[11px] text-warning">{stream.last_error}</p>}
        </div>
      </Card>
    </Link>
  );
}
