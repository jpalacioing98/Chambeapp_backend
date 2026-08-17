# Documento Base para Ingeniería de Requerimientos

Proyecto: Plataforma Inteligente para la Contratación de Servicios Laborales con IA y Visualización 360 en Valledupar 

---

## 1. Información General del Proyecto

* 
**Autores:** Jose David Palacio Mejía y Victor Alfonzo Ardila Montalván.


* 
**Director:** Amilkar Sierra Romano.


* 
**Institución:** Universidad Popular del Cesar.


* 
**Línea/Sub-línea de Investigación:** Transformación digital / Sistemas inteligentes.


* 
**Grupo de Investigación:** Gisico.
---

## 2. Definición del Problema (El "Por Qué")

Existe una **ausencia de mecanismos digitales integrales** capaces de transformar el trabajo informal de corta duración (como plomería, jardinería y reparaciones) en oportunidades organizadas, trazables y progresivamente formales.

### Factores Clave del Problema:

* 
**Alta Informalidad:** Más del 55% de la población ocupada en Colombia está en la informalidad (datos 2025-2026), afectando especialmente a ciudades intermedias como Valledupar.


* 
**Falta de Trazabilidad:** Inexistencia de contratos formales, nula regulación y falta de registro de ingresos del "rebusque".


* 
**Vacío Tecnológico:** Las soluciones actuales son intermediaciones informales que no contemplan la normativa de protección social (como la Ley 1429 de 2010 y la Ley 1562 de 2012).



---

## 3. Propuesta de Solución (El "Qué")

Desarrollar una **plataforma digital inteligente e interactiva** (móvil/web) que conecte de manera eficiente a empleadores y trabajadores de servicios ocasionales en Valledupar, integrando:

1. 
**Inteligencia Artificial (IA):** Para recomendación y asignación óptima de servicios.


2. 
**Visualización 3D:** Para mejorar la interacción con los servicios y escenarios de trabajo.


3. 
**Mecanismos de Formalización:** Trazabilidad de ingresos, reputación digital y enlace/soporte a esquemas de seguridad social.



---

## 4. Objetivos Específicos (Estrategia de Desarrollo)

Para efectos de la Ingeniería de Requerimientos, los objetivos marcan las fases de desarrollo del software:

* 
**Fase 1 (Análisis):** Identificar perfiles de usuarios, tipos de servicios y dinámicas contractuales en Valledupar.


* 
**Fase 2 (Diseño):** Diseñar la arquitectura de software y los módulos funcionales.


* 
**Fase 3 (Algoritmia - IA):** Desarrollar el motor de recomendación y asignación basado en perfiles, habilidades y comportamiento.


* 
**Fase 4 (Interfaz - 3D):** Desarrollar el módulo de visualización interactiva 3D/360.


* 
**Fase 5 (Confianza y Formalización):** Implementar las herramientas de registro de transacciones, historial de ingresos y sistema de calificación.



---

## 5. Núcleo para la Ingeniería de Requerimientos (Módulos del Sistema)

A partir de la justificación y los objetivos del proyecto, se identifican los siguientes macro-módulos para empezar a redactar las **Historias de Usuario (User Stories)** o **Casos de Uso**:

### A. Gestión de Usuarios y Perfiles

* 
**Registro Segmentado:** Distinción de roles (Trabajador Independiente / Empleador).


* 
**Perfil de Habilidades:** Registro detallado de competencias, experiencia y preferencias del trabajador.


* 
**Sistema de Reputación:** Módulo de calificación, comentarios e historial de servicios prestados para generar confianza.



### B. Motor de Match / Recomendación (IA)

* 
**Búsqueda Inteligente:** Procesamiento de perfiles mediante algoritmos de similitud y vectorización de información.


* 
**Asignación Automatizada:** Sugerencia de trabajadores ideales para tareas específicas según necesidades puntuales del empleador.



### C. Módulo de Visualización Interactiva 3D

* 
**Simulación de Entornos:** Representación gráfica en 3D/360 de escenarios de trabajo, ubicaciones o especificaciones técnicas del servicio para mitigar la incertidumbre antes de contratar.



### D. Gestión Contractual y Trazabilidad (Hacia la Formalización)

* 
**Registro de Servicios:** Creación, aceptación y seguimiento en tiempo real de órdenes de trabajo de corta duración.


* 
**Pasarela de Ingresos:** Registro contable e historial de ingresos de los trabajadores.


* 
**Mecanismo de Alerta/Enlace Legal:** Notificaciones orientadas a la formalización e información para el acceso a seguridad social y riesgos laborales (Soporte Ley 1429 y 1562).



### E. Comunicación y Notificaciones

* 
**Alertas en Tiempo Real:** Notificaciones push/mensajería para la confirmación de servicios, cancelaciones o actualizaciones.



---

## 6. Requerimientos No Funcionales Clave (Atributos de Calidad)

* 
**Usabilidad y Accesibilidad:** El diseño debe estar centrado en el usuario con interfaces intuitivas, dado que el público objetivo incluye trabajadores informales con distintos niveles de alfabetización digital.


* 
**Transparencia Algorítmica:** El sistema de recomendación por IA y el sistema de reputación deben ser equitativos y claros para evitar sesgos.


* 
**Seguridad de Datos:** Protección de la información financiera y personal de los usuarios (Trazabilidad y Registro seguro).


