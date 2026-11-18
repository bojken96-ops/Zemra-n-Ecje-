# Operations

## Environment variables
Every variable is documented inline in [`.env.example`](../.env.example). Secrets go only in `.env`.
API keys are never hardcoded, and the stored Gemini key and OAuth tokens are encrypted with
`TOKEN_ENCRYPTION_KEY` (Fernet). In production mode (compose) the backend refuses to start without
`TOKEN_ENCRYPTION_KEY` and `CAPTURE_AGENT_TOKEN`.

## Runtime settings (Dashboard → Settings)
Stored in `application_settings` and validated server-side: detection weights and thresholds (defaults:
chat 30 %, audio 25 %, visual 20 %, emoji 15 %, unique chatters 10 %), clip window (45 s / 35 s), min/max
length, merge gap, sentence snapping, vertical framing, fps, loudness; subtitle style, font, colours,
position; capture backend, audio mode, encoder, segment length, concurrency, alerts; storage limits and
retention; publishing (auto-publish, per-platform toggles, templates, delay, privacy, attempts); AI provider and language.

## Security model
* Single local owner account (argon2 password hash, strength check). Server-side sessions in Postgres
  (hashed tokens), HttpOnly SameSite=strict cookie, CSRF token required on every mutating request.
* All published ports bind to `127.0.0.1`. Postgres and Redis have no published ports. The API also rejects
  clients outside `ALLOWED_CLIENT_NETWORKS`.
* Per-IP rate limits (API and login) are kept in Redis.
* Capture-control endpoints (`/api/agent/*`) require `CAPTURE_AGENT_TOKEN` (constant-time compare). Segment
  paths are validated to stay inside `recordings/<stream>/<session>/`.
* Media is served only to the logged-in owner, with path-traversal protection and range requests.
* OAuth uses single-use 15-minute `state` values (plus PKCE for Google). Tokens are encrypted at rest.
* Audit log (`audit_logs`) covers logins, settings changes, creator authorisation, stream/capture/clip/publish actions.
* Structured JSON logs go to stdout (`docker compose logs -f backend worker`).

## Storage management
* `storage/recordings` holds raw segments (deleted after `recording_retention_hours` unless *protected*).
  Segments overlapping a clip are protected. `storage/clips/<id>/` holds `source.mp4` (horizontal cut, kept
  for regeneration), `clip.mp4`, `.ass`/`.srt`. Thumbnails and subtitles live in their own folders.
* The hourly cleanup removes expired temporary files and unprotected expired segments. It never touches
  segments of active captures or open candidates, temp folders of clips being processed, or any clip.
  Clips are deleted only by you, and not while processing or publishing.
* You get low-disk and over-allocation alerts as notifications. The agent stops capturing below
  `min_free_disk_gb`.

## Database
Alembic migrations live in `backend/migrations` and are applied automatically when the backend starts
(`docker compose run --rm backend migrate` to run manually). Schema highlights: unique video per stream,
one active capture per stream, unique `(clip, account)` publishing job, unique chat message per stream,
CHECK constraints on status columns.

Backup: `docker compose exec postgres pg_dump -U streampulse streampulse > backup.sql`.

## Development and tests
```bash
uv venv -p 3.12 .venv && uv pip install -p .venv -r requirements.txt -r requirements-dev.txt
# needs local PostgreSQL (db streampulse_test, user/pass streampulse), Redis and FFmpeg
cd backend && ../.venv/bin/pytest            # 74 tests
cd frontend && npm ci && npm run typecheck && npm run build
```
Dev servers: `uvicorn app.main:app --reload` (from backend/, `PYTHONPATH=.:..`), `celery -A
app.workers.celery_app:celery worker -Q default,media,publishing`, `celery ... beat`, `npm run dev`.
