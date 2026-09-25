"""ChambeApp backend — application factory."""

import os

from flask import Flask
from flask_smorest import Api

from app.extensions import db, migrate, jwt, cache, bcrypt, socketio, cors
from app.routes.auth import blp as auth_blp
from app.routes.users import blp as users_blp
from app.routes.solicitudes import blp as solicitudes_blp
from app.routes.contracts import blp as contracts_blp
from app.routes.chambas import blp as chambas_blp
from app.routes.maranas import blp as maranas_blp
from app.routes.anuncios import blp as anuncios_blp
from app.routes.notifications import blp as notifications_blp
from app.routes.payments import blp as payments_blp
from app.routes.ai import blp as ai_blp
from app.routes.chat import blp as chat_blp
from app.routes.chat_socket import register_chat_socketio
from app.routes.admin import blp as admin_blp
from app.routes.tickets import blp as tickets_blp
from app.routes.superadmin import blp as superadmin_blp
from app.routes.ofertas import blp as ofertas_blp
from app.routes.oferta_socket import register_ofertas_socketio
from app.routes.notification_socket import register_notification_socketio
from app.routes.legal import blp as legal_blp
from app.routes.kyc import blp as kyc_blp
from app.routes.subscriptions import blp as subscriptions_blp
from app.routes.wallet import blp as wallet_blp
from app.routes.prices import blp as prices_blp
from app.routes.auth_password import blp as auth_password_blp
from app.routes.disputes import blp as disputes_blp
from app.routes.email_verification import blp as email_verification_blp
from app.routes.otp import blp as otp_blp
from app.routes.payment_methods import blp as payment_methods_blp
from app.routes.habilidades import blp as habilidades_blp
from app.routes.providers import blp as providers_blp
from app.routes.onboarding import blp as onboarding_blp
from app.routes.portfolio import blp as portfolio_blp
from app.routes.ai_metrics import blp as ai_metrics_blp
from app.routes.negocios import blp as negocios_blp
from app.routes.merchant import blp as merchant_blp
from app.routes.trust import blp as trust_blp
from app.routes.user_preferences import blp as user_preferences_blp
from app.routes.two_factor import blp as two_factor_blp
from app.routes.regions import blp as regions_blp
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
    # message_queue: Redis permite emitir desde procesos externos (Celery).
    # En TestingConfig es None para no requerir Redis en los tests.
    socketio.init_app(
        app,
        cors_allowed_origins="*",
        async_mode="threading",
        message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"),
    )

    # API + blueprints (Flask-Smorest)
    api = Api(app)
    api.register_blueprint(auth_blp, url_prefix="/api/v1/auth")
    api.register_blueprint(users_blp, url_prefix="/api/v1/users")
    api.register_blueprint(solicitudes_blp, url_prefix="/api/v1/solicitudes")
    api.register_blueprint(contracts_blp, url_prefix="/api/v1/contracts")
    api.register_blueprint(chambas_blp, url_prefix="/api/v1/chambas")
    api.register_blueprint(maranas_blp, url_prefix="/api/v1/maranas")
    api.register_blueprint(anuncios_blp, url_prefix="/api/v1/anuncios")
    api.register_blueprint(notifications_blp, url_prefix="/api/v1/notifications")
    api.register_blueprint(payments_blp, url_prefix="/api/v1/payments")
    api.register_blueprint(ai_blp, url_prefix="/api/v1/ai")
    api.register_blueprint(chat_blp, url_prefix="/api/v1/chat")
    api.register_blueprint(admin_blp, url_prefix="/api/v1/admin")
    api.register_blueprint(tickets_blp, url_prefix="/api/v1/tickets")
    api.register_blueprint(superadmin_blp, url_prefix="/api/v1/superadmin")
    api.register_blueprint(ofertas_blp, url_prefix="/api/v1")
    api.register_blueprint(legal_blp, url_prefix="/api/v1/legal")
    api.register_blueprint(kyc_blp, url_prefix="/api/v1/kyc")
    api.register_blueprint(subscriptions_blp, url_prefix="/api/v1/subscriptions")
    api.register_blueprint(wallet_blp, url_prefix="/api/v1/wallet")
    api.register_blueprint(payment_methods_blp, url_prefix="/api/v1/metodos-pago")
    api.register_blueprint(habilidades_blp, url_prefix="/api/v1")
    api.register_blueprint(prices_blp, url_prefix="/api/v1/prices")
    api.register_blueprint(auth_password_blp, url_prefix="/api/v1/auth")
    api.register_blueprint(disputes_blp, url_prefix="/api/v1")
    api.register_blueprint(email_verification_blp, url_prefix="/api/v1/auth")
    api.register_blueprint(otp_blp, url_prefix="/api/v1/auth")
    api.register_blueprint(providers_blp, url_prefix="/api/v1/providers")
    api.register_blueprint(onboarding_blp, url_prefix="/api/v1/onboarding")
    api.register_blueprint(portfolio_blp, url_prefix="/api/v1/portfolio")
    api.register_blueprint(ai_metrics_blp, url_prefix="/api/v1/ai")
    api.register_blueprint(negocios_blp, url_prefix="/api/v1/negocios")
    api.register_blueprint(merchant_blp, url_prefix="/api/v1/merchant")
    api.register_blueprint(trust_blp, url_prefix="/api/v1/trust")
    api.register_blueprint(user_preferences_blp, url_prefix="/api/v1/users")
    api.register_blueprint(two_factor_blp, url_prefix="/api/v1/auth")
    api.register_blueprint(regions_blp, url_prefix="/api/v1/regions")

    # Handlers SocketIO (después de init_app)
    register_chat_socketio(socketio)
    register_ofertas_socketio(socketio)
    register_notification_socketio(socketio)

    # Cron job: limpiar monedas vencidas cada 24 horas
    def _setup_scheduler():
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from app.services.wallet import limpiar_monedas_vencidas

            scheduler = BackgroundScheduler()
            scheduler.add_job(
                func=limpiar_monedas_vencidas,
                trigger="interval",
                hours=24,
                id="limpiar_monedas_vencidas",
            )
            scheduler.start()
        except ImportError:
            pass  # APScheduler no instalado, saltar cron

    with app.app_context():
        _setup_scheduler()

        # Catálogo KYC alineado con el código: inserta faltantes y PODA
        # obsoletos (p. ej. "validacion_pago") sin necesidad de re-seed.
        # No corre en TESTING (los tests siembran su propio catálogo).
        if not app.config.get("TESTING"):
            try:
                from app.data.seed_kyc import sync_kyc_catalog
                sync_kyc_catalog()
            except Exception:
                pass

            # División regional: asegura las regiones base de Colombia.
            try:
                from app.data.seed_regions import sync_regions
                sync_regions()
            except Exception:
                pass

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
