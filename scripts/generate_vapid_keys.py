"""Genera claves VAPID para Web Push y las guarda en SystemConfig.

Uso:
    python scripts/generate_vapid_keys.py           # crea si no existen
    python scripts/generate_vapid_keys.py --force   # rota las claves

Requiere `pywebpush` (trae `py-vapid` y `cryptography`):
    pip install pywebpush==1.14.0

Importante: si rotas las claves, los navegadores con suscripciones viejas
dejan de recibir push hasta que vuelvan a suscribirse. En producción las
claves se generan UNA vez y no se vuelven a tocar.
"""

import argparse
import base64
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01

from app import create_app
from app.models.config import SystemConfig


def generar(force: bool = False) -> None:
    app = create_app()
    with app.app_context():
        if SystemConfig.get_value("vapid_public_key") and not force:
            print("Ya existen claves VAPID. Usa --force para rotarlas.")
            return

        vapid = Vapid01()
        vapid.generate_keys()
        public_bytes = vapid.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        public_key = base64.urlsafe_b64encode(public_bytes).rstrip(b"=").decode()
        private_pem = vapid.private_pem()
        if isinstance(private_pem, bytes):
            private_pem = private_pem.decode()

        SystemConfig.set_value("vapid_public_key", public_key)
        SystemConfig.set_value("vapid_private_key", private_pem)
        print("Claves VAPID guardadas en system_configs.")
        print("Public key:", public_key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Genera claves VAPID")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rota las claves aunque ya existan (invalida suscripciones)",
    )
    args = parser.parse_args()
    generar(force=args.force)
