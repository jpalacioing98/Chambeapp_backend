"""Blueprint público de Legal: Términos y Condiciones y Política de Datos (sin JWT).

GET /api/v1/legal/tyc            -> lee SystemConfig 'tyc_current' (value_type=json).
GET /api/v1/legal/politica-datos -> Política de datos (Habeas Data, Ley 1581).
"""

from flask import jsonify
from flask.views import MethodView
from flask_smorest import Blueprint, abort

from app.extensions import db
from app.models.config import SystemConfig

blp = Blueprint("legal", __name__, description="Términos y Condiciones y Política Legal públicos")

POLITICA_DATOS_CONTENT = """\
# Política de Tratamiento de Datos Personales - ChambeApp

## 1. Responsable del Tratamiento
ChambeApp S.A.S., identificada con NIT [por definir], con domicilio en Valledupar, Cesar, Colombia.

## 2. Finalidad del Tratamiento
Los datos personales serán tratados para:
- Gestión de la cuenta de usuario y autenticación.
- Prestación de los servicios de la plataforma (conexión entre proveedores y contratantes).
- Verificación de identidad (KYC) y seguridad.
- Gestión de pagos y facturación.
- Notificaciones relacionadas con solicitudes, contratos y pagos.
- Mejora de la experiencia del usuario y recomendaciones personalizadas.
- Cumplimiento de obligaciones legales y regulatorias.

## 3. Datos Recopilados
- Datos de identificación: nombre, correo electrónico, teléfono, documento de identidad.
- Datos de perfil: habilidades, experiencia, zona, fotografía.
- Datos de ubicación: coordenadas geoespaciales para búsquedas de proximidad.
- Datos financieros: métodos de pago, historial de transacciones.
- Datos de verificación: documentos KYC (cédula, RUT, certificados).

## 4. Base Legal del Tratamiento
- Autorización del titular (Ley 1581 de 2012, Art. 9).
- Ejecución de contrato o relación precontractual.
- Obligación legal.

## 5. Derechos del Titular
De conformidad con la Ley 1581 de 2012 y el Decreto 1377 de 2012:
- **Derecho de acceso:** Conocer qué datos tenemos y cómo los usamos.
- **Derecho de rectificación:** Corregir datos inexactos.
- **Derecho de supresión:** Solicitar la eliminación de datos cuando ya no sean necesarios.
- **Derecho de oposición:** Oponerse al tratamiento de sus datos.
- **Derecho a la portabilidad:** Recibir sus datos en formato estructurado.
- **Revocación de autorización:** En cualquier momento, sin efecto retroactivo.

## 6. Medidas de Seguridad
ChambeApp implementa medidas técnicas, administrativas y físicas para proteger los datos:
- Encriptación en tránsito (TLS) y en reposo.
- Control de acceso por roles y autenticación JWT.
- Auditoría de accesos y operaciones.
- Almacenamiento seguro de documentos KYC.

## 7. Transferencias Internacionales
No se realizan transferencias internacionales de datos fuera de Colombia,
salvo para el almacenamiento en servicios cloud con garantías equivalentes
a la normativa colombiana.

## 8. Retención de Datos
Los datos se conservarán mientras la cuenta del usuario esté activa o
se requiera para cumplir obligaciones legales. Al eliminar la cuenta,
los datos se anonimizan o eliminan en un plazo máximo de 30 días.

## 9. Contacto
Para ejercer sus derechos, contactar a nuestro oficial de protección de datos:
- Email: proteccion.datos@chambeapp.com
- Dirección: Valledupar, Cesar, Colombia

## 10. Vigencia
Esta política está vigente desde el 1 de enero de 2026.
Última actualización: 2026-09-16.

---

## 11. Datos del Módulo de Habilidades, Certificaciones y Oficios

Con el fin de ofrecer el sistema de validación de competencias y la progresión de oficios de la plataforma, se tratan los siguientes datos:

- **Competencias declaradas:** oficios y habilidades que el prestador registra en su perfil.
- **Resultados de evaluaciones (quizzes):** respuestas, aciertos y estado de aprobación de las micro-evaluaciones técnicas (umbral 80%).
- **Certificaciones técnicas:** institución (ej. SENA), título obtenido, año de emisión, código de verificación y documento soporte.
- **Endosos de clientes:** confirmaciones de competencias demostradas realizadas por los solicitantes al cerrar una orden.
- **Nivel de progresión:** nivel (1-5) asignado a cada oficio a partir de los criterios objetivos del módulo (trabajos, calificación, validaciones y titulación).

Estos datos se utilizan para: validar las competencias declaradas, otorgar insignias de verificación, alimentar la priorización del motor de recomendación por IA y aumentar la confianza entre usuarios. La verificación de títulos es documental e informativa previa, y no constituye una garantía de resultado.

## 12. Datos de los Contratos y de la Negociación

Al aceptar una oferta y firmar el contrato de prestación de servicios dentro de la aplicación, se tratan:

- **Contenido de las conversaciones del chat** entre Solicitante y Prestador (incluyendo montos, cotizaciones y acuerdos), que constituye anexo vinculante del contrato.
- **Condiciones de la negociación** acordadas explícitamente por las partes e incorporadas al contrato.
- **Firmas electrónicas** (trazo, nombre, documento de identidad y fecha) con valor probatorio como mensajes de datos (Ley 527 de 1999).
- **Historial de ofertas, contraofertas y contratos** (estados, montos y fechas) para la gestión de la relación contractual y la resolución de disputas.

Estos datos se conservan como registro de la relación entre las partes y solo se comunican a terceros cuando lo exija la ley o la autoridad competente.

## 13. Base Legal Complementaria
- Ley 527 de 1999 (comercio electrónico, mensajes de datos y firma electrónica).
- Ley 1581 de 2012 y Decreto 1377 de 2012 (protección de datos personales).
- Art. 6 del Código Sustantivo del Trabajo (servicios ocasionales entre particulares).
"""


@blp.route("/tyc")
class TyCPublic(MethodView):
    def get(self):
        """Retorna la versión vigente de T&C (público, sin autenticación)."""
        cfg = SystemConfig.query.filter_by(key="tyc_current").first()
        if not cfg:
            abort(404, message="No hay T&C configurados")
        data = SystemConfig.parse_value(cfg.value, "json") or {}
        return (
            jsonify(
                {
                    "version": data.get("version"),
                    "content": data.get("content"),
                    "published_at": data.get("published_at"),
                }
            ),
            200,
        )


@blp.route("/politica-datos")
class PoliticaDatosPublic(MethodView):
    def get(self):
        """Retorna la Política de Tratamiento de Datos Personales (Habeas Data).

        Endpoint público (sin autenticación) requerido por Ley 1581 de 2012.
        Retorna el contenido estático de la política de datos.
        """
        return (
            jsonify(
                {
                    "version": "1.1",
                    "content": POLITICA_DATOS_CONTENT,
                    "titulo": "Política de Tratamiento de Datos Personales",
                    "ley_aplicable": "Ley 1581 de 2012",
                    "decreto_aplicable": "Decreto 1377 de 2012",
                }
            ),
            200,
        )