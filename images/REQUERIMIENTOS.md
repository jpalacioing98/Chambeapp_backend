# Documento de Ingeniería de Requerimientos
## Chambea App — Plataforma Inteligente para la Contratación de Servicios Laborales

---

## 1. Información General

| Campo | Valor |
|:---|:---|
| **Nombre del Proyecto** | Chambea App |
| **Autores** | Jose David Palacio Mejía, Victor Alfonzo Ardila Montalván |
| **Director** | Amilkar Sierra Romano |
| **Institución** | Universidad Popular del Cesar |
| **Línea de Investigación** | Transformación digital / Sistemas inteligentes |
| **Grupo de Investigación** | Gisico |
| **Stack Tecnológico** | PWA con React, Backend REST/GraphQL, Base de datos relacional + NoSQL |
| **Alcance Geográfico Fase 1** | Valledupar, Cesar (Colombia) |
| **Alcance Nacional** | Escalable a nivel nacional en fases posteriores |

---

## 2. Definición del Problema

La población ocupada en Colombia presenta una informalidad superior al 55% (2025-2026), afectando desproporcionadamente a ciudades intermedias como Valledupar. No existen mecanismos digitales integrales que transformen el trabajo informal de corta duración en oportunidades organizadas, trazables y progresivamente formales. Las soluciones actuales son intermediaciones informales que no contemplan la normativa de protección social (Ley 1429 de 2010 y Ley 1562 de 2012).

---

## 3. Propuesta de Solución

Plataforma digital inteligente e interactiva (PWA) que conecte empleadores y trabajadores de servicios ocasionales en Valledupar, integrando:

1. **Motor de Recomendación (IA):** Algoritmos de similitud para matching óptimo entre perfiles.
2. **Visualización 360°:** Galería fotográfica inmersiva de escenarios de trabajo.
3. **Economía Virtual y Formalización:** Monedero digital, registro de ingresos, reputación y enlace a seguridad social.
4. **Verificación Rigurosa:** Validación de identidad con cédula y datos progresivos.

---

## 4. Roles de Usuario

| # | Rol | Descripción | Autenticación |
|:--|:---|:---|:---|
| R1 | **Trabajador Independiente** | Ofrece servicios, gestiona perfil, recibe calificaciones, accede a historial de ingresos | Registro con cédula + OTP |
| R2 | **Empleador / Solicitante** | Publica solicitudes, busca y contrata servicios, califica trabajadores | Registro con cédula + OTP |
| R3 | **Verificador de Documentos** | Valida cédulas, documentos de identidad y antecedentes de usuarios | Email + contraseña + 2FA |
| R4 | **Soporte / Mediador** | Gestiona disputas, media entre partes, resuelve reclamaciones | Email + contraseña + 2FA |
| R5 | **Administrador** | Gestiona usuarios, aprueba cuentas, configura categorías, monitorea actividad | Email + contraseña + 2FA |
| R6 | **Superadmin** | Control total del sistema, auditoría, configuración técnica, gestión financiera | Email + contraseña + 2FA + biometría |

---

## 5. Modelo de Autenticación y Registro

### 5.1 Flujo de Registro

El registro es **progresivo**. El usuario ingresa datos mínimos inicialmente y completa su perfil con el tiempo.

**Datos mínimos de registro (todos los roles):**
- Número de cédula / documento de identidad
- Número de teléfono celular
- Código OTP enviado por SMS
- Nombre completo
- Correo electrónico (opcional en fase inicial)

**Datos adicionales por rol:**

| Dato | Trabajador | Empleador |
|:---|:---|:---|
| Cédula (foto frontal) | Obligatorio | Obligatorio |
| Selfie con cédula | Obligatorio | Opcional |
| Dirección de residencia | Obligatorio | Obligatorio |
| Categoría de servicio | Obligatorio | No aplica |
| Descripción de habilidades | Obligatorio | No aplica |
| RUT / NIT | Opcional | Opcional |

### 5.2 Flujo de Inicio de Sesión

- **Método principal:** Teléfono + código OTP (para todos los roles).
- **Método alternativo:** Email + contraseña (para administradores y superadmin).
- **2FA obligatorio:** Para roles de administración (Verificador, Soporte, Admin, Superadmin).

---

## 6. Módulos Funcionales — Historias de Usuario y Criterios de Aceptación

---

### MÓDULO A: Autenticación y Registro

**Historia de US-A01:** Como usuario nuevo, quiero registrarme con mi número de teléfono y cédula, para poder acceder a la plataforma de forma segura.

**Criterios de Aceptación:**
1. WHEN usuario ingresa número de teléfono válido THEN sistema SHALL enviar código OTP de 6 dígitos por SMS.
2. WHEN usuario ingresa OTP correcto dentro de 5 minutos THEN sistema SHALL permitir continuar con el registro.
3. WHEN usuario ingresa OTP incorrecto 3 veces THEN sistema SHALL bloquear intentos por 15 minutos.
4. WHEN OTP expira (5 minutos) THEN sistema SHALL permitir solicitar reenvío.
5. WHEN usuario completa datos mínimos (cédula, nombre, teléfono) THEN sistema SHALL crear cuenta con estado "Pendiente de Verificación".
6. WHEN usuario envía foto de cédula THEN sistema SHALL notificar al Verificador para validación.
7. IF usuario ya tiene cédula registrada THEN sistema SHALL mostrar mensaje "Ya existe una cuenta con este documento" y NO crear cuenta.

