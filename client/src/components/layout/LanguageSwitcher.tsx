import { useTranslation } from "react-i18next";
import { SUPPORTED_LANGUAGES, setLanguage } from "../../i18n";
import clsx from "clsx";

export function LanguageSwitcher({ light }: { light?: boolean }) {
  const { i18n } = useTranslation();
  return (
    <select
      value={i18n.language}
      onChange={(e) => setLanguage(e.target.value)}
      className={clsx(
        "rounded-lg border px-2 py-1.5 text-sm outline-none",
        light ? "border-white/30 bg-white/10 text-white [color-scheme:dark]" : "border-slate-300 bg-white text-slate-700"
      )}
      aria-label="Lingua"
    >
      {SUPPORTED_LANGUAGES.map((l) => (
        <option key={l.code} value={l.code}>
          {l.flag} {l.label}
        </option>
      ))}
    </select>
  );
}
