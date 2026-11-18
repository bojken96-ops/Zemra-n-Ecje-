#!/bin/sh
set -e
cd /app/backend
case "$1" in
  api)
    alembic upgrade head
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
    ;;
  worker)
    exec celery -A app.workers.celery_app:celery worker --loglevel="${LOG_LEVEL:-INFO}" \
      -Q default,media,publishing --concurrency="${WORKER_CONCURRENCY:-2}"
    ;;
  beat)
    exec celery -A app.workers.celery_app:celery beat --loglevel="${LOG_LEVEL:-INFO}" \
      --schedule /tmp/celerybeat-schedule
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
