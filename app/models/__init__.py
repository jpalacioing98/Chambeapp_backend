"""Model package exports."""
from app.models.user import (
    RolUsuario,
    User,
    Profile,
    LegalAcceptance,
    Verification,
)
from app.models.solicitud import Solicitud, Rating, EstadoSolicitud
from app.models.oferta import Oferta, EstadoOferta
from app.models.contract import Contract, EstadoContrato, Dispute
from app.models.chamba import Chamba, EstadoChamba
from app.models.marana import Marana, EstadoMarana, MaranaOferta, EstadoMaranaOferta
from app.models.anuncio import (
    AnuncioLaboral,
    EstadoAnuncio,
    AnuncioPostulacion,
    EstadoPostulacionAnuncio,
)
from app.models.ticket import Ticket
from app.models.notification import Notification
from app.models.chat import Conversation, Message
from app.models.audit import AuditLog, write_audit
from app.models.config import SystemConfig, FeatureFlag
from app.models.kyc import DocumentoRequerido, DocumentoUsuario
from app.models.subscription import Suscripcion
from app.models.wallet import Wallet, Transaction, TipoTransaccion, TipoMoneda, Coin
from app.models.modalidad import Modalidad, Milestone, TipoModalidad, EstadoHito
from app.models.badges import BadgeType
from app.models.negocio import (
    Negocio, NegocioHorario, NegocioRating, NegocioReporte,
    TipoNegocio, EstadoNegocio, EstadoReporte, TipoReporte,
)
# Modelos que antes solo se importaban desde su submódulo: sin registrarlos
# aquí, db.create_all() NO creaba sus tablas (p.ej. notification_cascades)
# y el esquema quedaba incompleto tras un seed desde cero.
from app.models.cascade import NotificationCascade
from app.models.habilidad import Habilidad, HabilidadNivel, CertificacionTecnica
from app.models.merchant import MerchantPreference, MerchantPaymentMethod
from app.models.payment import Payment, EstadoPago
from app.models.payment_method import MetodoPago
from app.models.portfolio import PortfolioItem
from app.models.recommendation_log import RecommendationLog
from app.models.region import Region
from app.models.trust import TrustScore

__all__ = [
    "RolUsuario",
    "User",
    "Profile",
    "LegalAcceptance",
    "Verification",
    "Solicitud",
    "Rating",
    "EstadoSolicitud",
    "Oferta",
    "EstadoOferta",
    "Contract",
    "EstadoContrato",
    "Dispute",
    "Chamba",
    "EstadoChamba",
    "Marana",
    "EstadoMarana",
    "MaranaOferta",
    "EstadoMaranaOferta",
    "AnuncioLaboral",
    "EstadoAnuncio",
    "AnuncioPostulacion",
    "EstadoPostulacionAnuncio",
    "Ticket",
    "Notification",
    "Conversation",
    "Message",
    "AuditLog",
    "write_audit",
    "SystemConfig",
    "FeatureFlag",
    "DocumentoRequerido",
    "DocumentoUsuario",
    "Suscripcion",
    # Nuevos modelos RF-25/26/27/29
    "Wallet",
    "Transaction",
    "TipoTransaccion",
    "TipoMoneda",
    "Coin",
    "Modalidad",
    "Milestone",
    "TipoModalidad",
    "EstadoHito",
    "BadgeType",
    # Módulo Negocios
    "Negocio",
    "NegocioHorario",
    "NegocioRating",
    "NegocioReporte",
    "TipoNegocio",
    "EstadoNegocio",
    "EstadoReporte",
    "TipoReporte",
    # Modelos registrados para que create_all() cubra todo el esquema
    "NotificationCascade",
    "Habilidad",
    "HabilidadNivel",
    "CertificacionTecnica",
    "MerchantPreference",
    "MerchantPaymentMethod",
    "Payment",
    "EstadoPago",
    "MetodoPago",
    "PortfolioItem",
    "RecommendationLog",
    "Region",
    "TrustScore",
]
