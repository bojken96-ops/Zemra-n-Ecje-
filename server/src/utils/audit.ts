import { prisma } from "../lib/prisma";

export type AuditAction = "CREATE" | "UPDATE" | "DELETE";

export async function logAudit(params: {
  parishId: string;
  userId: string;
  action: AuditAction;
  entityType: string;
  entityId: string;
  oldValue?: unknown;
  newValue?: unknown;
}) {
  await prisma.auditLog.create({
    data: {
      parishId: params.parishId,
      userId: params.userId,
      action: params.action,
      entityType: params.entityType,
      entityId: params.entityId,
      oldValue: params.oldValue !== undefined ? JSON.stringify(params.oldValue) : null,
      newValue: params.newValue !== undefined ? JSON.stringify(params.newValue) : null,
    },
  });
}
