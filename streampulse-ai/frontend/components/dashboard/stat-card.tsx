import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function StatCard({ label, value, icon: Icon, hint, tone }: { label: string; value: React.ReactNode; icon: React.ElementType; hint?: string; tone?: "live" | "warning" | "destructive" | "success" }) {
  const color = tone ? { live: "text-live", warning: "text-warning", destructive: "text-destructive", success: "text-success" }[tone] : "text-primary";
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">{label}</p>
        <Icon className={cn("h-4 w-4", color)} />
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
    </Card>
  );
}
