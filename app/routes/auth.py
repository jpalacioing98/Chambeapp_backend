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
)

blp = Blueprint("auth", __name__, description="Autenticación y registro")

# Versión vigente de T&C (clickwrap Ley 527/1999)
TYC_VERSION = "1.0"


@blp.route("/register")
class Register(MethodView):
    @blp.arguments(RegisterSchema)
    @blp.response(201, MeSchema)
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

        return user


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

        access = create_access_token(identity=str(user.id))
        refresh = create_refresh_token(identity=str(user.id))
        return {"access_token": access, "refresh_token": refresh}


@blp.route("/refresh")
class Refresh(MethodView):
    @jwt_required(refresh=True)
    def post(self):
        """Renueva access_token usando refresh_token."""
        user_id = get_jwt_identity()
        access = create_access_token(identity=user_id)
        return {"access_token": access}


@blp.route("/me")
class Me(MethodView):
    @jwt_required()
    @blp.response(200, MeSchema)
    def get(self):
        """Retorna el perfil del usuario autenticado."""
        user_id = get_jwt_identity()
        return db.get_or_404(User, int(user_id))
