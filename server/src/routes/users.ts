import { Router } from "express";
import crypto from "crypto";
import { z } from "zod";
import { prisma } from "../lib/prisma";
import { requireAuth, AuthedRequest } from "../middleware/auth";
import { adminOnly } from "../middleware/roles";
import { logAudit } from "../utils/audit";
import { sendMail } from "../lib/mailer";

const router = Router();
router.use(requireAuth);

function publicUser(u: any) {
  const { passwordHash, refreshTokenHash, verifyToken, resetToken, ...rest } = u;
  return rest;
}

router.get("/", adminOnly, async (req: AuthedRequest, res) => {
  const users = await prisma.user.findMany({
    where: { parishId: req.user!.parishId },
    orderBy: { createdAt: "asc" },
  });
  res.json(users.map(publicUser));
});

const createSchema = z.object({
  name: z.string().min(2).max(120),
  email: z.string().email(),
  role: z.enum(["ADMIN", "TESORIERE", "VIEWER"]),
});

router.post("/", adminOnly, async (req: AuthedRequest, res) => {
  const parsed = createSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dati non validi" });
  const { name, email, role } = parsed.data;

  const existing = await prisma.user.findUnique({ where: { email: email.toLowerCase() } });
  if (existing) return res.status(409).json({ error: "Email già registrata" });

  const resetToken = crypto.randomBytes(32).toString("hex");
  const user = await prisma.user.create({
    data: {
      name,
      email: email.toLowerCase(),
      role,
      parishId: req.user!.parishId,
      resetToken,
      resetTokenExpiry: new Date(Date.now() + 72 * 3600 * 1000),
    },
  });

  const clientUrl = process.env.CLIENT_URL || "http://localhost:5173";
  await sendMail(
    user.email,
    "Sei stato invitato su Cassa Parrocchiale",
    `<p>Ciao ${name},</p><p>Un amministratore ti ha creato un account su Cassa Parrocchiale con ruolo ${role}.</p><p>Imposta la tua password cliccando qui: <a href="${clientUrl}/reset-password?token=${resetToken}">${clientUrl}/reset-password?token=${resetToken}</a></p>`
  );

  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "CREATE",
    entityType: "User",
    entityId: user.id,
    newValue: publicUser(user),
  });

  res.status(201).json(publicUser(user));
});

const updateSchema = z.object({
  name: z.string().min(2).max(120).optional(),
  role: z.enum(["ADMIN", "TESORIERE", "VIEWER"]).optional(),
  active: z.boolean().optional(),
});

router.put("/:id", adminOnly, async (req: AuthedRequest, res) => {
  const existing = await prisma.user.findFirst({ where: { id: req.params.id, parishId: req.user!.parishId } });
  if (!existing) return res.status(404).json({ error: "Utente non trovato" });
  const parsed = updateSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dati non validi" });

  if ((parsed.data.role && parsed.data.role !== "ADMIN") || parsed.data.active === false) {
    if (existing.role === "ADMIN") {
      const adminCount = await prisma.user.count({ where: { parishId: req.user!.parishId, role: "ADMIN", active: true } });
      if (adminCount <= 1) {
        return res.status(400).json({ error: "Deve rimanere almeno un amministratore attivo" });
      }
    }
  }

  const user = await prisma.user.update({ where: { id: existing.id }, data: parsed.data });
  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "UPDATE",
    entityType: "User",
    entityId: user.id,
    oldValue: publicUser(existing),
    newValue: publicUser(user),
  });
  res.json(publicUser(user));
});

router.delete("/:id", adminOnly, async (req: AuthedRequest, res) => {
  const existing = await prisma.user.findFirst({ where: { id: req.params.id, parishId: req.user!.parishId } });
  if (!existing) return res.status(404).json({ error: "Utente non trovato" });
  if (existing.id === req.user!.id) return res.status(400).json({ error: "Non puoi eliminare te stesso" });
  if (existing.role === "ADMIN") {
    const adminCount = await prisma.user.count({ where: { parishId: req.user!.parishId, role: "ADMIN", active: true } });
    if (adminCount <= 1) return res.status(400).json({ error: "Deve rimanere almeno un amministratore attivo" });
  }
  const user = await prisma.user.update({ where: { id: existing.id }, data: { active: false, refreshTokenHash: null } });
  await logAudit({
    parishId: req.user!.parishId,
    userId: req.user!.id,
    action: "DELETE",
    entityType: "User",
    entityId: existing.id,
    oldValue: publicUser(existing),
    newValue: publicUser(user),
  });
  res.json({ ok: true });
});

export default router;
