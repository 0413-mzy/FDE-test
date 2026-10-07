FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_API_BASE_URL=""
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 COMMERCE_STATIC_DIR=/app/static
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic.ini ./
COPY backend/migrations ./migrations
RUN pip install --no-cache-dir . && useradd --uid 10001 --create-home commerce
COPY --from=frontend /build/frontend/dist ./static
USER commerce
EXPOSE 8000
CMD ["python", "-m", "app.commerce.public_demo_start"]
