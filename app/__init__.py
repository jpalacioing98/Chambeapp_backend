"""ChambeApp backend — application factory."""

from flask import Flask
from flask_smorest import Api

from app.extensions import db, migrate, jwt, cache, bcrypt, socketio
from app.routes.auth import blp as auth_blp
from app.routes.users import blp as users_blp
from app.routes.services import blp as services_blp
from app.routes.orders import blp as orders_blp
from app.routes.notifications import blp as notifications_blp
from app.routes.payments import blp as payments_blp
from app.routes.ai import blp as ai_blp
from app.routes.chat import blp as chat_blp
from app.routes.chat_socket import register_chat_socketio


def create_app(config_class: str = "app.config.DevelopmentConfig") -> Flask:
    """Application factory (AUP Implementation)."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    cache.init_app(app)
    bcrypt.init_app(app)
    # threading: compatible con test client/werkzeug; en prod usar eventlet.
    socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")

    # API + blueprints (Flask-Smorest)
    api = Api(app)
    api.register_blueprint(auth_blp, url_prefix="/api/v1/auth")
    api.register_blueprint(users_blp, url_prefix="/api/v1/users")
    api.register_blueprint(services_blp, url_prefix="/api/v1/services")
    api.register_blueprint(orders_blp, url_prefix="/api/v1/orders")
    api.register_blueprint(notifications_blp, url_prefix="/api/v1/notifications")
    api.register_blueprint(payments_blp, url_prefix="/api/v1/payments")
    api.register_blueprint(ai_blp, url_prefix="/api/v1/ai")
    api.register_blueprint(chat_blp, url_prefix="/api/v1/chat")

    # Handlers SocketIO (después de init_app)
    register_chat_socketio(socketio)

    return app
