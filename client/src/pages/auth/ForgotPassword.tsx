import { FormEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { FormRow, Input } from "../../components/ui/Field";
import { Button } from "../../components/ui/Button";
import { api } from "../../lib/api";

export default function ForgotPassword() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post("/auth/forgot-password", { email });
    } finally {
      setLoading(false);
      setSent(true);
    }
  }

  return (
    <AuthLayout title={t("auth.forgotPasswordTitle")} subtitle={t("auth.forgotPasswordSubtitle")}>
      {sent ? (
        <p className="text-sm text-entrata-700">{t("auth.forgotPasswordSuccess")}</p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <FormRow label={t("auth.email")}>
            <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </FormRow>
          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? t("common.loading") : t("auth.sendResetLink")}
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
