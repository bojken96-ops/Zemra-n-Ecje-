# Cassa Parrocchiale

Web app responsive/PWA per la gestione della contabilità di una parrocchia: entrate, uscite, preventivi, bilanci mensili, utenti con ruoli, audit log, multi-lingua (Italiano / English / Shqip) e multi-valuta (EUR / ALL - Lek Albanese).

Il progetto è diviso in due parti:

- **`server/`** — API REST (Node.js, Express, TypeScript, Prisma + PostgreSQL, JWT, Google OAuth, invio email, export PDF/Excel)
- **`client/`** — Frontend PWA (React, TypeScript, Vite, Tailwind CSS, react-i18next, Recharts)

## Avvio rapido (sviluppo locale)

### 0. Database

Il progetto usa PostgreSQL sia in sviluppo che in produzione. Il modo più semplice per avviarlo in locale è Docker:

```bash
cd server
docker compose up -d       # avvia Postgres su localhost:5432 (vedi docker-compose.yml)
```

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

## Deploy su Render

Il repository include un `render.yaml` (Blueprint) che crea automaticamente:

- un database PostgreSQL gestito (`cassa-parrocchiale-db`)
- il servizio backend (`cassa-parrocchiale-api`) — esegue build, migrazioni e seed ad ogni deploy
- il sito statico frontend (`cassa-parrocchiale-web`)

Passaggi:

1. Crea un account su [render.com](https://render.com) (serve una carta per alcuni piani, ma i piani `free` inclusi nel Blueprint non la richiedono).
2. Nella dashboard Render: **New > Blueprint**, collega questo repository e la branch da pubblicare.
3. Render legge `render.yaml` e propone i tre servizi sopra. Durante la creazione ti chiederà di valorizzare le variabili contrassegnate come "da impostare": in particolare **imposta `DEFAULT_ADMIN_EMAIL` e `DEFAULT_ADMIN_PASSWORD` con una password robusta** (altrimenti il seed userà le credenziali di default, non sicure per un ambiente pubblico).
4. Conferma: Render costruisce ed avvia i tre servizi. Al termine, il frontend sarà raggiungibile su `https://cassa-parrocchiale-web.onrender.com` (o sul nome che hai scelto).
5. (Opzionale) Aggiungi in seguito, dalla dashboard del servizio backend, `GOOGLE_CLIENT_ID` per il login con Google e `SMTP_HOST`/`SMTP_USER`/`SMTP_PASS` per l'invio reale delle email (senza SMTP configurato, i link di conferma/reset vengono solo scritti nei log del servizio).

**Limiti noti dei piani gratuiti**, da tenere presenti per un uso reale:

- Il servizio backend gratuito va in stand-by dopo ~15 minuti di inattività: la prima richiesta dopo una pausa impiega qualche decina di secondi a "risvegliarlo".
- Il database Postgres gratuito ha una durata limitata nel tempo (verifica le condizioni attuali su render.com); per una parrocchia che userà l'app stabilmente conviene passare a un piano a pagamento.
- Il filesystem del piano gratuito **non è persistente**: gli allegati caricati nella sezione Entrate/Uscite vengono salvati su disco locale al servizio e **andranno persi ad ogni nuovo deploy o riavvio**. Per allegati persistenti serve un disco persistente Render (piano a pagamento) oppure migrare lo storage a un servizio esterno (es. S3-compatibile) — non ancora implementato in questa versione.

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

- Il database (sviluppo e produzione) è PostgreSQL. In locale si avvia con `docker compose up -d` (vedi `server/docker-compose.yml`); in produzione su Render viene fornito automaticamente dal Blueprint (`render.yaml`).
- Le email (conferma account, reset password, inviti) vengono inviate via SMTP se configurato in `server/.env` (o nelle variabili d'ambiente del servizio backend su Render); in assenza di configurazione SMTP vengono stampate nei log (modalità sviluppo).
- Gli allegati vengono salvati su disco (`server/uploads/`) e serviti solo tramite endpoint autenticato (nessun accesso diretto ai file). Su Render piano gratuito questo storage è effimero (vedi sezione "Deploy su Render" sopra).
