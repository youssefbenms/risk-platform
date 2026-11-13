# Image de l'application (API FastAPI + jobs ETL/IA) — une seule image, deux usages.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Utilisateur non-root : un attaquant qui compromet l'API n'est pas root dans le conteneur
RUN useradd --create-home --uid 1000 app
WORKDIR /app

# Dépendances d'abord : cette couche reste en cache tant que requirements.txt ne change pas
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src
# Le modèle entraîné est embarqué s'il existe (artefact versionné avec l'image)
COPY models ./models
RUN mkdir -p /app/data/raw && chown -R app:app /app
USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=4)"

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
