import "dotenv/config";
import express from "express";
import cors from "cors";
import helmet from "helmet";
import rateLimit from "express-rate-limit";

import authRoutes from "./routes/auth";
import categoryRoutes from "./routes/categories";
import userRoutes from "./routes/users";
import transactionRoutes from "./routes/transactions";
import budgetRoutes from "./routes/budgets";
import dashboardRoutes from "./routes/dashboard";
import settingsRoutes from "./routes/settings";
import reportRoutes from "./routes/reports";
import auditRoutes from "./routes/audit";

const app = express();
const PORT = Number(process.env.PORT || 4000);
const CLIENT_URL = process.env.CLIENT_URL || "http://localhost:5173";

app.use(helmet({ crossOriginResourcePolicy: false }));
app.use(cors({ origin: CLIENT_URL, credentials: true }));
app.use(express.json({ limit: "2mb" }));
app.use(express.urlencoded({ extended: true }));

const authLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 50, standardHeaders: true, legacyHeaders: false });
app.use("/api/auth", authLimiter, authRoutes);

app.use("/api/categories", categoryRoutes);
app.use("/api/users", userRoutes);
app.use("/api/transactions", transactionRoutes);
app.use("/api/budgets", budgetRoutes);
app.use("/api/dashboard", dashboardRoutes);
app.use("/api/settings", settingsRoutes);
app.use("/api/reports", reportRoutes);
app.use("/api/audit", auditRoutes);

app.get("/api/health", (_req, res) => res.json({ ok: true }));

app.use((req, res) => res.status(404).json({ error: "Endpoint non trovato" }));

// eslint-disable-next-line @typescript-eslint/no-unused-vars
app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error(err);
  if (err?.message?.includes("Tipo di file non consentito")) {
    return res.status(400).json({ error: err.message });
  }
  res.status(500).json({ error: "Errore interno del server" });
});

app.listen(PORT, () => {
  console.log(`Cassa Parrocchiale API in ascolto sulla porta ${PORT}`);
});