**Historia de US-A02:** Como usuario registrado, quiero iniciar sesión con mi teléfono y OTP, para acceder rápidamente sin recordar contraseñas.

**Criterios de Aceptación:**
1. WHEN usuario ingresa número registrado THEN sistema SHALL enviar OTP por SMS.
2. WHEN OTP es correcto THEN sistema SHALL autenticar y redirigir al dashboard correspondiente a su rol.
3. IF cuenta está bloqueada o suspendida THEN sistema SHALL mostrar mensaje informativo y NO permitir acceso.
4. WHEN usuario tiene 2FA activo THEN sistema SHALL solicitar segundo factor después del OTP.

**Historia de US-A03:** Como administrador, quiero autenticarme con email y contraseña + 2FA, para garantizar la seguridad del panel de administración.

**Criterios de Aceptación:**
1. WHEN admin ingresa credenciales correctas THEN sistema SHALL solicitar código 2FA (authenticator app o SMS).
2. WHEN 2FA es correcto THEN sistema SHALL otorgar sesión con token JWT de 8 horas.
3. WHEN 2FA falla 3 veces THEN sistema SHALL bloquear sesión y notificar al Superadmin.
4. IF sesión expira THEN sistema SHALL redirigir a login con mensaje de sesión expirada.

**Edge Cases:**
- WHEN usuario intenta registrar cédula ya verificada THEN sistema SHALL rechazar con mensaje claro.
- WHEN servicio SMS no está disponible THEN sistema SHALL ofrecer OTP por email como alternativa.
- WHEN usuario está en zona sin conectividad THEN sistema SHALL cachear último estado y reintentar al recuperar conexión.

---

### MÓDULO B: Gestión de Usuarios y Perfiles

**Historia de US-B01:** Como trabajador, quiero crear y editar mi perfil con mis habilidades, experiencia y zona de cobertura, para que los empleadores me encuentren fácilmente.

**Criterios de Aceptación:**
1. WHEN trabajador completa perfil con categoría, habilidades y dirección THEN sistema SHALL marcar perfil como "Activo".
2. WHEN trabajador sube foto de perfil THEN sistema SHALL validar formato (JPG/PNG) y tamaño (máx. 5MB).
3. WHEN trabajador edita perfil THEN sistema SHALL guardar cambios y actualizar motor de recomendación.
4. WHEN perfil tiene menos de 3 campos obligatorios completos THEN sistema SHALL mostrar badge "Perfil Incompleto" y guiar al usuario.
5. WHEN trabajador selecciona múltiples categorías THEN sistema SHALL permitir hasta 5 categorías principales.
6. WHEN trabajador define zona de cobertura THEN sistema SHALL usar GPS para geolocalizar y permitir ajuste manual del radio (máx. 50km desde Valledupar en Fase 1).

**Historia de US-B02:** Como empleador, quiero crear mi perfil con mi información básica, para poder publicar solicitudes de servicio.

**Criterios de Aceptación:**
1. WHEN empleador completa nombre, dirección y teléfono THEN sistema SHALL permitir publicar solicitudes.
2. WHEN empleador sube foto de perfil THEN sistema SHALL aceptar JPG/PNG hasta 5MB.
3. WHEN empleador registra múltiples direcciones THEN sistema SHALL permitir hasta 3 ubicaciones guardadas.
4. WHEN perfil está completo al 100% THEN sistema SHALL mostrar badge "Perfil Verificado".

**Historia de US-B03:** Como usuario, quiero ver el perfil público de un trabajador con sus calificaciones, experiencia y verificaciones, para tomar una decisión informada.

**Criterios de Aceptación:**
1. WHEN usuario accede al perfil de un trabajador THEN sistema SHALL mostrar: nombre, foto, categorías, calificación promedio, número de trabajos, tiempo de respuesta promedio.
2. WHEN trabajador tiene verificación de identidad THEN sistema SHALL mostrar badge "Identidad Verificada".
3. WHEN trabajador tiene más de 50 trabajos completados THEN sistema SHALL mostrar badge "Trabajador Confiable".
4. WHEN trabajador tiene menos de 3 calificaciones THEN sistema SHALL mostrar "Nuevo en la plataforma" en lugar de calificación numérica.
5. WHEN usuario solicita datos de contacto del trabajador THEN sistema SHALL ocultar teléfono/email hasta que se confirme la contratación.

**Edge Cases:**
- WHEN trabajador intenta cambiar categoría principal THEN sistema SHALL requerir re-verificación si la nueva categoría requiere certificaciones.
- WHEN empleador tiene más de 3 ubicaciones THEN sistema SHALL sugerir eliminar las menos usadas.
- WHEN perfil contiene información ofensiva o fraudulenta THEN sistema SHALL ocultar perfil y notificar a administración.

---

### MÓDULO C: Motor de Match / Recomendación (IA - Fase Básica)

**Historia de US-C01:** Como empleador, quiero recibir recomendaciones de trabajadores basadas en mi solicitud, para encontrar el profesional más adecuado rápidamente.

