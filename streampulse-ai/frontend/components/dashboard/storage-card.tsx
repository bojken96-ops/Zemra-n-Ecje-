import { HardDrive } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/misc";
import { formatBytes, humanize } from "@/lib/utils";
import type { StorageUsage } from "@/types";

export function StorageCard({ storage }: { storage: StorageUsage }) {
  const tone = storage.over_allocation || storage.low_disk ? "destructive" : storage.storage_percent > 75 ? "warning" : "primary";
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2"><HardDrive className="h-4 w-4 text-muted-foreground" /> Storage</CardTitle>
        <span className="text-xs text-muted-foreground">{formatBytes(storage.disk_free)} free on disk</span>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <div className="mb-1 flex justify-between text-xs"><span>{formatBytes(storage.storage_used)} used</span><span className="text-muted-foreground">of {formatBytes(storage.max_storage_bytes)} allocation</span></div>
          <Progress value={storage.storage_percent} tone={tone} />
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {Object.entries(storage.areas).map(([k, v]) => (
            <div key={k} className="flex justify-between"><span className="text-muted-foreground">{humanize(k)}</span><span className="tabular-nums">{formatBytes(v)}</span></div>
          ))}
        </div>
        {storage.low_disk && <p className="rounded-md bg-destructive/10 px-2 py-1.5 text-xs text-destructive">Low disk space — capture will stop below the configured minimum.</p>}
      </CardContent>
    </Card>
  );
}
