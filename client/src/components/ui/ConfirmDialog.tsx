import { useTranslation } from "react-i18next";
import { Modal } from "./Modal";
import { Button } from "./Button";

export function ConfirmDialog({
  open,
  title,
  body,
  onConfirm,
  onCancel,
  loading,
}: {
  open: boolean;
  title?: string;
  body?: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}) {
  const { t } = useTranslation();
  if (!open) return null;
  return (
    <Modal open={open} onClose={onCancel} title={title || t("common.confirmDeleteTitle")}>
      <p className="text-sm text-slate-600">{body || t("common.confirmDeleteBody")}</p>
      <div className="mt-5 flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel} disabled={loading}>
          {t("common.cancel")}
        </Button>
        <Button variant="danger" onClick={onConfirm} disabled={loading}>
          {loading ? t("common.saving") : t("common.delete")}
        </Button>
      </div>
    </Modal>
  );
}
