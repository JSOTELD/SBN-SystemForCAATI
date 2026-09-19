FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production
WORKDIR /srv/itam
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt && useradd --create-home app
COPY backend/app backend/app
COPY backend/run.py backend/run.py
COPY backend/preflight.py backend/preflight.py
COPY frontend frontend
COPY deployment/start.sh /srv/itam/start.sh
RUN mkdir -p /srv/itam/uploads && chown -R app:app /srv/itam && chmod +x /srv/itam/start.sh
USER app
WORKDIR /srv/itam/backend
EXPOSE 3001
CMD ["/srv/itam/start.sh"]
