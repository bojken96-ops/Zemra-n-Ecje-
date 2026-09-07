import "dotenv/config";
import bcrypt from "bcryptjs";
import { prisma } from "./lib/prisma";
import { DEFAULT_CATEGORIES } from "./lib/defaultCategories";

async function main() {
  const adminEmail = (process.env.DEFAULT_ADMIN_EMAIL || "admin@parrocchia.local").toLowerCase();
  const existing = await prisma.user.findUnique({ where: { email: adminEmail } });
  if (existing) {
    console.log(`Utente admin già esistente (${adminEmail}), seed saltato.`);
    return;
  }

  const parish = await prisma.parish.create({
    data: { name: process.env.DEFAULT_PARISH_NAME || "Parrocchia Santa Maria" },
  });

  await prisma.category.createMany({ data: DEFAULT_CATEGORIES.map((c) => ({ ...c, parishId: parish.id })) });

  const passwordHash = await bcrypt.hash(process.env.DEFAULT_ADMIN_PASSWORD || "Admin123!", 12);
  const admin = await prisma.user.create({
    data: {
      name: "Amministratore",
      email: adminEmail,
      passwordHash,
      role: "ADMIN",
      parishId: parish.id,
      emailVerified: true,
    },
  });

  await prisma.exchangeRate.create({ data: { parishId: parish.id, rateEurToAll: 100, createdById: admin.id } });

  console.log(`Seed completato. Admin: ${adminEmail} / password: ${process.env.DEFAULT_ADMIN_PASSWORD || "Admin123!"}`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
