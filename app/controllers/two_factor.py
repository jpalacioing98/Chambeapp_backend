"""Autenticación en dos pasos (2FA) — perfil unificado y login.

Métodos: SMS, app autenticadora (TOTP) y códigos de recuperación.

Endpoints:
  GET  /api/v1/auth/2fa                  → estado + métodos disponibles (JWT).
  POST /api/v1/auth/2fa/sms/send         → envía un código SMS (JWT).
  POST /api/v1/auth/2fa/setup/totp       → genera secreto + QR (JWT).
  POST /api/v1/auth/2fa/enable           → activa un método verificando código.
  POST /api/v1/auth/2fa/disable          → desactiva (password + código).
  POST /api/v1/auth/2fa/recovery-codes   → regenera códigos (password + código).
  POST /api/v1/auth/2fa/verify           → completa el login (público).
  POST /api/v1/auth/2fa/sms/resend       → reenvía SMS del login (público).
"""

from datetime import datetime, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import (
    jwt_required,
    get_jwt_identity,
    create_access_token,
    create_refresh_token,
)
from marshmallow import Schema, fields, validate

from app.extensions import db
from app.models.user import User
from app.rate_limit import check_login_rate_limit

blp = Blueprint("two_factor", __name__, description="Autenticación en dos pasos")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TwoFactorStatusSchema(Schema):
    enabled = fields.Boolean()
    method = fields.String()
    available_methods = fields.List(fields.String())
    has_phone = fields.Boolean()
    has_totp = fields.Boolean()
    recovery_codes_remaining = fields.Integer()


class TwoFactorVerifySchema(Schema):
    email = fields.Email(required=True)
    code = fields.String(required=True, validate=validate.Length(min=6, max=16))


class EnableSchema(Schema):
    method = fields.String(
        required=True, validate=validate.OneOf(["sms", "totp"])
    )
    code = fields.String(required=True, validate=validate.Length(min=6, max=16))


class PasswordCodeSchema(Schema):
    password = fields.String(required=True, validate=validate.Length(min=1))
    code = fields.String(required=True, validate=validate.Length(min=6, max=16))


class TotpSetupSchema(Schema):
    secret = fields.String()
    otpauth_uri = fields.String()
    qr_svg = fields.String(allow_none=True)


class EnableResultSchema(Schema):
    enabled = fields.Boolean()
    method = fields.String()
    recovery_codes = fields.List(fields.String())


class RecoveryCodesSchema(Schema):
    recovery_codes = fields.List(fields.String())


class SmsSendSchema(Schema):
    sent = fields.Boolean()
    expires_in = fields.Integer(allow_none=True)
    masked_phone = fields.String(allow_none=True)
    retry_after = fields.Integer(allow_none=True)
    dev_code = fields.String(allow_none=True)


class ResendSchema(Schema):
    email = fields.Email(required=True)


class MessageSchema(Schema):
    message = fields.String()


def _current_user() -> User:
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        abort(404, message="Usuario no encontrado.")
    return user


def _qr_de_error(result: bool | str) -> None:
    if result is True:
        return
    if result == "expired":
        abort(400, message="El código expiró. Solicita uno nuevo.")
    if result == "too_many":
        abort(429, message="Demasiados intentos. Solicita un código nuevo.")
    if result == "no_challenge":
        abort(
            400,
            message="No hay un código vigente. Solicita un código SMS primero.",
        )
    abort(400, message="Código incorrecto. Verifica e inténtalo de nuevo.")


# ---------------------------------------------------------------------------
# Estado y configuración
# ---------------------------------------------------------------------------

@blp.route("/2fa")
class TwoFactor(MethodView):
    @jwt_required()
    @blp.response(200, TwoFactorStatusSchema)
    def get(self):
        """Estado actual y métodos disponibles para el usuario."""
        from app.services.two_factor import count_recovery_codes

        user = _current_user()
        return {
            "enabled": user.two_factor_enabled,
            "method": user.two_factor_method or "sms",
            "available_methods": ["sms", "totp"],
            "has_phone": bool(user.telefono),
            "has_totp": bool(user.two_factor_secret),
            "recovery_codes_remaining": count_recovery_codes(user),
        }


@blp.route("/2fa/sms/send")
class TwoFactorSmsSend(MethodView):
    @jwt_required()
    @blp.response(200, SmsSendSchema)
    def post(self):
        """Envía un código SMS para activar/verificar el método SMS."""
        from app.services.two_factor import resend_sms_challenge

        user = _current_user()
        if not user.telefono:
            abort(
                400,
                message=(
                    "Agrega un número de celular en Datos de cuenta antes de "
                    "activar la verificación por SMS."
                ),
            )
        return resend_sms_challenge(user)


@blp.route("/2fa/setup/totp")
class TwoFactorTotpSetup(MethodView):
    @jwt_required()
    @blp.response(200, TotpSetupSchema)
    def post(self):
        """Genera un secreto TOTP pendiente + QR para la app autenticadora."""
        from app.services.two_factor import (
            encrypt_secret,
            generate_totp_secret,
            qr_svg,
            totp_uri,
        )

        user = _current_user()
        secret = generate_totp_secret()
        user.two_factor_pending_secret = encrypt_secret(secret)
        db.session.commit()

        uri = totp_uri(user, secret)
        return {
            "secret": secret,
            "otpauth_uri": uri,
            "qr_svg": qr_svg(uri),
        }


