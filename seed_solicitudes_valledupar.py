"""Seed: reemplaza todas las solicitudes por un set nuevo en Valledupar.

Borra las solicitudes existentes (con sus ofertas, ratings y contratos
asociados) y crea una docena de solicitudes completas localizadas en
Valledupar (lat 10.4806, lng -73.2495) con todos los campos:
titulo, categoria, descripcion, ubicacion, direccion, lat/lng,
presupuesto (algunas "a convenir"), fecha_deseada, urgencia, horario,
especificaciones_tecnicas y radio_km.

Uso:
    docker compose exec backend python -m seed_solicitudes_valledupar
"""

from datetime import date, timedelta

from app import create_app
from app.extensions import db
from app.models.solicitud import Rating, Solicitud, EstadoSolicitud, UrgenciaSolicitud
from app.models.user import User

# Centro de Valledupar (departamento del Cesar, Colombia).
VALLE_LAT = 10.4806
VALLE_LNG = -73.2495

SOLICITUDES = [
    {
        "titulo": "Fuga de agua en baño principal",
        "categoria": "plomería",
        "descripcion": "Reparación de fuga de agua en la tubería principal del baño del primer piso. El agua gotea constantemente bajo el lavamanos.",
        "ubicacion": "Valledupar",
        "direccion": "Cra 7 #14-20, Barrio Centro, Valledupar",
        "latitud": 10.4772,
        "longitud": -73.2508,
        "presupuesto": 120000,
        "fecha_deseada": date.today() + timedelta(days=2),
        "urgencia": UrgenciaSolicitud.SEMANA,
        "horario": "Mañana (6:00 - 12:00)",
        "radio_km": 6.0,
        "especificaciones_tecnicas": ["Tubería de PVC de 1/2\"", "Revisar empaques del lavamanos"],
    },
    {
        "titulo": "Instalación de mueble de cocina",
        "categoria": "carpintería",
        "descripcion": "Instalar mueble de cocina modular de 2.4 m con mesón en granito. Incluye nivelación y fijación a la pared.",
        "ubicacion": "Valledupar",
        "direccion": "Calle 15 #9-30, Barrio La Esperanza, Valledupar",
        "latitud": 10.4835,
        "longitud": -73.2459,
        "presupuesto": 150000,
        "fecha_deseada": date.today() + timedelta(days=4),
        "urgencia": UrgenciaSolicitud.FLEXIBLE,
        "horario": "Tarde (12:00 - 18:00)",
        "radio_km": 8.0,
        "especificaciones_tecnicas": ["Mueble modular 2.4 m", "Mesón granito 60 cm"],
    },
    {
        "titulo": "Reparar grifo que gotea",
        "categoria": "plomería",
        "descripcion": "Grifo de la cocina gotea de forma constante. Cambiar empaque y revisar el mezclador monomando.",
        "ubicacion": "Valledupar",
        "direccion": "Calle 8 #12-10, Barrio Dangond, Valledupar",
        "latitud": 10.4699,
        "longitud": -73.2561,
        "presupuesto": 80000,
        "fecha_deseada": date.today() + timedelta(days=1),
        "urgencia": UrgenciaSolicitud.HOY,
        "horario": "Mañana (6:00 - 12:00)",
        "radio_km": 5.0,
        "especificaciones_tecnicas": ["Grifo monomando de cocina"],
    },
    {
        "titulo": "Pintar fachada de casa",
        "categoria": "pintura",
        "descripcion": "Pintar fachada de casa de 2 pisos (~60 m²). Incluye lijado, imprimación y dos manos de pintura tipo I.",
        "ubicacion": "Valledupar",
        "direccion": "Cra 19 #16-40, Barrio San Fernando, Valledupar",
        "latitud": 10.4861,
        "longitud": -73.2417,
        "presupuesto": 350000,
        "fecha_deseada": date.today() + timedelta(days=6),
        "urgencia": UrgenciaSolicitud.FLEXIBLE,
        "horario": "Tarde (12:00 - 18:00)",
        "radio_km": 10.0,
        "especificaciones_tecnicas": ["Pintura tipo I color blanco", "60 m² aprox."],
    },
    {
        "titulo": "Instalar tres tomacorrientes",
        "categoria": "electricidad",
        "descripcion": "Instalar 3 tomacorrientes dobles en sala y habitaciones. Incluye canalización y verificación del tablero.",
        "ubicacion": "Valledupar",
        "direccion": "Calle 12 #7-45, Barrio Centro, Valledupar",
        "latitud": 10.4751,
        "longitud": -73.2533,
        "presupuesto": 150000,
        "fecha_deseada": date.today() + timedelta(days=3),
        "urgencia": UrgenciaSolicitud.SEMANA,
        "horario": "Mañana (6:00 - 12:00)",
        "radio_km": 5.0,
        "especificaciones_tecnicas": ["Tomacorriente doble 110V", "Revisar breaker"],
    },
    {
        "titulo": "Jardinera y poda de césped",
        "categoria": "jardinería",
        "descripcion": "Poda de césped, limpieza de jardineras y poda de 2 árboles pequeños en el patio trasero.",
        "ubicacion": "Valledupar",
        "direccion": "Cra 11 #20-15, Barrio Primero de Mayo, Valledupar",
        "latitud": 10.4903,
        "longitud": -73.2385,
        "presupuesto": None,
        "fecha_deseada": date.today() + timedelta(days=5),
        "urgencia": UrgenciaSolicitud.FLEXIBLE,
        "horario": "Mañana (6:00 - 12:00)",
        "radio_km": 8.0,
        "especificaciones_tecnicas": ["Patio de 80 m² aprox."],
    },
    {
        "titulo": "Aseo profundo de apartamento",
        "categoria": "aseo",
        "descripcion": "Aseo general de apartamento de 3 habitaciones: baños, cocina, pisos y ventanas. Sin productos de limpieza incluidos.",
        "ubicacion": "Valledupar",
        "direccion": "Calle 5 #10-25, Barrio San Joaquín, Valledupar",
        "latitud": 10.4672,
        "longitud": -73.2598,
        "presupuesto": 100000,
        "fecha_deseada": date.today() + timedelta(days=1),
        "urgencia": UrgenciaSolicitud.SEMANA,
        "horario": "Tarde (12:00 - 18:00)",
        "radio_km": 5.0,
        "especificaciones_tecnicas": ["3 habitaciones", "Incluir ventanas"],
    },
    {
        "titulo": "Soldar estructura de portón",
        "categoria": "soldadura",
        "descripcion": "Soldar refuerzos y bisagras de portón metálico de 3x2 m que se desprendió de la columna.",
        "ubicacion": "Valledupar",
        "direccion": "Cra 25 #8-50, Barrio Los Cortijos, Valledupar",
        "latitud": 10.4718,
        "longitud": -73.2623,
        "presupuesto": 200000,
        "fecha_deseada": date.today() + timedelta(days=4),
        "urgencia": UrgenciaSolicitud.SEMANA,
        "horario": "Mañana (6:00 - 12:00)",
        "radio_km": 9.0,
        "especificaciones_tecnicas": ["Portón 3x2 m", "Soldadura eléctrica"],
    },
    {
        "titulo": "Reparación de aire acondicionado",
        "categoria": "aire acondicionado",
        "descripcion": "Aire acondicionado split 12000 BTU no enfría. Revisar gas refrigerante, compresor y limpieza de filtros.",
        "ubicacion": "Valledupar",
        "direccion": "Calle 18 #10-33, Barrio Novalito, Valledupar",
        "latitud": 10.4817,
        "longitud": -73.2441,
        "presupuesto": None,
        "fecha_deseada": date.today() + timedelta(days=2),
        "urgencia": UrgenciaSolicitud.HOY,
        "horario": "Mañana (6:00 - 12:00)",
        "radio_km": 6.0,
        "especificaciones_tecnicas": ["Split 12000 BTU", "Verificar gas R410A"],
    },
    {
        "titulo": "Instalación de cerradura digital",
        "categoria": "cerrajería",
        "descripcion": "Instalar cerradura digital en puerta principal de madera. Incluye ajuste de chapa y configuración de códigos.",
        "ubicacion": "Valledupar",
        "direccion": "Cra 6 #16-22, Barrio Centro, Valledupar",
        "latitud": 10.4768,
        "longitud": -73.2487,
        "presupuesto": 120000,
        "fecha_deseada": date.today() + timedelta(days=3),
        "urgencia": UrgenciaSolicitud.SEMANA,
        "horario": "Tarde (12:00 - 18:00)",
        "radio_km": 4.0,
        "especificaciones_tecnicas": ["Puerta de madera", "Cerradura digital con código"],
    },
    {
        "titulo": "Cambio de empaque en llave de patio",
        "categoria": "plomería",
        "descripcion": "Cambiar empaque de llave de paso del patio que no cierra por completo y deja pasar agua.",
        "ubicacion": "Valledupar",
        "direccion": "Calle 21 #8-40, Barrio Villa del Rosario, Valledupar",
        "latitud": 10.4921,
        "longitud": -73.2348,
        "presupuesto": 60000,
        "fecha_deseada": date.today() + timedelta(days=1),
        "urgencia": UrgenciaSolicitud.SEMANA,
        "horario": "Mañana (6:00 - 12:00)",
        "radio_km": 5.0,
        "especificaciones_tecnicas": ["Llave de paso de patio"],
    },
    {
        "titulo": "Armar y colgar mueble de TV",
        "categoria": "carpintería",
        "descripcion": "Armar mueble de TV de MDF y fijarlo a la pared. Incluye nivelación y ocultamiento de cables.",
        "ubicacion": "Valledupar",
        "direccion": "Cra 14 #10-28, Barrio La Popa, Valledupar",
        "latitud": 10.4705,
        "longitud": -73.2555,
        "presupuesto": 90000,
        "fecha_deseada": date.today() + timedelta(days=2),
        "urgencia": UrgenciaSolicitud.SEMANA,
        "horario": "Tarde (12:00 - 18:00)",
        "radio_km": 6.0,
        "especificaciones_tecnicas": ["Mueble MDF 1.8 m", "Fijación a pared"],
    },
]


