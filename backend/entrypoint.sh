#!/bin/sh
# Role switch so one image serves multiple Railway services.
#   ROLE=api    (default) -> FastAPI on $PORT
#   ROLE=worker           -> Celery worker with embedded beat scheduler
#   ROLE=beat             -> standalone Celery beat (only if you split it out)
set -e

case "${ROLE:-api}" in
  worker)
    # Concurrency is pinned LOW on purpose: Celery's prefork pool otherwise spawns one process
    # per host CPU core (Railway exposes ~40+), forking the whole app into many GB of idle RAM.
    # Override with WORKER_CONCURRENCY if you ever need more parallelism.
    exec celery -A app.workers.celery_app worker --beat --loglevel=info \
      --concurrency="${WORKER_CONCURRENCY:-2}" --max-tasks-per-child=200
    ;;
  beat)
    exec celery -A app.workers.celery_app beat --loglevel=info
    ;;
  *)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8003}"
    ;;
esac
