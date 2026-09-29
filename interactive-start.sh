#!/bin/sh
set -eu
if [ "${RAPTORGATE_INTERACTIVE_DEMO:-}" != 1 ] || [ "${RAPTORGATE_PUBLIC_PREVIEW:-}" = 1 ] || [ -n "${DATABASE_URL:-}" ]; then
  echo 'Isolated SQLite interactive-demo mode required' >&2
  exit 1
fi
python src/manage.py migrate --noinput
python src/manage.py seed_interactive
exec gunicorn portal.wsgi:application --chdir src --bind "0.0.0.0:${PORT:-10000}" --workers 1 --access-logfile -
