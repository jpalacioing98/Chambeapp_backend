"""Asegura que todo usuario tenga billetera (backfill idempotente).

El registro ya crea la billetera; este sync cubre usuarios anteriores a la
migración de monedas y bases creadas con `db.create_all()`.
"""

from app.extensions import db
from app.models.user import User
from app.models.wallet import Wallet, Coin


def sync_wallets() -> int:
    """Crea la billetera de los usuarios que aún no la tienen."""
    con_wallet = {uid for (uid,) in db.session.query(Wallet.user_id).all()}
    faltantes = [
        uid
        for (uid,) in db.session.query(User.id).all()
        if uid not in con_wallet
    ]
    if not faltantes:
        return 0

    for user_id in faltantes:
        saldo_monedas = (
            db.session.query(db.func.coalesce(db.func.sum(Coin.cantidad), 0))
            .filter(Coin.user_id == user_id)
            .scalar()
            or 0
        )
        db.session.add(
            Wallet(
                user_id=user_id,
                saldo=0,
                saldo_bloqueado=0,
                monedas_saldo=int(saldo_monedas),
            )
        )
    db.session.commit()
    return len(faltantes)
