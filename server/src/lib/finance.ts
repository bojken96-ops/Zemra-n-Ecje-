import { prisma } from "./prisma";

export async function getCurrentRate(parishId: string): Promise<number> {
  const rate = await prisma.exchangeRate.findFirst({ where: { parishId }, orderBy: { effectiveDate: "desc" } });
  return rate?.rateEurToAll ?? 100;
}

export function toEur(amount: number, currency: "ALL" | "EUR", rateEurToAll: number): number {
  return currency === "EUR" ? amount : amount / rateEurToAll;
}

export interface Balances {
  cashALL: number;
  cashEUR: number;
  bankALL: number;
  bankEUR: number;
}

export async function computeBalances(parishId: string, asOfDate?: Date): Promise<Balances> {
  const where: any = { parishId, deletedAt: null };
  if (asOfDate) where.date = { lte: asOfDate };

  const rows = await prisma.transaction.groupBy({
    by: ["method", "currency", "type"],
    where,
    _sum: { amount: true },
  });

  const balances: Balances = { cashALL: 0, cashEUR: 0, bankALL: 0, bankEUR: 0 };
  for (const row of rows) {
    const key = `${row.method === "CASH" ? "cash" : "bank"}${row.currency}` as keyof Balances;
    const sum = row._sum.amount || 0;
    balances[key] += row.type === "ENTRATA" ? sum : -sum;
  }
  return balances;
}

export interface BucketKey {
  method: "CASH" | "BANK";
  currency: "ALL" | "EUR";
}

export const BUCKETS: BucketKey[] = [
  { method: "CASH", currency: "ALL" },
  { method: "CASH", currency: "EUR" },
  { method: "BANK", currency: "ALL" },
  { method: "BANK", currency: "EUR" },
];

export async function computeBucketedFlow(parishId: string, from: Date, to: Date) {
  const rows = await prisma.transaction.groupBy({
    by: ["method", "currency", "type"],
    where: { parishId, deletedAt: null, date: { gte: from, lte: to } },
    _sum: { amount: true },
  });
  const result: Record<string, { entrate: number; uscite: number }> = {};
  for (const b of BUCKETS) {
    result[`${b.method}_${b.currency}`] = { entrate: 0, uscite: 0 };
  }
  for (const row of rows) {
    const key = `${row.method}_${row.currency}`;
    if (!result[key]) result[key] = { entrate: 0, uscite: 0 };
    const sum = row._sum.amount || 0;
    if (row.type === "ENTRATA") result[key].entrate += sum;
    else result[key].uscite += sum;
  }
  return result;
}

export async function computePeriodSummary(parishId: string, from: Date, to: Date) {
  const where = { parishId, deletedAt: null, date: { gte: from, lte: to } };

  const [entrate, uscite, categoryBreakdown, count] = await Promise.all([
    prisma.transaction.groupBy({ by: ["currency"], where: { ...where, type: "ENTRATA" }, _sum: { amount: true } }),
    prisma.transaction.groupBy({ by: ["currency"], where: { ...where, type: "USCITA" }, _sum: { amount: true } }),
    prisma.transaction.groupBy({ by: ["categoryId", "type"], where, _sum: { amount: true } }),
    prisma.transaction.count({ where }),
  ]);

  const categoryIds = [...new Set(categoryBreakdown.map((c) => c.categoryId))];
  const categories = await prisma.category.findMany({ where: { id: { in: categoryIds } } });
  const catMap = new Map(categories.map((c) => [c.id, c]));

  const entrateByCategory = categoryBreakdown
    .filter((c) => c.type === "ENTRATA")
    .map((c) => ({ category: catMap.get(c.categoryId), amount: c._sum.amount || 0 }));
  const usciteByCategory = categoryBreakdown
    .filter((c) => c.type === "USCITA")
    .map((c) => ({ category: catMap.get(c.categoryId), amount: c._sum.amount || 0 }));

  const sumByCurrency = (rows: { currency: string; _sum: { amount: number | null } }[]) => ({
    ALL: rows.find((r) => r.currency === "ALL")?._sum.amount || 0,
    EUR: rows.find((r) => r.currency === "EUR")?._sum.amount || 0,
  });

  return {
    entrate: sumByCurrency(entrate as any),
    uscite: sumByCurrency(uscite as any),
    transactionCount: count,
    entrateByCategory,
    usciteByCategory,
  };
}
