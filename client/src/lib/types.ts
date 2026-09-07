export type Role = "ADMIN" | "TESORIERE" | "VIEWER";
export type TxType = "ENTRATA" | "USCITA";
export type Currency = "ALL" | "EUR";
export type Method = "CASH" | "BANK";
export type BudgetStatus = "BOZZA" | "APPROVATO" | "IN_CORSO" | "COMPLETATO" | "ANNULLATO";

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  parishId: string;
  emailVerified: boolean;
  active?: boolean;
  createdAt?: string;
}

export interface Parish {
  id: string;
  name: string;
  address: string | null;
  taxId: string | null;
  currency: Currency;
}

export interface Category {
  id: string;
  parishId: string;
  type: TxType;
  name: string;
  translationKey: string | null;
  active: boolean;
}

export interface Attachment {
  id: string;
  filename: string;
  mimeType: string;
  size: number;
  createdAt: string;
}

export interface Transaction {
  id: string;
  type: TxType;
  date: string;
  description: string;
  categoryId: string;
  category: { id: string; name: string; translationKey: string | null };
  amount: number;
  currency: Currency;
  method: Method;
  budgetId: string | null;
  budget: { id: string; number: string; title: string } | null;
  notes: string | null;
  exchangeRateUsed: number | null;
  createdById: string;
  createdBy: { id: string; name: string; email: string };
  createdAt: string;
  updatedAt: string;
  attachments: Attachment[];
}

export interface Budget {
  id: string;
  number: string;
  date: string;
  title: string;
  description: string | null;
  categoryId: string;
  category: { id: string; name: string; translationKey: string | null };
  plannedAmount: number;
  currency: Currency;
  plannedMethod: Method;
  status: BudgetStatus;
  createdBy: { id: string; name: string };
  createdAt: string;
  spentAmount: number;
  remainingAmount: number;
  transactionCount: number;
  transactions?: { id: string; date: string; description: string; amount: number; currency: Currency; method: Method }[];
}

export interface Balances {
  cashALL: number;
  cashEUR: number;
  bankALL: number;
  bankEUR: number;
}

export interface DashboardData {
  balances: Balances;
  exchangeRate: number;
  saldoTotaleEur: number;
  saldoCashEur: number;
  saldoBankEur: number;
  entrateDelMese: { ALL: number; EUR: number; eur: number };
  usciteDelMese: { ALL: number; EUR: number; eur: number };
  risultatoDelMeseEur: number;
  preventiviAperti: (Budget & { category: { name: string; translationKey: string | null } })[];
  ultimiMovimenti: Transaction[];
  trend: { month: string; entrate: number; uscite: number; saldo: number }[];
  expenseDistribution: { category: string; translationKey: string | null; amount: number }[];
}

export interface AuditLogEntry {
  id: string;
  action: "CREATE" | "UPDATE" | "DELETE";
  entityType: string;
  entityId: string;
  oldValue: any;
  newValue: any;
  createdAt: string;
  user: { name: string; email: string };
}
