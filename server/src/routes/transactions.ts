import { Router } from "express";
import { z } from "zod";
import fs from "fs";
import { prisma } from "../lib/prisma";
import { requireAuth, AuthedRequest } from "../middleware/auth";
import { canWrite } from "../middleware/roles";
import { logAudit } from "../utils/audit";
import { upload, UPLOAD_DIR } from "../lib/upload";
import path from "path";

const router = Router();
router.use(requireAuth);

const txSelect = {
  id: true,
  type: true,
  date: true,
  description: true,
  categoryId: true,
  category: { select: { id: true, name: true, translationKey: true } },
  amount: true,
  currency: true,
  method: true,
  budgetId: true,
  budget: { select: { id: true, number: true, title: true } },
  notes: true,
  exchangeRateUsed: true,
  createdById: true,
  createdBy: { select: { id: true, name: true, email: true } },
  createdAt: true,
  updatedAt: true,
  attachments: { select: { id: true, filename: true, mimeType: true, size: true, createdAt: true } },
} as const;

router.get("/", async (req: AuthedRequest, res) => {
  const q = req.query as Record<string, string>;
  const page = Math.max(1, parseInt(q.page || "1", 10));
  const pageSize = Math.min(200, Math.max(1, parseInt(q.pageSize || "50", 10)));

  const where: any = { parishId: req.user!.parishId, deletedAt: null };
  if (q.type) where.type = q.type;
  if (q.method) where.method = q.method;
  if (q.currency) where.currency = q.currency;
  if (q.categoryId) where.categoryId = q.categoryId;
  if (q.budgetId) where.budgetId = q.budgetId;
  if (q.dateFrom || q.dateTo) {
    where.date = {};
    if (q.dateFrom) where.date.gte = new Date(q.dateFrom);
    if (q.dateTo) where.date.lte = new Date(q.dateTo + "T23:59:59.999Z");
  }
  if (q.search) {
    where.OR = [
      { description: { contains: q.search } },
      { notes: { contains: q.search } },
    ];
  }

  const sortField = ["date", "amount", "createdAt", "description"].includes(q.sortBy) ? q.sortBy : "date";
  const sortDir = q.sortDir === "asc" ? "asc" : "desc";

  const [items, total] = await Promise.all([
    prisma.transaction.findMany({
      where,
      select: txSelect,
      orderBy: { [sortField]: sortDir },
      skip: (page - 1) * pageSize,
      take: pageSize,
    }),
    prisma.transaction.count({ where }),
  ]);

  res.json({ items, total, page, pageSize });
});

router.get("/:id", async (req: AuthedRequest, res) => {
  const tx = await prisma.transaction.findFirst({
    where: { id: req.params.id, parishId: req.user!.parishId, deletedAt: null },
    select: txSelect,
  });
  if (!tx) return res.status(404).json({ error: "Movimento non trovato" });
  res.json(tx);
});

const bodySchema = z.object({
  type: z.enum(["ENTRATA", "USCITA"]),
  date: z.string().min(1),
  description: z.string().min(1).max(300),
  categoryId: z.string().min(1),
  amount: z.coerce.number().positive(),
  currency: z.enum(["ALL", "EUR"]),
  method: z.enum(["CASH", "BANK"]),
  budgetId: z.string().optional().nullable(),
  notes: z.string().max(2000).optional().nullable(),
});

async function currentExchangeRate(parishId: string): Promise<number> {
  const rate = await prisma.exchangeRate.findFirst({ where: { parishId }, orderBy: { effectiveDate: "desc" } });
  return rate?.rateEurToAll ?? 100;
}

