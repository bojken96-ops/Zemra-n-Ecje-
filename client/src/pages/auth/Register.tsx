import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { FormRow, Input } from "../../components/ui/Field";
import { Button } from "../../components/ui/Button";
import { GoogleLoginButton } from "../../components/GoogleLoginButton";
import { useAuth } from "../../lib/AuthContext";
import { apiErrorMessage } from "../../lib/api";

export default function Register() {
  const { t } = useTranslation();
  const { register } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", confirmPassword: "", parishName: "" });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function update<K extends keyof typeof form>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (form.password.length < 8) {
      setError(t("auth.passwordMinLength"));
      return;
    }
    if (form.password !== form.confirmPassword) {
      setError(t("auth.passwordsDontMatch"));
      return;
    }
    setLoading(true);
    try {
      await register({ name: form.name, email: form.email, password: form.password, parishName: form.parishName });
      navigate("/", { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title={t("auth.createAccountTitle")} subtitle={t("auth.createAccountSubtitle")}>
      <form onSubmit={onSubmit} className="space-y-4">
        <FormRow label={t("auth.parishName")}>
          <Input required value={form.parishName} onChange={(e) => update("parishName", e.target.value)} />
        </FormRow>
        <FormRow label={t("auth.fullName")}>
          <Input required value={form.name} onChange={(e) => update("name", e.target.value)} autoComplete="name" />
        </FormRow>
        <FormRow label={t("auth.email")}>
          <Input
            type="email"
            required
            value={form.email}
            onChange={(e) => update("email", e.target.value)}
            autoComplete="email"
          />
        </FormRow>
        <FormRow label={t("auth.password")}>
          <Input
            type="password"
            required
            value={form.password}
            onChange={(e) => update("password", e.target.value)}
            autoComplete="new-password"
          />
        </FormRow>
        <FormRow label={t("auth.confirmPassword")}>
          <Input
            type="password"
            required
            value={form.confirmPassword}
            onChange={(e) => update("confirmPassword", e.target.value)}
            autoComplete="new-password"
          />
        </FormRow>
        {error && <p className="text-sm text-uscita-600">{error}</p>}
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? t("common.loading") : t("auth.registerButton")}
        </Button>
      </form>
      <div className="my-5 flex items-center gap-3 text-xs uppercase text-slate-400">
        <div className="h-px flex-1 bg-slate-200" />
        {t("auth.or")}
        <div className="h-px flex-1 bg-slate-200" />
      </div>
      <GoogleLoginButton onError={setError} />
      <p className="mt-6 text-center text-sm text-slate-500">
        {t("auth.alreadyHaveAccount")}{" "}
        <Link to="/login" className="font-medium text-brand-700 hover:underline">
          {t("auth.loginButton")}
        </Link>
      </p>
    </AuthLayout>
  );
}
