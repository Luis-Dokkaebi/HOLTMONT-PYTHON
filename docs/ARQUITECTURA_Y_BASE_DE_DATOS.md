# Arquitectura y Base de Datos

Documento técnico del modelo de datos, la arquitectura del software y el flujo de datos de
Holtmont Workspace.

---

## 1. Arquitectura del software

### 1.1 Vista de alto nivel

Holtmont Workspace es una **Web App monolítica serverless** sobre la plataforma Google. No hay
servidor propio: el "backend" es un proyecto de Google Apps Script ligado a un Spreadsheet, y la
"base de datos" son las hojas de ese Spreadsheet.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          NAVEGADOR (cliente)                           │
│  index.html  ── SPA Vue.js 3 (CDN, sin build) ──────────────┐         │
│    · Vistas por rol (Tracker, PPC, Ventas, Proyectos, KPI)  │         │
│    · Estado reactivo (isSubmitting, _tempId, drafts)        │         │
│    · workorder_form.html (formulario de Work Order)         │         │
└─────────────────────────────┬───────────────────────────────┘         │
                              │ google.script.run (RPC async)           │
                              ▼                                          │
┌──────────────────────────────────────────────────────────────────────┐
│                   GOOGLE APPS SCRIPT (backend, V8)                     │
│  CODIGO.js — funciones globales:                                      │
│    · doGet() → HtmlService sirve "Index"                             │
│    · Capa API (api*)  · Capa interna (internal*)  · Helpers          │
│    · LockService / CacheService (concurrencia)                       │
│    · PropertiesService (secretos y contadores)                       │
└───────┬───────────────────────┬──────────────────────┬──────────────┘
        │                       │                      │
        ▼                       ▼                      ▼
