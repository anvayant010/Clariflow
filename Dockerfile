# Clariflow: one container serves the API and the built web app.
# Stage 1 builds the React app; stage 2 runs the Python server.

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY fixtures ./fixtures
COPY evaluation ./evaluation
COPY deploy ./deploy
COPY --from=web /web/dist ./frontend/dist

# Recordings, the database and generated voice live on the mounted disk (a volume at /data) when the host has one.
# TRUSTED_PROXY_HOPS=1: one proxy (the host's) sits in front, so the visitor's address is read from X-Forwarded-For.
ENV DATA_DIR=/data \
    DATABASE_URL=sqlite:////data/clariflow.db \
    TRUSTED_PROXY_HOPS=1
RUN mkdir -p /data

EXPOSE 8000
# The host sets PORT; 8000 is the fallback. Secrets (the Gnani key) come from the host's settings, never from the image.
CMD ["sh", "-c", "uvicorn backend.app.main:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]
