"use client";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Save, XCircle } from "lucide-react";
import { api, put } from "@/lib/api";
import type { AppSettings } from "@/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { ErrorNote, PageHeader, Skeleton } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { humanize } from "@/lib/utils";

type Section = Exclude<keyof AppSettings, "environment">;
type Draft = Omit<AppSettings, "environment"> & { ai: AppSettings["ai"] & { api_key?: string } };

function Num({ label, value, onChange, step = 1, min, max, hint }: { label: string; value: number; onChange: (v: number) => void; step?: number; min?: number; max?: number; hint?: string }) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      <Input type="number" value={value} step={step} min={min} max={max} onChange={(e) => onChange(Number(e.target.value))} />
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}
function Toggle({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-md border p-3">
      <div><p className="text-sm">{label}</p>{hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}</div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}
function Choice<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="space-y-1.5"><Label>{label}</Label>
      <Select value={value} onChange={(e) => onChange(e.target.value as T)}>{options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
    </div>
  );
}
function Text({ label, value, onChange, type = "text", placeholder }: { label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string }) {
  return <div className="space-y-1.5"><Label>{label}</Label><Input type={type} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} /></div>;
}

export default function SettingsPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["settings"], queryFn: () => api<AppSettings>("/api/settings") });
  const [d, setD] = useState<Draft | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  useEffect(() => { if (q.data) { const { environment: _e, ...rest } = q.data; setD(structuredClone(rest)); } }, [q.data]);
  const save = useMutation({
    mutationFn: (section: Section) => put<AppSettings>("/api/settings", { [section]: d![section] }),
    onSuccess: (data, section) => { qc.setQueryData(["settings"], data); setSaved(section); setTimeout(() => setSaved(null), 2500); },
  });
  if (!d || !q.data) return <Skeleton className="h-96" />;
  const set = <S extends Section>(section: S, patch: Partial<Draft[S]>) => setD({ ...d, [section]: { ...d[section], ...patch } });
  const env = q.data.environment;
  const SaveBtn = ({ section }: { section: Section }) => (
    <div className="flex items-center gap-3 pt-2">
      <Button onClick={() => save.mutate(section)} disabled={save.isPending}><Save /> Save {humanize(section)}</Button>
      {saved === section && <span className="text-xs text-success">Saved</span>}
    </div>
  );
  const w = d.detection.weights;
  const wsum = w.chat + w.audio + w.visual + w.emoji + w.unique_users;

  return (
    <div>
      <PageHeader title="Settings" description="Runtime settings are stored in the database. Secrets for platforms live in .env." />
      <ErrorNote error={save.error} />
      <Tabs defaultValue="ai" className="mt-2">
        <TabsList className="flex-wrap">
          {["ai", "detection", "clips", "subtitles", "capture", "storage", "publishing", "system"].map((t) => <TabsTrigger key={t} value={t} className="capitalize">{t === "ai" ? "AI" : t}</TabsTrigger>)}
        </TabsList>

        <TabsContent value="ai">
          <Card><CardHeader><CardTitle>AI provider</CardTitle><CardDescription>Gemini evaluates candidate moments and writes titles/captions. The key is encrypted and never shown again.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              <Choice label="Provider" value={d.ai.provider} options={[["gemini", "Google Gemini"], ["none", "None (heuristics only)"]]} onChange={(v) => set("ai", { provider: v })} />
              <Text label="Model" value={d.ai.model} onChange={(v) => set("ai", { model: v })} />
              <Text label={`API key ${d.ai.api_key_configured ? "(configured — enter to replace)" : env.gemini_env_key_configured ? "(using GEMINI_API_KEY from .env)" : "(not configured)"}`} type="password" value={d.ai.api_key || ""} placeholder="AIza…" onChange={(v) => set("ai", { api_key: v })} />
              <Choice label="Default content language" value={d.ai.default_language} options={[["en", "English"], ["sq", "Albanian (Shqip)"]]} onChange={(v) => set("ai", { default_language: v })} />
              <Toggle label="Generate titles, captions and hashtags" checked={d.ai.generate_content} onChange={(v) => set("ai", { generate_content: v })} />
              <div className="md:col-span-2"><SaveBtn section="ai" /></div>
            </CardContent></Card>
        </TabsContent>

        <TabsContent value="detection">
          <Card><CardHeader><CardTitle>Detection</CardTitle><CardDescription>Signal weights (sum {wsum.toFixed(2)}; they are normalised). A clip needs the combined threshold AND enough individually elevated signals, including audio or visual evidence.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-5">
              {(["chat", "audio", "visual", "emoji", "unique_users"] as const).map((k) => <Num key={k} label={`${humanize(k)} weight`} step={0.05} min={0} max={1} value={w[k]} onChange={(v) => set("detection", { weights: { ...w, [k]: v } })} />)}
            </CardContent>
            <CardContent className="grid gap-4 md:grid-cols-4">
              <Num label="Window (s)" value={d.detection.window_seconds} onChange={(v) => set("detection", { window_seconds: v })} />
              <Num label="Baseline (min)" value={d.detection.baseline_minutes} onChange={(v) => set("detection", { baseline_minutes: v })} />
              <Num label="Combined threshold (0–1)" step={0.01} value={d.detection.candidate_threshold} onChange={(v) => set("detection", { candidate_threshold: v })} />
              <Num label="Elevated signal level (0–1)" step={0.05} value={d.detection.signal_elevated_threshold} onChange={(v) => set("detection", { signal_elevated_threshold: v })} />
              <Num label="Min elevated signals" value={d.detection.min_signals_above} onChange={(v) => set("detection", { min_signals_above: v })} />
              <Num label="Min AI viral score" value={d.detection.min_viral_score} onChange={(v) => set("detection", { min_viral_score: v })} />
              <Num label="Cooldown between clips (s)" value={d.detection.cooldown_seconds} onChange={(v) => set("detection", { cooldown_seconds: v })} />
            </CardContent>
            <CardContent className="grid gap-3 md:grid-cols-2">
              <Toggle label="Require AI evaluation" hint="If off and no AI is configured, heuristics decide." checked={d.detection.require_ai_evaluation} onChange={(v) => set("detection", { require_ai_evaluation: v })} />
              <Toggle label="Send keyframes to AI" checked={d.detection.send_keyframes_to_ai} onChange={(v) => set("detection", { send_keyframes_to_ai: v })} />
              <SaveBtn section="detection" />
            </CardContent></Card>
        </TabsContent>

        <TabsContent value="clips">
          <Card><CardHeader><CardTitle>Clip generation</CardTitle><CardDescription>Output is always H.264/AAC MP4 at 1080×1920 (9:16).</CardDescription></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-3">
              <Num label="Seconds before event" value={d.clips.pre_event_seconds} onChange={(v) => set("clips", { pre_event_seconds: v })} />
              <Num label="Seconds after event" value={d.clips.post_event_seconds} onChange={(v) => set("clips", { post_event_seconds: v })} />
              <Num label="Merge moments within (s)" value={d.clips.merge_gap_seconds} onChange={(v) => set("clips", { merge_gap_seconds: v })} />
              <Num label="Minimum length (s)" value={d.clips.min_length_seconds} onChange={(v) => set("clips", { min_length_seconds: v })} />
              <Num label="Maximum length (s)" value={d.clips.max_length_seconds} onChange={(v) => set("clips", { max_length_seconds: v })} />
              <Num label="Sentence snap (max s)" value={d.clips.sentence_snap_max_seconds} onChange={(v) => set("clips", { sentence_snap_max_seconds: v })} hint="Extends cuts so sentences aren't cut in half." />
              <Choice label="Vertical framing" value={d.clips.vertical_mode} options={[["blur_background", "Full frame on blurred background"], ["center_crop", "Centre crop (fills screen)"], ["fit_black", "Full frame on black"]]} onChange={(v) => set("clips", { vertical_mode: v })} />
              <Choice label="Frame rate" value={d.clips.target_fps} options={[["auto", "Auto (60 if source ≥ 50 fps)"], ["30", "30 fps"], ["60", "60 fps"]]} onChange={(v) => set("clips", { target_fps: v })} />
              <Num label="Loudness target (LUFS)" value={d.clips.loudness_target_lufs} onChange={(v) => set("clips", { loudness_target_lufs: v })} />
              <div className="md:col-span-3"><SaveBtn section="clips" /></div>
            </CardContent></Card>
        </TabsContent>

        <TabsContent value="subtitles">
          <Card><CardHeader><CardTitle>Subtitles</CardTitle><CardDescription>faster-whisper with word timestamps and automatic English/Albanian detection.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-3">
              <Toggle label="Burn subtitles into clips" checked={d.subtitles.enabled} onChange={(v) => set("subtitles", { enabled: v })} />
              <Choice label="Default style" value={d.subtitles.style} options={[["clean", "Clean white"], ["highlight", "Highlighted keywords"], ["animated", "Creator-style animated"], ["minimal", "Minimal"]]} onChange={(v) => set("subtitles", { style: v })} />
              <Text label="Font family" value={d.subtitles.font} onChange={(v) => set("subtitles", { font: v })} />
              <Num label="Font size" value={d.subtitles.font_size} onChange={(v) => set("subtitles", { font_size: v })} />
              <Choice label="Position" value={d.subtitles.position} options={[["bottom", "Bottom"], ["middle", "Middle"], ["top", "Top"]]} onChange={(v) => set("subtitles", { position: v })} />
              <Num label="Vertical margin (px)" value={d.subtitles.margin_v} onChange={(v) => set("subtitles", { margin_v: v })} />
              {(["primary_color", "highlight_color", "outline_color"] as const).map((k) => (
                <div key={k} className="space-y-1.5"><Label>{humanize(k)}</Label><div className="flex gap-2"><input type="color" className="h-9 w-12 rounded border bg-transparent" value={d.subtitles[k]} onChange={(e) => set("subtitles", { [k]: e.target.value.toUpperCase() })} /><Input value={d.subtitles[k]} onChange={(e) => set("subtitles", { [k]: e.target.value })} /></div></div>
              ))}
              <Num label="Max words per line" value={d.subtitles.max_words_per_line} onChange={(v) => set("subtitles", { max_words_per_line: v })} />
              <Toggle label="UPPERCASE" checked={d.subtitles.uppercase} onChange={(v) => set("subtitles", { uppercase: v })} />
              <div className="md:col-span-3"><SaveBtn section="subtitles" /></div>
            </CardContent></Card>
        </TabsContent>

        <TabsContent value="capture">
          <Card><CardHeader><CardTitle>Capture agent</CardTitle><CardDescription>Applied by the Windows capture agent. A capture method that is unavailable is reported — never silently swapped.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-3">
              <Choice label="Video capture backend" value={d.capture.video_backend} options={[["gfxcapture", "Windows Graphics Capture (FFmpeg 8+)"], ["gdigrab", "GDI window capture (window must stay visible)"]]} onChange={(v) => set("capture", { video_backend: v })} />
              <Choice label="Audio mode" value={d.capture.audio_mode} options={[["virtual_cable", "Virtual audio cable per stream"], ["dshow_device", "Single device (one stream at a time)"]]} onChange={(v) => set("capture", { audio_mode: v })} />
              <Choice label="Encoder" value={d.capture.video_encoder} options={[["auto", "Auto (GPU if available)"], ["libx264", "CPU (libx264)"], ["h264_nvenc", "NVIDIA NVENC"], ["h264_qsv", "Intel Quick Sync"], ["h264_amf", "AMD AMF"]]} onChange={(v) => set("capture", { video_encoder: v })} />
              <Num label="Segment length (s)" value={d.capture.segment_seconds} onChange={(v) => set("capture", { segment_seconds: v })} />
              <Num label="Frame rate" value={d.capture.framerate} onChange={(v) => set("capture", { framerate: v })} />
              <Num label="Max concurrent captures" value={d.capture.max_concurrent_captures} onChange={(v) => set("capture", { max_concurrent_captures: v })} />
              <Num label="Output width" value={d.capture.output_width} onChange={(v) => set("capture", { output_width: v })} />
              <Num label="Output height" value={d.capture.output_height} onChange={(v) => set("capture", { output_height: v })} />
              <Num label="Stop capture below free disk (GB)" value={d.capture.min_free_disk_gb} onChange={(v) => set("capture", { min_free_disk_gb: v })} />
              <Num label="Black-screen alert after (s)" value={d.capture.black_screen_alert_seconds} onChange={(v) => set("capture", { black_screen_alert_seconds: v })} />
              <Num label="Frozen-frame alert after (s)" value={d.capture.frozen_frame_alert_seconds} onChange={(v) => set("capture", { frozen_frame_alert_seconds: v })} />
              <div className="md:col-span-3"><SaveBtn section="capture" /></div>
            </CardContent></Card>
        </TabsContent>

        <TabsContent value="storage">
          <Card><CardHeader><CardTitle>Storage</CardTitle><CardDescription>Published clips and footage used by clips are never deleted automatically.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-3">
              <Num label="Maximum storage (GB)" value={d.storage.max_storage_gb} onChange={(v) => set("storage", { max_storage_gb: v })} />
              <Num label="Keep raw recordings (hours)" value={d.storage.recording_retention_hours} onChange={(v) => set("storage", { recording_retention_hours: v })} />
              <Num label="Keep temporary files (hours)" value={d.storage.temporary_retention_hours} onChange={(v) => set("storage", { temporary_retention_hours: v })} />
              <Num label="Low-disk alert at (% used)" value={d.storage.low_disk_alert_percent} onChange={(v) => set("storage", { low_disk_alert_percent: v })} />
              <Toggle label="Keep footage used by clips" checked={d.storage.keep_footage_used_by_clips} onChange={(v) => set("storage", { keep_footage_used_by_clips: v })} />
              <div className="md:col-span-3"><SaveBtn section="storage" /></div>
            </CardContent></Card>
        </TabsContent>

        <TabsContent value="publishing">
          <Card><CardHeader><CardTitle>Publishing</CardTitle><CardDescription>With automatic publishing off, clips wait for your approval.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-3">
              <Toggle label="Automatic publishing" hint="Publish every generated clip without approval." checked={d.publishing.auto_publish} onChange={(v) => set("publishing", { auto_publish: v })} />
              {(["youtube", "tiktok", "instagram"] as const).map((p) => <Toggle key={p} label={`Publish to ${humanize(p)}`} checked={!!d.publishing.platforms[p]} onChange={(v) => set("publishing", { platforms: { ...d.publishing.platforms, [p]: v } })} />)}
              <Text label="Hashtag template" value={d.publishing.hashtag_template} onChange={(v) => set("publishing", { hashtag_template: v })} />
              <Text label="Description template ({caption} {hashtags} {title})" value={d.publishing.description_template} onChange={(v) => set("publishing", { description_template: v })} />
              <Num label="Delay before publishing (min)" value={d.publishing.default_delay_minutes} onChange={(v) => set("publishing", { default_delay_minutes: v })} />
              <Num label="Max attempts" value={d.publishing.max_attempts} onChange={(v) => set("publishing", { max_attempts: v })} />
              <Choice label="YouTube visibility" value={d.publishing.youtube_privacy} options={[["private", "Private"], ["unlisted", "Unlisted"], ["public", "Public"]]} onChange={(v) => set("publishing", { youtube_privacy: v })} />
              <Choice label="TikTok privacy (if allowed for your app)" value={d.publishing.tiktok_privacy as "SELF_ONLY"} options={[["SELF_ONLY", "Only me"], ["MUTUAL_FOLLOW_FRIENDS" as "SELF_ONLY", "Friends"], ["FOLLOWER_OF_CREATOR" as "SELF_ONLY", "Followers"], ["PUBLIC_TO_EVERYONE" as "SELF_ONLY", "Everyone"]]} onChange={(v) => set("publishing", { tiktok_privacy: v })} />
              <div className="md:col-span-3"><SaveBtn section="publishing" /></div>
            </CardContent></Card>
        </TabsContent>

        <TabsContent value="system">
          <Card><CardHeader><CardTitle>Environment & credentials</CardTitle><CardDescription>Read-only status of values configured in .env.</CardDescription></CardHeader>
            <CardContent className="grid gap-2 md:grid-cols-2">
              {Object.entries(env).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between rounded-md border px-3 py-2 text-xs">
                  <span className="text-muted-foreground">{humanize(k)}</span>
                  {typeof v === "boolean" ? (v ? <CheckCircle2 className="h-4 w-4 text-success" /> : <XCircle className="h-4 w-4 text-destructive" />) : <span className="font-mono">{v}</span>}
                </div>
              ))}
            </CardContent></Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