@blp.route("/2fa/enable")
class TwoFactorEnable(MethodView):
    @jwt_required()
    @blp.arguments(EnableSchema)
    @blp.response(200, EnableResultSchema)
    def post(self, data):
        """Activa SMS o TOTP tras verificar un código del método elegido."""
        from app.services.two_factor import (
            clear_challenge,
            decrypt_secret,
            encrypt_secret,
            generate_recovery_codes,
            verify_code_for_method,
        )

        user = _current_user()
        method = data["method"]
        code = data["code"].strip()

        if method == "sms":
            if not user.telefono:
                abort(
                    400,
                    message="Agrega un celular antes de activar 2FA por SMS.",
                )
            if not verify_code_for_method(user, "sms", code):
                abort(400, message="Código SMS incorrecto o expirado.")
            user.two_factor_method = "sms"
            user.two_factor_secret = None
            user.two_factor_pending_secret = None
        else:
            if not (user.two_factor_pending_secret or user.two_factor_secret):
                abort(
                    400,
                    message=(
                        "Primero configura la app autenticadora "
                        "(POST /auth/2fa/setup/totp)."
                    ),
                )
            if not verify_code_for_method(user, "totp", code):
                abort(400, message="Código de la app autenticadora incorrecto.")

            secret = decrypt_secret(
                user.two_factor_pending_secret or user.two_factor_secret
            )
            user.two_factor_secret = encrypt_secret(secret or "")
            user.two_factor_pending_secret = None
            user.two_factor_method = "totp"

        user.two_factor_enabled = True
        user.two_factor_confirmed_at = datetime.now(timezone.utc)
        recovery_codes = generate_recovery_codes(user)
        clear_challenge(user.id)
        db.session.commit()

        return {
            "enabled": True,
            "method": user.two_factor_method,
            "recovery_codes": recovery_codes,
        }


@blp.route("/2fa/disable")
class TwoFactorDisable(MethodView):
    @jwt_required()
    @blp.arguments(PasswordCodeSchema)
    @blp.response(200, TwoFactorStatusSchema)
    def post(self, data):
        """Desactiva 2FA: exige contraseña + código vigente o de recuperación."""
        from app.services.two_factor import (
            clear_challenge,
            verify_second_factor,
        )

        user = _current_user()
        if not user.check_password(data["password"]):
            abort(401, message="Contraseña incorrecta.")

        result = verify_second_factor(user, data["code"])
        if result is not True:
            _qr_de_error(result)

        user.two_factor_enabled = False
        user.two_factor_method = "sms"
        user.two_factor_secret = None
        user.two_factor_pending_secret = None
        user.two_factor_confirmed_at = None
        from app.models.two_factor import TwoFactorRecoveryCode

        TwoFactorRecoveryCode.query.filter_by(user_id=user.id).delete()
        clear_challenge(user.id)
        db.session.commit()

        return {
            "enabled": False,
            "method": user.two_factor_method or "sms",
            "available_methods": ["sms", "totp"],
            "has_phone": bool(user.telefono),
            "has_totp": False,
            "recovery_codes_remaining": 0,
        }


@blp.route("/2fa/recovery-codes")
class TwoFactorRecoveryCodes(MethodView):
    @jwt_required()
    @blp.arguments(PasswordCodeSchema)
    @blp.response(200, RecoveryCodesSchema)
    def post(self, data):
        """Regenera los códigos de recuperación (password + código 2FA)."""
        from app.services.two_factor import (
            generate_recovery_codes,
            verify_second_factor,
        )

        user = _current_user()
        if not user.check_password(data["password"]):
            abort(401, message="Contraseña incorrecta.")
        if not user.two_factor_enabled:
            abort(400, message="La verificación en dos pasos no está activa.")

        result = verify_second_factor(user, data["code"])
        if result is not True:
            _qr_de_error(result)

        codes = generate_recovery_codes(user)
        db.session.commit()
        return {"recovery_codes": codes}


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@blp.route("/2fa/verify")
class TwoFactorVerify(MethodView):
    @blp.arguments(TwoFactorVerifySchema)
    def post(self, data):
        """Valida el segundo factor del login y emite los tokens."""
        from app.services.two_factor import verify_second_factor

        if not check_login_rate_limit():
            abort(429, message="Demasiados intentos. Intenta más tarde.")

        user = User.query.filter_by(email=data["email"]).first()
        if user is None:
            abort(401, message="Credenciales inválidas.")
        if not user.activo or user.status != "active":
            abort(403, message="Cuenta suspendida o inactiva.")
        if not user.two_factor_enabled:
            abort(400, message="La verificación en dos pasos no está activa.")

        result = verify_second_factor(user, data["code"])
        if result is not True:
            _qr_de_error(result)

        access = create_access_token(
            identity=str(user.id),
            additional_claims={
                "role": user.rol.value,
                "role_v": user.role_version,
            },
        )
        refresh = create_refresh_token(
            identity=str(user.id),
            additional_claims={"role_v": user.role_version},
        )
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()

        return {"access_token": access, "refresh_token": refresh}


@blp.route("/2fa/sms/resend")
class TwoFactorSmsResend(MethodView):
    @blp.arguments(ResendSchema)
    @blp.response(200, SmsSendSchema)
    def post(self, data):
        """Reenvía el código SMS del login (cooldown de 60 s)."""
        from app.services.two_factor import resend_sms_challenge

        if not check_login_rate_limit():
            abort(429, message="Demasiados intentos. Intenta más tarde.")

        user = User.query.filter_by(email=data["email"]).first()
        if (
            user is None
            or not user.two_factor_enabled
            or (user.two_factor_method or "sms") != "sms"
        ):
            # No revelar si el correo existe / tiene 2FA por SMS.
            return {"sent": True, "retry_after": 0}

        return resend_sms_challenge(user)
