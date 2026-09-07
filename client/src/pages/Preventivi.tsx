import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, apiErrorMessage } from "../lib/api";
import { Budget, BudgetStatus } from "../lib/types";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Input, Select } from "../components/ui/Field";
import { Modal } from "../components/ui/Modal";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { BudgetForm } from "../components/budgets/BudgetForm";
import { useAuth } from "../lib/AuthContext";
import { categoryLabel, formatAmount, formatDate } from "../lib/format";

const STATUSES: BudgetStatus[] = ["BOZZA", "APPROVATO", "IN_CORSO", "COMPLETATO", "ANNULLATO"];
const STATUS_TONE: Record<BudgetStatus, "neutral" | "brand" | "entrata" | "gold" | "uscita"> = {
  BOZZA: "neutral",
  APPROVATO: "brand",
  IN_CORSO: "gold",
  COMPLETATO: "entrata",
  ANNULLATO: "uscita",
};

export default function Preventivi() {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const canWrite = hasRole("ADMIN", "TESORIERE");

  const [items, setItems] = useState<Budget[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<BudgetStatus | "">("");

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Budget | null>(null);
  const [detail, setDetail] = useState<Budget | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Budget | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (search) params.search = search;
      if (status) params.status = status;
      const res = await api.get("/budgets", { params });
      setItems(res.data);
    } finally {
      setLoading(false);
    }
  }, [search, status]);

  useEffect(() => {
    load();
  }, [load]);

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await api.delete(`/budgets/${deleteTarget.id}`, { params: { confirm: "true" } });
      setDeleteTarget(null);
      load();
    } catch (err) {
      setDeleteError(apiErrorMessage(err));
    } finally {
      setDeleting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{t("budgets.title")}</h1>
          <p className="text-sm text-slate-500">{t("budgets.subtitle")}</p>
        </div>
        {canWrite && (
          <Button
            onClick={() => {
              setEditing(null);
              setFormOpen(true);
            }}
          >
            + {t("budgets.new")}
          </Button>
        )}
      </div>

      <Card>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Input placeholder={t("common.search")} value={search} onChange={(e) => setSearch(e.target.value)} />
          <Select value={status} onChange={(e) => setStatus(e.target.value as BudgetStatus | "")}>
            <option value="">{t("common.all")} - {t("common.status")}</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {t(`budgets.status${s}`)}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      {loading ? (
        <p className="text-slate-400">{t("common.loading")}</p>
      ) : items.length === 0 ? (
        <Card>
          <p className="py-8 text-center text-slate-400">{t("budgets.noBudgets")}</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((b) => {
            const pct = b.plannedAmount > 0 ? Math.min(100, (b.spentAmount / b.plannedAmount) * 100) : 0;
            const over = b.spentAmount > b.plannedAmount;
            return (
              <Card key={b.id} className="flex flex-col gap-2">
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-xs font-medium text-slate-400">{b.number}</p>
                    <p className="font-semibold text-slate-800">{b.title}</p>
                    <p className="text-xs text-slate-400">{categoryLabel(t, b.category)} · {formatDate(b.date)}</p>
                  </div>
                  <Badge tone={STATUS_TONE[b.status]}>{t(`budgets.status${b.status}`)}</Badge>
                </div>

                <div className="mt-1 space-y-1 text-sm">
                  <div className="flex justify-between">
                    <span className="text-slate-500">{t("budgets.plannedAmount")}</span>
                    <span className="font-medium">{formatAmount(b.plannedAmount, b.currency)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{t("budgets.spentAmount")}</span>
                    <span className="font-medium text-uscita-600">{formatAmount(b.spentAmount, b.currency)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">{t("budgets.remainingAmount")}</span>
                    <span className={`font-medium ${b.remainingAmount < 0 ? "text-uscita-600" : "text-entrata-600"}`}>
                      {formatAmount(b.remainingAmount, b.currency)}
                    </span>
                  </div>
                </div>

                <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full ${over ? "bg-uscita-500" : "bg-brand-600"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                {over && <p className="text-xs font-medium text-uscita-600">{t("budgets.overBudget")}</p>}

                <div className="mt-2 flex justify-end gap-3 text-xs font-medium">
                  <button
                    onClick={() => api.get(`/budgets/${b.id}`).then((res) => setDetail(res.data))}
                    className="text-brand-700 hover:underline"
                  >
                    {t("common.viewDetails")}
                  </button>
                  {canWrite && (
                    <>
                      <button
                        onClick={() => {
                          setEditing(b);
                          setFormOpen(true);
                        }}
                        className="text-brand-700 hover:underline"
                      >
                        {t("common.edit")}
                      </button>
                      <button
                        onClick={() => {
                          setDeleteError(null);
                          setDeleteTarget(b);
                        }}
                        className="text-uscita-600 hover:underline"
                      >
                        {t("common.delete")}
                      </button>
                    </>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={editing ? t("budgets.edit") : t("budgets.new")} wide>
        <BudgetForm
          initial={editing}
          onCancel={() => setFormOpen(false)}
          onSaved={() => {
            setFormOpen(false);
            load();
          }}
        />
      </Modal>

      <Modal open={!!detail} onClose={() => setDetail(null)} title={detail?.title || ""} wide>
        {detail && (
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div>
                <p className="text-slate-400">{t("budgets.plannedAmount")}</p>
                <p className="font-semibold">{formatAmount(detail.plannedAmount, detail.currency)}</p>
              </div>
              <div>
                <p className="text-slate-400">{t("budgets.spentAmount")}</p>
                <p className="font-semibold text-uscita-600">{formatAmount(detail.spentAmount, detail.currency)}</p>
              </div>
              <div>
                <p className="text-slate-400">{t("budgets.remainingAmount")}</p>
                <p className="font-semibold text-entrata-600">{formatAmount(detail.remainingAmount, detail.currency)}</p>
              </div>
            </div>
            <div>
              <h4 className="mb-2 text-sm font-semibold text-slate-700">{t("budgets.linkedExpenses")}</h4>
              {!detail.transactions || detail.transactions.length === 0 ? (
                <p className="text-sm text-slate-400">{t("budgets.noLinkedExpenses")}</p>
              ) : (
                <div className="divide-y divide-slate-100">
                  {detail.transactions.map((tx) => (
                    <div key={tx.id} className="flex items-center justify-between py-2 text-sm">
                      <div>
                        <p className="font-medium text-slate-700">{tx.description}</p>
                        <p className="text-xs text-slate-400">{formatDate(tx.date)}</p>
                      </div>
                      <span className="font-semibold text-uscita-600">{formatAmount(tx.amount, tx.currency)}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>

      <ConfirmDialog
        open={!!deleteTarget}
        body={deleteError || t("budgets.confirmDelete")}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        loading={deleting}
      />
    </div>
  );
}
