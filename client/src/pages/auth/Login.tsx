import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { FormRow, Input } from "../../components/ui/Field";
import { Button } from "../../components/ui/Button";
import { GoogleLoginButton } from "../../components/GoogleLoginButton";
import { useAuth } from "../../lib/AuthContext";
import { apiErrorMessage } from "../../lib/api";

export default function Login() {
  const { t } = useTranslation();
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: { pathname: string } } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate(location.state?.from?.pathname || "/", { replace: true });
    } catch (err) {
      setError(apiErrorMessage(err, t("auth.invalidCredentials")));
    } finally {
      setLoading(false);
    }
  }

  return (
    <AuthLayout title={t("auth.loginTitle")} subtitle={t("auth.loginSubtitle")}>
      <form onSubmit={onSubmit} className="space-y-4">
        <FormRow label={t("auth.email")}>
          <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </FormRow>
        <FormRow label={t("auth.password")}>
          <Input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </FormRow>
        {error && <p className="text-sm text-uscita-600">{error}</p>}
        <div className="flex items-center justify-between text-sm">
          <Link to="/forgot-password" className="text-brand-700 hover:underline">
            {t("auth.forgotPassword")}
          </Link>
        </div>
        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? t("common.loading") : t("auth.loginButton")}
        </Button>
      </form>
      <div className="my-5 flex items-center gap-3 text-xs uppercase text-slate-400">
        <div className="h-px flex-1 bg-slate-200" />
        {t("auth.or")}
        <div className="h-px flex-1 bg-slate-200" />
      </div>
      <GoogleLoginButton onError={setError} />
      <p className="mt-6 text-center text-sm text-slate-500">
        {t("auth.dontHaveAccount")}{" "}
        <Link to="/register" className="font-medium text-brand-700 hover:underline">
          {t("auth.registerButton")}
        </Link>
      </p>
    </AuthLayout>
  );
}
