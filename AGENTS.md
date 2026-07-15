# Guía de Agentes y Skills para el Proyecto Holtmont (AGENTS.md)

Este documento define el contexto técnico, las reglas de negocio y las "skills" que los agentes de IA (y desarrolladores) deben utilizar al interactuar con el código base del sistema Holtmont. Al trabajar en este repositorio, debes adherirte estrictamente a estas pautas para evitar romper funcionalidades críticas.

## 1. Dominio del Stack Tecnológico (GAS + Vue.js Monolítico)

- **Backend (Google Apps Script - GAS):**
  - Todo el código backend reside en `CODIGO.js`.
  - El frontend se comunica con el backend exclusivamente mediante `google.script.run`.
  - No intentes usar librerías de Node.js en el backend, el entorno de ejecución es Google Apps Script.
- **Frontend Monolítico:**
  - Toda la interfaz de usuario reside en un único archivo `index.html`.
  - El proyecto utiliza **Vue.js** importado mediante CDN (sin build step / no Node.js).
  - No introduzcas herramientas de compilación como Webpack o Vite. Todo el código CSS, HTML y JS del frontend debe estar inyectado o definido en línea dentro del propio `index.html`.

## 2. Prevención de Condiciones de Carrera y Duplicación

- **Frontend `_tempId`:**
  - Al crear una nueva fila, el frontend genera un `_tempId` y envía la solicitud asíncrona.
  - El frontend bloquea envíos duplicados con una bandera reactiva `isSubmitting`.
- **Backend Gatekeeper:**
  - La función `internalBatchUpdateTasks` actúa como protector (Gatekeeper). Utiliza `CacheService` usando el `_tempId` para bloquear ejecuciones concurrentes en la misma fila.
- **Resolución de Conflictos:**
  - Si un `FOLIO` no se encuentra, el sistema **siempre** debe intentar hacer coincidir las filas por la combinación de `CONCEPTO` y `FECHA`. Generar un nuevo `FOLIO` es el último recurso.
- **Respuesta Esperada:**
  - Las funciones backend como `apiSaveTrackerBatch` o `apiSavePPCData` deben retornar el objeto actualizado completo mediante `res.data` para que el frontend pueda fusionarlo y setear `_isNew = false`.

## 3. Reglas de Negocio Únicas (Routing y Sincronización)

- **El Caso Especial de Antonia (Ventas):**
  - Cualquier tarea originada desde `ANTONIA_VENTAS` (prefijo de folio "AV-") requiere "Reverse Sync" (sincronización bidireccional). Las actualizaciones hechas por otros miembros del equipo a esas tareas deben sincronizarse de vuelta a la hoja `ANTONIA_VENTAS`.
  - **Restricción de Enrutamiento Global:** Para cualquier otro usuario, está estrictamente prohibido enviar tareas a hojas que terminen en `(VENTAS)`. El código debe eliminar globalmente este sufijo usando `.replace(/\s*\(VENTAS\)/ig, "").trim()` (ver `apiSavePPCData` y `apiSaveTrackerBatch`).
- **Distribución Lateral ("Papa Caliente"):**
  - La delegación lateral y el seguimiento del equipo utilizan la columna `INVOLUCRADOS`. Modificar la lógica aquí debe hacerse con cuidado y respetando el "timeline" (`ESTATUS`). La columna `VENDEDOR` es exclusiva para asignaciones desde `ANTONIA_VENTAS`.

## 4. Manejo Avanzado de Google Sheets y Procesamiento de Datos

- **Búsqueda Dinámica de Encabezados:**
  - Las hojas de cálculo del personal tienen elementos de UI sobre los datos. No asumas que la fila 1 contiene los encabezados. Busca de forma dinámica el array de celdas que coincida estrictamente con elementos como `"ID"`.
- **Comparación Insensible (Case-Insensitive):**
  - Los datos que vienen del frontend pueden tener claves en minúscula (ej., `folio`). Todas las iteraciones y validaciones críticas (como buscar `FOLIO` o `ID`) deben usar `.toUpperCase().trim()`.
- **Evaluación de Progreso (AVANCE):**
  - 100% debe evaluarse como `'100'`, `'100%'` o, muy importante, el valor numérico `1` que retorna GAS para celdas con formato de porcentaje. Nunca evalúes el string `'1'` o `'1.0'` como 100%.

## 5. Integraciones: Make.com y Outlook

- **Manejo de Fechas:**
  - Los webhooks enviados a Make.com **deben** mantener el formato ISO 8601 (`.toISOString()`), incluyendo milisegundos y la "Z" UTC. No los elimines.
- **Payloads de Notificación:**
  - El sistema de notificación (Make.com -> Outlook) depende de conocer el origen de la tarea. Asegúrate de incluir indicadores de si la tarea proviene de `ANTONIA_VENTAS` (tabla de ventas) o del Tracker general.
