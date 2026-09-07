import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { FormRow, Input } from "../../components/ui/Field";
import { Button } from "../../components/ui/Button";
import { api, apiErrorMessage } from "../../lib/api";

export default function ResetPassword() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError(t("auth.passwordMinLength"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("auth.passwordsDontMatch"));
      return;
    }
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { token, password });
      setSuccess(true);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title={t("auth.resetPasswordTitle")} subtitle={t("auth.resetPasswordSubtitle")}>
      {success ? (
        <p className="text-sm text-entrata-700">{t("auth.resetPasswordSuccess")}</p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <FormRow label={t("auth.newPassword")}>
            <Input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </FormRow>
          <FormRow label={t("auth.confirmPassword")}>
            <Input
              type="password"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
            />
          </FormRow>
          {error && <p className="text-sm text-uscita-600">{error}</p>}
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? t("common.loading") : t("auth.resetPasswordButton")}
          </Button>
        </form>
      )}
      <p className="mt-6 text-center text-sm text-slate-500">
        <Link to="/login" className="font-medium text-brand-700 hover:underline">
          {t("auth.backToLogin")}
        </Link>
      </p>
    </AuthLayout>
  );
}
