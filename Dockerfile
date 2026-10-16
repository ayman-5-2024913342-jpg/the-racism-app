FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 APP_ENV=production
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-prod.txt ./
RUN pip install --no-cache-dir -r requirements-prod.txt
COPY . .
RUN useradd --create-home app && chown -R app /srv
USER app
EXPOSE 8000
# Migrations run first; the app refuses to start in production without a strong APP_SECRET_KEY.
CMD ["sh", "-c", "alembic upgrade head && gunicorn app.main:app -c gunicorn.conf.py"]
