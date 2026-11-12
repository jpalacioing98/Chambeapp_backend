"""pytest suite — Web Push (VAPID), suscripciones y preferencias (RF-10)."""

import pytest

from app import create_app
from app.extensions import db
from app.models.merchant import MerchantPreference
from app.models.notification import Notification
from app.models.push import PushSubscription
from app.models.user import User


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


def _register(client, email, rol="pds"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secret123",
            "rol": rol,
            "acepto_tyc": True,
            "ip": "127.0.0.1",
        },
    )


def _headers(client, email):
    token = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "secret123"},
    ).get_json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _user(client, email, rol="pds"):
    _register(client, email, rol=rol)
    return _headers(client, email)


def _uid(app, email):
    with app.app_context():
        return User.query.filter_by(email=email).first().id


# ---------------- Endpoints push ----------------
def test_vapid_key_503_sin_configurar(client):
    resp = client.get("/api/v1/push/vapid-public-key")
    assert resp.status_code == 503


def test_vapid_key_configurada(client, app):
    from app.models.config import SystemConfig

    with app.app_context():
        SystemConfig.set_value("vapid_public_key", "BEl62iUYgUivxIkv69yViEuiBIa")
    resp = client.get("/api/v1/push/vapid-public-key")
    assert resp.status_code == 200
    assert resp.get_json()["public_key"].startswith("BEl62")


def test_subscribe_upsert_y_delete(client, app):
    headers = _user(client, "pds@example.com")
    uid = _uid(app, "pds@example.com")
    payload = {
        "endpoint": "https://push.example.com/abc123",
        "keys": {"p256dh": "pkey", "auth": "asecret"},
        "user_agent": "pytest",
    }

    r1 = client.post("/api/v1/push/subscribe", json=payload, headers=headers)
    assert r1.status_code == 200
    assert r1.get_json()["ok"] is True

    # Segundo POST del mismo navegador: no duplica, actualiza.
    payload["keys"]["p256dh"] = "pkey2"
    r2 = client.post("/api/v1/push/subscribe", json=payload, headers=headers)
    assert r2.status_code == 200
    assert r2.get_json()["id"] == r1.get_json()["id"]

    with app.app_context():
        subs = PushSubscription.query.filter_by(user_id=uid).all()
        assert len(subs) == 1
        assert subs[0].p256dh == "pkey2"

    r3 = client.delete(
        "/api/v1/push/subscribe",
        json={"endpoint": payload["endpoint"]},
        headers=headers,
    )
    assert r3.status_code == 200
    assert r3.get_json()["deleted"] == 1


