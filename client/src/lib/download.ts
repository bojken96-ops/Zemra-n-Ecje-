import { api } from "./api";

export async function downloadAttachment(attachmentId: string, filename: string) {
  const res = await api.get(`/transactions/attachments/${attachmentId}/download`, { responseType: "blob" });
  const url = window.URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function downloadReport(url: string, filename: string) {
  const res = await api.get(url, { responseType: "blob" });
  const objUrl = window.URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = objUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(objUrl);
}
