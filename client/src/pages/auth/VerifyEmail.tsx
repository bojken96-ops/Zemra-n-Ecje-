import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { AuthLayout } from "./AuthLayout";
import { api } from "../../lib/api";

export default function VerifyEmail() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");

  useEffect(() => {
    let active = true;
    api
      .get("/auth/verify-email", { params: { token } })
      .then(() => active && setStatus("success"))
      .catch(() => active && setStatus("error"));
    return () => {
      active = false;
    };
  }, [token]);

  return (
    <AuthLayout title={t("auth.verifyEmailTitle")}>
      {status === "loading" && <p className="text-sm text-slate-500">{t("auth.verifyEmailInProgress")}</p>}
      {status === "success" && <p className="text-sm text-entrata-700">{t("auth.verifyEmailSuccess")}</p>}
      {status === "error" && <p className="text-sm text-uscita-600">{t("auth.verifyEmailError")}</p>}
      <p className="mt-6 text-center text-sm text-slate-500">
        <Link to="/login" className="font-medium text-brand-700 hover:underline">
          {t("auth.backToLogin")}
        </Link>
      </p>
    </AuthLayout>
  );
}
