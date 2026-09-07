import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../lib/AuthContext";
import { LanguageSwitcher } from "./LanguageSwitcher";

export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  const { t } = useTranslation();
  const { user, parish, logout } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  async function handleLogout() {
    if (confirm(t("auth.logoutConfirm"))) {
      await logout();
      navigate("/login");
    }
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuClick}
          className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 lg:hidden"
          aria-label="Menu"
        >
          ☰
        </button>
        <div>
          <p className="text-sm font-semibold text-slate-900">{parish?.name || t("app.name")}</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <LanguageSwitcher />
        <div className="relative">
          <button
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-slate-100"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-brand-100 text-sm font-semibold text-brand-700">
              {user?.name?.slice(0, 1).toUpperCase()}
            </div>
            <span className="hidden text-sm font-medium text-slate-700 sm:block">{user?.name}</span>
          </button>
          {menuOpen && (
            <>
              <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} />
              <div className="absolute right-0 z-20 mt-2 w-52 rounded-xl border border-slate-200 bg-white py-1 shadow-lg">
                <div className="border-b border-slate-100 px-3 py-2">
                  <p className="truncate text-sm font-medium text-slate-800">{user?.email}</p>
                  <p className="text-xs text-slate-400">{user?.role}</p>
                </div>
                <button
                  onClick={handleLogout}
                  className="w-full px-3 py-2 text-left text-sm text-uscita-600 hover:bg-slate-50"
                >
                  {t("common.logout")}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
