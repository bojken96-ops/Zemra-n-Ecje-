import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { api } from "../lib/api";
import { Card } from "../components/ui/Card";
import { Select } from "../components/ui/Field";
import { Button } from "../components/ui/Button";
import { formatAmount, categoryLabel } from "../lib/format";
import { downloadReport } from "../lib/download";

interface MonthlyReport {
  year: number;
  month: number;
  saldoIniziale: { cashALL: number; cashEUR: number; bankALL: number; bankEUR: number };
  saldoFinale: { cashALL: number; cashEUR: number; bankALL: number; bankEUR: number };
  totaleEntrate: { ALL: number; EUR: number };
  totaleUscite: { ALL: number; EUR: number };
  numeroMovimenti: number;
  entrateByCategory: { category: { name: string; translationKey: string | null } | null; amount: number }[];
  usciteByCategory: { category: { name: string; translationKey: string | null } | null; amount: number }[];
}

const YEARS = Array.from({ length: 8 }, (_, i) => new Date().getFullYear() - 5 + i);

export default function Bilancio() {
  const { t } = useTranslation();
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [report, setReport] = useState<MonthlyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [compareMonths, setCompareMonths] = useState<string[]>([]);
  const [compareData, setCompareData] = useState<MonthlyReport[]>([]);

  useEffect(() => {
    setLoading(true);
    api
      .get("/reports/monthly", { params: { year, month } })
      .then((res) => setReport(res.data))
      .finally(() => setLoading(false));
  }, [year, month]);

  useEffect(() => {
    if (compareMonths.length === 0) {
      setCompareData([]);
      return;
    }
    api.get("/reports/compare", { params: { months: compareMonths.join(",") } }).then((res) => setCompareData(res.data));
  }, [compareMonths]);

  const currentMonthKey = `${year}-${String(month).padStart(2, "0")}`;

  function addCurrentToCompare() {
    if (!compareMonths.includes(currentMonthKey)) setCompareMonths((m) => [...m, currentMonthKey]);
  }

  function removeCompare(key: string) {
    setCompareMonths((m) => m.filter((x) => x !== key));
  }

  const chartData = useMemo(() => {
    if (!report) return [];
    return [
      { name: "ALL", entrate: report.totaleEntrate.ALL, uscite: report.totaleUscite.ALL },
      { name: "EUR", entrate: report.totaleEntrate.EUR, uscite: report.totaleUscite.EUR },
    ];
  }, [report]);

  async function exportFile(format: "pdf" | "excel") {
    await downloadReport(
      `/reports/monthly/export?year=${year}&month=${month}&format=${format}`,
      `bilancio-${currentMonthKey}.${format === "pdf" ? "pdf" : "xlsx"}`
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{t("balance.title")}</h1>
          <p className="text-sm text-slate-500">{t("balance.subtitle")}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => exportFile("pdf")}>
            📄 {t("common.exportPdf")}
          </Button>
          <Button variant="secondary" onClick={() => exportFile("excel")}>
            📊 {t("common.exportExcel")}
          </Button>
        </div>
      </div>

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">{t("balance.selectMonth")}</label>
            <Select value={month} onChange={(e) => setMonth(Number(e.target.value))} className="!w-40">
              {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
                <option key={m} value={m}>
                  {t(`months.${m}`)}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">{t("balance.selectYear")}</label>
            <Select value={year} onChange={(e) => setYear(Number(e.target.value))} className="!w-32">
              {YEARS.map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </Select>
          </div>
          <Button variant="secondary" onClick={addCurrentToCompare}>
            + {t("balance.addComparison")}
          </Button>
        </div>
      </Card>

      {loading || !report ? (
        <p className="text-slate-400">{t("common.loading")}</p>
      ) : (
        <>
          <p className="text-center text-xs text-slate-400">{t("balance.equation")}</p>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <h3 className="mb-3 text-sm font-semibold text-brand-700">{t("balance.cashSection")}</h3>
              <table className="w-full text-sm">
                <tbody>
                  <tr className="border-b border-slate-100">
                    <td className="py-1.5 text-slate-500">{t("balance.saldoIniziale")} ALL</td>
                    <td className="py-1.5 text-right font-medium">{formatAmount(report.saldoIniziale.cashALL, "ALL")}</td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="py-1.5 text-slate-500">{t("balance.saldoIniziale")} EUR</td>
                    <td className="py-1.5 text-right font-medium">{formatAmount(report.saldoIniziale.cashEUR, "EUR")}</td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="py-1.5 text-slate-500">{t("balance.saldoFinale")} ALL</td>
                    <td className="py-1.5 text-right font-semibold text-brand-700">{formatAmount(report.saldoFinale.cashALL, "ALL")}</td>
                  </tr>
                  <tr>
                    <td className="py-1.5 text-slate-500">{t("balance.saldoFinale")} EUR</td>
                    <td className="py-1.5 text-right font-semibold text-brand-700">{formatAmount(report.saldoFinale.cashEUR, "EUR")}</td>
                  </tr>
                </tbody>
              </table>
            </Card>

            <Card>
              <h3 className="mb-3 text-sm font-semibold text-brand-700">{t("balance.bankSection")}</h3>
              <table className="w-full text-sm">
                <tbody>
                  <tr className="border-b border-slate-100">
                    <td className="py-1.5 text-slate-500">{t("balance.saldoIniziale")} ALL</td>
                    <td className="py-1.5 text-right font-medium">{formatAmount(report.saldoIniziale.bankALL, "ALL")}</td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="py-1.5 text-slate-500">{t("balance.saldoIniziale")} EUR</td>
                    <td className="py-1.5 text-right font-medium">{formatAmount(report.saldoIniziale.bankEUR, "EUR")}</td>
                  </tr>
                  <tr className="border-b border-slate-100">
                    <td className="py-1.5 text-slate-500">{t("balance.saldoFinale")} ALL</td>
                    <td className="py-1.5 text-right font-semibold text-brand-700">{formatAmount(report.saldoFinale.bankALL, "ALL")}</td>
                  </tr>
                  <tr>
                    <td className="py-1.5 text-slate-500">{t("balance.saldoFinale")} EUR</td>
                    <td className="py-1.5 text-right font-semibold text-brand-700">{formatAmount(report.saldoFinale.bankEUR, "EUR")}</td>
                  </tr>
                </tbody>
              </table>
            </Card>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <p className="text-xs font-medium uppercase text-slate-500">{t("balance.totaleEntrate")}</p>
              <p className="mt-1 text-lg font-semibold text-entrata-600">
                {formatAmount(report.totaleEntrate.ALL, "ALL")} / {formatAmount(report.totaleEntrate.EUR, "EUR")}
              </p>
            </Card>
            <Card>
              <p className="text-xs font-medium uppercase text-slate-500">{t("balance.totaleUscite")}</p>
              <p className="mt-1 text-lg font-semibold text-uscita-600">
                {formatAmount(report.totaleUscite.ALL, "ALL")} / {formatAmount(report.totaleUscite.EUR, "EUR")}
              </p>
            </Card>
            <Card>
              <p className="text-xs font-medium uppercase text-slate-500">{t("balance.risultatoNetto")}</p>
              <p className="mt-1 text-lg font-semibold text-brand-700">
                {formatAmount(report.totaleEntrate.ALL - report.totaleUscite.ALL, "ALL")} /{" "}
                {formatAmount(report.totaleEntrate.EUR - report.totaleUscite.EUR, "EUR")}
              </p>
            </Card>
            <Card>
              <p className="text-xs font-medium uppercase text-slate-500">{t("balance.numeroMovimenti")}</p>
              <p className="mt-1 text-lg font-semibold text-slate-800">{report.numeroMovimenti}</p>
            </Card>
          </div>

          <Card>
            <h3 className="mb-4 text-sm font-semibold text-slate-700">{t("balance.monthlyChart")}</h3>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef1f6" />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
                <Tooltip />
                <Legend />
                <Bar dataKey="entrate" name={t("transactions.ENTRATA")} fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="uscite" name={t("transactions.USCITA")} fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Card>
              <h3 className="mb-3 text-sm font-semibold text-slate-700">{t("balance.entrateCategoria")}</h3>
              {report.entrateByCategory.length === 0 ? (
                <p className="text-sm text-slate-400">{t("dashboard.noData")}</p>
              ) : (
                <ul className="space-y-1.5 text-sm">
                  {report.entrateByCategory.map((c, i) => (
                    <li key={i} className="flex justify-between">
                      <span className="text-slate-600">{c.category ? categoryLabel(t, c.category) : "N/D"}</span>
                      <span className="font-medium text-entrata-600">{c.amount.toFixed(2)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <h3 className="mb-3 text-sm font-semibold text-slate-700">{t("balance.speseCategoria")}</h3>
              {report.usciteByCategory.length === 0 ? (
                <p className="text-sm text-slate-400">{t("dashboard.noData")}</p>
              ) : (
                <ul className="space-y-1.5 text-sm">
                  {report.usciteByCategory.map((c, i) => (
                    <li key={i} className="flex justify-between">
                      <span className="text-slate-600">{c.category ? categoryLabel(t, c.category) : "N/D"}</span>
                      <span className="font-medium text-uscita-600">{c.amount.toFixed(2)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
        </>
      )}

      <Card>
        <h3 className="mb-3 text-sm font-semibold text-slate-700">{t("balance.compareTitle")}</h3>
        {compareData.length === 0 ? (
          <p className="text-sm text-slate-400">{t("dashboard.noData")}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
                  <th className="py-2 pr-4">{t("common.date")}</th>
                  <th className="py-2 pr-4 text-right">{t("balance.totaleEntrate")} (ALL/EUR)</th>
                  <th className="py-2 pr-4 text-right">{t("balance.totaleUscite")} (ALL/EUR)</th>
                  <th className="py-2 pr-4 text-right">{t("balance.risultatoNetto")} (ALL/EUR)</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {compareData.map((r) => {
                  const key = `${r.year}-${String(r.month).padStart(2, "0")}`;
                  return (
                    <tr key={key}>
                      <td className="py-2 pr-4 font-medium text-slate-700">
                        {t(`months.${r.month}`)} {r.year}
                      </td>
                      <td className="py-2 pr-4 text-right text-entrata-600">
                        {r.totaleEntrate.ALL.toFixed(2)} / {r.totaleEntrate.EUR.toFixed(2)}
                      </td>
                      <td className="py-2 pr-4 text-right text-uscita-600">
                        {r.totaleUscite.ALL.toFixed(2)} / {r.totaleUscite.EUR.toFixed(2)}
                      </td>
                      <td className="py-2 pr-4 text-right font-medium">
                        {(r.totaleEntrate.ALL - r.totaleUscite.ALL).toFixed(2)} /{" "}
                        {(r.totaleEntrate.EUR - r.totaleUscite.EUR).toFixed(2)}
                      </td>
                      <td className="py-2 text-right">
                        <button onClick={() => removeCompare(key)} className="text-xs text-uscita-600 hover:underline">
                          {t("common.delete")}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