┌───────────────┐     ┌──────────────────┐    ┌──────────────────────┐
│ Google Sheets │     │   Google Drive   │    │  Servicios externos  │
│ (base de datos)│     │ (archivos/banco) │    │  Make.com → Outlook  │
│  1 hoja/entidad│     │                  │    │  Google Gemini API   │
└───────────────┘     └──────────────────┘    └──────────────────────┘
```

### 1.2 Capas del backend (`CODIGO.js`)

| Capa | Prefijo | Responsabilidad |
|---|---|---|
| **API pública** | `api*` | Puntos de entrada invocados por el FE vía `google.script.run`. Validan, orquestan y retornan la envoltura `{success, …}`. |
| **Interna** | `internal*` | Lógica reutilizable (p. ej. `internalBatchUpdateTasks`, `internalFetchSheetData`, `internalUpdateTask`). No la llama el FE directamente. |
| **Helpers** | varios | `findSheetSmart`, `findHeaderRow`, `registrarLog`, `getOrCreateFolder`, `colIndexToLetter`, `ensureSheetWithHeaders`. |
| **Servicios** | `NotifierService`, `callGeminiAPI` | Integraciones externas. |
| **Triggers** | `onOpen`, `autoUpdateQuoteMetrics`, `generarFolioAutomatico` | Menú y automatizaciones programadas. |
| **Pruebas** | `test_*` | Autoverificación ejecutable dentro de GAS. |

### 1.3 Principios arquitectónicos (invariantes)

- **Buildless / monolítico:** todo el FE (HTML, CSS, JS, Vue) vive en `index.html`. Prohibido
  introducir Webpack/Vite/archivos `.vue`. Librerías solo por CDN.
- **Backend GAS puro:** sin dependencias npm en `CODIGO.js`.
- **Concurrencia controlada:** `LockService` (candado de script) para secciones críticas de
  escritura; `CacheService` como Gatekeeper anti-duplicación por `_tempId`.
- **Resiliencia de datos:** detección dinámica de encabezados y comparaciones case-insensitive
  para tolerar inconsistencias humanas en las hojas.
- **Auditoría transversal:** `registrarLog()` en toda mutación relevante.

---

## 2. Modelo de datos (Google Sheets como base de datos)

Cada "tabla" es una hoja del Spreadsheet. No hay claves foráneas forzadas por el motor: las
relaciones se mantienen por convención de columnas de ID y por nombre de hoja.

### 2.1 Catálogo de hojas

| Hoja (tabla) | Rol | Constante |
|---|---|---|
| `DB_DIRECTORY` | Directorio/organigrama persistido. | `APP_CONFIG.directorySheetName` |
| `PPCV3` | Maestro de actividades PPC. | `APP_CONFIG.ppcSheetName` |
| `PPC_BORRADOR` | Borradores de captura PPC. | `APP_CONFIG.draftSheetName` |
| `Datos` | Datos de ventas. | `APP_CONFIG.salesSheetName` |
| `LOG_SISTEMA` | Bitácora de auditoría. | `APP_CONFIG.logSheetName` |
| `ANTONIA_VENTAS` | Hoja maestra de ventas (fuente de folios `AV-`). | `FOLIO_CONFIG.SHEET_NAME` |
| `DB_SITIOS` | Sitios (proyectos raíz). | — |
| `DB_PROYECTOS` | Subproyectos ligados a sitios. | — |
| `DB_WO_MATERIALES` | Detalle WO: materiales. | `APP_CONFIG.woMaterialsSheet` |
| `DB_WO_MANO_OBRA` | Detalle WO: mano de obra. | `APP_CONFIG.woLaborSheet` |
| `DB_WO_HERRAMIENTAS` | Detalle WO: herramientas. | `APP_CONFIG.woToolsSheet` |
| `DB_WO_EQUIPOS` | Detalle WO: equipos. | `APP_CONFIG.woEquipSheet` |
| `DB_WO_PROGRAMA` | Detalle WO: programa. | `APP_CONFIG.woProgramSheet` |
| `<NOMBRE PERSONA>` | Tracker personal (una hoja por persona del directorio). | dinámica |
| `<NOMBRE PERSONA> (VENTAS)` | Cotizaciones de vendedores (`seller:true`). | dinámica |
| `KPI_COTIZACIONES` | Métricas de cotizaciones (escritas por el agente). | — |
| Hojas de agenda / hábitos | Eventos personales y hábitos. | dinámica |

### 2.2 Esquemas de columnas (tipos de datos)

Los tipos son los efectivos en Google Sheets: `TEXTO`, `FECHA` (Date de GAS), `NÚMERO`,
`PORCENTAJE` (número 0–1), `URL`.

#### `DB_DIRECTORY`
| Columna | Tipo | Descripción |
|---|---|---|
| `NOMBRE` | TEXTO | Nombre en mayúsculas (clave lógica). |
| `DEPARTAMENTO` | TEXTO | Departamento del organigrama. |
| `TIPO_HOJA` | TEXTO | `ESTANDAR` \| `HIBRIDO` \| `VENTAS`. |

#### `PPCV3` (maestro PPC)
`ID`, `ESPECIALIDAD`, `DESCRIPCION`, `RESPONSABLE`, `FECHA`, `RELOJ`, `CUMPLIMIENTO`, `ARCHIVO`,
`COMENTARIOS`, `COMENTARIOS PREVIOS`, `ESTATUS`, `AVANCE`, `CLASIFICACION`, `PRIORIDAD`, `RIESGOS`,
`FECHA_RESPUESTA`, `DETALLES_EXTRA`.

| Columna clave | Tipo | Nota |
|---|---|---|
| `ID` | TEXTO | Identidad de la actividad. |
| `RESPONSABLE` | TEXTO | Persona destino (enruta la distribución). |
| `FECHA` / `FECHA_RESPUESTA` | FECHA | — |
| `CUMPLIMIENTO` | TEXTO | Fallback `'NO'`. |
| `ESTATUS` | TEXTO | Fallback `'PENDIENTE'`. |
| `AVANCE` | PORCENTAJE/TEXTO | `1` = 100%. |

#### Tracker personal — `DEFAULT_TRACKER_HEADERS`
`ID`, `ESPECIALIDAD`, `CONCEPTO`, `FECHA`, `RELOJ`, `AVANCE`, `ESTATUS`, `COMENTARIOS`, `ARCHIVO`,
`CLASIFICACION`, `PRIORIDAD`, `FECHA_RESPUESTA`.
Columnas extendidas usadas por reglas de negocio: `INVOLUCRADOS` (delegación lateral "Papa Caliente")
y `VENDEDOR` (solo asignaciones desde `ANTONIA_VENTAS`).

#### Hojas de ventas — `DEFAULT_SALES_HEADERS`
`FOLIO`, `CLIENTE`, `CONCEPTO`, `VENDEDOR`, `FECHA`, `F. ENTREGA`, `ESTATUS`, `COMENTARIOS`,
`ARCHIVO`, `MONTO`, `F2`, `COTIZACION`, `TIMELINE`, `LAYOUT`, `AVANCE`.
`ANTONIA_VENTAS` agrega dinámicamente `MAP COT` y `PROCESO_LOG`.

#### `PPC_BORRADOR`
`ESPECIALIDAD`, `CONCEPTO`, `RESPONSABLE`, `HORAS`, `CUMPLIMIENTO`, `ARCHIVO`, `COMENTARIOS`,
`PREVIOS`, `PRIORIDAD`, `RIESGOS`, `RESTRICCIONES`, `FECHA_RESP`, `CLASIFICACION`, `FECHA_ALTA`,
`RUTA_CRITICA`, `ZONA`, `CONTRATISTA`, `CUANT_REQ`, `CUANT_REAL`, `DIAS_JSON` (JSON serializado).

#### `DB_SITIOS`
`ID_SITIO` (`SITE-<timestamp>`), `NOMBRE`, `CLIENTE`, `TIPO`, `ESTATUS`, `FECHA_CREACION`, `CREADO_POR`.

#### `DB_PROYECTOS`
`ID_PROYECTO`, `ID_SITIO` (FK → `DB_SITIOS.ID_SITIO`), `NOMBRE_SUBPROYECTO`, `TIPO`, `ESTATUS`,
`FECHA_CREACION`, `CREADO_POR`.

#### `LOG_SISTEMA`
`FECHA`, `USUARIO`, `ACCION`, `DETALLES`.

#### Agenda personal
`ID`, `USUARIO`, `TITULO`, `TIPO`, `FECHA`, `HORA_INICIO`, `HORA_FIN`, `DETALLES`, `CLASIFICACION`,
`ESTATUS`.

#### Hábitos
`ID`, `USUARIO`, `HABITO`, `META`, `LOG_JSON`, `FECHA_ACTUALIZACION`.

### 2.3 Relaciones (diagrama lógico)

```
USER_DB (código) ──1:1── DB_DIRECTORY.NOMBRE ──1:1── Hoja "<NOMBRE>" (tracker)
                                            └──0:1── Hoja "<NOMBRE> (VENTAS)"  (si seller)

