"""Auth blueprint: registro, login, refresh, me (RF-01, RF-17)."""

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)

from app.extensions import db
from app.models.user import User, Profile, LegalAcceptance, RolUsuario
from app.schemas.auth import (
    RegisterSchema,
    LoginSchema,
    MeSchema,
    RegisterResponseSchema,
)

blp = Blueprint("auth", __name__, description="Autenticación y registro")

# Versión vigente de T&C (clickwrap Ley 527/1999)
TYC_VERSION = "1.0"


@blp.route("/register")
class Register(MethodView):
    @blp.arguments(RegisterSchema)
    @blp.response(201, RegisterResponseSchema)
    def post(self, data):
        """RF-01 + RF-17: registro requiere acepto_tyc=true."""
        if not data["acepto_tyc"]:
            abort(400, message="Debe aceptar los Términos y Condiciones (RF-17).")

        if User.query.filter_by(email=data["email"]).first():
            abort(409, message="El email ya está registrado.")

        user = User(
            email=data["email"],
            rol=RolUsuario(data["rol"]),
            acepto_tyc=True,
        )
        user.set_password(data["password"])
        profile = Profile(user=user)

        db.session.add(user)
        db.session.add(profile)
        db.session.flush()  # obtener user.id para LegalAcceptance

        legal = LegalAcceptance(
            user_id=user.id,
            version_tyc=TYC_VERSION,
            ip=data.get("ip"),
        )
        db.session.add(legal)
        db.session.commit()

        access = create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.rol.value, "role_v": user.role_version},
        )
        refresh = create_refresh_token(identity=str(user.id))
        from app.schemas.auth import ProfileSchema

        result = {
            "id": user.id,
            "email": user.email,
            "rol": user.rol.value,
            "edad_verificada": user.edad_verificada,
            "acepto_tyc": user.acepto_tyc,
            "fecha_registro": user.fecha_registro,
            "activo": user.activo,
            "profile": ProfileSchema().dump(user.profile),
            "access_token": access,
            "refresh_token": refresh,
        }
        return result


@blp.route("/login")
class Login(MethodView):
    @blp.arguments(LoginSchema)
    def post(self, data):
        """Autentica y retorna access + refresh token (JWT 8h)."""
        user = User.query.filter_by(email=data["email"]).first()
        if not user or not user.check_password(data["password"]):
            abort(401, message="Credenciales inválidas.")
        if not user.activo:
            abort(403, message="Usuario inactivo.")
        if user.status != "active":
            abort(403, message="Cuenta suspendida o bloqueada. Contacta soporte.")

        access = create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.rol.value, "role_v": user.role_version},
        )
        refresh = create_refresh_token(identity=str(user.id))

        # Auditoría de último login.
        from datetime import datetime, timezone

        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        return {"access_token": access, "refresh_token": refresh}


@blp.route("/refresh")
class Refresh(MethodView):
    @jwt_required(refresh=True)
    def post(self):
        """Renueva access_token usando refresh_token (conserva claims de rol)."""
        user_id = get_jwt_identity()
        user = db.session.get(User, int(user_id))
        if user is None:
            abort(401, message="Usuario no encontrado.")
        access = create_access_token(
            identity=str(user.id),
            additional_claims={"role": user.rol.value, "role_v": user.role_version},
        )
        return {"access_token": access}


@blp.route("/me")
class Me(MethodView):
    @jwt_required()
    @blp.response(200, MeSchema)
    def get(self):
        """Retorna el perfil del usuario autenticado."""
        user_id = get_jwt_identity()
        return db.get_or_404(User, int(user_id))
