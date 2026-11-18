"use client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, RotateCcw, X } from "lucide-react";
import { api, post } from "@/lib/api";
import type { PublishJob } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorNote, PageHeader } from "@/components/ui/misc";
import { PLATFORMS } from "@/components/publishing/platform";
import { humanize, timeAgo } from "@/lib/utils";

const tone = (s: string) => (s === "published" ? "success" : s === "failed" ? "destructive" : s === "cancelled" ? "outline" : s === "scheduled" ? "default" : "warning") as "success" | "destructive" | "outline" | "default" | "warning";

export default function PublishingPage() {
  const qc = useQueryClient();
  const jobs = useQuery({ queryKey: ["jobs"], queryFn: () => api<PublishJob[]>("/api/publishing/jobs"), refetchInterval: 15_000 });
  const retry = useMutation({ mutationFn: (id: string) => post(`/api/publishing/jobs/${id}/retry`), onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }) });
  const cancel = useMutation({ mutationFn: (id: string) => post(`/api/publishing/jobs/${id}/cancel`), onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }) });

  return (
    <div>
      <PageHeader title="Publishing" description="Uploads go through each platform's official API. Platform review rules and posting limits are respected, never bypassed." />
      <ErrorNote error={retry.error || cancel.error} />
      <div className="mt-2 grid gap-4 lg:grid-cols-3">
        {PLATFORMS.map(({ key, label, icon: Icon, color }) => {
          const list = (jobs.data || []).filter((j) => j.platform === key);
          const counts = list.reduce<Record<string, number>>((acc, j) => ({ ...acc, [j.status]: (acc[j.status] || 0) + 1 }), {});
          return (
            <Card key={key} className="flex flex-col">
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Icon className={`h-4 w-4 ${color}`} /> {label}</CardTitle>
                <div className="flex flex-wrap gap-1 pt-1">{Object.entries(counts).map(([s, n]) => <Badge key={s} variant={tone(s)}>{humanize(s)} {n}</Badge>)}</div>
              </CardHeader>
              <CardContent className="max-h-[70vh] flex-1 space-y-2 overflow-y-auto scrollbar-thin">
                {list.length === 0 && <p className="py-8 text-center text-xs text-muted-foreground">No jobs yet</p>}
                {list.map((j) => (
                  <div key={j.id} className="rounded-md border p-3 text-xs">
                    <div className="flex items-start justify-between gap-2">
                      <p className="line-clamp-2 font-medium">{j.clip_title || String(j.metadata.title || "Clip")}</p>
                      <Badge variant={tone(j.status)}>{humanize(j.status)}</Badge>
                    </div>
                    <p className="mt-1 text-muted-foreground">
                      {j.status === "scheduled" && j.scheduled_at ? `Runs ${new Date(j.scheduled_at).toLocaleString()}` : `Created ${timeAgo(j.created_at)}`} · {j.attempts} attempt{j.attempts === 1 ? "" : "s"}
                    </p>
                    {j.error_message && <p className={`mt-1 ${j.status === "published" ? "text-muted-foreground" : "text-destructive"}`}>{j.error_message}</p>}
                    <div className="mt-2 flex gap-1">
                      {j.post_url && <Button size="sm" variant="outline" asChild><a href={j.post_url} target="_blank" rel="noreferrer"><ExternalLink /> View post</a></Button>}
                      {(j.status === "failed" || j.status === "cancelled") && <Button size="sm" variant="secondary" onClick={() => retry.mutate(j.id)}><RotateCcw /> Retry</Button>}
                      {["scheduled", "pending", "failed"].includes(j.status) && <Button size="sm" variant="ghost" onClick={() => cancel.mutate(j.id)}><X /> Cancel</Button>}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
