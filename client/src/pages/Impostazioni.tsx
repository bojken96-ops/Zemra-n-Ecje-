import { FormEvent, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, apiErrorMessage } from "../lib/api";
import { AuditLogEntry, Currency } from "../lib/types";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { FormRow, Input, Select } from "../components/ui/Field";
import { useAuth } from "../lib/AuthContext";
import { SUPPORTED_LANGUAGES, setLanguage } from "../i18n";
import { formatDateTime } from "../lib/format";

export default function Impostazioni() {
  const { t, i18n } = useTranslation();
  const { user, parish, hasRole, refreshMe } = useAuth();
  const isAdmin = hasRole("ADMIN");

  const [parishName, setParishName] = useState(parish?.name || "");
  const [parishAddress, setParishAddress] = useState(parish?.address || "");
  const [parishTaxId, setParishTaxId] = useState(parish?.taxId || "");
  const [baseCurrency, setBaseCurrency] = useState<Currency>(parish?.currency || "EUR");
  const [savingParish, setSavingParish] = useState(false);
  const [parishSaved, setParishSaved] = useState(false);

  const [rate, setRate] = useState<number | null>(null);
  const [newRate, setNewRate] = useState("");
  const [rateHistory, setRateHistory] = useState<{ id: string; rateEurToAll: number; effectiveDate: string; createdBy: { name: string } }[]>([]);
  const [savingRate, setSavingRate] = useState(false);

  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);

  useEffect(() => {
    setParishName(parish?.name || "");
    setParishAddress(parish?.address || "");
    setParishTaxId(parish?.taxId || "");
    setBaseCurrency(parish?.currency || "EUR");
  }, [parish]);

  const loadRate = useCallback(async () => {
    const res = await api.get("/settings/exchange-rate");
    setRate(res.data.rateEurToAll);
    const hist = await api.get("/settings/exchange-rate/history");
    setRateHistory(hist.data);
  }, []);

  useEffect(() => {
    loadRate();
  }, [loadRate]);

  useEffect(() => {
    if (isAdmin) {
      api.get("/audit", { params: { pageSize: 30 } }).then((res) => setAuditLog(res.data.items));
    }
  }, [isAdmin]);

  async function saveParish(e: FormEvent) {
    e.preventDefault();
    setSavingParish(true);
    setParishSaved(false);
    try {
      await api.put("/settings/parish", { name: parishName, address: parishAddress, taxId: parishTaxId, currency: baseCurrency });
      await refreshMe();
      setParishSaved(true);
    } finally {
      setSavingParish(false);
    }
  }

  async function saveRate(e: FormEvent) {
    e.preventDefault();
    setSavingRate(true);
    try {
      await api.post("/settings/exchange-rate", { rateEurToAll: Number(newRate) });
      setNewRate("");
      await loadRate();
    } catch (err) {
      alert(apiErrorMessage(err));
    } finally {
      setSavingRate(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{t("settings.title")}</h1>
        <p className="text-sm text-slate-500">{t("settings.subtitle")}</p>
      </div>

      <Card>
        <h3 className="mb-4 text-sm font-semibold text-slate-700">{t("settings.profileSection")}</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 text-sm">
          <div>
            <p className="text-slate-400">{t("common.name")}</p>
            <p className="font-medium text-slate-800">{user?.name}</p>
          </div>
          <div>
            <p className="text-slate-400">{t("common.email")}</p>
            <p className="font-medium text-slate-800">{user?.email}</p>
          </div>
          <div>
            <p className="text-slate-400">{t("common.role")}</p>
            <p className="font-medium text-slate-800">{user && t(`users.role${user.role}`)}</p>
          </div>
        </div>
      </Card>

      <Card>
        <h3 className="mb-4 text-sm font-semibold text-slate-700">{t("settings.languageSection")}</h3>
        <div className="flex gap-2">
          {SUPPORTED_LANGUAGES.map((l) => (
            <button
              key={l.code}
              onClick={() => setLanguage(l.code)}
              className={`rounded-lg border px-4 py-2 text-sm font-medium ${
                i18n.language === l.code ? "border-brand-600 bg-brand-50 text-brand-700" : "border-slate-300 text-slate-600 hover:bg-slate-50"
              }`}
            >
              {l.flag} {l.label}
            </button>
          ))}
        </div>
      </Card>

      <Card>
        <h3 className="mb-4 text-sm font-semibold text-slate-700">{t("settings.parishSection")}</h3>
        <form onSubmit={saveParish} className="space-y-4">
          <FormRow label={t("settings.parishName")}>
            <Input required value={parishName} onChange={(e) => setParishName(e.target.value)} disabled={!isAdmin} />
          </FormRow>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormRow label={t("settings.parishAddress")}>
              <Input value={parishAddress} onChange={(e) => setParishAddress(e.target.value)} disabled={!isAdmin} />
            </FormRow>
            <FormRow label={t("settings.parishTaxId")}>
              <Input value={parishTaxId} onChange={(e) => setParishTaxId(e.target.value)} disabled={!isAdmin} />
            </FormRow>
          </div>
          <FormRow label={t("settings.baseCurrency")}>
            <Select value={baseCurrency} onChange={(e) => setBaseCurrency(e.target.value as Currency)} disabled={!isAdmin} className="!w-40">
              <option value="EUR">EUR</option>
              <option value="ALL">ALL</option>
            </Select>
          </FormRow>
          {isAdmin && (
            <div className="flex items-center gap-3">
              <Button type="submit" disabled={savingParish}>
                {savingParish ? t("common.saving") : t("common.save")}
              </Button>
              {parishSaved && <span className="text-sm text-entrata-600">{t("settings.saveSuccess")}</span>}
            </div>
          )}
        </form>
      </Card>

      <Card>
        <h3 className="mb-1 text-sm font-semibold text-slate-700">{t("settings.exchangeRateSection")}</h3>
        <p className="mb-4 text-xs text-slate-400">{t("settings.exchangeRateHint")}</p>
        <div className="mb-4 rounded-lg bg-brand-50 px-4 py-3 text-brand-800">
          <span className="text-sm">{t("settings.exchangeRateLabel")} </span>
          <span className="text-lg font-semibold">{rate ?? "-"}</span>
          <span className="text-sm"> {t("settings.exchangeRateUnit")}</span>
        </div>
        {isAdmin && (
          <form onSubmit={saveRate} className="flex items-end gap-3">
            <FormRow label={`${t("settings.exchangeRateLabel")} (${t("settings.exchangeRateUnit")})`}>
              <Input
                type="number"
                min="0.01"
                step="0.01"
                required
                value={newRate}
                onChange={(e) => setNewRate(e.target.value)}
                className="!w-40"
              />
            </FormRow>
            <Button type="submit" disabled={savingRate}>
              {savingRate ? t("common.saving") : t("common.save")}
            </Button>
          </form>
        )}
        {rateHistory.length > 0 && (
          <div className="mt-4">
            <p className="mb-2 text-xs font-medium uppercase text-slate-400">{t("settings.exchangeRateHistory")}</p>
            <ul className="max-h-48 space-y-1 overflow-y-auto text-sm">
              {rateHistory.map((r) => (
                <li key={r.id} className="flex justify-between border-b border-slate-100 py-1">
                  <span className="text-slate-500">{formatDateTime(r.effectiveDate)} · {r.createdBy.name}</span>
                  <span className="font-medium">1 EUR = {r.rateEurToAll} ALL</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>

      {isAdmin && (
        <Card>
          <h3 className="mb-1 text-sm font-semibold text-slate-700">{t("settings.auditLogSection")}</h3>
          <p className="mb-4 text-xs text-slate-400">{t("settings.auditLogSubtitle")}</p>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                  <th className="py-2 pr-4">{t("settings.auditWhen")}</th>
                  <th className="py-2 pr-4">{t("settings.auditBy")}</th>
                  <th className="py-2 pr-4">{t("settings.auditAction")}</th>
                  <th className="py-2 pr-4">{t("settings.auditEntity")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {auditLog.map((entry) => (
                  <tr key={entry.id}>
                    <td className="py-2 pr-4 text-slate-500">{formatDateTime(entry.createdAt)}</td>
                    <td className="py-2 pr-4 text-slate-700">{entry.user?.name}</td>
                    <td className="py-2 pr-4">
                      <Badge tone={entry.action === "CREATE" ? "entrata" : entry.action === "DELETE" ? "uscita" : "brand"}>
                        {t(`settings.action${entry.action}`)}
                      </Badge>
                    </td>
                    <td className="py-2 pr-4 text-slate-500">
                      {entry.entityType} · {entry.entityId.slice(0, 8)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}
