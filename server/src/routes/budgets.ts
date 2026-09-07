import { Router } from "express";
import { z } from "zod";
import { prisma } from "../lib/prisma";
import { requireAuth, AuthedRequest } from "../middleware/auth";
import { canWrite } from "../middleware/roles";
import { logAudit } from "../utils/audit";

const router = Router();
router.use(requireAuth);

async function withSpent(budget: any) {
  const transactions = await prisma.transaction.findMany({
    where: { budgetId: budget.id, deletedAt: null },
    select: { amount: true, currency: true, date: true, description: true, id: true },
  });
  const spentSameCurrency = transactions
    .filter((t) => t.currency === budget.currency)
    .reduce((sum, t) => sum + t.amount, 0);
  const otherCurrencyTx = transactions.filter((t) => t.currency !== budget.currency);
  return {
    ...budget,
    spentAmount: spentSameCurrency,
    remainingAmount: budget.plannedAmount - spentSameCurrency,
    transactionCount: transactions.length,
    otherCurrencyTransactions: otherCurrencyTx,
  };
}

router.get("/", async (req: AuthedRequest, res) => {
  const q = req.query as Record<string, string>;
  const where: any = { parishId: req.user!.parishId };
  if (q.status) where.status = q.status;
  if (q.search) where.OR = [{ title: { contains: q.search } }, { number: { contains: q.search } }];

  const budgets = await prisma.budget.findMany({
    where,
    include: { category: { select: { id: true, name: true, translationKey: true } }, createdBy: { select: { id: true, name: true } } },
    orderBy: { createdAt: "desc" },
  });
  const withComputed = await Promise.all(budgets.map(withSpent));
  res.json(withComputed);
});

router.get("/:id", async (req: AuthedRequest, res) => {
  const budget = await prisma.budget.findFirst({
    where: { id: req.params.id, parishId: req.user!.parishId },
    include: {
      category: { select: { id: true, name: true, translationKey: true } },
      createdBy: { select: { id: true, name: true } },
      transactions: {
        where: { deletedAt: null },
        select: { id: true, date: true, description: true, amount: true, currency: true, method: true },
        orderBy: { date: "desc" },
      },
    },
  });
  if (!budget) return res.status(404).json({ error: "Preventivo non trovato" });
  res.json(await withSpent(budget));
});

const createSchema = z.object({
  date: z.string().min(1),
  title: z.string().min(1).max(200),
  description: z.string().max(2000).optional().nullable(),
  categoryId: z.string().min(1),
  plannedAmount: z.coerce.number().positive(),
  currency: z.enum(["ALL", "EUR"]),
  plannedMethod: z.enum(["CASH", "BANK"]),
  status: z.enum(["BOZZA", "APPROVATO", "IN_CORSO", "COMPLETATO", "ANNULLATO"]).optional(),
});

router.post("/", canWrite, async (req: AuthedRequest, res) => {
  const parsed = createSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dati non validi", details: parsed.error.flatten() });
  const data = parsed.data;

  const category = await prisma.category.findFirst({ where: { id: data.categoryId, parishId: req.user!.parishId, type: "USCITA" } });
  if (!category) return res.status(400).json({ error: "Categoria non valida (deve essere una categoria di uscita)" });

  const year = new Date(data.date).getFullYear();
  const count = await prisma.budget.count({ where: { parishId: req.user!.parishId, number: { startsWith: `PR-${year}-` } } });
  const number = `PR-${year}-${String(count + 1).padStart(3, "0")}`;

  const budget = await prisma.budget.create({
    data: {
      parishId: req.user!.parishId,
      number,
      date: new Date(data.date),
      title: data.title,
      description: data.description || null,
      categoryId: data.categoryId,
      plannedAmount: data.plannedAmount,
      currency: data.currency,
      plannedMethod: data.plannedMethod,
      status: data.status || "BOZZA",
      createdById: req.user!.id,
    },
  });

  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "CREATE",
    entityType: "Budget",
    entityId: budget.id,
    newValue: budget,
  });

  res.status(201).json(await withSpent(budget));
});

const updateSchema = createSchema.partial();

router.put("/:id", canWrite, async (req: AuthedRequest, res) => {
  const existing = await prisma.budget.findFirst({ where: { id: req.params.id, parishId: req.user!.parishId } });
  if (!existing) return res.status(404).json({ error: "Preventivo non trovato" });
  const parsed = updateSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dati non validi" });
  const data = parsed.data;

  const budget = await prisma.budget.update({
    where: { id: existing.id },
    data: {
      ...(data.date ? { date: new Date(data.date) } : {}),
      ...(data.title ? { title: data.title } : {}),
      ...(data.description !== undefined ? { description: data.description || null } : {}),
      ...(data.categoryId ? { categoryId: data.categoryId } : {}),
      ...(data.plannedAmount !== undefined ? { plannedAmount: data.plannedAmount } : {}),
      ...(data.currency ? { currency: data.currency } : {}),
      ...(data.plannedMethod ? { plannedMethod: data.plannedMethod } : {}),
      ...(data.status ? { status: data.status } : {}),
    },
  });

  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "Budget",
    entityId: budget.id,
    oldValue: existing,
    newValue: budget,
  });

  res.json(await withSpent(budget));
});

router.delete("/:id", canWrite, async (req: AuthedRequest, res) => {
  const existing = await prisma.budget.findFirst({ where: { id: req.params.id, parishId: req.user!.parishId } });
  if (!existing) return res.status(404).json({ error: "Preventivo non trovato" });
  if (req.query.confirm !== "true") return res.status(400).json({ error: "Conferma richiesta per l'eliminazione (confirm=true)" });

  const linked = await prisma.transaction.count({ where: { budgetId: existing.id, deletedAt: null } });
  if (linked > 0) {
    return res.status(400).json({ error: "Impossibile eliminare: ci sono uscite collegate a questo preventivo" });
  }

  await prisma.budget.delete({ where: { id: existing.id } });
  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "DELETE",
    entityType: "Budget",
    entityId: existing.id,
    oldValue: existing,
  });
  res.json({ ok: true });
});

export default router;
