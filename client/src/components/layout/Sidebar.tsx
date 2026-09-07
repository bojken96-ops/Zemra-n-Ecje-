import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import clsx from "clsx";
import { useAuth } from "../../lib/AuthContext";

const items = [
  { to: "/", key: "dashboard", icon: "📊", end: true },
  { to: "/entrate", key: "entrate", icon: "💶" },
  { to: "/uscite", key: "uscite", icon: "💸" },
  { to: "/preventivi", key: "preventivi", icon: "📋" },
  { to: "/movimenti", key: "movimenti", icon: "📑" },
  { to: "/bilancio", key: "bilancio", icon: "📈" },
  { to: "/categorie", key: "categorie", icon: "🏷️" },
  { to: "/utenti", key: "utenti", icon: "👥", adminOnly: true },
  { to: "/impostazioni", key: "impostazioni", icon: "⚙️" },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { t } = useTranslation();
  const { hasRole } = useAuth();

  return (
    <nav className="flex h-full flex-col gap-1 p-3">
      <div className="mb-4 flex items-center gap-2 px-2 pt-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gold-400 font-serif text-lg font-bold text-brand-900">
          ✝
        </div>
        <span className="font-serif text-lg font-semibold text-white">{t("app.name")}</span>
      </div>
      {items
        .filter((i) => !i.adminOnly || hasRole("ADMIN"))
        .map((item) => (
          <NavLink
            key={item.key}
            to={item.to}
            end={item.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              clsx(
                "flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors",
                isActive ? "bg-white/15 text-white" : "text-brand-100/80 hover:bg-white/10 hover:text-white"
              )
            }
          >
            <span className="text-base">{item.icon}</span>
            {t(`nav.${item.key}`)}
          </NavLink>
        ))}
    </nav>
  );
}