**Criterios de Aceptación:**
1. WHEN empleador publica solicitud con categoría y descripción THEN sistema SHALL retornar máximo 10 recomendaciones ordenadas por score de similitud.
2. WHEN motor de recomendación calcula score THEN sistema SHALL considerar: categoría del servicio (40%), calificación promedio (25%), distancia geográfica (20%), tiempo de respuesta (15%).
3. WHEN no hay trabajadores disponibles en la categoría THEN sistema SHALL mostrar mensaje "No hay trabajadores disponibles en este momento" con opción de notificar cuando haya disponibilidad.
4. WHEN trabajador recomendado tiene calificación menor a 3.0 THEN sistema SHALL excluirlo de las recomendaciones principales.
5. WHEN múltiples trabajadores tienen score similar (diferencia < 5%) THEN sistema SHALL priorizar al que esté en línea actualmente.
6. WHEN empleador filtra por precio máximo THEN sistema SHALL excluir trabajadores cuya tarifa supere el filtro.
7. WHEN trabajador cambia disponibilidad THEN sistema SHALL actualizar recomendaciones en tiempo real (< 30 segundos).

**Historia de US-C02:** Como trabajador, quiero recibir alertas de solicitudes compatibles con mi perfil, para no perder oportunidades.

**Criterios de Aceptación:**
1. WHEN se publica solicitud que coincide con categoría del trabajador THEN sistema SHALL enviar notificación push within 1 minuto.
2. WHEN trabajador tiene modo "Disponible" activo THEN sistema SHALL incluirlo en recomendaciones.
3. WHEN trabajador tiene modo "No disponible" THEN sistema SHALL excluirlo de todas las recomendaciones.
4. WHEN trabajador recibe más de 5 alertas en 1 hora THEN sistema SHALL agruparlas en digest para evitar saturación.

**Historia de US-C03:** Como empleador, quiero buscar trabajadores manualmente por categoría, nombre o habilidad, para tener control sobre la selección.

**Criterios de Aceptación:**
1. WHEN empleador ingresa término de búsqueda THEN sistema SHALL retornar resultados en menos de 2 segundos.
2. WHEN búsqueda retorna resultados THEN sistema SHALL mostrar cantidad total y paginación (10 por página).
3. WHEN búsqueda no retorna resultados THEN sistema SHALL mostrar sugerencias de categorías similares.
4. WHEN empleador filtra por calificación mínima THEN sistema SHALL aplicar filtro y reordenar resultados.

**Edge Cases:**
- WHEN servicio de IA no está disponible THEN sistema SHALL usar ranking por calificación y distancia como fallback.
- WHEN datos de geolocalización son imprecisos THEN sistema SHALL usar dirección registrada como respaldo.
- WHEN trabajador tiene múltiples categorías THEN sistema SHALL mostrarlo en resultados de cada categoría con score independiente.

---

### MÓDULO D: Visualización 360°

**Historia de US-D01:** Como empleador, quiero ver fotografías 360° del lugar de trabajo o del estado del problema, para entender mejor el contexto antes de contratar.

**Criterios de Aceptación:**
1. WHEN empleador crea solicitud THEN sistema SHALL permitir adjuntar hasta 5 fotografías (JPG/PNG, máx. 10MB cada una).
2. WHEN empleador adjunta imagen 360° THEN sistema SHALL detectar formato equirectangular y habilitar visualizador interactivo.
3. WHEN usuario navega visualización 360° THEN sistema SHALL permitir rotación 360° horizontal y 180° vertical con gestos táctiles o mouse.
4. WHEN imagen carga THEN sistema SHALL mostrar progreso de carga y placeholder de baja resolución mientras carga la imagen completa.
5. WHEN trabajador visualiza solicitud THEN sistema SHALL mostrar imágenes 360° en tamaño ampliado con opción de pantalla completa.
6. WHEN usuario está en dispositivo móvil THEN sistema SHALL activar giróscopo para navegación por movimiento del dispositivo (si está disponible).

**Historia de US-D02:** Como trabajador, quiero subir fotos 360° de trabajos anteriores en mi perfil, para mostrar mi experiencia de forma inmersiva.

**Criterios de Aceptación:**
1. WHEN trabajador sube foto 360° THEN sistema SHALL agregarla a galería de perfil con descripción opcional.
2. WHEN galería tiene más de 10 imágenes THEN sistema SHALL paginar con 5 imágenes por página.
3. WHEN empleador visualiza galería THEN sistema SHALL permitir navegación fluida entre imágenes.
4. WHEN imagen tiene metadatos EXIF THEN sistema SHALL extraer y mostrar fecha y ubicación (si el usuario autoriza).

**Edge Cases:**
- WHEN imagen no es formato 360° válido THEN sistema SHALL tratarla como fotografía estándar.
- WHEN usuario tiene conectividad lenta THEN sistema SHALL cargar versiones de baja resolución primero (progressive loading).
- WHEN navegador no soporta WebGL THEN sistema SHALL ofrecer visualización panorámica 2D como alternativa.

---

### MÓDULO E: Gestión Contractual y Órdenes de Trabajo

**Historia de US-E01:** Como empleador, quiero crear una solicitud de servicio con descripción, categoría, fecha y presupuesto, para que los trabajadores interesados la postulen.

