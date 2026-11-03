FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run lint && npm run typecheck && npm run build

FROM python:3.11-slim AS runtime

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV PORT=8080

CMD ["sh", "-c", "exec uvicorn src.api:app --host 0.0.0.0 --port ${PORT}"]
