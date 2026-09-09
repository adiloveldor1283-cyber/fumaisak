#!/bin/bash
set -e

# Portni aniqlash (Railway bergan PORT yoki default 8000)
PORT="${PORT:-8000}"

echo ">>> Applying database migrations..."
python manage.py migrate --noinput

echo ">>> Collecting static files..."
python manage.py collectstatic --noinput

echo ">>> Starting Gunicorn on port $PORT..."
exec gunicorn DjangoProject.wsgi:application --bind "0.0.0.0:$PORT" --workers 2 --timeout 120
