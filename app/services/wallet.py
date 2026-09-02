"""Service layer: billetera virtual, monedas, modalidades y hitos (RF-25, RF-26, RF-27, RF-29).

Implementa la lógica de negocio para:
- Billetera virtual (depósitos, retiros, transacciones)
- Sistema de monedas (compra, uso, vencimiento)
- Modalidades de cobro (A con comisión, B sin comisión)
- Hitos de pago (creación, aprobación, rechazo)
"""

from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.wallet import Wallet, Transaction, TipoTransaccion, Coin, TipoMoneda
from app.models.modalidad import Modalidad, Milestone, TipoModalidad, EstadoHito
from app.models.contract import Contract, EstadoContrato
from app.models.solicitud import Solicitud


# --------------------------------------------------------------------------
# Billetera Virtual (RF-25)
# --------------------------------------------------------------------------

def get_or_create_wallet(user_id: int) -> Wallet:
    """Obtiene o crea la billetera de un usuario."""
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if wallet is None:
        wallet = Wallet(user_id=user_id, saldo=0, saldo_bloqueado=0)
        db.session.add(wallet)
        db.session.flush()
    return wallet


def get_wallet(user_id: int) -> Wallet:
    """Obtiene la billetera de un usuario (lanza error si no existe)."""
    wallet = Wallet.query.filter_by(user_id=user_id).first()
    if wallet is None:
        raise ValueError("El usuario no tiene billetera.")
    return wallet


def depositar(user_id: int, monto: int, pasarela: str = "nequi") -> Transaction:
    """RF-25.5: Deposita fondos en la billetera."""
    if monto < 1000:
        raise ValueError("El monto mínimo de depósito es $1,000 COP.")

    wallet = get_or_create_wallet(user_id)
    wallet.saldo += monto
    wallet.updated_at = datetime.now(timezone.utc)

    tx = Transaction(
        wallet_id=wallet.id,
        tipo=TipoTransaccion.DEPOSITO,
        monto=monto,
        descripcion=f"Depósito vía {pasarela}",
        referencia=f"DEP-{pasarela.upper()}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
    )
    db.session.add(tx)
    db.session.flush()
    return tx


def retirar(user_id: int, monto: int, cuenta_destino: str) -> Transaction:
    """RF-25.3: Retira fondos de la billetera a cuenta bancaria."""
    if monto < 10000:
        raise ValueError("El monto mínimo de retiro es $10,000 COP.")

    wallet = get_wallet(user_id)
    if wallet.saldo < monto:
        raise ValueError("Saldo insuficiente para retiro.")

    wallet.saldo -= monto
    wallet.saldo_bloqueado += monto
    wallet.updated_at = datetime.now(timezone.utc)

    tx = Transaction(
        wallet_id=wallet.id,
        tipo=TipoTransaccion.RETIRO,
        monto=-monto,
        descripcion=f"Retiro a {cuenta_destino}",
        referencia=f"RET-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
    )
    db.session.add(tx)
    db.session.flush()
    return tx


def descontar_comision(user_id: int, monto: int, referencia: str) -> Transaction:
    """Descuenta comisión de la billetera del PDS (RF-25.2)."""
    wallet = get_wallet(user_id)
    if wallet.saldo < monto:
        raise ValueError("Saldo insuficiente para comisión.")

    wallet.saldo -= monto
    wallet.updated_at = datetime.now(timezone.utc)

    tx = Transaction(
        wallet_id=wallet.id,
        tipo=TipoTransaccion.COMISION,
        monto=-monto,
        descripcion=f"Comisión por servicio",
        referencia=referencia,
    )
    db.session.add(tx)
    db.session.flush()
    return tx


def acreditar_pago(user_id: int, monto: int, referencia: str) -> Transaction:
    """Acredita monto neto al PDS tras completar servicio."""
    wallet = get_or_create_wallet(user_id)
    wallet.saldo += monto
    wallet.updated_at = datetime.now(timezone.utc)

    tx = Transaction(
        wallet_id=wallet.id,
        tipo=TipoTransaccion.DEPOSITO,
        monto=monto,
        descripcion=f"Pago por servicio completado",
        referencia=referencia,
    )
    db.session.add(tx)
    db.session.flush()
    return tx


