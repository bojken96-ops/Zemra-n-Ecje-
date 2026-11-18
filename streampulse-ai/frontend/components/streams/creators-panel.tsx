"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck, ShieldOff, Trash2, UserPlus } from "lucide-react";
import { del, patch, post } from "@/lib/api";
import type { Creator } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { ErrorNote } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";

const empty = { name: "", youtube_channel_id: "", profile_image: "", authorised: false, authorisation_notes: "", preferred_language: "en" };

export function CreatorsPanel({ creators }: { creators: Creator[] }) {
  const qc = useQueryClient();
  const [form, setForm] = useState(empty);
  const [open, setOpen] = useState(false);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["creators"] }); qc.invalidateQueries({ queryKey: ["streams"] }); };
  const create = useMutation({
    mutationFn: () => post("/api/creators", { ...form, youtube_channel_id: form.youtube_channel_id || null, profile_image: form.profile_image || null, authorisation_notes: form.authorisation_notes || null }),
    onSuccess: () => { setForm(empty); setOpen(false); refresh(); },
  });
  const update = useMutation({ mutationFn: ({ id, body }: { id: string; body: object }) => patch(`/api/creators/${id}`, body), onSuccess: refresh });
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/creators/${id}`), onSuccess: refresh });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Capture only starts for creators marked as authorised, with a note describing the authorisation.</p>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild><Button size="sm"><UserPlus /> Add creator</Button></DialogTrigger>
          <DialogContent>
            <DialogTitle>Add creator</DialogTitle>
            <DialogDescription>Streams from this channel are attached automatically.</DialogDescription>
            <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
              <div className="space-y-1.5"><Label>Name</Label><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></div>
              <div className="space-y-1.5"><Label>YouTube channel ID (UC…)</Label><Input value={form.youtube_channel_id} onChange={(e) => setForm({ ...form, youtube_channel_id: e.target.value })} placeholder="optional" /></div>
              <div className="space-y-1.5"><Label>Profile image URL</Label><Input value={form.profile_image} onChange={(e) => setForm({ ...form, profile_image: e.target.value })} placeholder="optional" /></div>
              <div className="space-y-1.5"><Label>Preferred language for captions</Label>
                <Select value={form.preferred_language} onChange={(e) => setForm({ ...form, preferred_language: e.target.value })}><option value="en">English</option><option value="sq">Albanian (Shqip)</option></Select>
              </div>
              <div className="flex items-center justify-between rounded-md border p-3"><div><p className="text-sm">Authorised to capture</p><p className="text-[11px] text-muted-foreground">You have this creator's permission.</p></div><Switch checked={form.authorised} onCheckedChange={(v) => setForm({ ...form, authorised: v })} /></div>
              {form.authorised && <div className="space-y-1.5"><Label>Authorisation notes (required)</Label><Textarea value={form.authorisation_notes} onChange={(e) => setForm({ ...form, authorisation_notes: e.target.value })} placeholder="e.g. Written agreement signed 2026-11-01, covers clipping and reposting." required /></div>}
              <ErrorNote error={create.error} />
              <Button className="w-full" disabled={create.isPending}>Save creator</Button>
            </form>
          </DialogContent>
        </Dialog>
      </div>
      <ErrorNote error={update.error || remove.error} />
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {creators.map((c) => (
          <Card key={c.id} className="flex items-start gap-3 p-4">
            {c.profile_image ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={c.profile_image} alt="" className="h-10 w-10 rounded-full" />
            ) : <span className="flex h-10 w-10 items-center justify-center rounded-full bg-secondary text-sm">{c.name[0]}</span>}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2"><p className="truncate text-sm font-medium">{c.name}</p><Badge variant="secondary">{c.preferred_language.toUpperCase()}</Badge></div>
              <p className="truncate text-[11px] text-muted-foreground">{c.youtube_channel_id || "No channel ID"}</p>
              {c.authorised ? <Badge variant="success" className="mt-2"><ShieldCheck className="h-3 w-3" /> Authorised</Badge> : <Badge variant="warning" className="mt-2"><ShieldOff className="h-3 w-3" /> Not authorised</Badge>}
              {c.authorisation_notes && <p className="mt-1 line-clamp-2 text-[11px] text-muted-foreground">{c.authorisation_notes}</p>}
            </div>
            <div className="flex flex-col gap-1">
              <Select className="h-7 w-16 px-1 text-[11px]" value={c.preferred_language} onChange={(e) => update.mutate({ id: c.id, body: { preferred_language: e.target.value } })}><option value="en">EN</option><option value="sq">SQ</option></Select>
              {c.authorised && <Button size="sm" variant="ghost" onClick={() => update.mutate({ id: c.id, body: { authorised: false } })}>Revoke</Button>}
              <Button size="icon" variant="ghost" onClick={() => confirm(`Delete ${c.name}?`) && remove.mutate(c.id)}><Trash2 /></Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