- **Emails Reales:**
  - Los usuarios en `USER_DB` están mapeados a sus correos corporativos reales (`@holtmont.com`). Verifica esto antes de probar integraciones.

## 6. Testing Local y Verificaciones

- **Mocking Local:**
  - Las funciones en `CODIGO.js` deben probarse creando stubs para los servicios de GAS (ej. `SpreadsheetApp`, `CacheService`, `PropertiesService`).
- **Scripts de Verificación:**
  - Siempre debes ejecutar las pruebas pertinentes tras modificaciones:
    - Directorio y Departamentos: `node test_departments.js`
    - Sintaxis y Lógica de Frontend: `node check_html2.js` (si `check_html.js` falla por errores de parseo o compatibilidad, utiliza `check_html2.js` como respaldo funcional).

## 7. Homogeneidad de UI / CSS Estricto

- **Reglas Tipográficas:**
  - Aplica de forma unificada en tablas (`.table-excel`, `.mini-table`, `.exec-table`, `.table`):
    - Tamaño y fuente: `font-size: 11px !important; font-family: 'Arial', sans-serif !important;`
  - **Encabezados:** Todos en minúsculas (`text-transform: lowercase !important;`), a excepción explícita del encabezado 'Folio' o 'ID'.
  - **Celdas y Formularios:** Todos los datos (textos, inputs, selects) en mayúsculas (`text-transform: uppercase !important;`).
- **Restricciones Funcionales UI:**
  - No implementes funciones con micrófonos, dado que GAS bloquea su uso.
  - Algunos elementos visuales (ej., ciertos botones o columnas en `PPC_FORM`) son meramente "mocks" estéticos y no deben acoplarse con persistencia de base de datos a menos que se solicite explícitamente.

## 8. Quality Control en Pull Requests (submit)

- **Mandatory Quality Checks:**
  - Cada vez que uses la herramienta `submit` para hacer un Pull Request, **debes** incluir y responder las siguientes 5 preguntas de control de calidad en la descripción del PR. **Además, todos los comentarios y descripciones del PR deben redactarse SIEMPRE en ESPAÑOL/SPANISH:**
    1. ¿Tiene un feedback loop que verifique el código generado?
    2. ¿Cómo se hace el rollback si falla?
    3. ¿Tiene observabilidad en producción?
    4. ¿Escala si el equipo crece?
    5. ¿Tu equipo lo mantiene sin ti?
  - Estas preguntas aseguran que los cambios introducidos sean seguros, mantenibles y sigan las mejores prácticas de ingeniería de software.

---
---


# 🤖 AI Agent Specific Skills

A continuación, se definen los "Skills" accionables que los agentes de IA (como Claude Code, Cursor o Jules) deben tener activamente en mente y ejecutar según el contexto de su trabajo.

## 🛠️ Skill: Monolithic Frontend Mastery
**Descripción:** Capacidad para operar dentro de una arquitectura sin empaquetadores (buildless).
**Cuándo usarlo:** Cada vez que leas, modifiques o crees UI en `index.html`.
**Reglas a seguir:**
- **Inyección Directa:** Todo Vue.js, HTML, y CSS vive en `index.html` (o `workorder_form.html`). No uses Node.js, Webpack, Vite, ni crees archivos `.vue`.
- **CDN Only:** Si necesitas una librería, inclúyela vía CDN en el `<head>`.
- **Sintaxis de Vue 3 (Composition API preferido):** Mantén la lógica reactiva dentro del bloque `<script type="module">` usando `ref()`, `reactive()`, y exponiéndolas globalmente a `window` si interactúan con llamadas de GAS (`google.script.run`).

## 🛡️ Skill: GAS Backend Guardian
**Descripción:** Capacidad para escribir y mantener código backend seguro y funcional en Google Apps Script (GAS).
**Cuándo usarlo:** Cada vez que modifiques `CODIGO.js`.
**Reglas a seguir:**
- **Prohibición de Node en Backend:** El backend es GAS. Ignora paquetes de npm; no sirven en `CODIGO.js`.
- **Puente Frontend-Backend:** El frontend se comunica **exclusivamente** mediante `google.script.run`. Toda función que el frontend llame debe estar definida en el scope global de `CODIGO.js`.
- **Pase de Contexto de Usuario:** Siempre pasa `currentUsername.value` desde Vue.js hacia el backend para registrar auditorías usando la función `registrarLog(user, action_type, description)`.
- **Data Validation Fallbacks:** Al guardar en celdas con listas desplegables (Data Validation), implementa fallbacks estrictos. Ej: Si `ESTATUS` viene vacío o inválido, fuerza `'PENDIENTE'`. Si `CUMPLIMIENTO` viene vacío, fuerza `'NO'`.