**Criterios de Aceptación:**
1. WHEN empleador crea solicitud THEN sistema SHALL requerir: categoría, descripción (mín. 20 caracteres), fecha preferida, ubicación, rango de presupuesto.
2. WHEN solicitud se publica THEN sistema SHALL notificar a trabajadores compatibles en zona de cobertura.
3. WHEN solicitud tiene menos de 20 caracteres en descripción THEN sistema SHALL mostrar validación "Descripción muy corta".
4. WHEN presupuesto supera $500.000 COP THEN sistema SHALL sugerir categorías premium.
5. WHEN solicitud se publica THEN sistema SHALL generar costo de 200 monedas del monedero del empleador.
6. IF empleador no tiene saldo suficiente THEN sistema SHALL redirigir a recarga de monedas antes de publicar.
7. WHEN solicitud está activa THEN sistema SHALL mostrarla por 7 días o hasta que sea asignada.

**Historia de US-E02:** Como trabajador, quiero postularme a una solicitud pagando monedas o aceptando comisión, para conseguir trabajo.

**Criterios de Aceptación:**
1. WHEN trabajador postula con monedas THEN sistema SHALL debitar entre 20-50 monedas según categoría.
2. WHEN trabajador elige comisión THEN sistema SHALL registrar postulación sin débito y aplicar comisión al completar trabajo.
3. WHEN trabajador no tiene saldo THEN sistema SHALL ofrecer opciones: recargar monedas o elegir comisión.
4. WHEN trabajador postula THEN sistema SHALL enviar perfil resumido al empleador (nombre, calificación, categoría, distancia).
5. WHEN empleador recibe postulación THEN sistema SHALL notificar inmediatamente.
6. WHEN trabajador postula a la misma solicitud 2 veces THEN sistema SHALL rechazar con mensaje "Ya te postulaste a esta solicitud".

**Historia de US-E03:** Como empleador, quiero aceptar la postulación de un trabajador, para formalizar la contratación.

**Criterios de Aceptación:**
1. WHEN empleador acepta postulación THEN sistema SHALL cambiar estado de solicitud a "Asignada".
2. WHEN solicitud se asigna THEN sistema SHALL revelar datos de contacto mutuos (nombre, teléfono).
3. WHEN solicitud se asigna THEN sistema SHALL crear "Orden de Trabajo" con: ID único, fecha de creación, acuerdos registrados.
4. WHEN solicitud se asigna THEN sistema SHALL notificar al trabajador seleccionado y rechazar automáticamente las demás postulaciones.
5. WHEN empleador acepta postulación THEN sistema SHALL iniciar timer de 24 horas para confirmación del trabajador.
6. WHEN trabajador no confirma en 24 horas THEN sistema SHALL liberar la solicitud y permitir nuevas postulaciones.

**Historia de US-E04:** Como trabajador, quiero confirmar una asignación y gestionar el ciclo de vida del trabajo (en proceso, completado), para mantener trazabilidad.

**Criterios de Aceptación:**
1. WHEN trabajador confirma asignación THEN sistema SHALL cambiar estado a "En Proceso".
2. WHEN trabajador marca trabajo como "Completado" THEN sistema SHALL notificar al empleador para confirmación.
3. WHEN empleador confirma completado THEN sistema SHALL cambiar estado a "Finalizado" y activar sistema de calificación.
4. WHEN empleador rechaza completado THEN sistema SHALL abrir disputa automática.
5. WHEN trabajo está "En Proceso" por más de 30 días THEN sistema SHALL notificar a ambas partes y ofrecer opciones de cierre.
6. WHEN trabajo se cancela por empleador THEN sistema SHALL devolver monedas al trabajador si pagó por postulación.
7. WHEN trabajo se cancela por trabajador THEN sistema SHALL registrar en historial y afectar reputación negativamente.

**Edge Cases:**
- WHEN empleador publica solicitud con categoría inexistente THEN sistema SHALL rechazar y sugerir categorías válidas.
- WHEN trabajador acepta pero no hay forma de contacto THEN sistema SHALL mediar comunicación a través del chat interno.
- WHEN ambas partes cancelan simultáneamente THEN sistema SHALL registrar como "Mutua cancelación" sin afectar reputación.

---

### MÓDULO F: Monedero Digital y Pagos

**Historia de US-F01:** Como usuario, quiero ver mi saldo de monedas virtuales y historial de transacciones, para controlar mis finanzas en la plataforma.

**Criterios de Aceptación:**
1. WHEN usuario accede a monedero THEN sistema SHALL mostrar saldo actual en monedas y equivalente en COP.
2. WHEN usuario ve historial THEN sistema SHALL listar transacciones ordenadas por fecha (más reciente primero) con: tipo (recarga/gasto/comisión), monto, fecha, descripción.
3. WHEN historial tiene más de 20 transacciones THEN sistema SHALL paginar con 20 por página.
4. WHEN saldo es 0 THEN sistema SHALL mostrar mensaje "Tu monedero está vacío" con botón de recarga prominente.
5. WHEN usuario tiene transacciones THEN sistema SHALL permitir filtrar por tipo y rango de fechas.

**Historia de US-F02:** Como usuario, quiero recargar monedas virtuales vía Nequi, para poder publicar o postularme a servicios.