DB_SITIOS.ID_SITIO ──1:N── DB_PROYECTOS.ID_SITIO
DB_SITIOS ──(apiCreateStandardStructure)── STANDARD_PROJECT_STRUCTURE (subcarpetas/hojas)

PPCV3.RESPONSABLE ──enruta──▶ Hoja "<RESPONSABLE>" (distribución de tareas)
ANTONIA_VENTAS (folio AV-) ◀──reverse sync──▶ Hoja "<TRABAJADOR>" (delegación lateral)

Cualquier mutación ──▶ LOG_SISTEMA
```

> **Nota:** `USER_DB` (en `CODIGO.js`) es la fuente de credenciales/roles; `INITIAL_DIRECTORY`
> (también en código) es la fuente del organigrama, que se materializa en `DB_DIRECTORY` vía
> `apiResyncDirectory`. `test_departments.js` verifica que ambos coincidan con el organigrama oficial.

### 2.4 Identidad, secuencias y folios

| Entidad | Estrategia de ID |
|---|---|
| Sitio | `SITE-<Date.getTime()>` |
| Fila nueva (FE) | `_tempId` temporal → resuelto a `ID`/`FOLIO` en backend |
| Work Order | `WORKORDER_SEQ` (Script Property), `padStart(4,'0')`, folio `<INI-CLIENTE>-<Abrev-Depto>-####` |
| Ventas Antonia | `ANTONIA_SEQ` (Script Property), prefijo `AV-` |
| Secuencias por prefijo | `<PREFIJO>_SEQ` (Script Property) |

Los folios de proceso usan `FULL_PROCESS_NAMES` (L, CD, EP, CI, EV, CEC, RCC) para nombrar etapas
del pipeline de cotización.

---

## 3. Flujo de datos (casos principales)

