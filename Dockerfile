FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts
COPY public ./public
COPY assets ./assets
COPY data/guide ./data/guide
# Cloud Run injects $PORT
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --timeout-keep-alive 75