**Criterios de Aceptación:**
1. WHEN usuario solicita recarga THEN sistema SHALL mostrar montos predefinidos: 1.000, 5.000, 10.000, 20.000, 50.000 monedas.
2. WHEN usuario selecciona monto THEN sistema SHALL generar enlace de pago Nequi dinámico.
3. WHEN pago Nequi es confirmado automáticamente THEN sistema SHALL acreditar monedas en monedero sin aprobación manual.
4. WHEN pago no se confirma en 10 minutos THEN sistema SHALL cancelar transacción y notificar al usuario.
5. WHEN recarga es exitosa THEN sistema SHALL mostrar confirmación con nuevo saldo y enviar email de comprobante.
6. IF usuario intenta recargar más de $200.000 COP en una transacción THEN sistema SHALL requerir verificación adicional.

**Historia de US-F03:** Como trabajador, quiero que la comisión se calcule y descuente automáticamente al finalizar un trabajo, para no preocuparme por pagos manuales.

**Criterios de Aceptación:**
1. WHEN trabajo se finaliza con comisión THEN sistema SHALL calcular porcentaje según rango: < $100K = 5%, $110K-$300K = 7%, > $300K = 10%.
2. WHEN comisión se calcula THEN sistema SHALL mostrar desglose al trabajador antes de confirmar.
3. WHEN trabajador confirma THEN sistema SHALL descontar comisión del saldo del empleador (si aplica) o registrar deuda pendiente.
4. WHEN comisión no puede cobrarse THEN sistema SHALL registrar pendiente y bloquear nuevas postulaciones hasta regularizar.
5. WHEN empleador paga directamente al trabajador (fuera de plataforma) THEN sistema SHALL permitir registro manual del pago para trazabilidad.

**Edge Cases:**
- WHEN recarga falla por error de red THEN sistema SHALL reintentar automáticamente 2 veces antes de notificar.
- WHEN monedero tiene saldo negativo THEN sistema SHALL bloquear publicaciones y postulaciones.
- WHEN usuario solicita retiro de monedas THEN sistema SHALL ofrecer transferencia bancaria con mínimo de 10.000 monedas.

---

### MÓDULO G: Sistema de Reputación y Confianza

**Historia de US-G01:** Como empleador, quiero calificar al trabajador después de un servicio completado, para contribuir a la confianza de la comunidad.

**Criterios de Aceptación:**
1. WHEN trabajo se finaliza THEN sistema SHALL enviar solicitud de calificación al empleador dentro de 48 horas.
2. WHEN empleador califica THEN sistema SHALL solicitar: estrellas (1-5), comentario opcional (mín. 10 caracteres si se incluye).
3. WHEN calificación se envía THEN sistema SHALL actualizar promedio del trabajador y mostrar en su perfil.
4. WHEN empleador no califica en 48 horas THEN sistema SHALL enviar recordatorio y registrar como "Sin calificación" después de 7 días.
5. WHEN calificación es 1 o 2 estrellas THEN sistema SHALL sugerir al empleador abrir proceso de disputa.
6. WHEN calificación contiene lenguaje ofensivo THEN sistema SHALL filtrar y revisar antes de publicar.

**Historia de US-G02:** Como trabajador, quiero calificar al empleador después de un servicio, para alertar a otros trabajadores sobre experiencias.

**Criterios de Aceptación:**
1. WHEN trabajo se finaliza THEN sistema SHALL enviar solicitud de calificación al trabajador.
2. WHEN trabajador califica THEN sistema SHALL solicitar: estrellas (1-5), comentario opcional.
3. WHEN calificación se registra THEN sistema SHALL actualizar perfil público del empleador.
4. WHEN empleador tiene calificación promedio menor a 2.5 THEN sistema SHALL mostrar alerta "Perfil con baja calificación" en búsquedas.

**Historia de US-G03:** Como usuario, quiero ver badges de confianza en los perfiles, para identificar rápidamente usuarios confiables.

**Criterios de Aceptación:**
1. WHEN trabajador tiene verificación de identidad aprobada THEN sistema SHALL mostrar badge "Identidad Verificada" (icono de escudo verde).
2. WHEN trabajador tiene más de 50 trabajos completados THEN sistema SHALL mostrar badge "Trabajador Confiable".
3. WHEN trabajador tiene calificación promedio > 4.5 con más de 20 calificaciones THEN sistema SHALL mostrar badge "Top Trabajador".
4. WHEN trabajador responde en promedio menos de 30 minutos THEN sistema SHALL mostrar badge "Respuesta Rápida".
5. WHEN empleador tiene historial de pagos puntuales THEN sistema SHALL mostrar badge "Empleador Confiable".
6. WHEN usuario acumula 3 reportes negativos THEN sistema SHALL suspender cuenta temporalmente y revisar.

**Edge Cases:**
- WHEN calificación es manipulada (múltiples calificaciones del mismo dispositivo) THEN sistema SHALL detectar y excluir del promedio.
- WHEN trabajador califica a sí mismo THEN sistema SHALL rechazar y registrar intento.
- WHEN ambas partes califican negativamente THEN sistema SHALL escalar a mediación automática.

---

### MÓDULO H: Comunicación y Notificaciones

**Historia de US-H01:** Como usuario, quiero recibir notificaciones en tiempo real sobre eventos importantes, para no perderme oportunidades ni actualizaciones.

