"use client";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Unplug } from "lucide-react";
import { api, del, patch, post } from "@/lib/api";
import type { SocialAccount } from "@/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ErrorNote, PageHeader } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { PLATFORMS } from "@/components/publishing/platform";

const NOTES: Record<string, string> = {
  youtube: "Google OAuth with the youtube.upload scope. Unverified Google apps upload as private until verified.",
  tiktok: "TikTok Content Posting API (Direct Post). Until TikTok audits your app, posts are restricted to private (SELF_ONLY).",
  instagram: "Instagram API with Instagram Login. Requires a Business or Creator account; 50 API posts per 24 h.",
};

function AccountsInner() {
  const qc = useQueryClient();
  const params = useSearchParams();
  const accounts = useQuery({ queryKey: ["accounts"], queryFn: () => api<SocialAccount[]>("/api/accounts") });
  const config = useQuery({ queryKey: ["accounts-config"], queryFn: () => api<Record<string, boolean> & { redirect_uris: Record<string, string> }>("/api/accounts/config") });
  const connect = useMutation({ mutationFn: (p: string) => post<{ authorization_url: string }>(`/api/accounts/${p}/connect`), onSuccess: (d) => { window.location.href = d.authorization_url; } });
  const toggle = useMutation({ mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => patch(`/api/accounts/${id}?enabled=${enabled}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }) });
  const remove = useMutation({ mutationFn: (id: string) => del(`/api/accounts/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }) });

  return (
    <div>
      <PageHeader title="Accounts" description="Connect the social accounts StreamPulse publishes to. Tokens are encrypted at rest." />
      {params.get("connected") && <p className="mb-4 rounded-md border border-success/40 bg-success/10 px-3 py-2 text-xs text-success">Connected {params.get("connected")} successfully.</p>}
      {params.get("error") && <div className="mb-4"><ErrorNote error={`Connection failed: ${params.get("error")}`} /></div>}
      <ErrorNote error={connect.error || toggle.error || remove.error} />
      <div className="mt-2 grid gap-4 lg:grid-cols-3">
        {PLATFORMS.map(({ key, label, icon: Icon, color }) => {
          const list = (accounts.data || []).filter((a) => a.platform === key);
          const configured = config.data?.[key];
          return (
            <Card key={key}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2"><Icon className={`h-4 w-4 ${color}`} /> {label}</CardTitle>
                <CardDescription>{NOTES[key]}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {list.map((a) => (
                  <div key={a.id} className="flex items-center gap-3 rounded-md border p-3">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{a.account_name || a.account_id}</p>
                      <div className="mt-1 flex gap-1">{a.connected ? <Badge variant="success">Connected</Badge> : <Badge variant="destructive">Reconnect needed</Badge>}{a.token_expires_at && <Badge variant="outline">token until {new Date(a.token_expires_at).toLocaleDateString()}</Badge>}</div>
                    </div>
                    <Switch checked={a.enabled} onCheckedChange={(v) => toggle.mutate({ id: a.id, enabled: v })} aria-label="Enable publishing" />
                    <Button size="icon" variant="ghost" onClick={() => confirm("Disconnect this account?") && remove.mutate(a.id)}><Unplug /></Button>
                  </div>
                ))}
                {configured ? (
                  <Button className="w-full" variant={list.length ? "outline" : "default"} onClick={() => connect.mutate(key)} disabled={connect.isPending}><Link2 /> {list.length ? "Connect another / reconnect" : "Connect"}</Button>
                ) : (
                  <p className="rounded-md bg-muted p-3 text-[11px] text-muted-foreground">App credentials are not configured in <code>.env</code>. Register redirect URI <code className="break-all">{config.data?.redirect_uris?.[key]}</code> — see docs/PUBLISHING.md.</p>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

export default function AccountsPage() {
  return <Suspense><AccountsInner /></Suspense>;
}
