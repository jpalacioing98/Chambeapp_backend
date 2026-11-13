"""Service layer: billetera virtual, monedas, modalidades y hitos (RF-25, RF-26, RF-27, RF-29).

Implementa la lógica de negocio para:
- Billetera virtual (depósitos, retiros, transacciones)
- Sistema de monedas (compra, uso, vencimiento)
- Modalidades de cobro (A con comisión, B sin comisión)
- Hitos de pago (creación, aprobación, rechazo)
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.models.wallet import (
    Wallet,
    Transaction,
    TipoTransaccion,
    Coin,
    TipoMoneda,
    TipoMovimientoMonedas,
    PaqueteMonedas,
    CompraPaquete,
    MovimientoMonedas,
)
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
# Sistema de Monedas (RF-27) — billetera de monedas virtuales
# --------------------------------------------------------------------------

def _registrar_movimiento_monedas(
    user_id: int,
    wallet: Wallet,
    tipo: TipoMovimientoMonedas,
    cantidad: int,
    descripcion: str | None = None,
    referencia: str | None = None,
    paquete_id: int | None = None,
    vence_en: datetime | None = None,
) -> MovimientoMonedas:
    """Aplica un movimiento al saldo de monedas y lo deja en el libro."""
    wallet.monedas_saldo = max(0, int(wallet.monedas_saldo) + int(cantidad))
    wallet.updated_at = datetime.now(timezone.utc)
    mov = MovimientoMonedas(
        user_id=user_id,
        wallet_id=wallet.id,
        tipo=tipo.value,
        cantidad=int(cantidad),
        saldo_resultante=wallet.monedas_saldo,
        descripcion=descripcion,
        referencia=referencia,
        paquete_id=paquete_id,
        vence_en=vence_en,
    )
    db.session.add(mov)
    db.session.flush()
    return mov


def get_saldo_monedas(user_id: int) -> dict:
    """Saldo actual y totales históricos de monedas."""
    wallet = get_or_create_wallet(user_id)
    coins = Coin.query.filter_by(user_id=user_id).all()
    por_tipo = {"comprada": 0, "promocional": 0, "ganada": 0}
    for coin in coins:
        if coin.tipo.value in por_tipo:
            por_tipo[coin.tipo.value] += coin.cantidad

    gastada = (
        db.session.query(func.coalesce(func.sum(MovimientoMonedas.cantidad), 0))
        .filter(
            MovimientoMonedas.user_id == user_id,
            MovimientoMonedas.tipo == TipoMovimientoMonedas.GASTO.value,
        )
        .scalar()
        or 0
    )

    return {
        "saldo": wallet.monedas_saldo,
        "comprada": por_tipo["comprada"],
        "promocional": por_tipo["promocional"],
        "ganada": por_tipo["ganada"],
        "gastada": abs(int(gastada)),
        "total": wallet.monedas_saldo,
    }


def get_movimientos_monedas(user_id: int, limite: int = 100) -> list:
    """Historial de movimientos de monedas, más reciente primero."""
    return (
        MovimientoMonedas.query.filter_by(user_id=user_id)
        .order_by(MovimientoMonedas.creado_en.desc(), MovimientoMonedas.id.desc())
        .limit(max(1, min(int(limite), 500)))
        .all()
    )


def get_paquetes(solo_activos: bool = True) -> list:
    """Paquetes de monedas disponibles (o todos, para el superadmin)."""
    query = PaqueteMonedas.query
    if solo_activos:
        query = query.filter_by(activo=True)
    return query.order_by(PaqueteMonedas.orden.asc(), PaqueteMonedas.id.asc()).all()


def crear_paquete(data: dict, creado_por: int | None = None) -> PaqueteMonedas:
    """Crea un paquete de monedas (superadmin)."""
    paquete = PaqueteMonedas(
        nombre=data["nombre"].strip(),
        descripcion=(data.get("descripcion") or None),
        cantidad=int(data["cantidad"]),
        bonus=int(data.get("bonus", 0)),
        precio_cop=int(data["precio_cop"]),
        activo=bool(data.get("activo", True)),
        en_oferta=bool(data.get("en_oferta", False)),
        precio_oferta_cop=data.get("precio_oferta_cop"),
        oferta_desde=data.get("oferta_desde"),
        oferta_hasta=data.get("oferta_hasta"),
        orden=int(data.get("orden", 0)),
        creado_por=creado_por,
    )
    _validar_paquete(paquete)
    db.session.add(paquete)
    db.session.flush()
    return paquete


def actualizar_paquete(paquete_id: int, data: dict) -> PaqueteMonedas:
    """Edita un paquete existente (parcial)."""
    paquete = db.session.get(PaqueteMonedas, paquete_id)
    if paquete is None:
        raise ValueError("El paquete no existe.")

    for campo in (
        "nombre",
        "descripcion",
        "cantidad",
        "bonus",
        "precio_cop",
        "activo",
        "en_oferta",
        "precio_oferta_cop",
        "oferta_desde",
        "oferta_hasta",
        "orden",
    ):
        if campo in data:
            valor = data[campo]
            if campo == "nombre" and isinstance(valor, str):
                valor = valor.strip()
            setattr(paquete, campo, valor)

    _validar_paquete(paquete)
    db.session.flush()
    return paquete


def eliminar_paquete(paquete_id: int) -> PaqueteMonedas:
    """Desactiva un paquete (no se borran compras históricas)."""
    paquete = db.session.get(PaqueteMonedas, paquete_id)
    if paquete is None:
        raise ValueError("El paquete no existe.")
    paquete.activo = False
    db.session.flush()
    return paquete


def _validar_paquete(paquete: PaqueteMonedas) -> None:
    if paquete.cantidad < 1:
        raise ValueError("El paquete debe tener al menos 1 moneda.")
    if paquete.precio_cop < 1:
        raise ValueError("El precio del paquete debe ser mayor que 0.")
    if paquete.bonus < 0:
        raise ValueError("El bonus no puede ser negativo.")
    if paquete.en_oferta and not paquete.precio_oferta_cop:
        raise ValueError("Una oferta requiere precio promocional.")
    if (
        paquete.oferta_desde
        and paquete.oferta_hasta
        and paquete.oferta_desde > paquete.oferta_hasta
    ):
        raise ValueError("La fecha de inicio de la oferta no puede ser posterior a la de fin.")


def comprar_paquete(
    user_id: int,
    paquete_id: int,
    pasarela: str = "simulada",
) -> CompraPaquete:
    """Compra un paquete y acredita sus monedas al instante.

    La pasarela real se conectará detrás de esta función; mientras tanto el
    pago se registra como `simulada` y la compra queda en estado completado.
    """
    paquete = db.session.get(PaqueteMonedas, paquete_id)
    if paquete is None or not paquete.activo:
        raise ValueError("El paquete no está disponible.")

    total_monedas = int(paquete.cantidad) + int(paquete.bonus or 0)
    precio = paquete.precio_efectivo()

    compra = CompraPaquete(
        user_id=user_id,
        paquete_id=paquete.id,
        monedas=total_monedas,
        precio_cop=precio,
        pasarela=pasarela,
        estado="completado",
        referencia=f"CMP-{user_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
    )
    db.session.add(compra)
    db.session.flush()

    wallet = get_or_create_wallet(user_id)
    _registrar_movimiento_monedas(
        user_id,
        wallet,
        TipoMovimientoMonedas.COMPRA,
        total_monedas,
        descripcion=f"Compra de {paquete.nombre}",
        referencia=compra.referencia,
        paquete_id=paquete.id,
    )

    # Compatibilidad con el desglose por tipo de moneda.
    db.session.add(
        Coin(user_id=user_id, cantidad=total_monedas, tipo=TipoMoneda.COMPRADA)
    )
    db.session.flush()
    return compra


def usar_monedas(user_id: int, cantidad: int, motivo: str) -> bool:
    """Descuenta monedas del saldo y lo registra en el libro."""
    if cantidad < 1:
        raise ValueError("La cantidad de monedas debe ser mayor que 0.")

    wallet = get_or_create_wallet(user_id)
    if wallet.monedas_saldo < cantidad:
        raise ValueError("Monedas insuficientes.")

    # Descontar primero promocionales, luego ganadas, luego compradas
    restante = cantidad
    for tipo in (TipoMoneda.PROMOCIONAL, TipoMoneda.GANADA, TipoMoneda.COMPRADA):
        if restante <= 0:
            break
        coins = Coin.query.filter_by(user_id=user_id, tipo=tipo).all()
        for coin in coins:
            if restante <= 0:
                break
            if coin.cantidad <= restante:
                restante -= coin.cantidad
                coin.cantidad = 0
            else:
                coin.cantidad -= restante
                restante = 0

    _registrar_movimiento_monedas(
        user_id,
        wallet,
        TipoMovimientoMonedas.GASTO,
        -cantidad,
        descripcion=motivo,
        referencia=motivo,
    )
    return True


def dar_monedas_promocionales(user_id: int, cantidad: int, dias_vencimiento: int = 30) -> MovimientoMonedas:
    """Otorga monedas promocionales (bonificaciones)."""
    wallet = get_or_create_wallet(user_id)
    vence = datetime.now(timezone.utc) + timedelta(days=dias_vencimiento)
    db.session.add(
        Coin(
            user_id=user_id,
            cantidad=cantidad,
            tipo=TipoMoneda.PROMOCIONAL,
            vence_en=vence,
        )
    )
    return _registrar_movimiento_monedas(
        user_id,
        wallet,
        TipoMovimientoMonedas.PROMOCIONAL,
        cantidad,
        descripcion="Monedas promocionales",
        vence_en=vence,
    )


def dar_monedas_ganadas(user_id: int, cantidad: int) -> MovimientoMonedas:
    """Otorga monedas por completar servicios."""
    wallet = get_or_create_wallet(user_id)
    db.session.add(
        Coin(user_id=user_id, cantidad=cantidad, tipo=TipoMoneda.GANADA)
    )
    return _registrar_movimiento_monedas(
        user_id,
        wallet,
        TipoMovimientoMonedas.GANADA,
        cantidad,
        descripcion="Monedas ganadas",
    )


def limpiar_monedas_vencidas() -> int:
    """Expira monedas promocionales vencidas y ajusta el saldo."""
    cutoff = datetime.now(timezone.utc)
    vencidas = Coin.query.filter(
        Coin.tipo == TipoMoneda.PROMOCIONAL,
        Coin.vence_en.isnot(None),
        Coin.vence_en < cutoff,
        Coin.cantidad > 0,
    ).all()
    for coin in vencidas:
        wallet = get_or_create_wallet(coin.user_id)
        a_expirar = min(coin.cantidad, wallet.monedas_saldo)
        coin.cantidad = 0
        if a_expirar > 0:
            _registrar_movimiento_monedas(
                coin.user_id,
                wallet,
                TipoMovimientoMonedas.VENCIMIENTO,
                -a_expirar,
                descripcion="Vencimiento de monedas promocionales",
            )
    db.session.flush()
    return len(vencidas)


# --------------------------------------------------------------------------
# Situación financiera por rol
# --------------------------------------------------------------------------

def get_resumen_financiero(user_id: int, rol: str) -> dict:
    """Resumen de monedas + finanzas de la actividad en COP.

    Las cifras COP NO son el saldo interno de la billetera: representan lo
    que el usuario ha ganado o gastado dentro de la app (chambas, marañas,
    contratos, comisiones y retiros).
    """
    monedas = get_saldo_monedas(user_id)

    def _tx_total(tipo: TipoTransaccion) -> float:
        total = (
            db.session.query(func.coalesce(func.sum(Transaction.monto), 0))
            .join(Wallet, Wallet.id == Transaction.wallet_id)
            .filter(
                Wallet.user_id == user_id,
                Transaction.tipo == tipo,
            )
            .scalar()
            or 0
        )
        return abs(float(total))

    from app.models.contract import Contract, EstadoContrato
    from app.models.marana import Marana, EstadoMarana

    contratos_pds = Contract.query.filter_by(proveedor_id=user_id).all()
    contratos_pds_ok = [
        c for c in contratos_pds if c.estado == EstadoContrato.COMPLETADO
    ]
    contratos_cliente = Contract.query.filter_by(solicitante_id=user_id).all()
    contratos_cliente_ok = [
        c for c in contratos_cliente if c.estado == EstadoContrato.COMPLETADO
    ]

    maranas_pds = Marana.query.filter(
        Marana.pds_asignado_id == user_id,
        Marana.estado == EstadoMarana.PAGADO,
    ).all()
    maranas_cliente = Marana.query.filter(
        Marana.solicitante_id == user_id,
        Marana.estado == EstadoMarana.PAGADO,
    ).all()

    valor_chambas = sum(
        float(c.monto or (c.service.presupuesto if c.service else 0) or 0)
        for c in contratos_pds_ok
    )
    valor_maranas = sum(
        float(m.pago_monto_final or m.presupuesto or 0) for m in maranas_pds
    )
    valor_contratos_cliente = sum(
        float(c.monto or (c.service.presupuesto if c.service else 0) or 0)
        for c in contratos_cliente_ok
    )
    valor_maranas_cliente = sum(
        float(m.pago_monto_final or m.presupuesto or 0)
        for m in maranas_cliente
    )
    comisiones = _tx_total(TipoTransaccion.COMISION)
    retiros = _tx_total(TipoTransaccion.RETIRO)

    if rol == "pds":
        ingresos_detalle = {
            "chambas_cop": valor_chambas,
            "maranas_cop": valor_maranas,
            "otros_cop": 0.0,
        }
        egresos_detalle = {
            "chambas_cop": 0.0,
            "maranas_cop": 0.0,
            "comisiones_cop": comisiones,
            "otros_cop": 0.0,
        }
    else:
        # Solicitante y comerciante: pagan contratos/marañas dentro de la app.
        ingresos_detalle = {
            "chambas_cop": 0.0,
            "maranas_cop": 0.0,
            "otros_cop": 0.0,
        }
        egresos_detalle = {
            "chambas_cop": valor_contratos_cliente,
            "maranas_cop": valor_maranas_cliente,
            "comisiones_cop": comisiones,
            "otros_cop": 0.0,
        }

    ingresos = sum(ingresos_detalle.values())
    egresos = sum(egresos_detalle.values())

    resumen: dict = {
        "rol": rol,
        "monedas": {
            "saldo": monedas["saldo"],
            "compradas": monedas["comprada"],
            "gastadas": monedas["gastada"],
            "promocionales": monedas["promocional"],
            "ganadas": monedas["ganada"],
        },
        "finanzas": {
            "ingresos_cop": ingresos,
            "egresos_cop": egresos,
            "neto_cop": ingresos - egresos,
            "ingresos_detalle": ingresos_detalle,
            "egresos_detalle": egresos_detalle,
            "retiros_cop": retiros,
        },
    }

    if rol == "pds":
        resumen["pds"] = {
            "contratos_total": len(contratos_pds),
            "contratos_completados": len(contratos_pds_ok),
            "valor_contratos_cop": sum(
                float(c.monto or (c.service.presupuesto if c.service else 0) or 0)
                for c in contratos_pds
            ),
            "valor_completados_cop": valor_chambas,
            "ganancias_chambas_cop": valor_chambas,
            "ganancias_maranas_cop": valor_maranas,
            "retiros_cop": retiros,
            "comisiones_cop": comisiones,
            "gastado_plataforma_monedas": monedas["gastada"],
        }

    elif rol == "merchant":
        from app.models.anuncio import (
            AnuncioLaboral,
            AnuncioPostulacion,
            EstadoAnuncio,
        )

        anuncios = AnuncioLaboral.query.filter_by(negocio_id=user_id).all()
        publicados = [a for a in anuncios if a.estado == EstadoAnuncio.PUBLICADO]
        postulaciones = (
            db.session.query(func.count(AnuncioPostulacion.id))
            .join(
                AnuncioLaboral,
                AnuncioLaboral.id == AnuncioPostulacion.anuncio_id,
            )
            .filter(AnuncioLaboral.negocio_id == user_id)
            .scalar()
            or 0
        )
        resumen["merchant"] = {
            "anuncios_total": len(anuncios),
            "anuncios_publicados": len(publicados),
            "postulaciones_recibidas": int(postulaciones),
            "gastado_plataforma_monedas": monedas["gastada"],
            "ventas_cop": None,  # Pendiente: no existe modelo de ventas.
        }

    return resumen



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
