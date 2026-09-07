import { TFunction } from "i18next";
import { Currency } from "./types";

export function formatAmount(amount: number, currency: Currency): string {
  const formatted = new Intl.NumberFormat("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(
    amount
  );
  return currency === "EUR" ? `€ ${formatted}` : `${formatted} L`;
}

export function formatEur(amount: number): string {
  return new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(amount);
}

export function formatDate(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return new Intl.DateTimeFormat("it-IT", { day: "2-digit", month: "2-digit", year: "numeric" }).format(d);
}

export function formatDateTime(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return new Intl.DateTimeFormat("it-IT", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(d);
}

export function categoryLabel(t: TFunction, category: { name: string; translationKey?: string | null }): string {
  if (category.translationKey) {
    const translated = t(`categoriesData.${category.translationKey}`);
    if (translated && translated !== `categoriesData.${category.translationKey}`) return translated;
  }
  return category.name;
}

export function toInputDate(date: string | Date): string {
  const d = typeof date === "string" ? new Date(date) : date;
  return d.toISOString().slice(0, 10);
}