**Criterios de Aceptación:**
1. WHEN ocurre evento relevante THEN sistema SHALL enviar notificación in-app inmediatamente.
2. WHEN usuario tiene email registrado THEN sistema SHALL enviar email transaccional para eventos críticos (asignación, disputa, pago).
3. WHEN usuario tiene teléfono registrado THEN sistema SHALL enviar SMS para eventos de seguridad (OTP, cambio de contraseña).
4. WHEN usuario tiene navegador compatible THEN sistema SHALL solicitar permiso para Web Push notifications.
5. WHEN usuario recibe notificación THEN sistema SHALL permitir: marcar leída, archivar, ir al detalle.
6. WHEN notificación es de alta prioridad THEN sistema SHALL mostrar toast persistente hasta que el usuario la descarte.
7. WHEN usuario tiene más de 10 notificaciones sin leer THEN sistema SHALL mostrar badge con contador.

**Historia de US-H02:** Como usuario, quiero configurar mis preferencias de notificación, para recibir solo lo que me interesa.

**Criterios de Aceptación:**
1. WHEN usuario accede a configuración THEN sistema SHALL mostrar categorías de notificación: Nuevas solicitudes, Postulaciones, Asignaciones, Pagos, Calificaciones, Disputas, Marketing.
2. WHEN usuario desactiva categoría THEN sistema SHALL dejar de enviar notificaciones de ese tipo por todos los canales.
3. WHEN usuario cambia preferencias THEN sistema SHALL aplicar cambios inmediatamente.
4. WHEN usuario activa "No molestar" THEN sistema SHALL silenciar notificaciones push en horario configurado.

**Historia de US-H03:** Como empleador y trabajador, quiero tener un chat integrado en la orden de trabajo, para comunicarnos durante el servicio.

**Criterios de Aceptación:**
1. WHEN orden de trabajo se asigna THEN sistema SHALL habilitar chat entre empleador y trabajador.
2. WHEN usuario envía mensaje THEN sistema SHALL entregar en tiempo real (< 2 segundos).
3. WHEN usuario está offline THEN sistema SHALL almacenar mensajes y entregar al reconectar.
4. WHEN chat contiene información de pago fuera de plataforma THEN sistema SHALL marcar como "Pago externo registrado" y recomendar usar monedero.
5. WHEN orden se cierra THEN sistema SHALL archivar chat pero mantener disponible para consulta por 90 días.

**Edge Cases:**
- WHEN usuario bloquea notificaciones del navegador THEN sistema SHALL notificar que no recibirá alertas push y sugerir activar email.
- WHEN servicio de SMS falla THEN sistema SHALL usar email como respaldo y registrar intento fallido.
- WHEN chat recibe spam o contenido ofensivo THEN sistema SHALL filtrar y reportar al sistema de soporte.

---

### MÓDULO I: Resolución de Disputas

**Historia de US-I01:** Como usuario, quiero abrir una disputa cuando un servicio no se completó correctamente, para proteger mis intereses.

**Criterios de Aceptación:**
1. WHEN usuario reporta problema THEN sistema SHALL crear disputa con: motivo (selección), descripción, evidencia (fotos/documentos), fecha del incidente.
2. WHEN disputa se abre THEN sistema SHALL notificar a la contraparte y al equipo de Soporte/Mediador.
3. WHEN disputa se crea THEN sistema SHALL congelar la calificación de ambas partes hasta resolución.
4. WHEN evidencia se adjunta THEN sistema SHALL aceptar: fotos (hasta 5), documentos PDF (hasta 3), capturas de chat.
5. WHEN disputa se registra THEN sistema SHALL asignar ID único y número de caso.
6. WHEN ambas partes tienen evidencia THEN sistema SHALL mostrar timeline de eventos con timestamps.

**Historia de US-I02:** Como Soporte/Mediador, quiero revisar disputas y emitir una resolución justa, para mantener la confianza en la plataforma.

**Criterios de Aceptación:**
1. WHEN mediador revisa disputa THEN sistema SHALL mostrar: evidencia de ambas partes, historial de interacciones, reputación de ambos usuarios.
2. WHEN mediador toma decisión THEN sistema SHALL registrar: resolución, justificación, acciones tomadas (reembolso, suspensión, etc.).
3. WHEN resolución implica reembolso THEN sistema SHALL ejecutar transferencia de monedas automáticamente.
4. WHEN resolución implica suspensión THEN sistema SHALL desactivar cuenta del usuario sancionado temporalmente.
5. WHEN ambas partes aceptan resolución THEN sistema SHALL cerrar disputa y restaurar capacidad de calificación.
6. WHEN una parte apela THEN sistema SHALL escalar a Administrador para revisión final.
7. WHEN disputa no se resuelve en 7 días THEN sistema SHALL escalar automáticamente a Superadmin.

**Historia de US-I03:** Como usuario, quiero ver el estado de mi disputa en tiempo real, para saber qué está pasando con mi caso.

**Criterios de Aceptación:**
1. WHEN usuario accede a disputa THEN sistema SHALL mostrar: estado (Abierta, En Revisión, Resuelta, Apelada), fecha de apertura, tiempo estimado de resolución.
2. WHEN estado cambia THEN sistema SHALL notificar a ambas partes por in-app y email.
3. WHEN disputa se resuelve THEN sistema SHALL enviar resumen detallado de la decisión a ambos usuarios.

