import { Router } from "express";
import bcrypt from "bcryptjs";
import crypto from "crypto";
import { z } from "zod";
import { OAuth2Client } from "google-auth-library";
import { prisma } from "../lib/prisma";
import { signAccessToken, signRefreshToken, verifyRefreshToken } from "../lib/jwt";
import { sendMail, verifyEmailTemplate, resetPasswordTemplate } from "../lib/mailer";
import { requireAuth, AuthedRequest } from "../middleware/auth";
import { DEFAULT_CATEGORIES } from "../lib/defaultCategories";

const router = Router();
const googleClient = new OAuth2Client(process.env.GOOGLE_CLIENT_ID);

const CLIENT_URL = process.env.CLIENT_URL || "http://localhost:5173";

function genToken() {
  return crypto.randomBytes(32).toString("hex");
}

function publicUser(user: {
  id: string;
  email: string;
  name: string;
  role: string;
  parishId: string;
  emailVerified: boolean;
}) {
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    role: user.role,
    parishId: user.parishId,
    emailVerified: user.emailVerified,
  };
}

async function issueTokens(userId: string, role: string, parishId: string) {
  const accessToken = signAccessToken({ sub: userId, role, parishId });
  const refreshToken = signRefreshToken(userId);
  const refreshTokenHash = crypto.createHash("sha256").update(refreshToken).digest("hex");
  await prisma.user.update({ where: { id: userId }, data: { refreshTokenHash } });
  return { accessToken, refreshToken };
}

const registerSchema = z.object({
  name: z.string().min(2).max(120),
  email: z.string().email(),
  password: z.string().min(8).max(128),
  parishName: z.string().min(2).max(180),
});

router.post("/register", async (req, res) => {
  const parsed = registerSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dati non validi", details: parsed.error.flatten() });
  const { name, email, password, parishName } = parsed.data;

  const existing = await prisma.user.findUnique({ where: { email: email.toLowerCase() } });
  if (existing) return res.status(409).json({ error: "Email già registrata" });

  const passwordHash = await bcrypt.hash(password, 12);
  const verifyToken = genToken();

  const result = await prisma.$transaction(async (tx) => {
    const parish = await tx.parish.create({ data: { name: parishName } });
    await tx.category.createMany({
      data: DEFAULT_CATEGORIES.map((c) => ({ ...c, parishId: parish.id })),
    });
    const user = await tx.user.create({
      data: {
        name,
        email: email.toLowerCase(),
        passwordHash,
        role: "ADMIN",
        parishId: parish.id,
        verifyToken,
        verifyTokenExpiry: new Date(Date.now() + 24 * 3600 * 1000),
      },
    });
    await tx.exchangeRate.create({
      data: { parishId: parish.id, rateEurToAll: 100, createdById: user.id },
    });
    return { parish, user };
  });

  await sendMail(
    result.user.email,
    "Conferma il tuo account - Cassa Parrocchiale",
    verifyEmailTemplate(`${CLIENT_URL}/verify-email?token=${verifyToken}`, result.user.name)
  );

  const tokens = await issueTokens(result.user.id, result.user.role, result.user.parishId);
  res.status(201).json({ user: publicUser(result.user), ...tokens });
});

const loginSchema = z.object({ email: z.string().email(), password: z.string().min(1) });

router.post("/login", async (req, res) => {
  const parsed = loginSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dati non validi" });
  const { email, password } = parsed.data;

  const user = await prisma.user.findUnique({ where: { email: email.toLowerCase() } });
  if (!user || !user.passwordHash || !user.active) {
    return res.status(401).json({ error: "Credenziali non valide" });
  }
  const ok = await bcrypt.compare(password, user.passwordHash);
  if (!ok) return res.status(401).json({ error: "Credenziali non valide" });

  const tokens = await issueTokens(user.id, user.role, user.parishId);
  res.json({ user: publicUser(user), ...tokens });
});

router.post("/google", async (req, res) => {
  const { idToken } = req.body as { idToken?: string };
  if (!idToken) return res.status(400).json({ error: "idToken mancante" });
  if (!process.env.GOOGLE_CLIENT_ID) {
    return res.status(501).json({ error: "Login con Google non configurato sul server" });
  }
  try {
    const ticket = await googleClient.verifyIdToken({ idToken, audience: process.env.GOOGLE_CLIENT_ID });
    const payload = ticket.getPayload();
    if (!payload || !payload.email) return res.status(401).json({ error: "Token Google non valido" });

    let user = await prisma.user.findFirst({
      where: { OR: [{ googleId: payload.sub }, { email: payload.email.toLowerCase() }] },
    });

    if (!user) {
      const parish = await prisma.parish.create({ data: { name: `Parrocchia di ${payload.name || payload.email}` } });
      await prisma.category.createMany({ data: DEFAULT_CATEGORIES.map((c) => ({ ...c, parishId: parish.id })) });
      user = await prisma.user.create({
        data: {
          name: payload.name || payload.email,
          email: payload.email.toLowerCase(),
          googleId: payload.sub,
          role: "ADMIN",
          parishId: parish.id,
          emailVerified: true,
        },
      });
      await prisma.exchangeRate.create({ data: { parishId: parish.id, rateEurToAll: 100, createdById: user.id } });
    } else if (!user.googleId) {
      user = await prisma.user.update({ where: { id: user.id }, data: { googleId: payload.sub, emailVerified: true } });
    }

    if (!user.active) return res.status(403).json({ error: "Account disattivato" });

    const tokens = await issueTokens(user.id, user.role, user.parishId);
    res.json({ user: publicUser(user), ...tokens });
  } catch (e) {
    res.status(401).json({ error: "Verifica Google fallita" });
  }
});

