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

    # OpenAPI / Flask-Smorest
    API_TITLE = "ChambeApp API"
    API_VERSION = "v1"
    OPENAPI_VERSION = "3.0.3"
    PROPAGATE_EXCEPTIONS = True


class DevelopmentConfig(Config):
    DEBUG = True


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
    PROPAGATE_EXCEPTIONS = False


# ---------------- RF-08: Pasarela de Pagos ----------------
# Comisión de plataforma (T&C §7.1). 12% sobre el monto del servicio.
COMMISSION_RATE = 0.12
# Umbral de exención: montos < 50000 COP no generan comisión (T&C §7.1).
COMMISSION_EXEMPT_THRESHOLD = 50000
# Plazo de auto-liberación de escrow sin quejas (RF-08.6): 48h.
ESCROW_AUTO_RELEASE_HOURS = 48
