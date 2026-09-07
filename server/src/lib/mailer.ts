import nodemailer from "nodemailer";

const hasSmtp = !!process.env.SMTP_HOST;

const transporter = hasSmtp
  ? nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port: Number(process.env.SMTP_PORT || 587),
      secure: Number(process.env.SMTP_PORT) === 465,
      auth: process.env.SMTP_USER
        ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS }
        : undefined,
    })
  : nodemailer.createTransport({ jsonTransport: true });

const FROM = process.env.SMTP_FROM || "Cassa Parrocchiale <no-reply@cassaparrocchiale.local>";

export async function sendMail(to: string, subject: string, html: string) {
  const info = await transporter.sendMail({ from: FROM, to, subject, html });
  if (!hasSmtp) {
    // Dev mode: no real SMTP configured, log the email content (and the link inside) to console.
    console.log(`\n[MAIL:DEV] To: ${to} | Subject: ${subject}\n${html}\n`);
  }
  return info;
}

export function verifyEmailTemplate(link: string, name: string) {
  return `<p>Ciao ${name},</p><p>Conferma il tuo indirizzo email cliccando il link seguente:</p><p><a href="${link}">${link}</a></p><p>Il link scade tra 24 ore.</p>`;
}

export function resetPasswordTemplate(link: string, name: string) {
  return `<p>Ciao ${name},</p><p>Hai richiesto il reset della password. Clicca il link seguente per impostarne una nuova:</p><p><a href="${link}">${link}</a></p><p>Se non hai richiesto tu il reset, ignora questa email. Il link scade tra 1 ora.</p>`;
}
