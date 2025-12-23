# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Build stage: resolve and install dependencies into a self-contained venv.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime stage: the venv and the source, nothing else. No compiler, no pip
# cache, no build tooling.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=library_system.settings

RUN groupadd --system app && useradd --system --gid app --home-dir /app app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . /app

# Bake the admin/DRF static assets into the image so the runtime container
# never needs write access to do it. Settings require a SECRET_KEY when DEBUG
# is off; this one is used for the duration of this RUN and nothing else.
RUN SECRET_KEY=collectstatic-only \
    DB_ENGINE=django.db.backends.sqlite3 \
    python manage.py collectstatic --noinput \
    && chown -R app:app /app/staticfiles

USER app

EXPOSE 8000

# Uses the app's own /health/ endpoint, which checks database connectivity.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "library_system.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