def get_historial(user_id: int, desde=None, hasta=None) -> list:
    """Obtiene historial de transacciones de la billetera."""
    wallet = get_wallet(user_id)
    query = Transaction.query.filter_by(wallet_id=wallet.id)
    if desde:
        query = query.filter(Transaction.created_at >= desde)
    if hasta:
        query = query.filter(Transaction.created_at <= hasta)
    return query.order_by(Transaction.created_at.desc()).all()


# --------------------------------------------------------------------------
# Sistema de Monedas (RF-27)
# --------------------------------------------------------------------------

# Paquetes de monedas (RF-27.2)
PAQUETES_MONEDAS = {
    "basico": {"cantidad": 50, "precio": 5000, "bonus": 0},
    "estandar": {"cantidad": 150, "precio": 15000, "bonus": 15},  # +10%
    "premium": {"cantidad": 350, "precio": 30000, "bonus": 50},  # +17%
}


def get_saldo_monedas(user_id: int) -> dict:
    """Obtiene el saldo de monedas por tipo."""
    coins = Coin.query.filter_by(user_id=user_id).all()
    resultado = {"comprada": 0, "promocional": 0, "ganada": 0}
    for coin in coins:
        if coin.tipo in resultado:
            resultado[coin.tipo.value] += coin.cantidad
    return resultado


def comprar_monedas(user_id: int, paquete: str) -> Coin:
    """RF-27.1: Compra monedas con dinero real."""
    if paquete not in PAQUETES_MONEDAS:
        raise ValueError(f"Paquete no válido: {paquete}")

    config = PAQUETES_MONEDAS[paquete]
    cantidad_total = config["cantidad"] + config["bonus"]

    coin = Coin(
        user_id=user_id,
        cantidad=cantidad_total,
        tipo=TipoMoneda.COMPRADA,
        vence_en=None,  # Las compradas no expiran
    )
    db.session.add(coin)
    db.session.flush()
    return coin


def usar_monedas(user_id: int, cantidad: int, motivo: str) -> bool:
    """RF-27.2: Usa monedas (descuenta del saldo)."""
    saldo = get_saldo_monedas(user_id)
    total_disponible = saldo["comprada"] + saldo["promocional"] + saldo["ganada"]

    if total_disponible < cantidad:
        raise ValueError("Monedas insuficientes.")

    # Descontar primero promocionales (pesan menos), luego ganadas, luego compradas
    restante = cantidad
    for tipo in ["promocional", "ganada", "comprada"]:
        if restante <= 0:
            break
        coins = Coin.query.filter_by(user_id=user_id, tipo=TipoMoneda(tipo)).all()
        for coin in coins:
            if restante <= 0:
                break
            if coin.cantidad <= restante:
                restante -= coin.cantidad
                coin.cantidad = 0
            else:
                coin.cantidad -= restante
                restante = 0

    db.session.flush()
    return True


def dar_monedas_promocionales(user_id: int, cantidad: int, dias_vencimiento: int = 30) -> Coin:
    """Otorga monedas promocionales (bonificaciones)."""
    coin = Coin(
        user_id=user_id,
        cantidad=cantidad,
        tipo=TipoMoneda.PROMOCIONAL,
        vence_en=datetime.now(timezone.utc) + timedelta(days=dias_vencimiento),
    )
    db.session.add(coin)
    db.session.flush()
    return coin


def dar_monedas_ganadas(user_id: int, cantidad: int) -> Coin:
    """Otorga monedas por completar servicios."""
    coin = Coin(
        user_id=user_id,
        cantidad=cantidad,
        tipo=TipoMoneda.GANADA,
        vence_en=None,  # Las ganadas no expiran
    )
    db.session.add(coin)
    db.session.flush()
    return coin


