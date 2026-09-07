import clsx from "clsx";
import { ReactNode } from "react";

const toneClasses = {
  entrata: "bg-entrata-50 text-entrata-700",
  uscita: "bg-uscita-50 text-uscita-700",
  neutral: "bg-slate-100 text-slate-700",
  brand: "bg-brand-50 text-brand-700",
  gold: "bg-amber-50 text-amber-700",
};

export function Badge({ tone = "neutral", children }: { tone?: keyof typeof toneClasses; children: ReactNode }) {
  return (
    <span className={clsx("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium", toneClasses[tone])}>
      {children}
    </span>
  );
}
