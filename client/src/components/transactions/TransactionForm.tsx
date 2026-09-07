import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, apiErrorMessage } from "../../lib/api";
import { Budget, Category, Currency, Method, Transaction, TxType } from "../../lib/types";
import { FormRow, Input, Select, Textarea } from "../ui/Field";
import { Button } from "../ui/Button";
import { categoryLabel, toInputDate } from "../../lib/format";
import { downloadAttachment } from "../../lib/download";

export function TransactionForm({
  type,
  initial,
  onSaved,
  onCancel,
}: {
  type: TxType;
  initial?: Transaction | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [categories, setCategories] = useState<Category[]>([]);
  const [budgets, setBudgets] = useState<Budget[]>([]);
  const [date, setDate] = useState(initial ? toInputDate(initial.date) : toInputDate(new Date()));
  const [description, setDescription] = useState(initial?.description || "");
  const [categoryId, setCategoryId] = useState(initial?.categoryId || "");
  const [amount, setAmount] = useState(initial ? String(initial.amount) : "");
  const [currency, setCurrency] = useState<Currency>(initial?.currency || "EUR");
  const [method, setMethod] = useState<Method>(initial?.method || "CASH");
  const [budgetId, setBudgetId] = useState(initial?.budgetId || "");
  const [notes, setNotes] = useState(initial?.notes || "");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/categories", { params: { type, active: true } }).then((res) => setCategories(res.data));
    if (type === "USCITA") {
      api.get("/budgets", { params: { status: "APPROVATO" } }).then((res) => setBudgets(res.data));
    }
  }, [type]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!categoryId) {
      setError(t("common.required"));
      return;
    }
    setLoading(true);
    const fd = new FormData();
    fd.append("type", type);
    fd.append("date", date);
    fd.append("description", description);
    fd.append("categoryId", categoryId);
    fd.append("amount", amount);
    fd.append("currency", currency);
    fd.append("method", method);
    if (type === "USCITA" && budgetId) fd.append("budgetId", budgetId);
    if (notes) fd.append("notes", notes);
    if (file) fd.append("attachment", file);

    try {
      if (initial) {
        await api.put(`/transactions/${initial.id}`, fd);
      } else {
        await api.post("/transactions", fd);
      }
      onSaved();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <FormRow label={t("common.date")}>
          <Input type="date" required value={date} onChange={(e) => setDate(e.target.value)} />
        </FormRow>
        <FormRow label={t("common.category")}>
          <Select required value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
            <option value="">{t("common.select")}</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {categoryLabel(t, c)}
              </option>
            ))}
          </Select>
        </FormRow>
      </div>

      <FormRow label={t("common.description")}>
        <Input required value={description} onChange={(e) => setDescription(e.target.value)} maxLength={300} />
      </FormRow>

      <div className="grid grid-cols-3 gap-4">
        <FormRow label={t("common.amount")}>
          <Input
            type="number"
            required
            min="0.01"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </FormRow>
        <FormRow label={t("common.currency")}>
          <Select value={currency} onChange={(e) => setCurrency(e.target.value as Currency)}>
            <option value="EUR">EUR</option>
            <option value="ALL">ALL</option>
          </Select>
        </FormRow>
        <FormRow label={t("common.method")}>
          <Select value={method} onChange={(e) => setMethod(e.target.value as Method)}>
            <option value="CASH">{t("common.cash")}</option>
            <option value="BANK">{t("common.bank")}</option>
          </Select>
        </FormRow>
      </div>

      {type === "USCITA" && (
        <FormRow label={t("transactions.budgetOptional")}>
          <Select value={budgetId} onChange={(e) => setBudgetId(e.target.value)}>
            <option value="">{t("transactions.noBudget")}</option>
            {budgets.map((b) => (
              <option key={b.id} value={b.id}>
                {b.number} - {b.title}
              </option>
            ))}
          </Select>
        </FormRow>
      )}

      <FormRow label={`${t("common.notes")} (${t("common.optional")})`}>
        <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={2000} />
      </FormRow>

      <FormRow label={`${t("common.attachment")} (${t("common.optional")})`}>
        <input
          type="file"
          accept="application/pdf,image/*"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-lg file:border-0 file:bg-brand-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-brand-700 hover:file:bg-brand-100"
        />
        <p className="mt-1 text-xs text-slate-400">{t("transactions.attachmentHint")}</p>
        {initial?.attachments && initial.attachments.length > 0 && (
          <ul className="mt-2 space-y-1">
            {initial.attachments.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => downloadAttachment(a.id, a.filename)}
                  className="text-xs text-brand-700 hover:underline"
                >
                  📎 {a.filename}
                </button>
              </li>
            ))}
          </ul>
        )}
      </FormRow>

      {error && <p className="text-sm text-uscita-600">{error}</p>}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={loading}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" disabled={loading}>
          {loading ? t("common.saving") : t("common.save")}
        </Button>
      </div>
    </form>
  );
}
