import { Router } from "express";
import { prisma } from "../lib/prisma";
import { requireAuth, AuthedRequest } from "../middleware/auth";
import { computeBalances, computePeriodSummary, getCurrentRate, toEur } from "../lib/finance";

const router = Router();
router.use(requireAuth);

router.get("/", async (req: AuthedRequest, res) => {
  const parishId = req.user!.parishId;
  const now = new Date();
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
  const monthEnd = new Date(now.getFullYear(), now.getMonth() + 1, 0, 23, 59, 59, 999);

  const [balances, monthSummary, openBudgets, recentTx, rate] = await Promise.all([
    computeBalances(parishId),
    computePeriodSummary(parishId, monthStart, monthEnd),
    prisma.budget.findMany({
      where: { parishId, status: { in: ["BOZZA", "APPROVATO", "IN_CORSO"] } },
      include: { category: { select: { name: true, translationKey: true } } },
      orderBy: { date: "desc" },
      take: 10,
    }),
    prisma.transaction.findMany({
      where: { parishId, deletedAt: null },
      orderBy: { date: "desc" },
      take: 10,
      select: {
        id: true,
        type: true,
        date: true,
        description: true,
        amount: true,
        currency: true,
        method: true,
        category: { select: { name: true, translationKey: true } },
      },
    }),
    getCurrentRate(parishId),
  ]);

  const cashTotalEur = toEur(balances.cashALL, "ALL", rate) + balances.cashEUR;
  const bankTotalEur = toEur(balances.bankALL, "ALL", rate) + balances.bankEUR;
  const totalEur = cashTotalEur + bankTotalEur;

  const entrateEur = toEur(monthSummary.entrate.ALL, "ALL", rate) + monthSummary.entrate.EUR;
  const usciteEur = toEur(monthSummary.uscite.ALL, "ALL", rate) + monthSummary.uscite.EUR;

  // Last 6 months trend for charts
  const trend: { month: string; entrate: number; uscite: number; saldo: number }[] = [];
  let runningBalanceEur: number | null = null;
  for (let i = 5; i >= 0; i--) {
    const start = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const end = new Date(now.getFullYear(), now.getMonth() - i + 1, 0, 23, 59, 59, 999);
    const summary = await computePeriodSummary(parishId, start, end);
    const e = toEur(summary.entrate.ALL, "ALL", rate) + summary.entrate.EUR;
    const u = toEur(summary.uscite.ALL, "ALL", rate) + summary.uscite.EUR;
    const balAtEnd = await computeBalances(parishId, end);
    const balEur =
      toEur(balAtEnd.cashALL, "ALL", rate) + balAtEnd.cashEUR + toEur(balAtEnd.bankALL, "ALL", rate) + balAtEnd.bankEUR;
    trend.push({ month: start.toISOString().slice(0, 7), entrate: e, uscite: u, saldo: balEur });
    runningBalanceEur = balEur;
  }

  const expenseDistribution = monthSummary.usciteByCategory.map((c) => ({
    category: c.category?.name || "N/D",
    translationKey: c.category?.translationKey || null,
    amount: c.amount,
  }));

  res.json({
    balances,
    exchangeRate: rate,
    saldoTotaleEur: totalEur,
    saldoCashEur: cashTotalEur,
    saldoBankEur: bankTotalEur,
    entrateDelMese: { ...monthSummary.entrate, eur: entrateEur },
    usciteDelMese: { ...monthSummary.uscite, eur: usciteEur },
    risultatoDelMeseEur: entrateEur - usciteEur,
    preventiviAperti: openBudgets,
    ultimiMovimenti: recentTx,
    trend,
    expenseDistribution,
  });
});

export default router;
