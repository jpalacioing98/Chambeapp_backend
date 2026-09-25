"""Autenticación de Socket.IO mediante JWT.

Los handlers de Socket.IO no usan los decoradores HTTP de
flask-jwt-extended; en su lugar se decodifica el JWT del handshake
(`auth`) o del payload del evento. Regla crítica: NUNCA confiar en
`user_id` enviado por el cliente — la identidad siempre se deriva del token.
"""

from flask_jwt_extended import decode_token


def decode_socket_user_id(token=None, auth=None, data=None) -> int | None:
    """Devuelve el `sub` (user_id) de un JWT válido en socket, o None.

    Fuentes del token, en orden: `token` directo, handshake `auth` (dict con
    `token`/`access_token`) y payload del evento `data`. Devuelve None si no
    hay token o si el token es inválido/expirado.
    """
    if not token:
        if isinstance(auth, dict):
            token = auth.get("token") or auth.get("access_token")
        if not token and isinstance(data, dict):
            token = data.get("token") or data.get("access_token")
    if not token:
        return None
    try:
        decoded = decode_token(token)
        return int(decoded["sub"])
    except Exception:
        return None