def test_subscribe_acepta_expiration_time_y_campos_extra(client, app):
    """El navegador envía `expirationTime` y `toJSON()` puede añadir más."""
    headers = _user(client, "pds@example.com")
    resp = client.post(
        "/api/v1/push/subscribe",
        json={
            "endpoint": "https://push.example.com/con-expira",
            "expirationTime": None,
            "keys": {"p256dh": "pkey", "auth": "asecret"},
            "extra_del_navegador": "ignorar",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["ok"] is True


def test_subscribe_requiere_auth(client):
    r = client.post(
        "/api/v1/push/subscribe",
        json={
            "endpoint": "https://push.example.com/x",
            "keys": {"p256dh": "p", "auth": "a"},
        },
    )
    assert r.status_code == 401


def test_mismo_endpoint_se_reasigna_a_otro_usuario(client, app):
    h1 = _user(client, "uno@example.com")
    h2 = _user(client, "dos@example.com")
    uid2 = _uid(app, "dos@example.com")
    payload = {
        "endpoint": "https://push.example.com/compartido",
        "keys": {"p256dh": "p", "auth": "a"},
    }
    assert client.post("/api/v1/push/subscribe", json=payload, headers=h1).status_code == 200
    assert client.post("/api/v1/push/subscribe", json=payload, headers=h2).status_code == 200
    with app.app_context():
        subs = PushSubscription.query.all()
        assert len(subs) == 1
        assert subs[0].user_id == uid2


# ---------------- Preferencias ----------------
def test_crear_notificacion_respeta_preferencia(client, app):
    from app.controllers.notifications import crear_notificacion

    _user(client, "pds@example.com")
    uid = _uid(app, "pds@example.com")
    with app.app_context():
        db.session.add(
            MerchantPreference(user_id=uid, notif_nueva_solicitud=False)
        )
        db.session.commit()

        assert crear_notificacion(uid, "nueva_solicitud", "hola") is None
        db.session.commit()
        assert Notification.query.filter_by(user_id=uid).count() == 0


def test_preferencias_default_permiten(client, app):
    from app.controllers.notifications import crear_notificacion

    _user(client, "pds@example.com")
    uid = _uid(app, "pds@example.com")
    with app.app_context():
        notif = crear_notificacion(uid, "nueva_solicitud", "hola")
        db.session.commit()
        assert notif is not None
        assert Notification.query.filter_by(user_id=uid).count() == 1


def test_mapa_tipos_preferencia():
    from app.services.preferencias import preferencia_para_tipo

    assert preferencia_para_tipo("nueva_solicitud") == "notif_nueva_solicitud"
    assert preferencia_para_tipo("oferta_nueva") == "notif_nueva_solicitud"
    assert preferencia_para_tipo("negocio:rating") == "notif_nueva_resena"
    assert preferencia_para_tipo("kyc_aprobado") == "notif_estado_kyc"
    assert preferencia_para_tipo("contrato_confirmado") == "notif_pago_recibido"
    assert preferencia_para_tipo("formalizacion") is None


# ---------------- Dispatch push ----------------
def test_push_no_se_envia_si_esta_deshabilitado(client, app, monkeypatch):
    import app.services.push as push_service
    from app.controllers.notifications import crear_notificacion

    _user(client, "pds@example.com")
    uid = _uid(app, "pds@example.com")
    enviados = []
    monkeypatch.setattr(
        push_service,
        "enviar_push",
        lambda sub, payload: enviados.append(payload) or True,
    )

    with app.app_context():
        db.session.add(
            MerchantPreference(user_id=uid, push_enabled=False)
        )
        db.session.add(
            PushSubscription(
                user_id=uid,
                endpoint="https://push.example.com/1",
                p256dh="p",
                auth="a",
            )
        )
        db.session.commit()
        crear_notificacion(uid, "nueva_solicitud", "hola")
        db.session.commit()
        assert enviados == []


def test_push_test_envia_a_las_suscripciones(client, app, monkeypatch):
    import app.services.push as push_service

    headers = _user(client, "pds@example.com")
    uid = _uid(app, "pds@example.com")
    enviados = []
    monkeypatch.setattr(
        push_service,
        "enviar_push",
        lambda sub, payload: enviados.append(payload) or True,
    )
    with app.app_context():
        db.session.add(
            PushSubscription(
                user_id=uid,
                endpoint="https://push.example.com/prueba",
                p256dh="p",
                auth="a",
            )
        )
        db.session.commit()

    r = client.post("/api/v1/push/test", headers=headers)
    assert r.status_code == 200, r.get_json()
    assert r.get_json() == {"sent": 1, "subscriptions": 1}
    assert enviados[0]["data"]["url"] == "/notificaciones"


def test_push_test_sin_suscripciones(client):
    headers = _user(client, "pds@example.com")
    r = client.post("/api/v1/push/test", headers=headers)
    assert r.status_code == 200
    assert r.get_json() == {"sent": 0, "subscriptions": 0}


def test_push_se_envia_si_esta_habilitado(client, app, monkeypatch):
    import app.services.push as push_service
    from app.controllers.notifications import crear_notificacion

    _user(client, "pds@example.com")
    uid = _uid(app, "pds@example.com")
    enviados = []
    monkeypatch.setattr(
        push_service,
        "enviar_push",
        lambda sub, payload: enviados.append(payload) or True,
    )

    with app.app_context():
        db.session.add(
            PushSubscription(
                user_id=uid,
                endpoint="https://push.example.com/2",
                p256dh="p",
                auth="a",
            )
        )
        db.session.commit()
        crear_notificacion(uid, "nueva_solicitud", "hay trabajo cerca")
        db.session.commit()
        assert len(enviados) == 1
        assert enviados[0]["body"] == "hay trabajo cerca"
        assert enviados[0]["data"]["url"] == "/notificaciones"