router.post("/refresh", async (req, res) => {
  const { refreshToken } = req.body as { refreshToken?: string };
  if (!refreshToken) return res.status(400).json({ error: "refreshToken mancante" });
  try {
    const payload = verifyRefreshToken(refreshToken);
    const user = await prisma.user.findUnique({ where: { id: payload.sub } });
    if (!user || !user.refreshTokenHash) return res.status(401).json({ error: "Sessione non valida" });
    const hash = crypto.createHash("sha256").update(refreshToken).digest("hex");
    if (hash !== user.refreshTokenHash) return res.status(401).json({ error: "Sessione non valida" });
    const tokens = await issueTokens(user.id, user.role, user.parishId);
    res.json(tokens);
  } catch {
    res.status(401).json({ error: "refreshToken non valido o scaduto" });
  }
});

router.post("/logout", requireAuth, async (req: AuthedRequest, res) => {
  await prisma.user.update({ where: { id: req.user!.id }, data: { refreshTokenHash: null } });
  res.json({ ok: true });
});

router.get("/verify-email", async (req, res) => {
  const token = req.query.token as string;
  if (!token) return res.status(400).json({ error: "Token mancante" });
  const user = await prisma.user.findUnique({ where: { verifyToken: token } });
  if (!user || !user.verifyTokenExpiry || user.verifyTokenExpiry < new Date()) {
    return res.status(400).json({ error: "Token non valido o scaduto" });
  }
  await prisma.user.update({
    where: { id: user.id },
    data: { emailVerified: true, verifyToken: null, verifyTokenExpiry: null },
  });
  res.json({ ok: true });
});

router.post("/resend-verification", requireAuth, async (req: AuthedRequest, res) => {
  const user = await prisma.user.findUnique({ where: { id: req.user!.id } });
  if (!user) return res.status(404).json({ error: "Utente non trovato" });
  if (user.emailVerified) return res.json({ ok: true });
  const verifyToken = genToken();
  await prisma.user.update({
    where: { id: user.id },
    data: { verifyToken, verifyTokenExpiry: new Date(Date.now() + 24 * 3600 * 1000) },
  });
  await sendMail(
    user.email,
    "Conferma il tuo account - Cassa Parrocchiale",
    verifyEmailTemplate(`${CLIENT_URL}/verify-email?token=${verifyToken}`, user.name)
  );
  res.json({ ok: true });
});

router.post("/forgot-password", async (req, res) => {
  const { email } = req.body as { email?: string };
  if (!email) return res.status(400).json({ error: "Email mancante" });
  const user = await prisma.user.findUnique({ where: { email: email.toLowerCase() } });
  if (user && user.passwordHash) {
    const resetToken = genToken();
    await prisma.user.update({
      where: { id: user.id },
      data: { resetToken, resetTokenExpiry: new Date(Date.now() + 3600 * 1000) },
    });
    await sendMail(
      user.email,
      "Reset password - Cassa Parrocchiale",
      resetPasswordTemplate(`${CLIENT_URL}/reset-password?token=${resetToken}`, user.name)
    );
  }
  // Always respond success to avoid leaking which emails are registered.
  res.json({ ok: true });
});

const resetSchema = z.object({ token: z.string().min(1), password: z.string().min(8).max(128) });

router.post("/reset-password", async (req, res) => {
  const parsed = resetSchema.safeParse(req.body);
  if (!parsed.success) return res.status(400).json({ error: "Dati non validi" });
  const { token, password } = parsed.data;
  const user = await prisma.user.findUnique({ where: { resetToken: token } });
  if (!user || !user.resetTokenExpiry || user.resetTokenExpiry < new Date()) {
    return res.status(400).json({ error: "Token non valido o scaduto" });
  }
  const passwordHash = await bcrypt.hash(password, 12);
  await prisma.user.update({
    where: { id: user.id },
    data: { passwordHash, resetToken: null, resetTokenExpiry: null, refreshTokenHash: null },
  });
  res.json({ ok: true });
});

router.get("/me", requireAuth, async (req: AuthedRequest, res) => {
  const user = await prisma.user.findUnique({ where: { id: req.user!.id }, include: { parish: true } });
  if (!user) return res.status(404).json({ error: "Utente non trovato" });
  res.json({ user: publicUser(user), parish: user.parish });
});

export default router;
