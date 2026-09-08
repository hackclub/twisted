#!/bin/bash

uv run manage.py migrate --noinput
uv run gunicorn -w 3 mysite.wsgi:application \
    --bind 0.0.0.0:8000 \
    --threads=4 \
    --worker-class=gthread \
    --log-level info \
    --capture-output
