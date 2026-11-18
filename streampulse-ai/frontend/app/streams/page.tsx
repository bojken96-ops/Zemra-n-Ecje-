"use client";
import { useQuery } from "@tanstack/react-query";
import { Radio } from "lucide-react";
import { api } from "@/lib/api";
import type { Creator, Stream } from "@/types";
import { AddStream } from "@/components/streams/add-stream";
import { CreatorsPanel } from "@/components/streams/creators-panel";
import { StreamCard } from "@/components/streams/stream-card";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/misc";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function StreamsPage() {
  const streams = useQuery({ queryKey: ["streams"], queryFn: () => api<Stream[]>("/api/streams"), refetchInterval: 15_000 });
  const creators = useQuery({ queryKey: ["creators"], queryFn: () => api<Creator[]>("/api/creators") });
  const list = streams.data || [];
  const order = { live: 0, reconnecting: 1, upcoming: 2, offline: 3, ended: 4, error: 5 } as Record<string, number>;
  const sorted = [...list].sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9));

  return (
    <div>
      <PageHeader title="Streams" description="Paste a livestream URL. StreamPulse confirms liveness with the YouTube API, then captures, monitors chat and finds moments." />
      <Tabs defaultValue="streams">
        <TabsList><TabsTrigger value="streams">Livestreams ({list.length})</TabsTrigger><TabsTrigger value="creators">Creators ({creators.data?.length ?? 0})</TabsTrigger></TabsList>
        <TabsContent value="streams" className="space-y-6">
          <AddStream creators={creators.data || []} />
          {streams.isLoading ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-72" />)}</div>
          ) : sorted.length ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{sorted.map((s) => <StreamCard key={s.id} stream={s} />)}</div>
          ) : (
            <EmptyState icon={Radio} title="No streams yet">Add a creator, mark them authorised, then paste their livestream URL above.</EmptyState>
          )}
        </TabsContent>
        <TabsContent value="creators"><CreatorsPanel creators={creators.data || []} /></TabsContent>
      </Tabs>
    </div>
  );
}
