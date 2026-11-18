"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link2, Plus } from "lucide-react";
import { post } from "@/lib/api";
import type { Creator, Stream } from "@/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { ErrorNote } from "@/components/ui/misc";

export function AddStream({ creators }: { creators: Creator[] }) {
  const qc = useQueryClient();
  const [url, setUrl] = useState("");
  const [creatorId, setCreatorId] = useState("");
  const add = useMutation({
    mutationFn: () => post<Stream>("/api/streams", { url, creator_id: creatorId || null }),
    onSuccess: () => {
      setUrl("");
      qc.invalidateQueries({ queryKey: ["streams"] });
    },
  });
  return (
    <Card className="p-4">
      <form onSubmit={(e) => { e.preventDefault(); add.mutate(); }} className="flex flex-col gap-3 md:flex-row">
        <div className="relative flex-1">
          <Link2 className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-9" placeholder="Paste a YouTube livestream URL (watch, youtu.be, /live/…, @channel/live)" value={url} onChange={(e) => setUrl(e.target.value)} required />
        </div>
        <Select className="md:w-56" value={creatorId} onChange={(e) => setCreatorId(e.target.value)}>
          <option value="">Auto-match creator by channel</option>
          {creators.map((c) => <option key={c.id} value={c.id}>{c.name}{c.authorised ? "" : " (not authorised)"}</option>)}
        </Select>
        <Button disabled={add.isPending}><Plus /> {add.isPending ? "Checking…" : "Add stream"}</Button>
      </form>
      <div className="mt-2"><ErrorNote error={add.error} /></div>
    </Card>
  );
}