def limpiar_monedas_vencidas() -> int:
    """Limpia monedas promocionales vencidas."""
    cutoff = datetime.now(timezone.utc)
    vencidas = Coin.query.filter(
        Coin.tipo == TipoMoneda.PROMOCIONAL,
        Coin.vence_en < cutoff,
        Coin.cantidad > 0,
    ).all()
    for coin in vencidas:
        coin.cantidad = 0
    db.session.flush()
    return len(vencidas)


# --------------------------------------------------------------------------
# Modalidades de Cobro (RF-26)
# --------------------------------------------------------------------------

def crear_modalidad(service_id: int, tipo: str) -> Modalidad:
    """RF-26.1: Establece la modalidad de cobro de una solicitud."""
    # Verificar que no exista ya una modalidad
    existente = Modalidad.query.filter_by(service_id=service_id).first()
    if existente:
        raise ValueError("Ya existe una modalidad para esta solicitud.")

    modalidad = Modalidad(
        service_id=service_id,
        tipo=TipoModalidad(tipo),
        monedas_requeridas=50 if tipo == "B_sin_comision" else None,
    )
    db.session.add(modalidad)
    db.session.flush()
    return modalidad


def get_modalidad(service_id: int) -> Modalidad:
    """Obtiene la modalidad de una solicitud."""
    modalidad = Modalidad.query.filter_by(service_id=service_id).first()
    if modalidad is None:
        # Por defecto, modalidad A (con comisión)
        modalidad = Modalidad(
            service_id=service_id,
            tipo=TipoModalidad.A_COMISION,
            monedas_requeridas=None,
        )
        db.session.add(modalidad)
        db.session.flush()
    return modalidad


# --------------------------------------------------------------------------
# Hitos de Pago (RF-29)
# --------------------------------------------------------------------------

def crear_hitos(contract_id: int, hitos_data: list) -> list:
    """RF-29.1: Crea hitos de pago para un contrato largo."""
    contract = db.session.get(Contract, contract_id)
    if contract is None:
        raise ValueError("El contrato no existe.")

    # Verificar que no existan hitos
    existentes = Milestone.query.filter_by(contract_id=contract_id).count()
    if existentes > 0:
        raise ValueError("Ya existen hitos para este contrato.")

    hitos = []
    for i, data in enumerate(hitos_data, 1):
        hito = Milestone(
            contract_id=contract_id,
            numero=i,
            descripcion=data.get("descripcion", f"Hito {i}"),
            monto=data.get("monto", 0),
            estado=EstadoHito.PENDIENTE,
        )
        db.session.add(hito)
        hitos.append(hito)

    db.session.flush()
    return hitos


def aprobar_hito(hito_id: int) -> Milestone:
    """RF-29.2: Aprueba un hito de pago."""
    hito = db.session.get(Milestone, hito_id)
    if hito is None:
        raise ValueError("El hito no existe.")
    if hito.estado != EstadoHito.PENDIENTE:
        raise ValueError("Solo se puede aprobar un hito pendiente.")

    hito.estado = EstadoHito.APROBADO
    hito.aprobado_en = datetime.now(timezone.utc)
    db.session.flush()
    return hito


def rechazar_hito(hito_id: int) -> Milestone:
    """RF-29.4: Rechaza un hito de pago."""
    hito = db.session.get(Milestone, hito_id)
    if hito is None:
        raise ValueError("El hito no existe.")
    if hito.estado != EstadoHito.PENDIENTE:
        raise ValueError("Solo se puede rechazar un hito pendiente.")

    hito.estado = EstadoHito.RECHAZADO
    db.session.flush()
    return hito


def get_hitos(contract_id: int) -> list:
    """Obtiene los hitos de un contrato."""
    return Milestone.query.filter_by(contract_id=contract_id).order_by(Milestone.numero).all()


def verificar_todos_aprobados(contract_id: int) -> bool:
    """Verifica si todos los hitos de un contrato están aprobados."""
    hitos = get_hitos(contract_id)
    return len(hitos) > 0 and all(h.estado == EstadoHito.APROBADO for h in hitos)
