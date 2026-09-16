"""Shared Flask extensions (initialized in factory)."""

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


try:
    from celery import Celery as _RealCelery
except ImportError:
    _RealCelery = None

celery = _RealCelery("chambeapp") if _RealCelery else _CeleryStub()