**Edge Cases:**
- WHEN disputa es por monto menor a $50.000 COP THEN sistema SHALL ofrecer resolución express con mediación automática.
- WHEN usuario intenta abrir disputa después de 30 días THEN sistema SHALL rechazar con mensaje "Plazo de reclamación vencido".
- WHEN ambas partes abren disputas simultáneas THEN sistema SHALL fusionar en un solo caso.

---

### MÓDULO J: Panel de Administración

**Historia de US-J01:** Como Administrador, quiero gestionar usuarios (aprobar, suspender, eliminar), para mantener la integridad de la plataforma.

**Criterios de Aceptación:**
1. WHEN admin accede a lista de usuarios THEN sistema SHALL mostrar: nombre, rol, estado, fecha de registro, calificación, número de servicios.
2. WHEN admin aprueba cuenta THEN sistema SHALL cambiar estado a "Activo" y notificar al usuario.
3. WHEN admin suspends cuenta THEN sistema SHALL bloquear acceso y notificar al usuario con motivo.
4. WHEN admin elimina cuenta THEN sistema SHALL requerir confirmación y mantener datos en auditoría por 2 años.
5. WHEN admin busca usuarios THEN sistema SHALL permitir filtrar por: rol, estado, fecha, categoría, calificación.
6. WHEN admin accede a dashboard THEN sistema SHALL mostrar métricas: usuarios activos, servicios completados, ingresos totales, disputas abiertas.

**Historia de US-J02:** Como Verificador, quiero validar documentos de identidad de los usuarios, para garantizar la seguridad de la plataforma.

**Criterios de Aceptación:**
1. WHEN verificador recibe solicitud THEN sistema SHALL mostrar: foto de cédula, selfie con cédula, datos registrados.
2. WHEN verificador aprueba THEN sistema SHALL actualizar estado del usuario a "Verificado" y emitir badge.
3. WHEN verificador rechaza THEN sistema SHALL solicitar razón y notificar al usuario para que reenvíe documentos.
4. WHEN verificador tiene más de 10 solicitudes pendientes THEN sistema SHALL mostrar alerta de carga de trabajo.
5. WHEN verificación tarda más de 48 horas THEN sistema SHALL escalar a Administrador.

**Historia de US-J03:** Como Superadmin, quiero tener acceso total al sistema con auditoría completa, para garantizar la operación segura.

**Criterios de Aceptación:**
1. WHEN Superadmin accede THEN sistema SHALL mostrar panel completo: usuarios, finanzas, configuración, logs de auditoría.
2. WHEN Superadmin ejecuta acción crítica THEN sistema SHALL requerir confirmación y registrar en log de auditoría.
3. WHEN Superadmin modifica configuración THEN sistema SHALL aplicar cambios y notificar a Administradores.
4. WHEN Superadmin revisa finanzas THEN sistema SHALL mostrar: ingresos por monedas, comisiones, recargas, retiros, balance neto.
5. WHEN Superadmin accede a logs THEN sistema SHALL permitir búsqueda por: usuario, fecha, acción, IP.

**Edge Cases:**
- WHEN admin intenta eliminar su propia cuenta THEN sistema SHALL rechazar con "No puedes eliminar tu propia cuenta".
- WHEN verificador aprueba documentos sospechosos THEN sistema SHALL registrar y escalar a Superadmin.
- WHEN Superadmin suspende a otro Superadmin THEN sistema SHALL requerir aprobación de 2 Superadmins.

---

## 7. Requerimientos No Funcionales

### 7.1 Rendimiento

| Requisito | Métrica |
|:---|:---|
| Tiempo de carga inicial PWA | < 3 segundos en 4G |
| Respuesta de API | < 500ms en 95% de las peticiones |
| Motor de recomendación | < 2 segundos para retornar resultados |
| Búsqueda de texto | < 2 segundos |
| Chat en tiempo real | Entrega de mensajes < 2 segundos |
| Notificaciones push | Entrega < 30 segundos |
| Visualización 360° | Carga inicial < 5 segundos, interacción sin lag |

### 7.2 Escalabilidad

- Soportar inicialmente 1.000 usuarios concurrentes en Valledupar.
- Arquitectura escalable horizontalmente para llegar a 100.000 usuarios a nivel nacional.
- Base de datos con réplicas para alta disponibilidad.

### 7.3 Seguridad

| Requisito | Descripción |
|:---|:---|
| Cifrado en tránsito | TLS 1.3 en todas las comunicaciones |
| Cifrado en reposo | AES-256 para datos sensibles (cédulas, datos financieros) |
| Autenticación | JWT con expiración de 8 horas, refresh tokens |
| Rate limiting | Máximo 100 requests/minuto por usuario |
| Protección de datos | Cumplimiento Ley 1581 de 2012 (Habeas Data Colombia) |
| Auditoría | Log inmutable de acciones críticas por 2 años |
| Contraseñas | Bcrypt con salt, mínimo 8 caracteres, complejidad mixta |

### 7.4 Usabilidad y Accesibilidad

