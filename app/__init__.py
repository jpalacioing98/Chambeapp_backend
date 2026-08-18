"""ChambeApp backend — application factory."""

from flask import Flask
from flask_smorest import Api

from app.extensions import db, migrate, jwt, cache, bcrypt
from app.routes.auth import blp as auth_blp
from app.routes.users import blp as users_blp
from app.routes.services import blp as services_blp


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

    # API + blueprints (Flask-Smorest)
    api = Api(app)
    api.register_blueprint(auth_blp, url_prefix="/api/v1/auth")
    api.register_blueprint(users_blp, url_prefix="/api/v1/users")
    api.register_blueprint(services_blp, url_prefix="/api/v1/services")

    return app
