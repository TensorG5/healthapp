# ---- Стадия 1: ставим зависимости ----
FROM python:3.12.7-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Стадия 2: финальный образ ----
FROM python:3.12.7-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Непривилегированный пользователь с фиксированным UID (нужен для прав на /var/log/healthapp на хосте)
RUN groupadd --system --gid 10001 healthapp \
 && useradd  --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin healthapp

COPY --from=builder /install /usr/local
WORKDIR /srv
COPY app ./app

USER healthapp
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["python", "-m", "app.healthcheck"]

CMD ["python", "-m", "app.main"]
