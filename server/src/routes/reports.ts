import { Router } from "express";
import PDFDocument from "pdfkit";
import ExcelJS from "exceljs";
import { prisma } from "../lib/prisma";
import { requireAuth, AuthedRequest } from "../middleware/auth";
import { computeBalances, computeBucketedFlow, computePeriodSummary } from "../lib/finance";

const router = Router();
router.use(requireAuth);

function monthRange(year: number, month: number) {
  const start = new Date(year, month - 1, 1);
  const end = new Date(year, month, 0, 23, 59, 59, 999);
  const prevEnd = new Date(year, month - 1, 0, 23, 59, 59, 999);
  return { start, end, prevEnd };
}

async function buildMonthlyReport(parishId: string, year: number, month: number) {
  const { start, end, prevEnd } = monthRange(year, month);
  const [saldoIniziale, saldoFinale, flow, summary] = await Promise.all([
    computeBalances(parishId, prevEnd),
    computeBalances(parishId, end),
    computeBucketedFlow(parishId, start, end),
    computePeriodSummary(parishId, start, end),
  ]);

  return {
    year,
    month,
    saldoIniziale,
    saldoFinale,
    flow,
    totaleEntrate: summary.entrate,
    totaleUscite: summary.uscite,
    numeroMovimenti: summary.transactionCount,
    entrateByCategory: summary.entrateByCategory,
    usciteByCategory: summary.usciteByCategory,
  };
}

router.get("/monthly", async (req: AuthedRequest, res) => {
  const year = parseInt((req.query.year as string) || String(new Date().getFullYear()), 10);
  const month = parseInt((req.query.month as string) || String(new Date().getMonth() + 1), 10);
  const report = await buildMonthlyReport(req.user!.parishId, year, month);
  res.json(report);
});

router.get("/compare", async (req: AuthedRequest, res) => {
  const months = ((req.query.months as string) || "").split(",").filter(Boolean);
  if (months.length === 0) return res.status(400).json({ error: "Specificare almeno un mese (YYYY-MM)" });
  const reports = await Promise.all(
    months.map((m) => {
      const [y, mo] = m.split("-").map((x) => parseInt(x, 10));
      return buildMonthlyReport(req.user!.parishId, y, mo);
    })
  );
  res.json(reports);
});

