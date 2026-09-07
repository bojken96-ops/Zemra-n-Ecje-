import { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { LanguageSwitcher } from "../../components/layout/LanguageSwitcher";

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-brand-900 via-brand-700 to-brand-800 px-4 py-10">
      <div className="absolute right-4 top-4">
        <LanguageSwitcher light />
      </div>
      <div className="w-full max-w-md">
        <div className="mb-6 text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-gold-400 text-2xl font-serif font-bold text-brand-900 shadow-lg">
            ✝
          </div>
          <h1 className="font-serif text-2xl font-semibold text-white">{t("app.name")}</h1>
        </div>
        <div className="rounded-2xl bg-white p-6 shadow-2xl sm:p-8">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
          <div className="mt-6">{children}</div>
        </div>
      </div>
    </div>
  );
}
