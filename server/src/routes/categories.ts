import { Router } from "express";
import { z } from "zod";
import { prisma } from "../lib/prisma";
import { requireAuth, AuthedRequest } from "../middleware/auth";
import { adminOnly } from "../middleware/roles";
import { logAudit } from "../utils/audit";

const router = Router();
router.use(requireAuth);

router.get("/", async (req: AuthedRequest, res) => {
  const { type, active } = req.query as { type?: string; active?: string };
  const categories = await prisma.category.findMany({
    where: {
      parishId: req.user!.parishId,
      ...(type ? { type: type as "ENTRATA" | "USCITA" } : {}),
      ...(active !== undefined ? { active: active === "true" } : {}),
    },
    orderBy: { name: "asc" },
  });
  res.json(categories);
});

const createSchema = z.object({
  name: z.string().min(1).max(120),
  type: z.enum(["ENTRATA", "USCITA"]),
});

router.post("/", adminOnly, async (req: AuthedRequest, res) => {
  const parsed = createSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dati non validi" });
  const category = await prisma.category.create({
    data: { ...parsed.data, parishId: req.user!.parishId },
  });
  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "CREATE",
    entityType: "Category",
    entityId: category.id,
    newValue: category,
  });
  res.status(201).json(category);
});

const updateSchema = z.object({
  name: z.string().min(1).max(120).optional(),
  active: z.boolean().optional(),
});

router.put("/:id", adminOnly, async (req: AuthedRequest, res) => {
  const existing = await prisma.category.findFirst({ where: { id: req.params.id, parishId: req.user!.parishId } });
  if (!existing) return res.status(404).json({ error: "Categoria non trovata" });
  const parsed = updateSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dati non validi" });
  const category = await prisma.category.update({ where: { id: existing.id }, data: parsed.data });
  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Category",
    entityId: category.id,
    oldValue: existing,
    newValue: category,
  });
  res.json(category);
});

router.delete("/:id", adminOnly, async (req: AuthedRequest, res) => {
  const existing = await prisma.category.findFirst({ where: { id: req.params.id, parishId: req.user!.parishId } });
  if (!existing) return res.status(404).json({ error: "Categoria non trovata" });
  const inUse = await prisma.transaction.count({ where: { categoryId: existing.id } });
  if (inUse > 0) {
    const category = await prisma.category.update({ where: { id: existing.id }, data: { active: false } });
    await logAudit({
      parishId: req.user!.parishId,
      userId: req.user!.id,
      action: "UPDATE",
      entityType: "Category",
      entityId: category.id,
      oldValue: existing,
      newValue: category,
    });
    return res.json({ ok: true, deactivated: true, category });
  }
  await prisma.category.delete({ where: { id: existing.id } });
  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "DELETE",
    entityType: "Category",
    entityId: existing.id,
    oldValue: existing,
  });
  res.json({ ok: true, deactivated: false });
});

export default router;
