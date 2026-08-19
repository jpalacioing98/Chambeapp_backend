"""SocketIO handlers para ofertas (negociación pds/solicitante).

Al conectar, el cliente se une a la sala `user:<user_id>` derivada del JWT
del socket, de modo que los emits dirigidos (`oferta:nueva`,
`oferta:actualizada`) lleguen solo al usuario correspondiente.
"""

from flask_socketio import join_room, emit
from flask_jwt_extended import decode_token

from app.extensions import socketio


def register_ofertas_socketio(sio) -> None:
    """Registra el handler de conexión que une al usuario a su sala."""

    @sio.on("connect")
    def on_connect(auth=None):
        user_id = None
        try:
            if isinstance(auth, dict):
                token = auth.get("token") or auth.get("access_token")
                if token:
                    decoded = decode_token(token)
                    user_id = int(decoded["sub"])
        except Exception:
            user_id = None

        if user_id is not None:
            join_room(f"user:{user_id}")
            emit("status", {"msg": f"Conectado a sala user:{user_id}"})
