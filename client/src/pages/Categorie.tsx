import { FormEvent, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, apiErrorMessage } from "../lib/api";
import { Category, TxType } from "../lib/types";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { FormRow, Input, Select } from "../components/ui/Field";
import { Modal } from "../components/ui/Modal";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { useAuth } from "../lib/AuthContext";
import { categoryLabel } from "../lib/format";

export default function Categorie() {
  const { t } = useTranslation();
  const { hasRole } = useAuth();
  const isAdmin = hasRole("ADMIN");

  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState("");
  const [type, setType] = useState<TxType>("ENTRATA");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Category | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [info, setInfo] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/categories");
      setCategories(res.data);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await api.post("/categories", { name, type });
      setFormOpen(false);
      setName("");
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(cat: Category) {
    await api.put(`/categories/${cat.id}`, { active: !cat.active });
    load();
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await api.delete(`/categories/${deleteTarget.id}`, { params: { confirm: "true" } });
      if (res.data.deactivated) setInfo(t("categories.deactivatedInfo"));
      setDeleteTarget(null);
      load();
    } finally {
      setDeleting(false);
    }
  }

  const entrate = categories.filter((c) => c.type === "ENTRATA");
  const uscite = categories.filter((c) => c.type === "USCITA");

  function renderList(list: Category[]) {
    return (
      <div className="divide-y divide-slate-100">
        {list.map((c) => (
          <div key={c.id} className="flex items-center justify-between py-2.5">
            <span className={`text-sm ${c.active ? "text-slate-800" : "text-slate-400 line-through"}`}>
              {categoryLabel(t, c)}
            </span>
            <div className="flex items-center gap-3">
              {!c.active && <Badge tone="neutral">{t("common.inactive")}</Badge>}
              {isAdmin && (
                <>
                  <button onClick={() => toggleActive(c)} className="text-xs font-medium text-brand-700 hover:underline">
                    {c.active ? t("categories.deactivateAction") : t("categories.activateAction")}
                  </button>
                  <button onClick={() => setDeleteTarget(c)} className="text-xs font-medium text-uscita-600 hover:underline">
                    {t("common.delete")}
                  </button>
                </>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{t("categories.title")}</h1>
          <p className="text-sm text-slate-500">{t("categories.subtitle")}</p>
        </div>
        {isAdmin && <Button onClick={() => setFormOpen(true)}>+ {t("categories.new")}</Button>}
      </div>

      {info && (
        <div className="rounded-lg bg-brand-50 px-4 py-2 text-sm text-brand-700">
          {info}
          <button onClick={() => setInfo(null)} className="ml-3 text-xs underline">
            {t("common.close")}
          </button>
        </div>
      )}

      {loading ? (
        <p className="text-slate-400">{t("common.loading")}</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <Card>
            <h3 className="mb-2 text-sm font-semibold text-entrata-700">{t("categories.entrate")}</h3>
            {renderList(entrate)}
          </Card>
          <Card>
            <h3 className="mb-2 text-sm font-semibold text-uscita-700">{t("categories.uscite")}</h3>
            {renderList(uscite)}
          </Card>
        </div>
      )}

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={t("categories.new")}>
        <form onSubmit={onSubmit} className="space-y-4">
          <FormRow label={t("categories.name")}>
            <Input required value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
          </FormRow>
          <FormRow label={t("categories.type")}>
            <Select value={type} onChange={(e) => setType(e.target.value as TxType)}>
              <option value="ENTRATA">{t("categories.entrate")}</option>
              <option value="USCITA">{t("categories.uscite")}</option>
            </Select>
          </FormRow>
          {error && <p className="text-sm text-uscita-600">{error}</p>}
          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="secondary" onClick={() => setFormOpen(false)} disabled={saving}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={saving}>
              {saving ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={!!deleteTarget}
        body={t("categories.confirmDelete")}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={confirmDelete}
        loading={deleting}
      />
    </div>
  );
}
