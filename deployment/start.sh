#!/bin/sh
set -eu
python -m flask --app run.py upgrade-production-db
python preflight.py
exec gunicorn --bind 0.0.0.0:3001 --workers 2 --threads 4 --timeout 60 --access-logfile - --error-logfile - run:app
