import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";
import { api } from "../lib/api";
import { DashboardData } from "../lib/types";
import { StatCard, Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { formatAmount, formatDate, formatEur, categoryLabel } from "../lib/format";

const PIE_COLORS = ["#3563d4", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899", "#84cc16", "#f97316"];

export default function Dashboard() {
  const { t } = useTranslation();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/dashboard")
      .then((res) => setData(res.data))
      .finally(() => setLoading(false));
  }, []);

  if (loading || !data) {
    return <div className="text-slate-400">{t("common.loading")}</div>;
  }

  const trendData = data.trend.map((m) => {
    const [y, mo] = m.month.split("-");
    return {
      label: `${t(`months.${parseInt(mo, 10)}`).slice(0, 3)} ${y.slice(2)}`,
      entrate: Math.round(m.entrate * 100) / 100,
      uscite: Math.round(m.uscite * 100) / 100,
      saldo: Math.round(m.saldo * 100) / 100,
    };
  });

  const pieData = data.expenseDistribution.map((e) => ({
    name: e.translationKey ? t(`categoriesData.${e.translationKey}`, e.category) : e.category,
    value: Math.round(e.amount * 100) / 100,
  }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{t("dashboard.title")}</h1>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label={t("dashboard.saldoTotale")}
          value={formatEur(data.saldoTotaleEur)}
          tone="brand"
          icon="💰"
          sub={t("dashboard.equivalentEur")}
        />
        <StatCard label={t("dashboard.saldoCash")} value={formatEur(data.saldoCashEur)} icon="🪙" />
        <StatCard label={t("dashboard.saldoBank")} value={formatEur(data.saldoBankEur)} icon="🏦" />
        <StatCard
          label={t("dashboard.risultatoDelMese")}
          value={formatEur(data.risultatoDelMeseEur)}
          tone={data.risultatoDelMeseEur >= 0 ? "positive" : "negative"}
          icon="📈"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t("dashboard.cashALL")} value={formatAmount(data.balances.cashALL, "ALL")} />
        <StatCard label={t("dashboard.cashEUR")} value={formatAmount(data.balances.cashEUR, "EUR")} />
        <StatCard label={t("dashboard.bankALL")} value={formatAmount(data.balances.bankALL, "ALL")} />
        <StatCard label={t("dashboard.bankEUR")} value={formatAmount(data.balances.bankEUR, "EUR")} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <StatCard
          label={t("dashboard.entrateDelMese")}
          value={formatEur(data.entrateDelMese.eur)}
          tone="positive"
          sub={`${formatAmount(data.entrateDelMese.ALL, "ALL")} / ${formatAmount(data.entrateDelMese.EUR, "EUR")}`}
        />
        <StatCard
          label={t("dashboard.usciteDelMese")}
          value={formatEur(data.usciteDelMese.eur)}
          tone="negative"
          sub={`${formatAmount(data.usciteDelMese.ALL, "ALL")} / ${formatAmount(data.usciteDelMese.EUR, "EUR")}`}
        />
        <StatCard label={t("dashboard.preventiviAperti")} value={String(data.preventiviAperti.length)} icon="📋" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <h3 className="mb-4 text-sm font-semibold text-slate-700">{t("dashboard.entrateVsUscite")}</h3>
          {trendData.every((d) => d.entrate === 0 && d.uscite === 0) ? (
            <p className="py-10 text-center text-sm text-slate-400">{t("dashboard.noData")}</p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef1f6" />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
                <Tooltip formatter={(v: any) => formatEur(Number(v))} />
                <Legend />
                <Bar dataKey="entrate" name={t("transactions.ENTRATA")} fill="#10b981" radius={[4, 4, 0, 0]} />
                <Bar dataKey="uscite" name={t("transactions.USCITA")} fill="#ef4444" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card>
          <h3 className="mb-4 text-sm font-semibold text-slate-700">{t("dashboard.andamentoSaldo")}</h3>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eef1f6" />
              <XAxis dataKey="label" tick={{ fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
              <Tooltip formatter={(v: any) => formatEur(Number(v))} />
              <Line type="monotone" dataKey="saldo" name={t("dashboard.saldoTotale")} stroke="#3563d4" strokeWidth={2.5} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <h3 className="mb-4 text-sm font-semibold text-slate-700">{t("dashboard.distribuzioneSpese")}</h3>
          {pieData.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-400">{t("dashboard.noData")}</p>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                  {pieData.map((_, idx) => (
                    <Cell key={idx} fill={PIE_COLORS[idx % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v: any) => Number(v).toFixed(2)} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card className="lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-slate-700">{t("dashboard.ultimiMovimenti")}</h3>
            <Link to="/movimenti" className="text-xs font-medium text-brand-700 hover:underline">
              {t("dashboard.viewAll")}
            </Link>
          </div>
          {data.ultimiMovimenti.length === 0 ? (
            <p className="py-10 text-center text-sm text-slate-400">{t("dashboard.noRecentTransactions")}</p>
          ) : (
            <div className="divide-y divide-slate-100">
              {data.ultimiMovimenti.map((mv) => (
                <div key={mv.id} className="flex items-center justify-between py-2.5">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-800">{mv.description}</p>
                    <p className="text-xs text-slate-400">
                      {formatDate(mv.date)} · {categoryLabel(t, mv.category)}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={mv.type === "ENTRATA" ? "entrata" : "uscita"}>
                      {mv.type === "ENTRATA" ? "+" : "-"}
                      {formatAmount(mv.amount, mv.currency)}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700">{t("dashboard.preventiviAperti")}</h3>
          <Link to="/preventivi" className="text-xs font-medium text-brand-700 hover:underline">
            {t("dashboard.viewAll")}
          </Link>
        </div>
        {data.preventiviAperti.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">{t("dashboard.noOpenBudgets")}</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {data.preventiviAperti.map((b) => (
              <div key={b.id} className="rounded-xl border border-slate-200 p-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-400">{b.number}</span>
                  <Badge tone="brand">{t(`budgets.status${b.status}`)}</Badge>
                </div>
                <p className="mt-1 truncate text-sm font-semibold text-slate-800">{b.title}</p>
                <p className="text-xs text-slate-400">{categoryLabel(t, b.category)}</p>
                <p className="mt-2 text-sm font-medium text-brand-700">
                  {formatAmount(b.plannedAmount, b.currency)}
                </p>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
