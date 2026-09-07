# Cassa Parrocchiale

Web app responsive/PWA per la gestione della contabilità di una parrocchia: entrate, uscite, preventivi, bilanci mensili, utenti con ruoli, audit log, multi-lingua (Italiano / English / Shqip) e multi-valuta (EUR / ALL - Lek Albanese).

Il progetto è diviso in due parti:

- **`server/`** — API REST (Node.js, Express, TypeScript, Prisma + SQLite, JWT, Google OAuth, invio email, export PDF/Excel)
- **`client/`** — Frontend PWA (React, TypeScript, Vite, Tailwind CSS, react-i18next, Recharts)

## Avvio rapido

### 1. Backend

```bash
cd server
cp .env.example .env      # personalizza segreti/SMTP/Google se necessario
npm install
npx prisma migrate deploy
npm run seed               # crea la parrocchia demo + utente amministratore
npm run dev                 # http://localhost:4000
```

Credenziali admin create dal seed (modificabili in `.env`):

- Email: `admin@parrocchia.local`
- Password: `Admin123!`

### 2. Frontend

```bash
cd client
cp .env.example .env
npm install
npm run dev                 # http://localhost:5173 (proxy verso /api -> :4000)
```

Apri `http://localhost:5173`. L'interfaccia parte in Italiano; la lingua si cambia dalla topbar o da Impostazioni.

## Funzionalità principali

- **Autenticazione**: email/password, Google Sign-In (richiede `GOOGLE_CLIENT_ID`), registrazione, conferma email, password dimenticata/reset, logout, refresh token.
- **Ruoli**: ADMIN (accesso completo), TESORIERE (entrate/uscite/preventivi/bilanci), VIEWER (sola lettura).
- **Dashboard**: saldo totale/cassa/banca, saldi per valuta, entrate/uscite/risultato del mese, preventivi aperti, ultimi movimenti, grafici (entrate vs uscite, andamento saldo, distribuzione spese).
- **Entrate / Uscite / Movimenti**: creazione con categoria, valuta, metodo (cassa/banca), allegato, note; ricerca, filtri, ordinamento, modifica, eliminazione con conferma (soft delete + audit log).
- **Preventivi**: numero automatico, stato (bozza/approvato/in corso/completato/annullato), calcolo automatico di speso/rimanente dalle uscite collegate.
- **Bilancio mensile**: saldo iniziale/finale separato per Cassa/Banca e per valuta (ALL/EUR, mai mescolate), totali, spese/entrate per categoria, confronto tra mesi, esportazione PDF ed Excel.
- **Cambio valuta**: tasso configurabile (1 EUR = X ALL) salvato in ogni movimento al momento della registrazione, così i dati storici non cambiano se il tasso viene aggiornato in seguito.
- **Categorie**: modificabili dall'amministratore, categorie iniziali precaricate per entrate e uscite.
- **Utenti**: gestione ruoli e stato, invito via email con link per impostare la password.
- **Audit log**: traccia creazioni/modifiche/eliminazioni di movimenti, preventivi, categorie e utenti con valore precedente/nuovo.
- **Isolamento dati**: ogni dato è associato alla parrocchia dell'utente autenticato; nessun accesso incrociato tra parrocchie diverse.

## Note tecniche

- Il database di sviluppo usa SQLite (`server/prisma/dev.db`) per semplicità; in produzione basta cambiare `DATABASE_URL` in `server/.env` a una stringa `postgresql://...` (lo schema Prisma è già compatibile).
- Le email (conferma account, reset password, inviti) vengono inviate via SMTP se configurato in `server/.env`; in assenza di configurazione SMTP vengono stampate in console (modalità sviluppo).
- Gli allegati vengono salvati in `server/uploads/` e serviti solo tramite endpoint autenticato (nessun accesso diretto ai file).
