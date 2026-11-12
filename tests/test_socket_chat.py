"""pytest - Socket.IO: el evento `join` unificado.

Flask-SocketIO guarda UN handler por evento: si otro módulo registra
`join`, pisa el del chat y la sala de la conversación nunca se une
(mensajes en vivo rotos). Estos tests fijan el comportamiento único:

· `join` une al usuario a `user:<id>` y a `conversation_<id>`.
· Un participante NO puede unirse a una conversación ajena.
· Un mensaje enviado por HTTP llega por socket a la contraparte.
· `join_feed` solo permite las salas públicas `mapa` y `anuncios`.
· Los pines de negocio llegan únicamente a quien está en `mapa`.
· `safe_emit` devuelve False (sin lanzar) cuando el broker falla.
"""

import pytest

from app import create_app
from app.extensions import db, socketio
from app.services.realtime import get_emit_stats, safe_emit


@pytest.fixture
def app():
    app = create_app("app.config.TestingConfig")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _register(client, email, rol="solicitante"):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secret123",
            "rol": rol,
            "acepto_tyc": True,
            "ip": "127.0.0.1",
        },
    )
    assert resp.status_code in (200, 201), resp.get_json()


def _login(client, email):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "secret123"},
    ).get_json()
    return resp["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _nombres(received):
    return [m["name"] for m in received]


def test_join_une_usuario_y_conversacion(app, client):
    _register(client, "a@example.com")
    _register(client, "b@example.com")
    token_a = _login(client, "a@example.com")
    token_b = _login(client, "b@example.com")

    conv = client.post(
        "/api/v1/chat/conversations",
        headers=_auth(token_a),
        json={"otro_usuario_id": 2},
    ).get_json()

    socket = socketio.test_client(app, auth={"token": token_a})
    socket.get_received()  # evento de conexión

    socket.emit("join", {"conversation_id": conv["id"], "token": token_a})
    recibidos = socket.get_received()
    nombres = _nombres(recibidos)

    assert "joined" in nombres
    assert "status" in nombres
    assert any(
        f"conversación {conv['id']}" in str(m["args"]) for m in recibidos if m["name"] == "status"
    )
    socket.disconnect()


def test_join_no_autorizado_a_conversacion_ajena(app, client):
    _register(client, "a@example.com")
    _register(client, "b@example.com")
    _register(client, "c@example.com")
    token_a = _login(client, "a@example.com")
    token_c = _login(client, "c@example.com")

    conv = client.post(
        "/api/v1/chat/conversations",
        headers=_auth(token_a),
        json={"otro_usuario_id": 2},
    ).get_json()

    socket = socketio.test_client(app, auth={"token": token_c})
    socket.get_received()
    socket.emit("join", {"conversation_id": conv["id"], "token": token_c})
    recibidos = socket.get_received()

    assert "error" in _nombres(recibidos)
    socket.disconnect()


def test_mensaje_http_llega_por_socket(app, client):
    _register(client, "a@example.com")
    _register(client, "b@example.com")
    token_a = _login(client, "a@example.com")
    token_b = _login(client, "b@example.com")

    conv = client.post(
        "/api/v1/chat/conversations",
        headers=_auth(token_a),
        json={"otro_usuario_id": 2},
    ).get_json()

    socket = socketio.test_client(app, auth={"token": token_a})
    socket.get_received()
    socket.emit("join", {"conversation_id": conv["id"], "token": token_a})
    socket.get_received()

    resp = client.post(
        f"/api/v1/chat/conversations/{conv['id']}/messages",
        headers=_auth(token_b),
        json={"contenido": "hola en vivo"},
    )
    assert resp.status_code == 201

    recibidos = socket.get_received()
    mensajes = [m for m in recibidos if m["name"] == "message"]
    assert mensajes, _nombres(recibidos)
    args = mensajes[-1]["args"]
    payload = args[0] if isinstance(args, (list, tuple)) else args
    assert payload["contenido"] == "hola en vivo"
    socket.disconnect()


def test_mensaje_por_socket_llega_a_la_contraparte(app, client):
    """El chat en vivo real: A envía por socket y B lo recibe sin HTTP.

    Cubre el handler `message` (persistencia + difusión a la sala del hilo
    y a la sala personal del peer), que era el camino roto en producción.
    """
    _register(client, "a@example.com")
    _register(client, "b@example.com")
    token_a = _login(client, "a@example.com")
    token_b = _login(client, "b@example.com")

    conv = client.post(
        "/api/v1/chat/conversations",
        headers=_auth(token_a),
        json={"otro_usuario_id": 2},
    ).get_json()

    socket_a = socketio.test_client(app, auth={"token": token_a})
    socket_b = socketio.test_client(app, auth={"token": token_b})
    socket_a.get_received()
    socket_b.get_received()

    # B abre el hilo; A envía por socket.
    socket_b.emit("join", {"conversation_id": conv["id"]})
    socket_b.get_received()
    socket_a.emit(
        "message",
        {"conversation_id": conv["id"], "contenido": "hola por socket"},
    )

    recibidos = socket_b.get_received()
    mensajes = [m for m in recibidos if m["name"] == "message"]
    assert mensajes, _nombres(recibidos)
    args = mensajes[-1]["args"]
    payload = args[0] if isinstance(args, (list, tuple)) else args
    assert payload["contenido"] == "hola por socket"
    assert payload["sender_id"] == 1
    assert payload["conversation_id"] == conv["id"]

    socket_a.disconnect()
    socket_b.disconnect()


# ── Salas de difusión (mapa / anuncios) ─────────────────────────────────


def test_join_feed_mapa_recibe_pines(app, client):
    """Quien entra a `mapa` recibe los pines; el resto no paga el tráfico."""
    _register(client, "mapa@example.com")
    token = _login(client, "mapa@example.com")

    socket = socketio.test_client(app, auth={"token": token})
    socket.get_received()

    socket.emit("join_feed", {"room": "mapa"})
    assert "joined" in _nombres(socket.get_received())

    assert safe_emit("negocio:pin", {"id": 42, "nombre": "Panadería"}, room="mapa")

    recibidos = socket.get_received()
    pines = [m for m in recibidos if m["name"] == "negocio:pin"]
    assert pines, _nombres(recibidos)
    args = pines[-1]["args"]
    payload = args[0] if isinstance(args, (list, tuple)) else args
    assert payload["id"] == 42
    socket.disconnect()


def test_feed_no_llega_a_quien_no_se_suscribio(app, client):
    """El pin ya no se difunde a todos los conectados."""
    _register(client, "fuera@example.com")
    token = _login(client, "fuera@example.com")

    socket = socketio.test_client(app, auth={"token": token})
    socket.get_received()

    safe_emit("negocio:pin", {"id": 7}, room="mapa")

    assert "negocio:pin" not in _nombres(socket.get_received())
    socket.disconnect()


def test_join_feed_rechaza_salas_privadas(app, client):
    """Un cliente no puede suscribirse a la sala personal de otro usuario."""
    _register(client, "intruso@example.com")
    token = _login(client, "intruso@example.com")

    socket = socketio.test_client(app, auth={"token": token})
    socket.get_received()

    socket.emit("join_feed", {"room": "user:1"})
    recibidos = socket.get_received()
    assert "error" in _nombres(recibidos)
    socket.disconnect()


# ── safe_emit: nunca lanza y reporta el fallo ───────────────────────────


def test_safe_emit_devuelve_true_en_emision_normal(app):
    assert safe_emit("negocio:pin", {"id": 1}, room="mapa") is True


def test_safe_emit_devuelve_false_si_el_broker_falla(app, monkeypatch):
    """Un Redis caído no debe tumbar la petición HTTP que ya persistió."""

    def boom(*_args, **_kwargs):
        raise RuntimeError("redis caído")

    antes = get_emit_stats()["failed"]
    monkeypatch.setattr(socketio, "emit", boom)

    assert safe_emit("negocio:pin", {"id": 1}, room="mapa") is False
    assert get_emit_stats()["failed"] == antes + 1
