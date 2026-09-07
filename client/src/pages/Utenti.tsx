import { FormEvent, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, apiErrorMessage } from "../lib/api";
import { Role, User } from "../lib/types";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { FormRow, Input, Select } from "../components/ui/Field";
import { Modal } from "../components/ui/Modal";
import { ConfirmDialog } from "../components/ui/ConfirmDialog";
import { useAuth } from "../lib/AuthContext";
import { formatDate } from "../lib/format";

const ROLES: Role[] = ["ADMIN", "TESORIERE", "VIEWER"];

export default function Utenti() {
  const { t } = useTranslation();
  const { user: me } = useAuth();

  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("VIEWER");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [deactivateTarget, setDeactivateTarget] = useState<User | null>(null);
  const [deactivating, setDeactivating] = useState(false);
  const [deactivateError, setDeactivateError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/users");
      setUsers(res.data);
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
      await api.post("/users", { name, email, role });
      setFormOpen(false);
      setName("");
      setEmail("");
      setRole("VIEWER");
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setSaving(false);
    }
  }

  async function changeRole(u: User, newRole: Role) {
    try {
      await api.put(`/users/${u.id}`, { role: newRole });
      load();
    } catch (err) {
      alert(apiErrorMessage(err));
    }
  }

  async function confirmDeactivate() {
    if (!deactivateTarget) return;
    setDeactivating(true);
    setDeactivateError(null);
    try {
      await api.delete(`/users/${deactivateTarget.id}`);
      setDeactivateTarget(null);
      load();
    } catch (err) {
      setDeactivateError(apiErrorMessage(err));
    } finally {
      setDeactivating(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">{t("users.title")}</h1>
          <p className="text-sm text-slate-500">{t("users.subtitle")}</p>
        </div>
        <Button onClick={() => setFormOpen(true)}>+ {t("users.new")}</Button>
      </div>

      <Card className="!p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs font-medium uppercase tracking-wide text-slate-400">
                <th className="px-4 py-3">{t("common.name")}</th>
                <th className="px-4 py-3">{t("common.email")}</th>
                <th className="px-4 py-3">{t("common.role")}</th>
                <th className="px-4 py-3">{t("users.emailVerified")}</th>
                <th className="px-4 py-3">{t("common.status")}</th>
                <th className="px-4 py-3">{t("common.createdAt")}</th>
                <th className="px-4 py-3 text-right">{t("common.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-slate-400">
                    {t("common.loading")}
                  </td>
                </tr>
              )}
              {!loading &&
                users.map((u) => (
                  <tr key={u.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-medium text-slate-800">{u.name}</td>
                    <td className="px-4 py-3 text-slate-600">{u.email}</td>
                    <td className="px-4 py-3">
                      <Select
                        value={u.role}
                        onChange={(e) => changeRole(u, e.target.value as Role)}
                        disabled={u.id === me?.id}
                        className="!w-auto py-1 text-xs"
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {t(`users.role${r}`)}
                          </option>
                        ))}
                      </Select>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={u.emailVerified ? "entrata" : "neutral"}>
                        {u.emailVerified ? t("users.emailVerified") : t("users.emailNotVerified")}
                      </Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={u.active ? "entrata" : "uscita"}>
                        {u.active ? t("common.active") : t("common.inactive")}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-slate-500">{u.createdAt ? formatDate(u.createdAt) : "-"}</td>
                    <td className="px-4 py-3 text-right">
                      {u.active && u.id !== me?.id && (
                        <button
                          onClick={() => {
                            setDeactivateError(null);
                            setDeactivateTarget(u);
                          }}
                          className="text-xs font-medium text-uscita-600 hover:underline"
                        >
                          {t("common.delete")}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Modal open={formOpen} onClose={() => setFormOpen(false)} title={t("users.new")}>
        <form onSubmit={onSubmit} className="space-y-4">
          <FormRow label={t("common.name")}>
            <Input required value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
          </FormRow>
          <FormRow label={t("common.email")}>
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </FormRow>
          <FormRow label={t("common.role")}>
            <Select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {t(`users.role${r}`)}
                </option>
              ))}
            </Select>
            <p className="mt-1 text-xs text-slate-400">
              {role === "ADMIN" && t("users.roleADMINDesc")}
              {role === "TESORIERE" && t("users.roleTESORIEREDesc")}
              {role === "VIEWER" && t("users.roleVIEWERDesc")}
            </p>
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
        open={!!deactivateTarget}
        body={deactivateError || t("users.confirmDeactivate")}
        onCancel={() => setDeactivateTarget(null)}
        onConfirm={confirmDeactivate}
        loading={deactivating}
      />
    </div>
  );
}