router.post("/", canWrite, upload.single("attachment"), async (req: AuthedRequest, res) => {
  const parsed = bodySchema.safeParse(req.body);
  if (!parsed.success) {
    if (req.file) fs.unlink(req.file.path, () => undefined);
    return res.status(400).json({ error: "Dati non validi", details: parsed.error.flatten() });
  }
  const data = parsed.data;

  const category = await prisma.category.findFirst({ where: { id: data.categoryId, parishId: req.user!.parishId } });
  if (!category || category.type !== data.type) {
    if (req.file) fs.unlink(req.file.path, () => undefined);
    return res.status(400).json({ error: "Categoria non valida per il tipo di movimento" });
  }

  if (data.budgetId) {
    const budget = await prisma.budget.findFirst({ where: { id: data.budgetId, parishId: req.user!.parishId } });
    if (!budget) {
      if (req.file) fs.unlink(req.file.path, () => undefined);
      return res.status(400).json({ error: "Preventivo non valido" });
    }
  }

  const exchangeRateUsed = await currentExchangeRate(req.user!.parishId);

  const tx = await prisma.transaction.create({
    data: {
      parishId: req.user!.parishId,
      type: data.type,
      date: new Date(data.date),
      description: data.description,
      categoryId: data.categoryId,
      amount: data.amount,
      currency: data.currency,
      method: data.method,
      budgetId: data.type === "USCITA" ? data.budgetId || null : null,
      notes: data.notes || null,
      exchangeRateUsed,
      createdById: req.user!.id,
    },
    select: txSelect,
  });

  if (req.file) {
    await prisma.attachment.create({
      data: {
        transactionId: tx.id,
        filename: req.file.originalname,
        path: req.file.filename,
        mimeType: req.file.mimetype,
        size: req.file.size,
        uploadedById: req.user!.id,
      },
    });
  }

  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "CREATE",
    entityType: "Transaction",
    entityId: tx.id,
    newValue: tx,
  });

  const full = await prisma.transaction.findUnique({ where: { id: tx.id }, select: txSelect });
  res.status(201).json(full);
});

router.put("/:id", canWrite, upload.single("attachment"), async (req: AuthedRequest, res) => {
  const existing = await prisma.transaction.findFirst({
    where: { id: req.params.id, parishId: req.user!.parishId, deletedAt: null },
    select: txSelect,
  });
  if (!existing) {
    if (req.file) fs.unlink(req.file.path, () => undefined);
    return res.status(404).json({ error: "Movimento non trovato" });
  }

  const parsed = bodySchema.partial().safeParse(req.body);
  if (!parsed.success) {
    if (req.file) fs.unlink(req.file.path, () => undefined);
    return res.status(400).json({ error: "Dati non validi" });
  }
  const data = parsed.data;

  if (data.categoryId) {
    const category = await prisma.category.findFirst({ where: { id: data.categoryId, parishId: req.user!.parishId } });
    if (!category) return res.status(400).json({ error: "Categoria non valida" });
  }

  const tx = await prisma.transaction.update({
    where: { id: existing.id },
    data: {
      ...(data.type ? { type: data.type } : {}),
      ...(data.date ? { date: new Date(data.date) } : {}),
      ...(data.description ? { description: data.description } : {}),
      ...(data.categoryId ? { categoryId: data.categoryId } : {}),
      ...(data.amount !== undefined ? { amount: data.amount } : {}),
      ...(data.currency ? { currency: data.currency } : {}),
      ...(data.method ? { method: data.method } : {}),
      ...(data.budgetId !== undefined ? { budgetId: data.budgetId || null } : {}),
      ...(data.notes !== undefined ? { notes: data.notes || null } : {}),
    },
    select: txSelect,
  });

  if (req.file) {
    await prisma.attachment.create({
      data: {
        transactionId: tx.id,
        filename: req.file.originalname,
        path: req.file.filename,
        mimeType: req.file.mimetype,
        size: req.file.size,
        uploadedById: req.user!.id,
      },
    });
  }

  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Transaction",
    entityId: tx.id,
    oldValue: existing,
    newValue: tx,
  });

  const full = await prisma.transaction.findUnique({ where: { id: tx.id }, select: txSelect });
  res.json(full);
});

router.delete("/:id", canWrite, async (req: AuthedRequest, res) => {
  const existing = await prisma.transaction.findFirst({
    where: { id: req.params.id, parishId: req.user!.parishId, deletedAt: null },
    select: txSelect,
  });
  if (!existing) return res.status(404).json({ error: "Movimento non trovato" });

  if (req.query.confirm !== "true") {
    return res.status(400).json({ error: "Conferma richiesta per l'eliminazione (confirm=true)" });
  }

  const tx = await prisma.transaction.update({
    where: { id: existing.id },
    data: { deletedAt: new Date(), deletedById: req.user!.id },
  });

  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "DELETE",
    entityType: "Transaction",
    entityId: tx.id,
    oldValue: existing,
  });

  res.json({ ok: true });
});

router.get("/attachments/:attachmentId/download", async (req: AuthedRequest, res) => {
  const attachment = await prisma.attachment.findUnique({ where: { id: req.params.attachmentId }, include: { transaction: true } });
  if (!attachment || !attachment.transaction || attachment.transaction.parishId !== req.user!.parishId) {
    return res.status(404).json({ error: "Allegato non trovato" });
  }
  const filePath = path.join(UPLOAD_DIR, attachment.path);
  res.download(filePath, attachment.filename);
});

export default router;
