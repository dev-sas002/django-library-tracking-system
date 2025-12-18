#!/bin/sh
# Container entrypoint.
#
# The web service migrates and seeds before serving; the Celery services set
# RUN_MIGRATIONS=0 / RUN_SEED=0 so that exactly one process owns schema changes.
set -eu

if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "[entrypoint] applying migrations"
    python manage.py migrate --noinput
fi

if [ "${RUN_SEED:-1}" = "1" ]; then
    echo "[entrypoint] seeding demo data (idempotent)"
    python manage.py seed_library
fi

exec "$@"
