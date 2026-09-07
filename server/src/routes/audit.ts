import { Router } from "express";
import { prisma } from "../lib/prisma";
import { requireAuth, AuthedRequest } from "../middleware/auth";
import { adminOnly } from "../middleware/roles";

const router = Router();
router.use(requireAuth, adminOnly);

router.get("/", async (req: AuthedRequest, res) => {
  const q = req.query as Record<string, string>;
  const page = Math.max(1, parseInt(q.page || "1", 10));
  const pageSize = Math.min(200, Math.max(1, parseInt(q.pageSize || "50", 10)));
  const where: any = { parishId: req.user!.parishId };
  if (q.entityType) where.entityType = q.entityType;
  if (q.entityId) where.entityId = q.entityId;

  const [items, total] = await Promise.all([
    prisma.auditLog.findMany({
      where,
      include: { user: { select: { name: true, email: true } } },
      orderBy: { createdAt: "desc" },
      skip: (page - 1) * pageSize,
      take: pageSize,
    }),
    prisma.auditLog.count({ where }),
  ]);

  res.json({
    items: items.map((i) => ({
      ...i,
      oldValue: i.oldValue ? JSON.parse(i.oldValue) : null,
      newValue: i.newValue ? JSON.parse(i.newValue) : null,
    })),
    total,
    page,
    pageSize,
  });
});

export default router;