def _borrar_solicitudes() -> int:
    """Elimina todas las solicitudes y sus dependencias transitivas.

    Se usa TRUNCATE ... CASCADE sobre las tablas que referencian a
    solicitudes/contratos (ofertas, ratings, disputes, milestones,
    payments, suscripciones, notifications) y luego se borran las
    solicitudes. CASCADE limpia de forma determinista las FK.
    """
    from sqlalchemy import text

    # Categoría dev / seed: se truncan las tablas de trabajo para no chocar
    # con FKs transitivas (disputes→contracts, milestones→contracts, etc.).
    tablas = [
        "notifications",
        "suscripciones",
        "payments",
        "milestones",
        "disputes",
        "ofertas",
        "ratings_solicitud",
        "contracts",
        "solicitudes",
    ]
    for t in tablas:
        db.session.execute(text(f'TRUNCATE TABLE "{t}" RESTART IDENTITY CASCADE'))
    db.session.commit()
    print("  TRUNCADAS tablas de trabajo (solicitudes, ofertas, contratos, etc.)")
    return 0


def seed() -> int:
    app = create_app()
    with app.app_context():
        print("Eliminando solicitudes existentes...")
        _borrar_solicitudes()

        empleador = User.query.filter_by(email="solicitante@chambeapp.com").first()
        if empleador is None:
            raise SystemExit("No existe el usuario solicitante@chambeapp.com")

        creadas = 0
        for spec in SOLICITUDES:
            solicitud = Solicitud(
                solicitante_id=empleador.id,
                titulo=spec["titulo"],
                categoria=spec["categoria"],
                descripcion=spec["descripcion"],
                ubicacion=spec["ubicacion"],
                direccion=spec["direccion"],
                latitud=spec["latitud"],
                longitud=spec["longitud"],
                presupuesto=spec["presupuesto"],
                fecha_deseada=spec["fecha_deseada"],
                urgencia=spec["urgencia"],
                horario=spec["horario"],
                especificaciones_tecnicas=spec["especificaciones_tecnicas"],
                radio_km=spec["radio_km"],
                estado=EstadoSolicitud.PUBLICADO,
            )
            db.session.add(solicitud)
            creadas += 1

        db.session.commit()
        print(f"  CREADAS {creadas} solicitudes en Valledupar")
        return creadas


if __name__ == "__main__":
    seed()