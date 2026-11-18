import { Badge } from "@/components/ui/badge";
import { humanize } from "@/lib/utils";

export function StreamStatusBadge({ status }: { status: string }) {
  if (status === "live")
    return (
      <Badge variant="live">
        <span className="h-1.5 w-1.5 animate-live-pulse rounded-full bg-live" /> LIVE
      </Badge>
    );
  const v = status === "reconnecting" ? "warning" : status === "upcoming" ? "default" : status === "error" ? "destructive" : "secondary";
  return <Badge variant={v}>{humanize(status)}</Badge>;
}

export function CaptureStatusBadge({ status }: { status: string | undefined }) {
  if (!status) return <Badge variant="outline">No capture</Badge>;
  const v = status === "recording" ? "success" : status === "failed" ? "destructive" : ["reconnecting", "starting", "stopping", "pending"].includes(status) ? "warning" : "secondary";
  return <Badge variant={v}>{status === "recording" ? "● Recording" : humanize(status)}</Badge>;
}

export function ClipStatusBadge({ status }: { status: string }) {
  const v = { ready: "warning", approved: "default", published: "success", failed: "destructive", publishing: "default", processing: "secondary", rejected: "outline" }[status] as
    | "warning" | "default" | "success" | "destructive" | "secondary" | "outline" | undefined;
  return <Badge variant={v || "secondary"}>{status === "ready" ? "Awaiting approval" : humanize(status)}</Badge>;
}

export function ScorePill({ score }: { score: number | null | undefined }) {
  const s = Math.round(score || 0);
  const tone = s >= 80 ? "text-success" : s >= 60 ? "text-warning" : "text-muted-foreground";
  return <span className={`font-mono text-xs font-semibold ${tone}`}>{s}</span>;
}
