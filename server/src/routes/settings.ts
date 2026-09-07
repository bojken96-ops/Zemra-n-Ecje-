import { Router } from "express";
import { z } from "zod";
import { prisma } from "../lib/prisma";
import { requireAuth, AuthedRequest } from "../middleware/auth";
import { adminOnly } from "../middleware/roles";
import { logAudit } from "../utils/audit";
import { getCurrentRate } from "../lib/finance";

const router = Router();
router.use(requireAuth);

router.get("/parish", async (req: AuthedRequest, res) => {
  const parish = await prisma.parish.findUnique({ where: { id: req.user!.parishId } });
  res.json(parish);
});

const parishSchema = z.object({
  name: z.string().min(2).max(180).optional(),
  address: z.string().max(300).optional().nullable(),
  taxId: z.string().max(60).optional().nullable(),
  currency: z.enum(["ALL", "EUR"]).optional(),
});

router.put("/parish", adminOnly, async (req: AuthedRequest, res) => {
  const parsed = parishSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dati non validi" });
  const existing = await prisma.parish.findUnique({ where: { id: req.user!.parishId } });
  const parish = await prisma.parish.update({ where: { id: req.user!.parishId }, data: parsed.data });
  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Parish",
    entityId: parish.id,
    oldValue: existing,
    newValue: parish,
  });
  res.json(parish);
});

router.get("/exchange-rate", async (req: AuthedRequest, res) => {
  const rate = await getCurrentRate(req.user!.parishId);
  res.json({ rateEurToAll: rate });
});

router.get("/exchange-rate/history", async (req: AuthedRequest, res) => {
  const rates = await prisma.exchangeRate.findMany({
    where: { parishId: req.user!.parishId },
    orderBy: { effectiveDate: "desc" },
    include: { createdBy: { select: { name: true } } },
    take: 50,
  });
  res.json(rates);
});

const rateSchema = z.object({ rateEurToAll: z.coerce.number().positive() });

router.post("/exchange-rate", adminOnly, async (req: AuthedRequest, res) => {
  const parsed = rateSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Tasso di cambio non valido" });
  const rate = await prisma.exchangeRate.create({
    data: { parishId: req.user!.parishId, rateEurToAll: parsed.data.rateEurToAll, createdById: req.user!.id },
  });
  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "CREATE",
    entityType: "ExchangeRate",
    entityId: rate.id,
    newValue: rate,
  });
  res.status(201).json(rate);
});

export default router;
