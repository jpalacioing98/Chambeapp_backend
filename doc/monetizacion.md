# Sistema de Monetización - Chambea App

Este documento detalla el modelo de negocio y el sistema de monetización híbrido diseñado para **Chambea App**, una plataforma enfocada en trabajadores informales. El sistema opera mediante una economía de moneda virtual y un esquema de comisiones por rangos de ingresos, utilizando métodos de recarga integrados con soluciones empresariales locales.

---

## 1. Economía de la Moneda Virtual

La plataforma utiliza una moneda digital interna para simplificar las transacciones dentro de la aplicación y evitar la fricción constante de micropagos tradicionales.

*   **Valor de Cambio Fijo:** 
    $$\text{1 Moneda Virtual} = \$100 \text{ COP (Pesos Colombianos)}$$

---

## 2. Flujo de Monetización para Clientes (Solicitantes)

Los clientes particulares que requieran un servicio deberán adquirir monedas virtuales para poder publicar su requerimiento.

*   **Costo de Publicación:** **200 monedas** (equivalente a $\$20.000$ COP) por cada solicitud de servicio creada.
*   **Privacidad:** Los datos de contacto del cliente permanecen ocultos inicialmente y solo se revelarán al prestador del servicio una vez que el solicitante acepte formalmente a un trabajador.

---

## 3. Flujo de Monetización para Trabajadores (Prestadores de Servicio)

Para garantizar la accesibilidad y dar opciones de flexibilidad al trabajador, se implementará un **modelo híbrido** configurable para aplicar a las ofertas de empleo:

### Opción A: Pago por Aplicación (Monedas)
El trabajador puede gastar una pequeña cantidad de monedas de su monedero virtual para postularse a una oferta. El costo varía según la categoría del servicio:
*   **Rango de costo:** Entre **20 y 50 monedas** (equivalente a un valor entre $\$2.000$ y $\$5.000$ COP).

### Opción B: Comisión por Porcentaje del Trabajo
Si el trabajador prefiere no gastar monedas por adelantado, puede optar por una comisión que se descontará del valor total del trabajo una vez sea completado y pagado. Las comisiones se estructuran bajo los siguientes rangos:

| Rango de Valor del Trabajo (COP) | Porcentaje de Comisión |
| :--- | :--- |
| Menos de $\$100.000$ | **5%** |
| Entre $\$110.000$ y $\$300.000$ | **7%** |
| Más de $\$300.000$ | **10%** |

---

## 4. Gestión Financiera e Integración Tecnológica

Para brindar transparencia y evitar el uso de pasarelas de pago tradicionales de alto costo para el usuario, se estructurará el sistema de la siguiente manera:

### Panel de Gestión Financiera (Monedero Digital)
Cada perfil de usuario (tanto cliente como trabajador) contará con un apartado financiero visible donde podrá:
*   Ver el saldo actual de sus monedas virtuales.
*   Revisar el historial de transacciones (recargas, gastos por solicitudes o postulaciones, y comisiones).

### Pasarela de Recarga Automatizada (Integración con Nequi)
Para automatizar la compra de los paquetes de monedas sin pagar altas tarifas de intermediación, se utilizarán las **soluciones para negocios de Nequi**:
*   La recarga se hará directamente desde la app mediante la integración de la API de Nequi o enlaces de pago dinámicos.
*   El sistema de Chambea App detectará automáticamente la confirmación de la transferencia empresarial.
*   Una vez verificado el pago por el sistema, las monedas se acreditarán de inmediato en el monedero digital del usuario sin necesidad de una aprobación manual.