#!/bin/sh
# Role switch so one image serves multiple Railway services.
#   ROLE=api    (default) -> FastAPI on $PORT
#   ROLE=worker           -> Celery worker with embedded beat scheduler
#   ROLE=beat             -> standalone Celery beat (only if you split it out)
set -e

case "${ROLE:-api}" in
  worker)
    exec celery -A app.workers.celery_app worker --beat --loglevel=info
    ;;
  beat)
    exec celery -A app.workers.celery_app beat --loglevel=info
    ;;
  *)
    exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8003}"
    ;;
esac
