"""pytest suite — chat/mensajería (RF-16). Solo REST (sin WS)."""

import pytest

from app import create_app
from app.extensions import db
from app.config import TestingConfig


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


def _register(client, email, **overrides):
    payload = {
        "email": email,
        "password": "secret123",
        "rol": "pds",
        "acepto_tyc": True,
        "ip": "127.0.0.1",
    }
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def _login(client, email):
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "secret123"},
    ).get_json()
    return resp["access_token"]


def _auth(client, token):
    return {"Authorization": f"Bearer {token}"}


def _make_users(client):
    _register(client, "a@example.com")
    _register(client, "b@example.com")
    _register(client, "c@example.com")
    token_a = _login(client, "a@example.com")
    token_b = _login(client, "b@example.com")
    token_c = _login(client, "c@example.com")
    return token_a, token_b, token_c


def test_create_conversation_201(client):
    token_a, token_b, _ = _make_users(client)
    resp = client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_a),
        json={"otro_usuario_id": 2},
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["id"] is not None
    # orden normalizado: a=1, b=2
    assert data["user_a_id"] == 1
    assert data["user_b_id"] == 2


def test_create_conversation_existing_200(client):
    token_a, token_b, _ = _make_users(client)
    r1 = client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_a),
        json={"otro_usuario_id": 2},
    )
    assert r1.status_code == 201
    # B inicia con A → debe devolver la misma (200)
    r2 = client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_b),
        json={"otro_usuario_id": 1},
    )
    assert r2.status_code == 200
    assert r2.get_json()["id"] == r1.get_json()["id"]


def test_create_conversation_self_400(client):
    token_a, _, _ = _make_users(client)
    resp = client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_a),
        json={"otro_usuario_id": 1},
    )
    assert resp.status_code == 400


def test_list_conversations_with_last_message(client):
    token_a, token_b, _ = _make_users(client)
    client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_a),
        json={"otro_usuario_id": 2},
    )
    # enviar mensaje
    client.post(
        "/api/v1/chat/conversations/1/messages",
        headers=_auth(client, token_a),
        json={"contenido": "hola B"},
    )
    resp = client.get(
        "/api/v1/chat/conversations", headers=_auth(client, token_a)
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["last_message"]["contenido"] == "hola B"


def test_send_and_history(client):
    token_a, token_b, _ = _make_users(client)
    client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_a),
        json={"otro_usuario_id": 2},
    )
    r = client.post(
        "/api/v1/chat/conversations/1/messages",
        headers=_auth(client, token_a),
        json={"contenido": "mensaje 1"},
    )
    assert r.status_code == 201
    assert r.get_json()["leido"] is False

    hist = client.get(
        "/api/v1/chat/conversations/1/messages", headers=_auth(client, token_a)
    )
    assert hist.status_code == 200
    assert len(hist.get_json()) == 1
    assert hist.get_json()[0]["contenido"] == "mensaje 1"


def test_non_participant_send_403(client):
    token_a, token_b, token_c = _make_users(client)
    client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_a),
        json={"otro_usuario_id": 2},
    )
    resp = client.post(
        "/api/v1/chat/conversations/1/messages",
        headers=_auth(client, token_c),
        json={"contenido": "intruso"},
    )
    assert resp.status_code == 403


def test_non_participant_read_history_403(client):
    token_a, token_b, token_c = _make_users(client)
    client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_a),
        json={"otro_usuario_id": 2},
    )
    resp = client.get(
        "/api/v1/chat/conversations/1/messages", headers=_auth(client, token_c)
    )
    assert resp.status_code == 403


def test_mark_read(client):
    token_a, token_b, _ = _make_users(client)
    client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_a),
        json={"otro_usuario_id": 2},
    )
    client.post(
        "/api/v1/chat/conversations/1/messages",
        headers=_auth(client, token_a),
        json={"contenido": "leeme"},
    )
    # B marca como leídos
    resp = client.patch(
        "/api/v1/chat/conversations/1/messages/read", headers=_auth(client, token_b)
    )
    assert resp.status_code == 200
    assert len(resp.get_json()) == 1
    assert resp.get_json()[0]["leido"] is True

    # historial confirma leido
    hist = client.get(
        "/api/v1/chat/conversations/1/messages", headers=_auth(client, token_b)
    )
    assert hist.get_json()[0]["leido"] is True


def test_conversation_peer_perspectiva(client):
    """El peer embebido respeta la perspectiva: A ve a B y B ve a A."""
    _register(client, "a@example.com", nombre="Usuario A", username="usera")
    _register(client, "b@example.com", nombre="Usuario B", username="userb")
    token_a = _login(client, "a@example.com")
    token_b = _login(client, "b@example.com")

    client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_a),
        json={"otro_usuario_id": 2},
    )

    # A consulta → peer es B (id=2)
    conv_a = client.get(
        "/api/v1/chat/conversations", headers=_auth(client, token_a)
    ).get_json()
    assert len(conv_a) == 1
    peer_a = conv_a[0]["otro_participante"]
    assert peer_a["id"] == 2
    assert peer_a["nombre"] == "Usuario B"
    assert peer_a["username"] == "userb"
    assert "verificado" in peer_a
    assert "rol" in peer_a

    # B consulta → peer es A (id=1)
    conv_b = client.get(
        "/api/v1/chat/conversations", headers=_auth(client, token_b)
    ).get_json()
    assert len(conv_b) == 1
    peer_b = conv_b[0]["otro_participante"]
    assert peer_b["id"] == 1
    assert peer_b["nombre"] == "Usuario A"
    assert peer_b["username"] == "usera"


def test_conversation_peer_en_post(client):
    """POST /conversations también devuelve el peer embebido."""
    _register(client, "a@example.com", nombre="Usuario A")
    _register(client, "b@example.com", nombre="Usuario B")
    token_a = _login(client, "a@example.com")

    resp = client.post(
        "/api/v1/chat/conversations",
        headers=_auth(client, token_a),
        json={"otro_usuario_id": 2},
    )
    assert resp.status_code == 201
    peer = resp.get_json()["otro_participante"]
    assert peer["id"] == 2
    assert peer["nombre"] == "Usuario B"