### 3.1 Alta y distribución de una actividad PPC

```
Usuario captura actividad en index.html (Vue)
   │  genera _tempId, isSubmitting=true
   ▼
google.script.run.apiSavePPCData(payload, activeUser)
   │
   ├─ LockService.tryLock(30s)
   ├─ Escribe/asegura hoja PPCV3 (crea encabezados si falta)
   ├─ Por cada item: resuelve RESPONSABLE → hoja destino
   │     · aplica Ley de Antonia (no mezclar con ANTONIA_VENTAS)
   │     · filtra sufijo (VENTAS) si el usuario no es Antonia
   │     · internalBatchUpdateTasks(targetSheet, tasks, useOwnLock=false)
   ├─ Escribe logs en lote a LOG_SISTEMA
   └─ return { success:true, ids:[...] }
   ▼
FE fusiona respuesta, setea _isNew=false, isSubmitting=false
```

### 3.2 Guardado en el tracker con anti-duplicación (Gatekeeper)

```
apiSaveTrackerBatch(personName, tasks, username)
   └─ internalBatchUpdateTasks(sheetName, tasksArray, useOwnLock)
        ├─ findHeaderRow(values)         # encabezados dinámicos
        ├─ CacheService: lock por _tempId + hoja   # Gatekeeper
        ├─ match por FOLIO/ID (toUpperCase().trim())
        │     └─ fallback: match por CONCEPTO + FECHA
        │          └─ último recurso: generar folio nuevo
        ├─ fallbacks: ESTATUS→'PENDIENTE', CUMPLIMIENTO→'NO'
        ├─ AVANCE: 1 (número) ó '100'/'100%' ⇒ 100%
        └─ return { success, data: fila_actualizada }
```

### 3.3 Notificación a Outlook (asignación de tarea)

```
Backend arma payload (folio, titulo, fechas ISO, correoDestino, asignadoPor)
   └─ NotifierService.sendToOutlook(payload)
        └─ UrlFetchApp.fetch(WEBHOOK_OUTLOOK_URL, POST JSON)
             └─ Make.com → crea evento en Outlook 365 del destinatario
```

### 3.4 Reportes de KPI asistidos por Gemini (programado)

```
Trigger diario 07:00 → autoUpdateQuoteMetrics()
   ├─ runQuoteMetricsAgent(params)
   │     ├─ agrega métricas de cotizaciones
   │     ├─ callGeminiAPI(prompt) → resumen ejecutivo
   │     └─ guarda LAST_AGENT_RUN (Script Property)
   └─ _sendAgentEmail(...) → correo con métricas + resumen
```

---

## 4. Modelo de seguridad

- **Autenticación:** credenciales en `USER_DB` (`apiLogin`). Las contraseñas están en texto plano en
  el código (limitación conocida del diseño interno actual — ver Pipeline §Riesgos).
- **Autorización (RBAC):** `getSystemConfig(role, username)` determina módulos y hojas visibles.
  Ramas especiales cableadas por `username`.
- **Aislamiento de datos:** cada persona ve su hoja espejo; los admins ven monitores adicionales.
- **Auditoría:** `LOG_SISTEMA` registra login, logout, altas, actualizaciones y errores críticos.
- **Superficie de red:** salidas HTTPS solo a Make.com y a la API de Gemini (scope
  `script.external_request`).

---

## 5. Concurrencia y consistencia

| Mecanismo | Dónde | Propósito |
|---|---|---|
| `LockService.getScriptLock()` | `apiSavePPCData` (30s), `apiSaveSite`/`apiSaveSubProject` (5s), `apiAddEmployee` (10s), `getDirectoryFromDB` | Serializar escrituras y evitar carreras entre usuarios. |
| `CacheService` (Gatekeeper) | `internalBatchUpdateTasks` | Bloquear inserciones duplicadas del mismo evento (`_tempId`). |
| `isSubmitting` (FE) | `index.html` | Evitar doble clic / doble envío. |
| Escritura en lote (`setValues`) | logs y filas | Rendimiento en V8 y atomicidad relativa. |

La consistencia es **eventual y por convención**: al no haber transacciones, las escrituras se
protegen con candados y la identidad de filas se resuelve con la cadena FOLIO → CONCEPTO+FECHA →
nuevo folio.
