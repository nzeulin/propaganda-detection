FROM node:24-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY app/ ./app/
COPY config/ ./config/
COPY data/ ./data/
COPY --from=frontend /build/dist ./frontend/dist/
RUN useradd --create-home --uid 1000 veritas && mkdir -p /app/.local-data && chown -R veritas:veritas /app
USER veritas
ENV PYTHONUNBUFFERED=1 FRONTEND_DIST=/app/frontend/dist DATABASE_PATH=/app/.local-data/investigations.db
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