- Diseño responsive mobile-first (PWA optimizada para móviles).
- Navegación máxima 3 clics para llegar a cualquier funcionalidad.
- Soporte para lectores de pantalla (WCAG 2.1 nivel AA).
- Contraste mínimo 4.5:1 para texto, 3:1 para elementos UI.
- Fuentes legibles: mínimo 14px para cuerpo de texto.
- Soporte offline básico: visualización de perfil, historial,聊天缓存.

### 7.5 Disponibilidad

- Uptime mínimo: 99.5% (máx. 43.8 horas de downtime al año).
- Mantenimiento programado: domingos 2:00 AM - 6:00 AM (hora local).
- Backup automático diario con retención de 30 días.
- Disaster recovery: RPO < 1 hora, RTO < 4 horas.

### 7.6 Compatibilidad

- Navegadores: Chrome 90+, Safari 14+, Firefox 88+, Edge 90+.
- Sistemas operativos móviles: Android 8+, iOS 14+.
- Resolución mínima: 360px de ancho.
- Soporte para conexiones 3G/4G/5G y WiFi.

---

## 8. Requerimientos Legales y Normativos

| Requisito | Descripción |
|:---|:---|
| Ley 1581 de 2012 | Habeas Data: consentimiento informado para recolección de datos personales |
| Ley 1429 de 2010 | Formalización del trabajo: mecanismos para facilitar la formalización progresiva |
| Ley 1562 de 2012 | Riesgos laborales: información y enlace a esquemas de seguridad social |
| Ley 2300 de 2023 | Seguridad social para trabajadores independientes: guía de orientación |
| RGPD (si aplica) | Protección de datos para usuarios internacionales futuros |
| Términos y Condiciones | Documento legal aceptado durante registro |
| Política de Privacidad | Descripción clara de uso de datos, cookies y terceros |

---

## 9. Fuera del Alcance (Fase 1)

- Pagos con tarjeta de crédito/débito directos (solo Nequi).
- Integración con bancos tradicionales para retiros.
- Sistema de seguros para trabajadores.
- App nativa iOS/Android (solo PWA).
- Gamificación avanzada (puntos, niveles, recompensas).
- Marketplace de herramientas o productos.
- Soporte multiidioma (solo español).
- Integración con redes sociales para login (solo teléfono + OTP).

---

## 10. Preguntas Abiertas

| # | Pregunta | Impacto | Estado |
|:--|:---|:---|:---|
| 1 | ¿Se necesita integración con RUES para verificación de cédulas en tiempo real? | Alto | Pendiente |
| 2 | ¿Qué pasarela de SMS se usará (Twilio,本地供应商)? | Medio | Pendiente |
| 3 | ¿Se requiere certificado SSL wildcard para el dominio? | Medio | Pendiente |
| 4 | ¿Cuál es el presupuesto estimado para hosting y servicios cloud en Fase 1? | Alto | Pendiente |
| 5 | ¿Se necesita cumplimiento PCI-DSS para manejo de monedas virtuales? | Alto | Pendiente |
| 6 | ¿Los datos de cédula se almacenan o solo se verifican y descartan? | Alto | Pendiente |
| 7 | ¿Se requiere interfaz de administración móvil o solo web? | Bajo | Pendiente |

---

## 11. Matriz de Trazabilidad

| Módulo | Historias | Roles Asociados | Fase |
|:---|:---|:---|:---|
| A: Autenticación | US-A01, US-A02, US-A03 | Todos los roles | 1 |
| B: Perfiles | US-B01, US-B02, US-B03 | Trabajador, Empleador | 1 |
| C: Motor IA | US-C01, US-C02, US-C03 | Trabajador, Empleador | 1 |
| D: Visualización 360° | US-D01, US-D02 | Trabajador, Empleador | 1 |
| E: Contratos | US-E01, US-E02, US-E03, US-E04 | Trabajador, Empleador | 1 |
| F: Monedero | US-F01, US-F02, US-F03 | Todos los roles | 1 |
| G: Reputación | US-G01, US-G02, US-G03 | Trabajador, Empleador | 1 |
| H: Notificaciones | US-H01, US-H02, US-H03 | Todos los roles | 1 |
| I: Disputas | US-I01, US-I02, US-I03 | Todos los roles | 1 |
| J: Administración | US-J01, US-J02, US-J03 | Admin, Verificador, Superadmin | 1 |

---

## 12. Glosario

| Término | Definición |
|:---|:---|
| **Moneda Virtual** | Unidad digital interna de la plataforma (1 moneda = $100 COP) |
| **Chambe** | Término coloquial para "trabajo" o "empleo" en Colombia |
| **OTP** | One-Time Password, código de un solo uso enviado por SMS |
| **PWA** | Progressive Web App, aplicación web con capacidades nativas |
| **Score de Similitud** | Valor numérico calculado por el algoritmo de matching (0-100) |
| **Escrow** | Mecanismo de depósito temporal para garantizar pagos |
| **2FA** | Autenticación de dos factores |
| **JWT** | JSON Web Token, mecanismo de autenticación stateless |
| **WCAG** | Web Content Accessibility Guidelines, estándar de accesibilidad web |

---

*Documento generado como parte del Proyecto de Grado — Universidad Popular del Cesar*
*Versión: 1.0 — Fecha: Julio 2026*
