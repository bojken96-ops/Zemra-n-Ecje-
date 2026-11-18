"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Clapperboard } from "lucide-react";
import { api } from "@/lib/api";
import type { Clip } from "@/types";
import { ClipCard } from "@/components/clips/clip-card";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/misc";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

const FILTERS: Record<string, string> = {
  all: "",
  awaiting: "ready",
  approved: "approved,publishing",
  published: "published",
  processing: "processing",
  failed: "failed",
};

export default function ClipsPage() {
  const [filter, setFilter] = useState("all");
  const status = FILTERS[filter];
  const clips = useQuery({ queryKey: ["clips", filter], queryFn: () => api<Clip[]>(`/api/clips?limit=200${status ? `&status=${status}` : ""}`), refetchInterval: 20_000 });

  return (
    <div>
      <PageHeader title="Clips" description="Vertical 1080×1920 clips with subtitles and AI captions. Hover to preview." />
      <Tabs value={filter} onValueChange={setFilter} className="mb-5">
        <TabsList>
          {Object.keys(FILTERS).map((k) => <TabsTrigger key={k} value={k} className="capitalize">{k === "awaiting" ? "Awaiting approval" : k}</TabsTrigger>)}
        </TabsList>
      </Tabs>
      {clips.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[520px]" />)}</div>
      ) : clips.data?.length ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">{clips.data.map((c) => <ClipCard key={c.id} clip={c} />)}</div>
      ) : (
        <EmptyState icon={Clapperboard} title="No clips in this view" />
      )}
    </div>
  );
}
