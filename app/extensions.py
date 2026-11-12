"""Shared Flask extensions (initialized in factory)."""

import os

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_jwt_extended import JWTManager
from flask_caching import Cache
from flask_bcrypt import Bcrypt
from flask_socketio import SocketIO
from flask_cors import CORS

db = SQLAlchemy()
migrate = Migrate()
jwt = JWTManager()
cache = Cache()
bcrypt = Bcrypt()
socketio = SocketIO()
cors = CORS()


class _CeleryStub:
    """Stub Celery for test/dev environments where Celery is not installed."""
    def task(self, *args, **kwargs):
        def decorator(fn):
            fn.delay = lambda *a, **kw: None
            fn.apply_async = lambda *a, **kw: None
            return fn
        return decorator

    def send_task(self, *args, **kwargs):
        return None


def _build_celery():
    """Crea la ÚNICA instancia de Celery de la aplicación.

    Antes existían dos: `app.extensions.celery` (sin broker → Celery caía a
    `amqp://guest@localhost:5672//`) y `app.tasks.celery_app` (broker Redis,
    la que realmente ejecutaba el worker). La cascada de notificaciones
    usaba la primera, así que `send_phase_task.delay()` fallaba con
    `Connection refused` y la task ni siquiera estaba registrada en el
    worker (`celery -A app.tasks.celery_app inspect registered` no la
    listaba).

    Ahora todas las tasks usan esta instancia. `include` es lo que hace que
    el worker importe y registre las tasks de otros módulos (cascada).
    """
    try:
        from celery import Celery as _RealCelery
    except ImportError:  # pragma: no cover — Celery es dependencia dura
        return _CeleryStub()

    broker = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    app = _RealCelery(
        "chambeapp",
        broker=broker,
        backend=broker,
        include=[
            "app.tasks",
            "app.services.cascade",
        ],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="America/Bogota",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=300,      # 5 minutos máx por task
        task_soft_time_limit=240,  # 4 minutos soft limit
        worker_prefetch_multiplier=1,
        worker_max_tasks_per_child=100,
        broker_connection_retry_on_startup=True,
    )
    return app


celery = _build_celery()
