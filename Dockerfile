# ChambeApp Backend - All-in-One Dockerfile
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    postgresql \
    postgresql-client \
    postgresql-contrib \
    postgresql-17-postgis-3 \
    redis-server \
    supervisor \
    curl \
    gnupg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN PG_VERSION=$(ls /usr/lib/postgresql/ | head -1) && \
    echo "PostgreSQL version: $PG_VERSION"

COPY --from=coollabsio/minio:latest /usr/bin/minio /usr/local/bin/minio
COPY --from=coollabsio/minio:latest /usr/bin/mc /usr/local/bin/mc

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN PG_VERSION=$(ls /usr/lib/postgresql/ | head -1) && \
    mkdir -p /var/lib/postgresql/$PG_VERSION/main && \
    chown -R postgres:postgres /var/lib/postgresql

RUN mkdir -p /var/run/postgresql /var/run/redis /var/log/supervisor /var/log/postgresql /data/minio \
    && chown -R postgres:postgres /var/run/postgresql /var/log/postgresql \
    && chown -R redis:redis /var/run/redis \
    && useradd -r -s /bin/bash -d /home/minio-user -m minio-user 2>/dev/null || true \
    && chown -R minio-user:minio-user /data/minio

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

COPY docker-entrypoint-allinone.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint-allinone.sh

COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

EXPOSE 5000 5432 6379 9000 9001

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/v1/auth/health')" || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint-allinone.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]