"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import type { Analytics } from "@/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader, Skeleton } from "@/components/ui/misc";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { StorageCard } from "@/components/dashboard/storage-card";
import { humanize } from "@/lib/utils";

const COLORS = ["hsl(262 83% 64%)", "hsl(199 89% 55%)", "hsl(38 92% 55%)", "hsl(152 62% 45%)", "hsl(330 81% 60%)", "hsl(0 84% 58%)", "hsl(240 5% 62%)"];
const tip = { contentStyle: { background: "hsl(240 8% 7%)", border: "1px solid hsl(240 5% 16%)", borderRadius: 8, fontSize: 12 } };
const axis = { tick: { fontSize: 11, fill: "hsl(240 5% 62%)" } };

export default function AnalyticsPage() {
  const [days, setDays] = useState("30");
  const q = useQuery({ queryKey: ["analytics", days], queryFn: () => api<Analytics>(`/api/analytics?days=${days}`) });
  const a = q.data;
  const platforms = ["youtube", "tiktok", "instagram"].map((p) => {
    const row: Record<string, string | number> = { platform: humanize(p) };
    for (const r of a?.by_platform || []) if (r.platform === p) row[r.status] = r.count;
    return row;
  });
  const candidates = Object.entries(a?.candidates || {}).map(([name, value]) => ({ name: humanize(name), value }));

  return (
    <div>
      <PageHeader title="Analytics" description="Detection, clipping and publishing performance.">
        <Tabs value={days} onValueChange={setDays}><TabsList>{["7", "30", "90"].map((d) => <TabsTrigger key={d} value={d}>{d} days</TabsTrigger>)}</TabsList></Tabs>
      </PageHeader>
      {!a ? <Skeleton className="h-96" /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card className="lg:col-span-2">
            <CardHeader><CardTitle>Clips generated and published per day</CardTitle></CardHeader>
            <CardContent className="h-64"><ResponsiveContainer><BarChart data={a.series} margin={{ left: -20 }}><CartesianGrid strokeDasharray="3 3" stroke="hsl(240 5% 16%)" /><XAxis dataKey="date" tickFormatter={(d) => d.slice(5)} {...axis} /><YAxis allowDecimals={false} {...axis} /><Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 11 }} /><Bar dataKey="clips" fill={COLORS[0]} radius={[4, 4, 0, 0]} /><Bar dataKey="published" fill={COLORS[3]} radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Moment types</CardTitle></CardHeader>
            <CardContent className="h-64"><ResponsiveContainer><PieChart><Pie data={a.by_moment_type.map((m) => ({ name: humanize(m.moment_type), value: m.count }))} dataKey="value" nameKey="name" innerRadius={50} outerRadius={85} paddingAngle={2}>{a.by_moment_type.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Pie><Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 11 }} /></PieChart></ResponsiveContainer></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Detected moments by outcome</CardTitle></CardHeader>
            <CardContent className="h-64"><ResponsiveContainer><BarChart data={candidates} layout="vertical" margin={{ left: 20 }}><CartesianGrid strokeDasharray="3 3" stroke="hsl(240 5% 16%)" /><XAxis type="number" allowDecimals={false} {...axis} /><YAxis type="category" dataKey="name" width={80} {...axis} /><Tooltip {...tip} /><Bar dataKey="value" fill={COLORS[1]} radius={[0, 4, 4, 0]} /></BarChart></ResponsiveContainer></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Publishing by platform</CardTitle></CardHeader>
            <CardContent className="h-64"><ResponsiveContainer><BarChart data={platforms} margin={{ left: -20 }}><CartesianGrid strokeDasharray="3 3" stroke="hsl(240 5% 16%)" /><XAxis dataKey="platform" {...axis} /><YAxis allowDecimals={false} {...axis} /><Tooltip {...tip} /><Legend wrapperStyle={{ fontSize: 11 }} />{["published", "processing", "scheduled", "failed"].map((s, i) => <Bar key={s} dataKey={s} stackId="a" fill={[COLORS[3], COLORS[2], COLORS[0], COLORS[5]][i]} />)}</BarChart></ResponsiveContainer></CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Clips per creator</CardTitle></CardHeader>
            <CardContent className="h-64"><ResponsiveContainer><BarChart data={a.by_creator} margin={{ left: -20 }}><CartesianGrid strokeDasharray="3 3" stroke="hsl(240 5% 16%)" /><XAxis dataKey="creator" {...axis} /><YAxis allowDecimals={false} {...axis} /><Tooltip {...tip} /><Bar dataKey="clips" fill={COLORS[4]} radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></CardContent>
          </Card>
          <StorageCard storage={a.storage} />
        </div>
      )}
    </div>
  );
}
