import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, apiErrorMessage } from "../../lib/api";
import { Budget, BudgetStatus, Category, Currency, Method } from "../../lib/types";
import { FormRow, Input, Select, Textarea } from "../ui/Field";
import { Button } from "../ui/Button";
import { categoryLabel, toInputDate } from "../../lib/format";

const STATUSES: BudgetStatus[] = ["BOZZA", "APPROVATO", "IN_CORSO", "COMPLETATO", "ANNULLATO"];

export function BudgetForm({
  initial,
  onSaved,
  onCancel,
}: {
  initial?: Budget | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const { t } = useTranslation();
  const [categories, setCategories] = useState<Category[]>([]);
  const [date, setDate] = useState(initial ? toInputDate(initial.date) : toInputDate(new Date()));
  const [title, setTitle] = useState(initial?.title || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [categoryId, setCategoryId] = useState(initial?.categoryId || "");
  const [plannedAmount, setPlannedAmount] = useState(initial ? String(initial.plannedAmount) : "");
  const [currency, setCurrency] = useState<Currency>(initial?.currency || "EUR");
  const [plannedMethod, setPlannedMethod] = useState<Method>(initial?.plannedMethod || "CASH");
  const [status, setStatus] = useState<BudgetStatus>(initial?.status || "BOZZA");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get("/categories", { params: { type: "USCITA", active: true } }).then((res) => setCategories(res.data));
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!categoryId) {
      setError(t("common.required"));
      return;
    }
    setLoading(true);
    const payload = { date, title, description, categoryId, plannedAmount: Number(plannedAmount), currency, plannedMethod, status };
    try {
      if (initial) await api.put(`/budgets/${initial.id}`, payload);
      else await api.post("/budgets", payload);
      onSaved();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <FormRow label={t("budgets.budgetTitle")}>
        <Input required value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
      </FormRow>
      <FormRow label={`${t("common.description")} (${t("common.optional")})`}>
        <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} maxLength={2000} />
      </FormRow>
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
      <div className="grid grid-cols-3 gap-4">
        <FormRow label={t("budgets.plannedAmount")}>
          <Input
            type="number"
            required
            min="0.01"
            step="0.01"
            value={plannedAmount}
            onChange={(e) => setPlannedAmount(e.target.value)}
          />
        </FormRow>
        <FormRow label={t("common.currency")}>
          <Select value={currency} onChange={(e) => setCurrency(e.target.value as Currency)}>
            <option value="EUR">EUR</option>
            <option value="ALL">ALL</option>
          </Select>
        </FormRow>
        <FormRow label={t("budgets.plannedMethod")}>
          <Select value={plannedMethod} onChange={(e) => setPlannedMethod(e.target.value as Method)}>
            <option value="CASH">{t("common.cash")}</option>
            <option value="BANK">{t("common.bank")}</option>
          </Select>
        </FormRow>
      </div>
      <FormRow label={t("budgets.status")}>
        <Select value={status} onChange={(e) => setStatus(e.target.value as BudgetStatus)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`budgets.status${s}`)}
            </option>
          ))}
        </Select>
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