## 🧬 Skill: Anti-Duplication & Race Condition Resolver
**Descripción:** Prevención absoluta de duplicidad de tareas o filas debido a asincronía y múltiples clicks de usuario.
**Cuándo usarlo:** Al modificar cualquier flujo que cree, actualice o asigne tareas (ej. `apiSaveTrackerBatch`, `internalBatchUpdateTasks`, `apiSavePPCData`).
**Reglas a seguir:**
- **Bloqueo Frontend (`isSubmitting`):** Todo botón de guardado en `index.html` debe ligarse a un estado reactivo `isSubmitting` que prevenga múltiples llamadas simultáneas a GAS.
- **Identidad Temporal (`_tempId`):** Las filas nuevas generan un `_tempId` único en el frontend antes de enviarse.
- **Gatekeeper con CacheService:** En el backend, usa `CacheService.getScriptCache()` usando el `_tempId` y el nombre de la hoja como "Lock" (candado) para bloquear inserciones paralelas del mismo evento.
- **Resolución Histórica (Fallback):** Si estás actualizando y la búsqueda de `FOLIO` o `ID` falla (ej. error de escritura), haz un fallback buscando la combinación exacta de `CONCEPTO` y `FECHA`.

## 🧭 Skill: Complex Routing & Reverse Sync
**Descripción:** Capacidad para manejar las reglas idiosincráticas de asignación de tareas en la empresa.
**Cuándo usarlo:** Al tocar lógica de distribución de filas a hojas de personal.
**Reglas a seguir:**
- **La Ley de Antonia (Ventas):** Las asignaciones y el Tracker general *no deben* mezclarse con la tabla core de ventas (`ANTONIA_VENTAS`). Todo enrutamiento general debe enviar las tareas a su Tracker personal ('ANTONIA PINEDA LOPEZ').
- **Filtro de Sufijo de Ventas:** Para cualquier usuario que **no** sea Antonia, debes remover silenciosamente el sufijo `(VENTAS)` de la hoja destino globalmente (`targetSheet.replace(/\s*\(VENTAS\)/ig, "").trim()`).
- **Reverse Sync (Prefijo AV-):** Si una tarea tiene el prefijo `AV-` (vino de `ANTONIA_VENTAS`), cualquier actualización lateral en hojas de otros trabajadores debe reflejarse de forma bidireccional enviando los cambios de vuelta a la hoja maestra de Antonia.

## 🕵️ Skill: Dynamic Sheet Parsing & Case-Insensitivity
**Descripción:** Capacidad para leer datos resilientes frente a inconsistencias humanas en Google Sheets.
**Cuándo usarlo:** Al leer o escribir matrices bidimensionales obtenidas con `.getValues()`.
**Reglas a seguir:**
- **No asumas la Fila 1:** Busca dinámicamente la fila de encabezados evaluando si el array contiene columnas clave (ej. `cells.includes("ID")`).
- **Insensibilidad Extrema:** Los payloads del frontend pueden enviar propiedades como `folio`, mientras el backend espera `FOLIO`. Siempre itera sobre las claves de los objetos y compáralas usando `.toUpperCase().trim()`.
- **Interpretación del 100%:** Para la columna `AVANCE`, el valor `1` crudo de GAS (porcentaje) debe evaluarse como 100%.

## 🔌 Skill: Bulletproof External Integrations
**Descripción:** Interacción segura con plataformas de terceros como Make.com y Outlook 365.
**Cuándo usarlo:** Al enviar webhooks o notificaciones calendarizadas.
**Reglas a seguir:**
- **Integridad de Fechas:** Nunca mutar una fecha al enviarla por webhook. Usa exactamente el string estándar `fecha.toISOString()`. Asegúrate de que retenga los milisegundos y la letra "Z" al final para que Make.com parsee correctamente el UTC.
- **Contexto de Origen de Tarea:** Los payloads de webhook (`NotifierService.sendToOutlook`) deben especificar si el registro viene de una "tabla de ventas" o del "tracker general" para que Make formatee correctamente el correo.

## 🧪 Skill: Local Test Runner
**Descripción:** Capacidad para verificar que tus modificaciones no destruyen el entorno de producción.
**Cuándo usarlo:** Inmediatamente después de aplicar cambios y antes de solicitar code review o commit.
**Reglas a seguir:**
- **Verificación de Organigrama:** Ejecuta `node test_departments.js` si tocas `USER_DB` o `INITIAL_DIRECTORY`.
- **Syntax Check Frontend:** Ejecuta `node check_html2.js` para asegurar que las modificaciones en `index.html` no contengan errores de sintaxis catastróficos.
