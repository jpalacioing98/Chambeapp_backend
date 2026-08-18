"""ChambeApp backend — application factory."""

from flask import Flask
from flask_smorest import Api

from app.extensions import db, migrate, jwt, cache, bcrypt, socketio, cors
from app.routes.auth import blp as auth_blp
from app.routes.users import blp as users_blp
from app.routes.services import blp as services_blp
from app.routes.orders import blp as orders_blp
from app.routes.notifications import blp as notifications_blp
from app.routes.payments import blp as payments_blp
from app.routes.ai import blp as ai_blp
from app.routes.chat import blp as chat_blp
from app.routes.chat_socket import register_chat_socketio
from app.routes.admin import blp as admin_blp
from app.routes.tickets import blp as tickets_blp
from app.routes.superadmin import blp as superadmin_blp
from app.models.user import User


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
    # CORS para /api/* (auth por Bearer header, sin cookies → sin credenciales).
    cors.init_app(
        app,
        resources={r"/api/*": {
            "origins": "*",
            "allow_headers": ["Content-Type", "Authorization"],
            "methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        }},
    )
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
    api.register_blueprint(admin_blp, url_prefix="/api/v1/admin")
    api.register_blueprint(tickets_blp, url_prefix="/api/v1/tickets")
    api.register_blueprint(superadmin_blp, url_prefix="/api/v1/superadmin")

    # Handlers SocketIO (después de init_app)
    register_chat_socketio(socketio)

    # Carga el usuario desde el identity del JWT (current_user / lookup).
    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        try:
            uid = int(identity)
        except (ValueError, TypeError):
            return None
        return User.query.get(uid)

    return app
