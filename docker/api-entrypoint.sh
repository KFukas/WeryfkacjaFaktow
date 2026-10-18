#!/bin/sh
set -e
# Migracje i dane przykładowe (idempotentne), potem API.
alembic upgrade head
python -m backend.seed
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
