import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, apiErrorMessage } from "../lib/api";
import { Category, Currency, Method, Transaction, TxType } from "../lib/types";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Input, Select } from "../components/ui/Field";
import { Modal } from "../components/ui/Modal";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { TransactionForm } from "../components/transactions/TransactionForm";
import { useAuth } from "../lib/AuthContext";
import { categoryLabel, formatAmount, formatDate } from "../lib/format";

interface Props {
  mode: TxType | "ALL";
}

const PAGE_SIZE = 20;

export default function TransactionsPage({ mode }: Props) {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const canWrite = hasRole("ADMIN", "TESORIERE");

  const [items, setItems] = useState<Transaction[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [categories, setCategories] = useState<Category[]>([]);

  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [method, setMethod] = useState<Method | "">("");
  const [currency, setCurrency] = useState<Currency | "">("");
  const [typeFilter, setTypeFilter] = useState<TxType | "">("");
  const [sortBy, setSortBy] = useState("date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Transaction | null>(null);
  const [newType, setNewType] = useState<TxType>(mode === "USCITA" ? "USCITA" : "ENTRATA");
  const [deleteTarget, setDeleteTarget] = useState<Transaction | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (mode !== "ALL") {
      api.get("/categories", { params: { type: mode } }).then((res) => setCategories(res.data));
    } else {
      api.get("/categories").then((res) => setCategories(res.data));
    }
  }, [mode]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string | number> = {
        page,
        pageSize: PAGE_SIZE,
        sortBy,
        sortDir,
      };
      if (mode !== "ALL") params.type = mode;
      else if (typeFilter) params.type = typeFilter;
      if (search) params.search = search;
      if (dateFrom) params.dateFrom = dateFrom;
      if (dateTo) params.dateTo = dateTo;
      if (categoryId) params.categoryId = categoryId;
      if (method) params.method = method;
      if (currency) params.currency = currency;

      const res = await api.get("/transactions", { params });
      setItems(res.data.items);
      setTotal(res.data.total);
    } finally {
      setLoading(false);
    }
  }, [mode, page, sortBy, sortDir, typeFilter, search, dateFrom, dateTo, categoryId, method, currency]);

  useEffect(() => {
    load();
  }, [load]);

  function resetFilters() {
    setSearch("");
    setDateFrom("");
    setDateTo("");
    setCategoryId("");
    setMethod("");
    setCurrency("");
    setTypeFilter("");
    setPage(1);
  }

  function openNew(type: TxType) {
    setNewType(type);
    setEditing(null);
    setFormOpen(true);
  }

  function openEdit(tx: Transaction) {
    setNewType(tx.type);
    setEditing(tx);
    setFormOpen(true);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await api.delete(`/transactions/${deleteTarget.id}`, { params: { confirm: "true" } });
      setDeleteTarget(null);
      load();
    } catch (err) {
      alert(apiErrorMessage(err));
    } finally {
      setDeleting(false);
    }
  }

  const title =
    mode === "ENTRATA" ? t("transactions.entrateTitle") : mode === "USCITA" ? t("transactions.usciteTitle") : t("transactions.movimentiTitle");

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
          {mode === "ALL" && <p className="text-sm text-slate-500">{t("transactions.movimentiSubtitle")}</p>}
        </div>
        {canWrite && mode !== "ALL" && (
          <Button onClick={() => openNew(mode)}>+ {mode === "ENTRATA" ? t("transactions.entrataNew") : t("transactions.uscitaNew")}</Button>
        )}
        {canWrite && mode === "ALL" && (
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => openNew("ENTRATA")}>
              + {t("transactions.entrataNew")}
            </Button>
            <Button variant="secondary" onClick={() => openNew("USCITA")}>
              + {t("transactions.uscitaNew")}
            </Button>
          </div>
        )}
      </div>

      <Card>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <div className="col-span-2 sm:col-span-1">
            <Input
              placeholder={t("transactions.searchPlaceholder")}
              value={search}
              onChange={(e) => {
                setPage(1);
                setSearch(e.target.value);
              }}
            />
          </div>
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => {
              setPage(1);
              setDateFrom(e.target.value);
            }}
            title={t("common.from")}
          />
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => {
              setPage(1);
              setDateTo(e.target.value);
            }}
            title={t("common.to")}
          />
          {mode === "ALL" && (
            <Select
              value={typeFilter}
              onChange={(e) => {
                setPage(1);
                setTypeFilter(e.target.value as TxType | "");
              }}
            >
              <option value="">{t("common.all")} - {t("transactions.type")}</option>
              <option value="ENTRATA">{t("transactions.ENTRATA")}</option>
              <option value="USCITA">{t("transactions.USCITA")}</option>
            </Select>
          )}
          <Select
            value={categoryId}
            onChange={(e) => {
              setPage(1);
              setCategoryId(e.target.value);
            }}
          >
            <option value="">{t("common.all")} - {t("common.category")}</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {categoryLabel(t, c)}
              </option>
            ))}
          </Select>
          <Select
            value={method}
            onChange={(e) => {
              setPage(1);
              setMethod(e.target.value as Method | "");
            }}
          >
            <option value="">{t("common.all")} - {t("common.method")}</option>
            <option value="CASH">{t("common.cash")}</option>
            <option value="BANK">{t("common.bank")}</option>
          </Select>
          <Select
            value={currency}
            onChange={(e) => {
              setPage(1);
              setCurrency(e.target.value as Currency | "");
            }}
          >
            <option value="">{t("common.all")} - {t("common.currency")}</option>
            <option value="EUR">EUR</option>
            <option value="ALL">ALL</option>
          </Select>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span>{t("common.sortBy")}</span>
            <Select value={sortBy} onChange={(e) => setSortBy(e.target.value)} className="!w-auto py-1">
              <option value="date">{t("common.date")}</option>
              <option value="amount">{t("common.amount")}</option>
              <option value="createdAt">{t("common.createdAt")}</option>
              <option value="description">{t("common.description")}</option>
            </Select>
            <button
              onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
              className="rounded-lg border border-slate-300 px-2 py-1 hover:bg-slate-50"
            >
              {sortDir === "asc" ? "↑" : "↓"}
            </button>
          </div>
          <button onClick={resetFilters} className="text-xs font-medium text-brand-700 hover:underline">
            {t("common.resetFilters")}
          </button>
        </div>
      </Card>

      <Card className="!p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs font-medium uppercase tracking-wide text-slate-400">
                <th className="px-4 py-3">{t("common.date")}</th>
                {mode === "ALL" && <th className="px-4 py-3">{t("transactions.type")}</th>}
                <th className="px-4 py-3">{t("common.description")}</th>
                <th className="px-4 py-3">{t("common.category")}</th>
                <th className="px-4 py-3">{t("common.method")}</th>
                <th className="px-4 py-3 text-right">{t("common.amount")}</th>
                <th className="px-4 py-3">{t("common.user")}</th>
                {canWrite && <th className="px-4 py-3 text-right">{t("common.actions")}</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-400">
                    {t("common.loading")}
                  </td>
                </tr>
              )}
              {!loading && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-slate-400">
                    {t("transactions.noTransactions")}
                  </td>
                </tr>
              )}
              {!loading &&
                items.map((tx) => (
                  <tr key={tx.id} className="hover:bg-slate-50">
                    <td className="whitespace-nowrap px-4 py-3 text-slate-600">{formatDate(tx.date)}</td>
                    {mode === "ALL" && (
                      <td className="px-4 py-3">
                        <Badge tone={tx.type === "ENTRATA" ? "entrata" : "uscita"}>{t(`transactions.${tx.type}`)}</Badge>
                      </td>
                    )}
                    <td className="max-w-[220px] truncate px-4 py-3 font-medium text-slate-800">{tx.description}</td>
                    <td className="px-4 py-3 text-slate-600">{categoryLabel(t, tx.category)}</td>
                    <td className="px-4 py-3 text-slate-600">{t(`common.${tx.method.toLowerCase()}`)}</td>
                    <td
                      className={`whitespace-nowrap px-4 py-3 text-right font-semibold ${
                        tx.type === "ENTRATA" ? "text-entrata-600" : "text-uscita-600"
                      }`}
                    >
                      {tx.type === "ENTRATA" ? "+" : "-"}
                      {formatAmount(tx.amount, tx.currency)}
                    </td>
                    <td className="px-4 py-3 text-slate-500">{tx.createdBy?.name}</td>
                    {canWrite && (
                      <td className="px-4 py-3 text-right">
                        <div className="flex justify-end gap-2">
                          <button onClick={() => openEdit(tx)} className="text-xs font-medium text-brand-700 hover:underline">
                            {t("common.edit")}
                          </button>
                          <button
                            onClick={() => setDeleteTarget(tx)}
                            className="text-xs font-medium text-uscita-600 hover:underline"
                          >
                            {t("common.delete")}
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between border-t border-slate-100 px-4 py-3 text-xs text-slate-500">
          <span>
            {t("common.page")} {page} {t("common.of")} {totalPages} ({total})
          </span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-lg border border-slate-300 px-2 py-1 disabled:opacity-40"
            >
              ‹
            </button>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              className="rounded-lg border border-slate-300 px-2 py-1 disabled:opacity-40"
            >
              ›
            </button>
          </div>
        </div>
      </Card>

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={
          editing
            ? newType === "ENTRATA"
              ? t("transactions.entrataEdit")
              : t("transactions.uscitaEdit")
            : newType === "ENTRATA"
            ? t("transactions.entrataNew")
            : t("transactions.uscitaNew")
        }
        wide
      >
        <TransactionForm
          type={newType}
          initial={editing}
          onCancel={() => setFormOpen(false)}
          onSaved={() => {
            setFormOpen(false);
            load();
          }}
        />
      </Modal>

      <ConfirmDialog
        open={!!deleteTarget}
        body={t("transactions.confirmDeleteTransaction")}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        loading={deleting}
      />
    </div>
  );
}
