import { HTMLAttributes } from "react";
import clsx from "clsx";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("rounded-2xl border border-slate-200 bg-white p-5 shadow-sm", className)} {...props} />;
}

export function StatCard({
  label,
  value,
  sub,
  tone = "neutral",
  icon,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "positive" | "negative" | "brand";
  icon?: string;
}) {
  const toneClasses: Record<string, string> = {
    neutral: "text-slate-900",
    positive: "text-entrata-600",
    negative: "text-uscita-600",
    brand: "text-brand-700",
  };
  return (
    <Card className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</span>
        {icon && <span className="text-lg">{icon}</span>}
      </div>
      <span className={clsx("text-2xl font-semibold", toneClasses[tone])}>{value}</span>
      {sub && <span className="text-xs text-slate-400">{sub}</span>}
    </Card>
  );
}
