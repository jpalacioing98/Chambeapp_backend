"""Configuration classes for ChambeApp backend."""

import os
from datetime import timedelta


class Config:
    """Base configuration."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret-change-me")

    # JWT: access 8h, refresh 30d (RF auth)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=8)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    # DB: PostgreSQL en prod; SQLite fallback para dev/test sin Postgres
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///chambeapp.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Cache (Redis en prod/dev; SimpleCache en test)
    CACHE_TYPE = os.environ.get("CACHE_TYPE", "RedisCache")
    CACHE_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # SocketIO message queue (Redis en prod/dev para emitir desde Celery;
    # None en test para evitar conexiones a Redis inexistente).
    SOCKETIO_MESSAGE_QUEUE = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # OpenAPI / Flask-Smorest
    API_TITLE = "ChambeApp API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    PROPAGATE_EXCEPTIONS = True

    # ---------------- RF-08: Pasarela Nequi ----------------
    # Numero Nequi de la plataforma para transferencia manual (sin pasarela externa).
    NEQUI_NUMBER = os.environ.get("NEQUI_NUMBER", "3000000000")
    NEQUI_TITULAR = os.environ.get("NEQUI_TITULAR", "ChambeApp")

    # Onurix SMS (2FA) - https://docs.onurix.com
    ONURIX_CLIENT = os.environ.get("ONURIX_CLIENT")
    ONURIX_KEY = os.environ.get("ONURIX_KEY")
    ONURIX_APP_NAME = os.environ.get("ONURIX_APP_NAME", "ChambeApp")
    # SMS_SEND_DEV=1 envía SMS reales en desarrollo (requiere credenciales Onurix)
    SMS_SEND_DEV = os.environ.get("SMS_SEND_DEV", "0") == "1"


class DevelopmentConfig(Config):
    DEBUG = True
    # PostgreSQL con PostGIS para desarrollo (dev = prod)
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        "postgresql://chambeapp:chambeapp_dev@localhost:5432/chambeapp"
    )


class ProductionConfig(Config):
    DEBUG = False
    # En producción forzar PostgreSQL vía DATABASE_URL


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "TEST_DATABASE_URL", "sqlite:///:memory:"
    )
    CACHE_TYPE = "SimpleCache"
    SOCKETIO_MESSAGE_QUEUE = None
    PROPAGATE_EXCEPTIONS = False
    
    @classmethod
    def init(cls):
        """Set testing environment variables."""
        os.environ["TESTING"] = "1"
        os.environ["FLASK_TESTING"] = "1"


# ---------------- RF-08: Pasarela de Pagos ----------------
# Comisión de plataforma (T&C §7.1). 12% sobre el monto del servicio.
COMMISSION_RATE = 0.12
# Umbral de exención: montos < 50000 COP no generan comisión (T&C §7.1).
COMMISSION_EXEMPT_THRESHOLD = 50000
# Plazo de auto-liberación de pagos pendientes sin confirmación (RF-08.6): 48h.
ESCROW_AUTO_RELEASE_HOURS = 48