router.get("/monthly/export", async (req: AuthedRequest, res) => {
  const year = parseInt((req.query.year as string) || String(new Date().getFullYear()), 10);
  const month = parseInt((req.query.month as string) || String(new Date().getMonth() + 1), 10);
  const format = (req.query.format as string) || "pdf";
  const parish = await prisma.parish.findUnique({ where: { id: req.user!.parishId } });
  const report = await buildMonthlyReport(req.user!.parishId, year, month);
  const monthLabel = `${String(month).padStart(2, "0")}-${year}`;

  if (format === "excel") {
    const workbook = new ExcelJS.Workbook();
    const sheet = workbook.addWorksheet(`Bilancio ${monthLabel}`);
    sheet.columns = [
      { header: "Voce", key: "voce", width: 30 },
      { header: "ALL", key: "all", width: 18 },
      { header: "EUR", key: "eur", width: 18 },
    ];
    sheet.addRow({ voce: `Bilancio ${parish?.name || ""} - ${monthLabel}` });
    sheet.addRow({});
    sheet.addRow({ voce: "Saldo iniziale Cash", all: report.saldoIniziale.cashALL, eur: report.saldoIniziale.cashEUR });
    sheet.addRow({ voce: "Saldo iniziale Bank", all: report.saldoIniziale.bankALL, eur: report.saldoIniziale.bankEUR });
    sheet.addRow({});
    sheet.addRow({ voce: "Totale Entrate", all: report.totaleEntrate.ALL, eur: report.totaleEntrate.EUR });
    sheet.addRow({ voce: "Totale Uscite", all: report.totaleUscite.ALL, eur: report.totaleUscite.EUR });
    sheet.addRow({
      voce: "Risultato netto",
      all: report.totaleEntrate.ALL - report.totaleUscite.ALL,
      eur: report.totaleEntrate.EUR - report.totaleUscite.EUR,
    });
    sheet.addRow({});
    sheet.addRow({ voce: "Saldo finale Cash", all: report.saldoFinale.cashALL, eur: report.saldoFinale.cashEUR });
    sheet.addRow({ voce: "Saldo finale Bank", all: report.saldoFinale.bankALL, eur: report.saldoFinale.bankEUR });
    sheet.addRow({});
    sheet.addRow({ voce: "Numero movimenti", all: report.numeroMovimenti });
    sheet.addRow({});
    sheet.addRow({ voce: "Entrate per categoria" });
    for (const c of report.entrateByCategory) sheet.addRow({ voce: c.category?.name || "N/D", all: c.amount });
    sheet.addRow({});
    sheet.addRow({ voce: "Uscite per categoria" });
    for (const c of report.usciteByCategory) sheet.addRow({ voce: c.category?.name || "N/D", all: c.amount });

    res.setHeader("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
    res.setHeader("Content-Disposition", `attachment; filename="bilancio-${monthLabel}.xlsx"`);
    await workbook.xlsx.write(res);
    return res.end();
  }

  // PDF
  const doc = new PDFDocument({ margin: 40 });
  res.setHeader("Content-Type", "application/pdf");
  res.setHeader("Content-Disposition", `attachment; filename="bilancio-${monthLabel}.pdf"`);
  doc.pipe(res);

  doc.fontSize(18).text(`${parish?.name || "Parrocchia"}`, { align: "center" });
  doc.fontSize(14).text(`Bilancio mensile - ${monthLabel}`, { align: "center" });
  doc.moveDown(1.5);

  doc.fontSize(12).text("Saldo iniziale", { underline: true });
  doc.fontSize(10).text(`Cash: ${report.saldoIniziale.cashALL.toFixed(2)} ALL / ${report.saldoIniziale.cashEUR.toFixed(2)} EUR`);
  doc.text(`Bank: ${report.saldoIniziale.bankALL.toFixed(2)} ALL / ${report.saldoIniziale.bankEUR.toFixed(2)} EUR`);
  doc.moveDown();

  doc.fontSize(12).text("Movimenti del periodo", { underline: true });
  doc.fontSize(10).text(`Totale Entrate: ${report.totaleEntrate.ALL.toFixed(2)} ALL / ${report.totaleEntrate.EUR.toFixed(2)} EUR`);
  doc.text(`Totale Uscite: ${report.totaleUscite.ALL.toFixed(2)} ALL / ${report.totaleUscite.EUR.toFixed(2)} EUR`);
  doc.text(
    `Risultato netto: ${(report.totaleEntrate.ALL - report.totaleUscite.ALL).toFixed(2)} ALL / ${(
      report.totaleEntrate.EUR - report.totaleUscite.EUR
    ).toFixed(2)} EUR`
  );
  doc.text(`Numero movimenti: ${report.numeroMovimenti}`);
  doc.moveDown();

  doc.fontSize(12).text("Saldo finale", { underline: true });
  doc.fontSize(10).text(`Cash: ${report.saldoFinale.cashALL.toFixed(2)} ALL / ${report.saldoFinale.cashEUR.toFixed(2)} EUR`);
  doc.text(`Bank: ${report.saldoFinale.bankALL.toFixed(2)} ALL / ${report.saldoFinale.bankEUR.toFixed(2)} EUR`);
  doc.moveDown();

  doc.fontSize(12).text("Entrate per categoria", { underline: true });
  doc.fontSize(10);
  for (const c of report.entrateByCategory) doc.text(`${c.category?.name || "N/D"}: ${c.amount.toFixed(2)}`);
  doc.moveDown();

  doc.fontSize(12).text("Uscite per categoria", { underline: true });
  doc.fontSize(10);
  for (const c of report.usciteByCategory) doc.text(`${c.category?.name || "N/D"}: ${c.amount.toFixed(2)}`);

  doc.end();
});

export default router;
