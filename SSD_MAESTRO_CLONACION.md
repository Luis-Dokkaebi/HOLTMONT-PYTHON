# SSD MAESTRO — Holtmont Workspace
## Documento de Especificación de Sistema para Clonación Total (Software/System Design Document)

> **Versión:** 2.0.0 (Edición Extendida) · **Fecha:** 2026-07-02 · **Alcance:** Este documento es la fuente única capaz de reconstruir el sistema completo — backend, frontend, modelo de datos, reglas de negocio, integraciones y despliegue — con el mínimo de referencias externas al código fuente. A diferencia de la v1.0.0, esta edición **embebe el código fuente literal** de las funciones y métodos más críticos del sistema (no solo su descripción), de modo que el documento sea, por sí mismo, suficiente para reconstruir el núcleo funcional sin tener que reabrir `CODIGO.js`/`index.html`.
>
> Complementa (no reemplaza) a `SDD_HOLTMONT_WORKSPACE.md`, `PAPA_CALIENTE_SDD.md`, `SDD_OUTLOOK_INTEGRATION.md`, `SDD_KPI_ADMIN.md`, `FRONTEND ANTONIA.md` y `AGENTS.md`.

---

## 0. Cómo usar este documento

El documento tiene tres partes:

- **PARTE I — Narrativa (§1 a §18):** arquitectura, modelo de datos, reglas de negocio, organigrama, integraciones, despliegue y deuda técnica, con nivel de detalle suficiente para entender **por qué** el sistema está hecho como está hecho.
- **PARTE II — Anexos de código fuente (§19 a §21):** el cuerpo **literal y completo** de las funciones backend más críticas (`CODIGO.js`), de los métodos frontend más críticos (`index.html`), y el inventario completo de las ~90 variables de estado reactivo de Vue con su propósito exacto.
- **PARTE III — Migración a Python/FastAPI (§22–§23):** §22 es el checklist de verificación de paridad funcional, pensado para auditar una reimplementación contra este SSD ítem por ítem. §23 es la guía de mejora consciente — qué patrones del código original **no** conviene replicar tal cual, con evidencia concreta y el remedio recomendado en FastAPI/Python. Si el objetivo **no** es leer el sistema original sino **verificar/mejorar una migración ya en curso**, empezar directamente en §22–§23 y usar el resto del documento como referencia de detalle bajo demanda (cada ítem cita la sección exacta donde está la spec completa).

Si tuvieras que reconstruir "Holtmont Workspace" desde una carpeta vacía, sigue este orden:

1. Lee §1–§4 para entender qué es el sistema, con qué tecnologías está hecho, y cómo se relacionan sus 3 capas.
2. Lee §5 para el esquema completo de la base de datos (hojas y columnas exactas de Google Sheets).
3. Lee §6 para el organigrama completo (41 usuarios, sin contraseñas) y la matriz de permisos por rol.
4. Lee §7 para el catálogo de las ~140 funciones del backend, agrupadas por responsabilidad.
5. Lee §8 para el mapa de vistas y el inventario de estado reactivo del frontend.
6. Lee §9 para el sistema de diseño (Design Tokens).
7. Lee §10 para las reglas de negocio críticas, **con ejemplos de payload JSON antes/después** de cada transición relevante.
8. Lee §11–§13 para integraciones externas, triggers y el estado real de seguridad.
9. Lee §14–§16 para testing, la guía de despliegue paso a paso, y la deuda técnica conocida (incluye 3 bugs reales confirmados en el sistema original).
10. Lee §17–§18 para el índice función-por-función y el índice de documentos relacionados.
11. Usa **§19 (Anexo A)** para copiar/pegar el código backend literal de las funciones más críticas (19 subsecciones, cubre prácticamente todos los módulos del backend).
12. Usa **§20 (Anexo B)** para copiar/pegar el código frontend literal de los métodos Vue más críticos.
13. Usa **§21 (Anexo C)** para el inventario completo de las ~90 variables `ref()`/`reactive()` del frontend.
14. Usa **§22** como checklist activo si estás auditando una migración: cada ítem `☐` tiene un criterio de aceptación verificable y cita dónde está la spec completa. Los ítems marcados 🐛 son bugs confirmados del sistema original que se recomienda **corregir, no replicar** en una reimplementación nueva.
15. Lee **§23** antes de escribir código nuevo en la migración: son 12 anti-patrones reales del código original (hardcodeo de reglas de negocio por nombre de persona, funciones gigantes, doble fuente de verdad, validación manual en vez de esquemas, etc.), cada uno con evidencia concreta y el remedio aplicable en FastAPI/Python — no son las contraseñas ni la API key (eso ya está en §13/§22.11/§22.15), son los demás atajos tomados "por velocidad".

---

## 1. Resumen Ejecutivo

**Holtmont Workspace** es una plataforma interna tipo ERP/CRM/BPM ligero para **Holtmont** (empresa de construcción/ingeniería), usada por 41 cuentas de usuario repartidas en 19 departamentos posibles (CEO, RH, Finanzas, Compras, Presupuestos, Calidad, Seguridad, Precios Unitarios, Diseño, Ventas, Electromecánica, HVAC, Construcción, Limpieza, Almacén y Maquinaria, Administración, Facturación, Maquinaria, EHS).

Resuelve cuatro problemas de negocio:

1. **Seguimiento de tareas por persona ("Trackers")**: cada empleado tiene su propia hoja de cálculo tipo Excel dentro de la app, con columnas de especialidad, concepto, fechas, avance, estatus, comentarios y archivos adjuntos.
2. **Flujo de cotizaciones de Ventas ("Papa Caliente")**: un pipeline Kanban de 7 etapas (`L → CD → EP → CI → EV → CEC → RCC`) que delega automáticamente el trabajo de una cotización entre Ventas, Diseño y Presupuestos, con sincronización bidireccional de vuelta a la hoja maestra `ANTONIA_VENTAS`.
3. **Checklist operativo por sitio ("Módulo PPC")**: formularios de campo (Interno/Preoperativo/Cliente) gestionados centralmente por el rol `PPC_ADMIN`.
4. **Órdenes de trabajo de campo ("Work Orders")**: formulario especializado (vista `WORKORDER_FORM`, markup vivo dentro de `index.html` — ver nota de código huérfano en §3 y §16) para capturar materiales, mano de obra, herramientas, equipo y programa de una obra, con generación automática de folio y control vehicular.

No existe backend propio ni base de datos SQL: **Google Sheets es la base de datos**, **Google Apps Script (GAS) es el backend**, y **Vue 3 vía CDN sin build step es el frontend**, todo dentro de un único proyecto de Google Apps Script desplegado como Web App. El código fuente actual (a la fecha de este documento) tiene 6249 líneas de backend (`CODIGO.js`) y 10142 líneas de frontend (`index.html`, que incluye su propia copia inline del formulario de Work Order), más un archivo adicional `workorder_form.html` de 928 líneas que **no está conectado a la aplicación en ejecución** — ver hallazgo detallado en §3 y §16.

---

## 2. Stack Tecnológico y Restricciones Arquitectónicas No Negociables

| Capa | Tecnología | Notas |
|---|---|---|
| Backend | Google Apps Script (V8 runtime) | Un único archivo `CODIGO.js` (6249 líneas). Sin `npm`, sin Node.js en runtime. |
| Frontend | Vue 3 (Composition API) vía CDN (`unpkg.com/vue@3/dist/vue.global.js`) | Sin build step, sin Webpack/Vite, sin SFC `.vue`. Todo vive inline en `index.html` (10142 líneas). |
| UI/CSS | Bootstrap 5.3.0 (CDN), CSS custom con Design Tokens en `:root`, Animate.css 4.1.1, Anime.js 3.2.1 | Ver §9. |
| Modales | SweetAlert2 11 (CDN) | Todos los diálogos de confirmación/asignación (`Swal.fire`, `Swal.showLoading`). |
| Gráficas | Chart.js (CDN, sin pin de versión) | Usado en KPI Dashboard. |
| Fuentes | Google Fonts: Roboto (300/400/500/700) + Share Tech Mono | Cargadas vía `<link>` en `<head>`. |
| Base de datos | Google Sheets (hoja de cálculo activa, `SpreadsheetApp.getActiveSpreadsheet()`) | Una única Spreadsheet contiene todas las "tablas" como pestañas (`Sheet`). |
| Archivos | Google Drive (vía `DriveApp`/`UrlFetchApp` desde GAS) | Subida en Base64 desde el navegador, decodificado en el backend. |
| Automatización externa | Make.com (webhook único, `hook.us2.make.com`) + Power Automate (Microsoft 365) | Ver §11. Actualmente **implementado y activo en producción**, no es un diseño propuesto (ver corrección respecto a versiones previas de este documento). |
| IA | Google Gemini API (vía `UrlFetchApp` en `callGeminiAPI`) | Usado para resúmenes de productividad y transcripción de audio. Key gestionada vía `PropertiesService` (`apiSaveGeminiKey`/`apiCheckGeminiKey`). |
| Zona horaria | `America/Mexico_City` (`appsscript.json`) | Todo cálculo de fecha asume esta zona salvo el UTC explícito hacia Make.com/Outlook. |
| Runtime | V8 (`"runtimeVersion": "V8"` en `appsscript.json`) | |
| Dependencias de testing local | `acorn` (parser JS), `jsdom` (DOM simulado) — únicas entradas de `package.json` | Nunca se despliegan a GAS; solo se usan en `node test_*.js`/`check_html*.js`. |

### 2.1 OAuth Scopes exactos (`appsscript.json`)

```json
{
  "timeZone": "America/Mexico_City",
  "dependencies": {},
  "exceptionLogging": "STACKDRIVER",
  "oauthScopes": [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/script.external_request",
    "https://www.googleapis.com/auth/script.scriptapp",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/script.container.ui"
  ],
  "runtimeVersion": "V8"
}
```

| Scope | Por qué se necesita |
|---|---|
| `spreadsheets` | Leer/escribir todas las hojas (base de datos completa del sistema) |
| `drive` | Crear carpetas `[Año]/[Mes]/[Cliente]`, subir/archivar adjuntos |
| `script.external_request` | `UrlFetchApp` hacia Make.com (Outlook) y Gemini API |
| `script.scriptapp` | Instalar/gestionar triggers programados (`ScriptApp.newTrigger`) |
| `userinfo.email` | Disponible para `Session.getActiveUser().getEmail()` (usado en `generarDashboard`, no en el login principal, que es propio vía `USER_DB`) |
| `script.container.ui` | Menú custom nativo de Sheets (`onOpen`, `SpreadsheetApp.getUi()`) |

### 2.2 Restricciones que un clon **debe** respetar (extraídas de `AGENTS.md`)

1. **Todo el backend vive en un solo archivo `CODIGO.js`.** No se permite dividir en módulos importables — GAS no soporta `import`/`require` de módulos propios en este proyecto (no usa `clasp` con múltiples archivos `.gs` separados por convención del equipo; todo backend es un único script).
2. **Toda la UI vive en `index.html`.** El archivo `workorder_form.html` existe en el repositorio pero no está conectado a la aplicación real (§3, §16) — en la práctica, la UI del formulario de Work Order también vive dentro de `index.html`. Cualquier librería nueva se agrega por `<script src="...">` CDN en el `<head>`, nunca vía `npm install`.
3. **La comunicación cliente-servidor es exclusivamente `google.script.run`** (RPC asíncrono nativo de GAS: `google.script.run.withSuccessHandler(fn).withFailureHandler(fn).nombreDeFuncion(args)`), nunca `fetch()` a un endpoint REST propio (salvo las llamadas salientes desde el backend hacia Make.com/Gemini vía `UrlFetchApp`).
4. **No se pueden usar micrófonos/`getUserMedia`** — GAS Web Apps corren en un iframe sandboxed que bloquea el acceso a hardware de audio en la mayoría de contextos; la función `transcribirConGemini` recibe audio ya grabado en Base64, no graba en vivo desde el navegador de forma confiable.
5. **Fallbacks estrictos de datos.** Si `ESTATUS` viene vacío/inválido al guardar, se fuerza `'PENDIENTE'`. Si `CUMPLIMIENTO` viene vacío, se fuerza `'NO'`. Esto vive en la capa de escritura (`internalBatchUpdateTasks`/`apiSavePPCData`), no en el frontend.
6. **Homogeneidad tipográfica obligatoria en toda tabla** (`.table-excel`, `.mini-table`, `.exec-table`, `.table`): `font-size: 11px !important; font-family: 'Arial', sans-serif !important;`. Cabeceras en minúsculas (excepto "Folio"/"ID"). Datos de celdas/inputs/selects en mayúsculas.

---

## 3. Estructura del Repositorio (archivo por archivo)

```
REAL-HOLTMONT/
├── CODIGO.js                    # Backend GAS completo — ÚNICA fuente de verdad del servidor (6249 líneas)
├── CODIGO.js.bak                # Respaldo manual pre-refactor — NO USAR como referencia (desactualizado)
├── CODIGO.js.orig               # Versión previa a un merge/patch — histórico, NO USAR
├── CODIGO.js.rej                # Fragmento de patch rechazado (`.rej`) — residuo de un merge fallido, IGNORAR
├── index.html                   # Frontend monolítico Vue 3 completo (10142 líneas): HTML+CSS+JS inline
├── workorder_form.html          # ⚠️ Fragmento Vue de Work Orders NO conectado a la app en ejecución — ver hallazgo en §16 (928 líneas)
├── verification.html            # Página auxiliar de verificación/QA manual
├── appsscript.json              # Manifest de Apps Script: timezone, OAuth scopes, runtime
├── package.json / package-lock.json  # Dependencias SOLO para testing local en Node (acorn, jsdom) — no se despliegan a GAS
├── image.png                    # Referencia visual (mock/diseño)
│
├── AGENTS.md                    # Reglas de negocio críticas + "skills" para agentes de IA que editen este repo
├── CREDENCIALES.md              # Tabla de usuarios/roles/departamentos del organigrama (contiene contraseñas en texto plano — ver §13)
├── README.md                    # Placeholder mínimo
├── SDD_HOLTMONT_WORKSPACE.md    # SDD general de arquitectura, design tokens y catálogo de API (v2.0.0)
├── SDD_KPI_ADMIN.md             # SDD del Dashboard de KPIs para administradores
├── SDD_OUTLOOK_INTEGRATION.md   # SDD de la integración con Outlook/Power Automate (implementación ya viva en producción, ver §11.2)
├── PAPA_CALIENTE_SDD.md         # SDD del flujo de cotizaciones "Papa Caliente" (máquina de estados de 7 pasos)
├── FRONTEND ANTONIA.md          # SDD de refactor UI/UX del Data Grid (hitboxes, timeline, accordion)
├── SSD_MAESTRO_CLONACION.md     # ESTE documento
├── plan_productivity.md         # Notas de planeación del módulo de productividad
│
├── tracker_productivity_tool.js / _tool2.js / _tool3.js         # Iteraciones del "agente" de métricas de productividad (histórico de versiones)
├── tracker_productivity_ui_tool.js … _ui_tool7.js               # Iteraciones de la UI del mismo módulo (histórico)
├── tracker_productivity_menu_tool.js                            # Menú asociado al módulo de productividad
│
├── check_html.js / check_html2.js / check_html_fix.js           # Linters/parsers locales de `index.html` (validan sintaxis JS embebida con `acorn`). `check_html2.js` es el respaldo funcional si `check_html.js` falla (AGENTS.md §6).
├── check_duplication.js / deduplicate_script.js / fix_all.js    # Scripts de diagnóstico/reparación de filas duplicadas en Sheets (uso manual, no automatizado)
├── fix_anotnia.js                                                # Fix puntual del caso especial de Antonia (histórico)
├── fix_date_temp_id.patch / fix_date_temp_id_clean.patch / fix_duplication.patch  # Parches aplicados manualmente en su momento — quedaron como registro, no se re-aplican
├── parse_dupes.js / parse_internal.js / parse_issue.js / parse_issue2.js / parse_tempId.js / get_issue_info.js  # Scripts ad-hoc de diagnóstico usados durante debugging de incidentes puntuales
├── syntax_check2.js                                              # Chequeo de sintaxis adicional
│
├── test_bug.js                    # Notas de análisis manual (comentarios, no asserts) sobre un bug real de reverse-sync: documenta por línea exacta (5543/5564/5606 de una versión previa de CODIGO.js) por qué `syncPayloads`/`safeRevTasks` NO deberían marcar una tarea completa sin pasar por PROCESO_LOG
├── test_case.js                    # Mockea `SpreadsheetApp`/`SS` con un stub in-memory (`mockFindSheet`) para probar un caso puntual de escritura
├── test_deduplication.js / _2.js   # Cargan CODIGO.js con el módulo `vm` de Node y stubs de `console`/`Logger`, verifican que el motor de guardado no cree filas duplicadas
├── test_departments.js             # Verifica que `INITIAL_DIRECTORY` + `USER_DB` en `CODIGO.js` coincidan EXACTAMENTE con el organigrama oficial por departamento (imagen de referencia del cliente). Sale con código != 0 si algo no coincide — es el test de regresión obligatorio tras tocar el organigrama
├── test_distribution.js / _2.js    # Prueban con mocks simples que la distribución de tareas hacia hojas de Tracker/Ventas ocurre correctamente
├── test_distribution_subagent.js / _2.js  # Verifican específicamente que la distribución lateral detecte asignaciones tanto en `VENDEDOR` como en `RESPONSABLE` e `INVOLUCRADOS` (no solo la primera), incluyendo un chequeo por regex directo sobre el código fuente
├── test_duplication_issue.js / _2.js      # Reproducen un incidente de duplicación específico reportado en producción, con un stub de `ANTONIA_VENTAS`
├── test_remove_worker.js           # Prueba el flujo `_removeWorker` (borrado de una tarea delegada en la hoja del trabajador cuando Antonia la reasigna)
├── test_script.js                  # Snippet aislado que prueba el filtro `dir.filter(...)` usado para calcular destinatarios de distribución (Ventas/Híbrido) excluyendo casos especiales como Eduardo Terán
├── test_subagent.js                # Verifica por regex sobre el código fuente que la lógica de distribución lateral capture `RESPONSABLE` e `INVOLUCRADOS`, no solo `VENDEDOR`
│
└── .gitignore
```

**Regla de oro para clonar:** la única fuente de verdad ejecutable son `CODIGO.js`, `index.html` y `appsscript.json` — **no** `workorder_form.html`, que pese a su nombre y a las menciones en `AGENTS.md`/los SDD narrativos, no está conectado a la aplicación real (§16). Todo lo que termina en `.bak`, `.orig`, `.rej`, `.patch`, o los `tracker_productivity_*_tool[2-7].js` / `_ui_tool[2-7].js` son iteraciones históricas o descartadas — **no reflejan el estado actual del sistema** (ver §16).

---

## 4. Arquitectura en Capas

```
┌─────────────────────────────────────────────────────────────────┐
│  NAVEGADOR (Cliente)                                             │
│  index.html  →  Vue 3 (createApp + setup(), Composition API)     │
│  · Login overlay · Sidebar (departamentos) · Data Grid (Excel-like)│
│  · Timeline "Papa Caliente" · Módulo PPC · Banco de Información  │
│  · KPI Dashboard (Chart.js) · Agenda/Calendario                  │
│  (workorder_form.html existe en el repo pero NO se carga, ver §16)│
└───────────────────────────┬─────────────────────────────────────┘
                            │ google.script.run.<funcion>(args)
                            │ (RPC asíncrono nativo de GAS, JSON serializado)
┌───────────────────────────▼─────────────────────────────────────┐
│  GOOGLE APPS SCRIPT (Backend) — CODIGO.js                         │
│  doGet(e) → sirve index.html vía HtmlService                      │
│  Funciones api*/internal* expuestas globalmente al frontend       │
│  Gatekeeper (CacheService) · LockService (folios/secuencias)      │
│  registrarLog() → auditoría en LOG_SISTEMA                        │
└──────┬───────────────────────────┬────────────────────┬──────────┘
       │                           │                    │
┌──────▼─────────┐       ┌─────────▼─────────┐  ┌───────▼───────────┐
│ Google Sheets   │       │ Google Drive       │  │ APIs externas      │
│ (Base de datos) │       │ (Archivos: fotos,  │  │ · Make.com webhook │
│ Hojas por        │       │  cotizaciones,     │  │  → Power Automate  │
│ persona +        │       │  layouts, evidencia)│  │  → Outlook 365     │
│ ANTONIA_VENTAS + │       │ Estructura:         │  │ · Gemini API       │
│ PPCV3 + DB_WO_*  │       │ [Año]/[Mes]/[Cliente]│ │  (resúmenes/audio) │
│ + DB_DIRECTORY + │       └────────────────────┘  └────────────────────┘
│ LOG_SISTEMA      │
└──────────────────┘
```

### 4.1 Ciclo de vida de una petición típica (guardado de una fila de Tracker)

1. Usuario edita una celda en el Data Grid (`index.html`) → Vue actualiza el `ref()` `staffTracker.value.data[i]` en memoria (reactividad local, sin red).
2. Usuario hace clic en "Guardar" → `saveRow(row, event)` (ver Anexo B, §20.6) marca `isSubmitting.value = true` y `row._isSaving = true` (doble bandera anti-doble-click), rellena `FECHA`/`HORA` si faltan, y llama `google.script.run.withSuccessHandler(...).withFailureHandler(...).internalUpdateTask(staffTracker.value.name, JSON.parse(JSON.stringify(row)), currentUsername.value)`.
3. GAS ejecuta `internalUpdateTask` (Anexo A, §19.4) en el servidor: aplica restricciones por rol, genera folio si es fila nueva, llama a `internalBatchUpdateTasks` (el Gatekeeper, Anexo A §19.3), y si la hoja de origen es `ANTONIA_VENTAS` o el usuario editado es un delegado, dispara la lógica de distribución/reverse-sync descrita en §10.2.
4. La respuesta (`res.data`) regresa al navegador; `saveRow` hace `Object.assign(row, res.data)` para fusionar el folio generado y cualquier campo saneado por el backend, y libera las banderas `isSubmitting`/`_isSaving`.
5. Si `res.moved === true` (la fila alcanzó 100% y fue archivada a la sección "TAREAS REALIZADAS"), el frontend recarga el Tracker completo (`reloadStaffTracker()`).

Este ciclo — edición local → RPC único → merge de la respuesta — es el patrón repetido en **todas** las pantallas del sistema (PPC, Work Orders, Proyectos, Agenda). No hay websockets ni polling: toda actualización es "pull" bajo demanda del usuario.

---

## 5. Modelo de Datos (Google Sheets)

No hay motor SQL: **cada "tabla" es una pestaña (`Sheet`) dentro de la Spreadsheet activa**, identificada por nombre. El backend busca hojas con `findSheetSmart(name)` (búsqueda tolerante a mayúsculas/espacios, código completo en Anexo A §19.1) y encabezados con `findHeaderRow(values)` (búsqueda heurística — **no asume que la fila 1 es el encabezado**, porque las hojas de personal suelen tener elementos de UI/branding sobre los datos; código completo también en §19.1).

### 5.1 Configuración central (`APP_CONFIG`, `CODIGO.js` líneas 15–28)

```js
const APP_CONFIG = {
  folderIdUploads: "",                 // ID de carpeta raíz de Drive para adjuntos (vacío = usa lógica dinámica)
  ppcSheetName: "PPCV3",               // Hoja maestra del módulo PPC (checklist de sitio, NO confundir con "Papa Caliente")
  draftSheetName: "PPC_BORRADOR",      // Borradores de PPC no enviados aún
  salesSheetName: "Datos",             // (uso interno legado)
  logSheetName: "LOG_SISTEMA",         // Auditoría global (login, cambios, errores)
  directorySheetName: "DB_DIRECTORY",  // Organigrama vivo (fuente de verdad en runtime, sincronizable)
  woMaterialsSheet: "DB_WO_MATERIALES",
  woLaborSheet: "DB_WO_MANO_OBRA",
  woToolsSheet: "DB_WO_HERRAMIENTAS",
  woEquipSheet: "DB_WO_EQUIPOS",
  woProgramSheet: "DB_WO_PROGRAMA"
};

const FOLIO_CONFIG = { SHEET_NAME: 'ANTONIA_VENTAS', COLUMN_NAME: 'Folio' };
```

Además, durante el guardado del módulo PPC (`apiSavePPCData`, ver Anexo A §19.6), el sistema crea **dinámicamente** dos hojas adicionales no listadas en `APP_CONFIG`:
- **`PPCV4`**: espejo exclusivo para las capturas de `ANTONIA_VENTAS`, con mapeo de encabezados alterno (`Fecha de Alta`, `Descripción de la Actividad`, `Archivos`, `Comentarios Semana en Curso`) para coincidir con un formato de pantalla legado.
- **`ADMINISTRADOR`**: hoja espejo de control, recibe copia de **toda** captura PPC y de toda distribución de Antonia, sin login propio — es el respaldo de auditoría visual para `ADMIN_CONTROL`.

> **Nota de nomenclatura importante:** el sistema tiene **dos conceptos distintos que ambos se abrevian "PPC"** y suelen confundirse:
> - **Módulo PPC** (`PPCV3`, `PPCV4`, `PPC_BORRADOR`, roles `PPC_ADMIN`/`WORKORDER_USER`, vistas `PPC_MENU`/`PPC_DINAMICO`/`PPC_FORM`): un checklist operativo por sitio con tres variantes (`PPC INTERNO`, `PPC PREOPERATIVO`, `PPC CLIENTE`), gestionado por Jesús Cantú.
> - **"Papa Caliente"** (columnas `PROCESO_LOG`/`MAP COT` en `ANTONIA_VENTAS`, ver §10.2): el pipeline Kanban de 7 etapas de cotizaciones de Ventas. **No comparten hoja ni lógica**, solo terminología del negocio.

### 5.2 `DB_DIRECTORY` — Organigrama vivo

| Columna | Tipo | Descripción |
|---|---|---|
| `NOMBRE` | texto | Nombre completo en mayúsculas (coincide con el nombre de la hoja Tracker de esa persona) |
| `DEPARTAMENTO` | texto | Uno de los 19 departamentos definidos en `allDepts` (§6.1) |
| `TIPO_HOJA` | texto | `ESTANDAR` \| `HIBRIDO` (vendedor+tracker) \| `VENTAS` (solo Antonia) |

Se auto-puebla la primera vez desde la constante `INITIAL_DIRECTORY` (`CODIGO.js` líneas 37–93, 36 registros — tabla completa en §6.4) si la hoja está vacía. `apiResyncDirectory()` (solo rol `ADMIN`) la re-escribe desde código y crea automáticamente cualquier hoja Tracker faltante. El código completo de `getDirectoryFromDB()` está en el Anexo A §19.1.

### 5.3 Hojas Tracker individuales (una por empleado, nombre = `NOMBRE` en `DB_DIRECTORY`)

Encabezados por defecto (`DEFAULT_TRACKER_HEADERS`, línea 95), creados automáticamente si la hoja no existe:

```
ID | ESPECIALIDAD | CONCEPTO | FECHA | RELOJ | AVANCE | ESTATUS | COMENTARIOS | ARCHIVO | CLASIFICACION | PRIORIDAD | FECHA_RESPUESTA
```

Columnas adicionales que aparecen dinámicamente según el flujo de negocio (no todas están en el default, pero el motor de escritura las soporta vía búsqueda case-insensitive y un mapa de **alias por columna** — ver la tabla `aliases` dentro de `internalBatchUpdateTasks`, Anexo A §19.3): `INVOLUCRADOS` (distribución lateral, ver §10.1), `VENDEDOR` (solo asignaciones desde `ANTONIA_VENTAS`), `F2`, `LAYOUT`, `COTIZACION`, `INFO CLIENTE`, `CORREO`, `CARPETA`, `PROCESO_LOG`, `MAP COT` (cuando la hoja recibe pasos delegados de Papa Caliente).

Las hojas de Tracker tienen además una **sección oculta de archivado automático**: cuando una fila alcanza estado completo (`ESTATUS` en `HECHO|TERMINADO|FINALIZADO|REALIZADO|COMPLETADO|DONE`, o `AVANCE`/`CUMPLIMIENTO` en `100|100%|SI|1` numérico), `internalBatchUpdateTasks` la mueve automáticamente por debajo de una fila separadora literal `"TAREAS REALIZADAS"`, sellando `FECHA_TERMINO` con la fecha del día si la columna existe. Esto es efectivamente un patrón "activo/histórico" implementado sin una segunda hoja.

### 5.4 `ANTONIA_VENTAS` — Hoja maestra de Ventas

Encabezados por defecto (`DEFAULT_SALES_HEADERS`, línea 96):

```
FOLIO | CLIENTE | CONCEPTO | VENDEDOR | FECHA | F. ENTREGA | ESTATUS | COMENTARIOS | ARCHIVO | MONTO | F2 | COTIZACION | TIMELINE | LAYOUT | AVANCE
```

Además contiene, en producción, las columnas ocultas de negocio (no visibles como UI simple pero leídas/escritas por el motor):
- **`PROCESO_LOG`**: JSON array — bitácora de la máquina de estados Papa Caliente (ver §10.2, estructura completa en `PAPA_CALIENTE_SDD.md` §4.1).
- **`MAP COT`**: string con emojis separado por `|` — representación visual/legible en la hoja del mismo timeline (ej. `🟢 L | 🔴 CD | ⚪ EP | ⚪ CI | ⚪ EV | ⚪ CEC | ⚪ RCC`).

Folios con formato `AV-XXXX` (prefijo fijo `AV-`, secuencia atómica en `PropertiesService` bajo la llave `SEQ_ANTONIA_SEQ_V2`, generada por `generateNumericSequence('ANTONIA_SEQ_V2')` con `LockService`, más un mecanismo de **auto-sanación**: cada vez que Antonia guarda un lote, `apiSaveTrackerBatch` escanea los folios `AV-XXXX` entrantes y, si detecta un número mayor al contador guardado en `PropertiesService`, adelanta el contador — esto evita que la secuencia se quede "atrás" si alguna fila fue creada con un folio manual más alto).

**Lista blanca de columnas editables sobre una fila ya existente de `ANTONIA_VENTAS`** (`allowedBase`, repetida literalmente en tres funciones — `apiSaveTrackerBatch`, `internalUpdateTask` y, de forma implícita, en la restricción de `restrictedUsers` — ver Anexo A §19.3/§19.4):

```
FOLIO, ID, ESTATUS, MAP COT, PROCESO_LOG, PROCESO, STATUS, AVANCE, AVANCE %, _rowIndex,
VENDEDOR, RESPONSABLE, INVOLUCRADOS, ENCARGADO, CONCEPTO, DESCRIPCION, CLIENTE, COTIZACION,
F2, LAYOUT, TIMELINE, AREA, CLASIFICACION, CLASI, DIAS, RELOJ, ESPECIALIDAD, ARCHIVO, ARCHIVOS,
COMENTARIOS, PRIORIDAD, PRIORIDAD DE COTIZACION, PRIO. COT., F. VISITA, F. INICIO, F. ENTREGA,
FECHA VISITA, FECHA INICIO, DÍAS FINALIZ. COTIZ, DIAS FINALIZ. COTIZ, CORREO, CARPETA,
INFO CLIENTE, CORREOS, CARPETAS, REQUISITOR
  + cualquier columna cuyo nombre contenga "FECHA" o "ALTA" (excepción genérica de fecha)
```

### 5.5 Módulo PPC (`PPCV3`, `PPCV4`, `PPC_BORRADOR`)

Encabezados base (`CODIGO.js` líneas 3136 y 3161):

```
ID | ESPECIALIDAD | DESCRIPCION | RESPONSABLE | FECHA | RELOJ | CUMPLIMIENTO | ARCHIVO | COMENTARIOS |
COMENTARIOS PREVIOS | ESTATUS | AVANCE | CLASIFICACION | PRIORIDAD | RIESGOS | FECHA_RESPUESTA | DETALLES_EXTRA
```

`CUMPLIMIENTO` usa fallback estricto `'NO'` si viene vacío (regla de `AGENTS.md` §2). El objeto que realmente se persiste (armado dentro de `apiSavePPCData`) usa nombres de columna distintos a los del checklist visual del formulario — el mapeo exacto item→columna está documentado en el Anexo A §19.6.

**Auto-migración de columnas para `JESUS_CANTU`:** si el usuario activo es `JESUS_CANTU`, el sistema agrega en caliente (si faltan) las columnas `RUTA_CRITICA, ZONA, CUANT_REQUERIDO, CUANT_REAL, CONTRATISTA, DIAS_L, DIAS_M, DIAS_X, DIAS_J, DIAS_V, DIAS_S, DIAS_D` al final de `PPCV3`, con formato negrita y fondo gris — soporte del checklist semanal por día de la semana usado en el módulo de "Interdisciplinaria".

### 5.6 `LOG_SISTEMA` — Auditoría global

```
FECHA | USUARIO | ACCION | DETALLES
```

Escrita exclusivamente vía `registrarLog(user, action, details)` (línea 298, código completo en Anexo A §19.1) — **toda función backend relevante debe llamarla** para trazabilidad (login/logout, altas/bajas de empleado, cambios de fecha, distribución de tareas, reverse-sync, errores críticos). Acciones observadas en el código: `LOGIN`, `LOGIN_FAIL`, `LOGOUT`, `MIGRACION_DB`, `RESYNC_DB`, `ADD_EMPLOYEE`, `DELETE_EMPLOYEE`, `KPI_COTIZACIONES`, `AUTO_KPI`, `RUN_COMPLETE` (agente), `CAMBIO_FECHA`, `ACTUALIZAR`/`ACTUALIZAR/COMENTARIO`, `REMOVED_WORKER`, `REMOVE_ERROR`, `DIST_FAIL`, `DIST_SKIP`, `DIST_ERROR`, `REVERSE_SYNC`/`REVERSE_SYNC_BATCH`, `BATCH_UPDATE`, `GUARDADO_PPC`, `ERROR_CRITICO_PPC`, `CONFIG_TRIGGER`.

### 5.7 Órdenes de Trabajo (`DB_WO_*`) — 5 hojas relacionales

Todas ligadas por la columna `FOLIO` (formato `SEQClDept DDMMYY`, generado por `generateWorkOrderFolio()`, código completo en Anexo A §19.5).

| Hoja (`APP_CONFIG.*`) | Headers |
|---|---|
| `DB_WO_MATERIALES` | `FOLIO, CANTIDAD, UNIDAD, TIPO, DESCRIPCION, COSTO, ESPECIFICACION, TOTAL, RESIDENTE, COMPRAS, CONTROLLER, ORDEN_COMPRA, PAGOS, ALMACEN, LOGISTICA, RESIDENTE_OBRA` |
| `DB_WO_MANO_OBRA` | `FOLIO, CATEGORIA, SALARIO, PERSONAL, SEMANAS, EXTRAS, NOCTURNO, FIN_SEMANA, OTROS, TOTAL` |
| `DB_WO_HERRAMIENTAS` | `FOLIO, CANTIDAD, UNIDAD, DESCRIPCION, COSTO, TOTAL, RESIDENTE, CONTROLLER, ALMACEN, LOGISTICA, RESIDENTE_FIN` |
| `DB_WO_EQUIPOS` | `FOLIO, CANTIDAD, UNIDAD, TIPO, DESCRIPCION, ESPECIFICACION, DIAS, HORAS, COSTO, TOTAL` |
| `DB_WO_PROGRAMA` | `FOLIO, DESCRIPCION, FECHA, DURACION, UNIDAD_DURACION, UNIDAD, CANTIDAD, PRECIO, TOTAL, RESPONSABLE, SECCION, ESTATUS` |

Nótese que las filas de `DB_WO_MATERIALES` y `DB_WO_HERRAMIENTAS` incorporan un sub-objeto `papaCaliente` en el payload del frontend (`m.papaCaliente.residente`, `.compras`, `.controller`, `.ordenCompra`, `.pagos`, `.almacen`, `.logistica`, `.residenteObra`/`.residenteFin`) — es una **tercera acepción** de "papa caliente" dentro del sistema: en el contexto de Work Orders, representa el flujo de aprobación secuencial (Residente → Compras → Controller → Almacén → Logística) de cada línea de material/herramienta, independiente del pipeline de cotizaciones de Ventas y del checklist PPC. Ver aclaración ampliada en §10.4.

**Algoritmo de folio de Work Order** (`generateWorkOrderFolio(clientName, deptName)`, código completo Anexo A §19.5):
`SEQ(4 dígitos, contador en Script Properties "WORKORDER_SEQ") + Iniciales(2 letras del cliente) + " " + Abreviatura de departamento (mapa fijo de 19 entradas, ej. "Construccion"→"Const", "Electromecanica"→"Electro") + " " + DDMMYY`.
Ejemplo: `0007HM Const 020726`.

### 5.8 Proyectos/Sitios (Cascada Sitio → Subproyecto → Tarea)

`apiSaveSite`, `apiSaveSubProject`, `apiFetchCascadeTree`, `apiSaveProjectTask`. Al crear un sitio nuevo, `apiCreateStandardStructure(siteId, user)` auto-genera subproyectos hijos siguiendo `STANDARD_PROJECT_STRUCTURE` (línea 102):

```
NAVE, AMPLIACION, PPC INTERNO, PPC PREOPERATIVO, PPC CLIENTE,
DOCUMENTOS, PLANOS Y DISEÑOS, FOTOGRAFIAS, CORRESPONDENCIA, REPORTES
```

Los 3 nodos que contienen `"PPC"` en el nombre se marcan `type: "PPC_MASTER"` para que el frontend los renderice con el motor de checklist en vez del árbol genérico; el resto se marca `type: "GENERAL"`.

### 5.9 Banco de Información / Banco de Cotizaciones (Google Drive)

`processQuoteRow()`, `archiveFile()`, `getBankRootFolder()`, `getOrCreateFolder()`: estructura de carpetas **`[Año] / [Mes] / [Cliente]`** creada dinámicamente. `apiFetchInfoBankCompanies(year, monthName)` y `apiFetchInfoBankData(year, monthName, companyName, folderName)` exponen esta jerarquía al frontend (vista "Banco de Información"). El archivado se dispara automáticamente cada vez que Antonia guarda una fila con `COTIZACION` o `ARCHIVO` no vacío (tanto en el flujo batch de `apiSaveTrackerBatch` como en el flujo de edición única de `internalUpdateTask`), además de poder correrse en lote retroactivo con `batchArchiveExistingQuotes()`/`runFullArchivingBatch()`. Límite práctico de subida: ~45–50MB por archivo (restricción de Base64 + timeout de GAS).

### 5.10 `KPI_COTIZACIONES`

Hoja de métricas agregadas escrita por `apiWriteQuoteMetricsToSheet()` y refrescada por el trigger diario `autoUpdateQuoteMetrics()`. Es una hoja **distinta** de la fuente que consume `apiFetchAdminKPIs()` (Anexo A §19.7) para el Dashboard de KPIs del CEO: `apiFetchAdminKPIs` recalcula en vivo directamente desde las hojas `<Vendedor> (VENTAS)` de los 6 vendedores activos, mientras que `KPI_COTIZACIONES` es un snapshot diario usado por el "agente" narrativo con Gemini (`runQuoteMetricsAgent`/`_sendAgentEmail`). Ver fórmulas de negocio exactas en `SDD_KPI_ADMIN.md` y su reproducción operativa en §10.5 de este documento.

### 5.11 `AGENDA_PERSONAL` y `HABITOS_LOG` — módulo de agenda/hábitos personales (no documentado en `APP_CONFIG`)

A diferencia de todas las demás hojas del sistema, estas dos **no están declaradas en la constante `APP_CONFIG`** (§5.1) — sus nombres están hardcodeados directamente como strings literales dentro de las funciones que las usan (`findSheetSmart("AGENDA_PERSONAL")`, `findSheetSmart("HABITOS_LOG")`, código completo en Anexo A §19.16). Se crean perezosamente la primera vez que alguien guarda un evento/hábito.

| Hoja | Headers |
|---|---|
| `AGENDA_PERSONAL` | `ID, USUARIO, TITULO, TIPO, FECHA, HORA_INICIO, HORA_FIN, DETALLES, CLASIFICACION, ESTATUS` |
| `HABITOS_LOG` | `ID, USUARIO, HABITO, META, LOG_JSON, FECHA_ACTUALIZACION` |

Particularidad de diseño: `apiFetchUnifiedAgenda(username)` (Anexo A §19.16) **si ninguna de las dos hojas existe todavía**, devuelve datos de ejemplo hardcodeados (rutina de mañana, gimnasio, comida; hábitos de lectura/ejercicio/meditación) en vez de un arreglo vacío — es un fallback de demostración intencional para que la UI de Agenda nunca se vea vacía en un tenant nuevo, no un error. Al clonar el sistema para una organización nueva, este comportamiento se mantiene hasta que el primer usuario guarda su primer evento real.

---

## 6. Organigrama, Roles y Matriz de Permisos (RBAC)

### 6.1 Departamentos (`allDepts`, dentro de `getSystemConfig()`, línea 563)

19 departamentos con `label`, `icon` (FontAwesome) y `color` propios:

| Clave | Label mostrado | Icono FA | Color |
|---|---|---|---|
| `CEO` | Dirección General (CEO) | `fa-crown` | `#b8860b` |
| `CONSTRUCCION` | Construcción | `fa-hard-hat` | `#e83e8c` |
| `COMPRAS` | Compras/Almacén | `fa-shopping-cart` | `#198754` |
| `PRESUPUESTOS` | Presupuestos | `fa-calculator` | `#6f42c1` |
| `PRECIOS UNITARIOS` | Precios Unitarios | `fa-dollar-sign` | `#20c997` |
| `SEGURIDAD` | Seguridad | `fa-shield-alt` | `#dc3545` |
| `EHS` | Seguridad (EHS) | `fa-shield-alt` | `#dc3545` |
| `DISEÑO` | Diseño & Ing. | `fa-drafting-compass` | `#0d6efd` |
| `ELECTROMECANICA` | Electromecánica | `fa-bolt` | `#ffc107` |
| `HVAC` | HVAC | `fa-fan` | `#fd7e14` |
| `LIMPIEZA` | Limpieza | `fa-broom` | `#0dcaf0` |
| `ALMACEN Y MAQUINARIA` | Almacén y Maquinaria | `fa-warehouse` | `#198754` |
| `ADMINISTRACION` | Administración | `fa-briefcase` | `#6f42c1` |
| `VENTAS` | Ventas | `fa-handshake` | `#0dcaf0` |
| `MAQUINARIA` | Maquinaria | `fa-truck` | `#20c997` |
| `FINANZAS` | Finanzas | `fa-coins` | `#198754` |
| `FACTURACION` | Facturación | `fa-file-invoice-dollar` | `#0d6efd` |
| `RH` | Recursos Humanos | `fa-users` | `#6610f2` |
| `CALIDAD` | Calidad | `fa-clipboard-check` | `#0dcaf0` |

`SEGURIDAD` y `EHS` son dos claves independientes con el mismo ícono/color — vestigio de un rebautizo de departamento (ver §6.5, historial de movimientos). `MAQUINARIA` y `FACTURACION` existen en `allDepts` pero no tienen ningún empleado activo asignado en `INITIAL_DIRECTORY` a la fecha de este documento — son departamentos "reservados" en el catálogo visual.

### 6.2 Roles del sistema

| Rol | Quién (usuarios reales) | Acceso otorgado por `getSystemConfig()` |
|---|---|---|
| `ADMIN` | `LUIS_CARLOS` (CEO) | Ve todos los departamentos (`allDepts`), todo el staff (`fullDirectory`), módulo KPI (`KPI_DASHBOARD`), monitor de Antonia (`MIRROR_TONITA`). Es el rol "por defecto" (rama `else` final de `getSystemConfig`) — cualquier rol no reconocido explícitamente cae aquí. `accessProjects: true`, `canSeeBancoJuntas: true`. |
| `ADMIN_CONTROL` | `JAIME_OLIVO`, `DIMAS_RAMOS` | Igual que ADMIN (todos los departamentos/staff) + módulo "Control" (`ADMIN_TRACKER`, hoja espejo `ADMINISTRADOR`) + monitor de Toñita (`MIRROR_TONITA`), **sin** módulo KPI. |
| `PPC_ADMIN` | `JESUS_CANTU` | Solo módulos PPC (Maestro + Semanal), `accessProjects: true`, `staff: []` (sin departamentos de personal). Su módulo PPC Maestro se relabelea dinámicamente a **"INTERDICIPLINARIA"** (sic, typo en el código fuente original, preservado intencionalmente aquí como referencia exacta). |
| `TONITA` | `ANTONIA_VENTAS` | Solo departamento `VENTAS` (de los 19 disponibles), mira su propio tracker (`mirror_staff` → `ANTONIA PINEDA LOPEZ`) + módulos PPC Maestro y Semanal. `accessProjects: false`, `canSeeBancoJuntas: false`. |
| `WORKORDER_USER` | `PREWORK_ORDER` | Solo el módulo "Pre Work Order" (variante relabeleada del módulo PPC maestro, `type: "ppc_native"`). Sin departamentos, `staff: []`. |
| `STAFF_USER` | Los 34 usuarios restantes | Ve únicamente "Mi Tabla" (su propio Tracker, `mirror_staff` apuntando a `staffName`) + "Agregar Actividad" (módulo PPC nativo). Si `seller: true` en `USER_DB`, se añade el módulo "Ventas" apuntando a `<staffName> (VENTAS)`. `accessProjects: false`. |

**Caso especial hardcodeado (no vive en `USER_DB`, vive directamente en `getSystemConfig()`):** si `username === 'JUANY_RODRIGUEZ'`, sin importar que su `role` en `USER_DB` sea `STAFF_USER`, recibe una rama de código separada que le da acceso ampliado a los departamentos `COMPRAS`, `FACTURACION`, `FINANZAS` (ve el staff completo de esos 3 departamentos, no solo su propio tracker). Es una excepción de negocio que **solo** existe como `if` explícito en el código — replicar este patrón (usuario específico con rama propia) es la forma establecida del sistema para dar permisos "a medida" sin crear un rol nuevo.

**Lista de usuarios con restricciones de edición reducidas sobre hojas ajenas** (`restrictedUsers`, dentro de `internalUpdateTask`, ver Anexo A §19.4): `ANGEL_SALINAS`, `TERESA_GARZA`, `EDUARDO_TERAN`, `EDUARDO_MANZANARES`, `RAMIRO_RODRIGUEZ`, `SEBASTIAN_PADILLA` — estos 6 son los mismos 6 "vendedores" que alimentan el Dashboard de KPIs (§5.10). Cuando editan una hoja que **no** es su propio tracker (ej. reciben una tarea delegada y la ven reflejada en otro lado), solo pueden tocar: `ESTATUS/STATUS, MAP COT, PROCESO, FOLIO/ID, AVANCE, REQUISITOR, INFO CLIENTE, F2, COTIZACION/COT, TIMELINE, LAYOUT, COMENTARIOS, CORREO/CARPETA(S), _rowIndex`.

### 6.3 Usuario → Rol → Tracker (`USER_DB`, `CODIGO.js` línea 212, **41 cuentas registradas**)

> Contraseñas omitidas intencionalmente — ver advertencia de seguridad en §13. `seller: true` implica que el usuario recibe también el módulo "Ventas" apuntando a la hoja `<staffName> (VENTAS)`, además de su tracker normal.

| Usuario (`USER_DB` key) | Rol | Nombre para mostrar (`label`) | Hoja Tracker (`staffName`) | Departamento | ¿Vendedor? |
|---|---|---|---|---|---|
| `JESUS_CANTU` | `PPC_ADMIN` | PPC Manager | — (sin tracker propio) | — | No |
| `JAIME_OLIVO` | `ADMIN_CONTROL` | Jaime Olivo | — | — | No |
| `PREWORK_ORDER` | `WORKORDER_USER` | Workorder | — | — | No |
| `ANTONIA_VENTAS` | `TONITA` | Antonia Pineda | ANTONIA PINEDA LOPEZ | VENTAS | No (usa `VENDEDOR`, no `seller`) |
| `LUIS_CARLOS` | `ADMIN` | Luis Carlos Holt Montero | LUIS CARLOS | CEO | No |
| `JUAN_JOSE_SANCHEZ` | `STAFF_USER` | Juan Jose Sanchez Muñiz | JUAN JOSE SANCHEZ | CEO | Sí |
| `DIMAS_RAMOS` | `ADMIN_CONTROL` | Dimas Eliel Ramos Garcia | DIMAS ELIEL RAMOS GARCIA | RH | No |
| `LAURA_HUERTA` | `STAFF_USER` | Laura Huerta Rocha | LAURA EDITH HUERTA ROCHA | RH | No |
| `LILIANA_MARTINEZ` | `STAFF_USER` | Liliana Martinez Ibarra | LILIANA AYLIN MARTINEZ IBARRA | RH | No |
| `FRANCISCO_SANCHEZ_SERNA` | `STAFF_USER` | Francisco Sanchez Serna | FRANCISCO SANCHEZ SERNA | RH | No |
| `JUANY_RODRIGUEZ` | `STAFF_USER` (+ excepción de código, ver §6.2) | Juana Maria Rodriguez Juarez | JUANA MARIA RODRIGUEZ JUAREZ | FINANZAS | No |
| `ZAIRA_AGUILAR` | `STAFF_USER` | Zaira Yazmin Aguilar Aguilon | ZAIRA YAZMIN AGUILAR AGUILON | FINANZAS | No |
| `SAIRA` | `STAFF_USER` | Zaira Yazmin Aguilar Aguilon | ZAIRA YAZMIN AGUILAR AGUILON | FINANZAS | No — **cuenta duplicada/legacy de `ZAIRA_AGUILAR`**, misma persona y mismo tracker, dos credenciales de acceso distintas |
| `ROCIO_CASTRO` | `STAFF_USER` | Rocio Castro Covarrubias | ROCIO ABIGAIL CASTRO COVARRUBIAS | FINANZAS | No |
| `DANIA_GONZALEZ` | `STAFF_USER` | Dania Lizbeth Gonzalez Lores | DANIA LIZBETH GONZALEZ LORES | FINANZAS | No |
| `SONIA_GARCIA` | `STAFF_USER` | Sonia Garcia Perez | SONIA GARCIA PEREZ | COMPRAS | No |
| `JUDITH_ECHAVARRIA` | `STAFF_USER` | Cristian Judith Echavarria Rodriguez | JUDITH ECHAVARRIA | COMPRAS | Sí |
| `VANESSA_DE_LARA` | `STAFF_USER` | Erika Vanessa Rodriguez De Lara | VANESSA DE LARA | COMPRAS | No |
| `EDUARDO_TERAN` | `STAFF_USER` (+ en `restrictedUsers`) | Jesus Eduardo Teran Garcia | EDUARDO TERAN | PRESUPUESTOS | Sí |
| `ANTONIA_PINEDA` | `STAFF_USER` | Antonia Pineda Lopez | ANTONIA PINEDA LOPEZ | PRESUPUESTOS | No — **mismo `staffName`/tracker que `ANTONIA_VENTAS`**, es la misma hoja vista desde dos cuentas distintas (una como "vendedora maestra" `TONITA`, otra como staff normal) |
| `CARLOS_MENDEZ` | `STAFF_USER` | Carlos Mendez Urbina | CARLOS MENDEZ | CALIDAD | No |
| `RUBI_MORENO` | `STAFF_USER` | Rubi Moreno Rodriguez | RUBI MORENO RODRIGUEZ | SEGURIDAD | No |
| `TERESA_GARZA` | `STAFF_USER` (+ en `restrictedUsers`) | Maria Teresa Hernandez Garza | TERESA GARZA | PRECIOS UNITARIOS | Sí |
| `GERALDINE_MARTINEZ` | `STAFF_USER` | Geraldine Marie Martinez Hernandez | GERALDINE MARTINEZ HERNANDEZ | PRECIOS UNITARIOS | No |
| `ANGEL_SALINAS` | `STAFF_USER` (+ en `restrictedUsers`) | Jose Angel Salinas Ramirez | ANGEL SALINAS | DISEÑO | Sí |
| `URIMAR_LOPEZ` | `STAFF_USER` | Edgar Urimar Lopez Maldonado | EDGAR URIMAR LOPEZ MALDONADO | DISEÑO | No |
| `EDUARDO_MANZANARES` | `STAFF_USER` (+ en `restrictedUsers`) | Eduardo Manzanares Sanchez | EDUARDO MANZANARES | VENTAS | Sí |
| `RAMIRO_RODRIGUEZ` | `STAFF_USER` (+ en `restrictedUsers`) | Ramiro Rodriguez Escalante | RAMIRO RODRIGUEZ | VENTAS | Sí |
| `SEBASTIAN_PADILLA` | `STAFF_USER` (+ en `restrictedUsers`) | Erick Sebastian Padilla Carrillo | SEBASTIAN PADILLA | VENTAS | Sí |
| `JEHU_MARTINEZ` | `STAFF_USER` | Jehu Arsenio Martinez Montes | JEHU MARTINEZ | ELECTROMECANICA | No |
| `MIGUEL_GALLARDO` | `STAFF_USER` | Miguel Angel Gallardo Jaramillo | MIGUEL GALLARDO | ELECTROMECANICA | No |
| `ROLANDO_MORENO` | `STAFF_USER` | Jesus Rolando Moreno Perez | ROLANDO MORENO | HVAC | No |
| `EMILIANO_AREDON` | `STAFF_USER` | Emiliano Arredondo Gomez | EMILIANO ARREDONDO GOMEZ | HVAC | No |
| `INGE_OLIVO` | `STAFF_USER` | Jaime Antonio Olivo Guerrero | JAIME OLIVO | CONSTRUCCION | No — **nombre de usuario `INGE_OLIVO` distinto de `JAIME_OLIVO` (cuenta `ADMIN_CONTROL`), pero mismo `staffName` "JAIME OLIVO"**: dos cuentas de login diferentes apuntan al mismo tracker |
| `RICARDO_MENDO` | `STAFF_USER` | Ricardo Alonso Mendo Morales | RICARDO MENDO | CONSTRUCCION | No |
| `ALFONSO_CORREA` | `STAFF_USER` | Alfonso Correa De Leon | ALFONSO CORREA | CONSTRUCCION | Sí |
| `CESAR_EDUARDO_GARCIA` | `STAFF_USER` | Cesar Eduardo Garcia Avalos | CESAR EDUARDO GARCIA AVALOS | CONSTRUCCION | No |
| `EDUARDO_BENITEZ` | `STAFF_USER` | Eduardo Israel Benitez Garcia | EDUARDO BENITEZ | LIMPIEZA | No |
| `DANIELA_CASTRO` | `STAFF_USER` | Daniela Castro | DANIELA CASTRO | GENERAL | No — **no aparece en `CREDENCIALES.md`**, cuenta activa en `USER_DB` sin documentación externa |
| `ANTONIO_SALAZAR` | `STAFF_USER` | Antonio Salazar | ANTONIO SALAZAR | GENERAL | No — **no aparece en `CREDENCIALES.md`**, cuenta activa en `USER_DB` sin documentación externa |
| `CESAR_GOMEZ` | `STAFF_USER` | Cesar Gomez | CESAR GOMEZ | GENERAL | No — ⚠️ **`CREDENCIALES.md` lo lista explícitamente en su sección "Bajas (eliminados de USER_DB)", pero la cuenta sigue presente y activa en `CODIGO.js`.** Es una inconsistencia real entre la documentación y el código en producción a la fecha de este documento — quien clone el sistema debe decidir cuál de las dos fuentes es la correcta y resolver la discrepancia (lo más probable, dado que el código es lo que efectivamente se ejecuta, es que la baja documentada en `CREDENCIALES.md` nunca se aplicó en `CODIGO.js`). |

### 6.4 `INITIAL_DIRECTORY` — Semilla del organigrama (`CODIGO.js` líneas 37–93, 36 registros)

Esta es la constante que puebla `DB_DIRECTORY` la primera vez (§5.2) y la que reconstruye `apiResyncDirectory()`. Es **la fuente de verdad para navegación por departamento** (distinta de `USER_DB`, que es la fuente de verdad para login/roles — normalmente coinciden en `staffName`↔`name`, con las excepciones ya anotadas en §6.3):

```js
const INITIAL_DIRECTORY = [
    // CEO
    { name: "LUIS CARLOS", dept: "CEO", type: "ESTANDAR" },
    { name: "JUAN JOSE SANCHEZ", dept: "CEO", type: "ESTANDAR" },
    // RECURSOS HUMANOS (RH)
    { name: "DIMAS ELIEL RAMOS GARCIA", dept: "RH", type: "ESTANDAR" },
    { name: "LAURA EDITH HUERTA ROCHA", dept: "RH", type: "ESTANDAR" },
    { name: "LILIANA AYLIN MARTINEZ IBARRA", dept: "RH", type: "ESTANDAR" },
    { name: "FRANCISCO SANCHEZ SERNA", dept: "RH", type: "ESTANDAR" },
    // FINANZAS
    { name: "JUANA MARIA RODRIGUEZ JUAREZ", dept: "FINANZAS", type: "ESTANDAR" },
    { name: "ZAIRA YAZMIN AGUILAR AGUILON", dept: "FINANZAS", type: "ESTANDAR" },
    { name: "ROCIO ABIGAIL CASTRO COVARRUBIAS", dept: "FINANZAS", type: "ESTANDAR" },
    { name: "DANIA LIZBETH GONZALEZ LORES", dept: "FINANZAS", type: "ESTANDAR" },
    // COMPRAS
    { name: "SONIA GARCIA PEREZ", dept: "COMPRAS", type: "ESTANDAR" },
    { name: "JUDITH ECHAVARRIA", dept: "COMPRAS", type: "ESTANDAR" },
    { name: "VANESSA DE LARA", dept: "COMPRAS", type: "ESTANDAR" },
    // PRESUPUESTOS
    { name: "EDUARDO TERAN", dept: "PRESUPUESTOS", type: "HIBRIDO" },
    { name: "ANTONIA PINEDA LOPEZ", dept: "PRESUPUESTOS", type: "ESTANDAR" },
    // CALIDAD
    { name: "CARLOS MENDEZ", dept: "CALIDAD", type: "ESTANDAR" },
    // SEGURIDAD
    { name: "RUBI MORENO RODRIGUEZ", dept: "SEGURIDAD", type: "ESTANDAR" },
    // PRECIOS UNITARIOS
    { name: "TERESA GARZA", dept: "PRECIOS UNITARIOS", type: "HIBRIDO" },
    { name: "GERALDINE MARTINEZ HERNANDEZ", dept: "PRECIOS UNITARIOS", type: "ESTANDAR" },
    // DISEÑO
    { name: "ANGEL SALINAS", dept: "DISEÑO", type: "HIBRIDO" },
    { name: "EDGAR URIMAR LOPEZ MALDONADO", dept: "DISEÑO", type: "ESTANDAR" },
    // VENTAS
    { name: "ANTONIA_VENTAS", dept: "VENTAS", type: "VENTAS" },
    { name: "EDUARDO MANZANARES", dept: "VENTAS", type: "HIBRIDO" },
    { name: "RAMIRO RODRIGUEZ", dept: "VENTAS", type: "HIBRIDO" },
    { name: "SEBASTIAN PADILLA", dept: "VENTAS", type: "HIBRIDO" },
    // ELECTROMECANICA
    { name: "JEHU MARTINEZ", dept: "ELECTROMECANICA", type: "ESTANDAR" },
    { name: "MIGUEL GALLARDO", dept: "ELECTROMECANICA", type: "ESTANDAR" },
    // HVAC
    { name: "ROLANDO MORENO", dept: "HVAC", type: "ESTANDAR" },
    { name: "EMILIANO ARREDONDO GOMEZ", dept: "HVAC", type: "ESTANDAR" },
    // CONSTRUCCION
    { name: "JAIME OLIVO", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "RICARDO MENDO", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "ALFONSO CORREA", dept: "CONSTRUCCION", type: "ESTANDAR" },
    { name: "CESAR EDUARDO GARCIA AVALOS", dept: "CONSTRUCCION", type: "ESTANDAR" },
    // LIMPIEZA
    { name: "EDUARDO BENITEZ", dept: "LIMPIEZA", type: "ESTANDAR" },
    // ALMACEN Y MAQUINARIA
    { name: "SONIA GARCIA PEREZ", dept: "ALMACEN Y MAQUINARIA", type: "ESTANDAR" },
    // SISTEMA (hoja espejo de control, sin login)
    { name: "ADMINISTRADOR", dept: "ADMINISTRACION", type: "HIBRIDO" },
    // GENERAL
    { name: "DANIELA CASTRO", dept: "GENERAL", type: "ESTANDAR" },
    { name: "CESAR GOMEZ", dept: "GENERAL", type: "ESTANDAR" }
];
```

Notas de lectura de esta tabla:
- **`SONIA GARCIA PEREZ` aparece dos veces** (COMPRAS y ALMACEN Y MAQUINARIA) — una sola persona con presencia en dos departamentos de navegación, pero una única cuenta `SONIA_GARCIA`/un único tracker.
- **`ADMINISTRADOR`** es la única entrada `type: "HIBRIDO"` que no corresponde a una persona física — es la hoja espejo de control usada por `ADMIN_CONTROL` (§6.2), sin cuenta de login propia asociada en `USER_DB`.
- **`type: "VENTAS"`** es exclusivo de la entrada `ANTONIA_VENTAS` — es el único valor de `TIPO_HOJA` reservado a la cuenta maestra de Ventas.
- **`type: "HIBRIDO"`** marca a los vendedores (`EDUARDO TERAN`, `TERESA GARZA`, `ANGEL SALINAS`, `EDUARDO MANZANARES`, `RAMIRO RODRIGUEZ`, `SEBASTIAN PADILLA`) — coincide exactamente con `seller: true` en `USER_DB` para esas mismas 6 personas más `JUAN_JOSE_SANCHEZ` y `ALFONSO_CORREA` y `JUDITH_ECHAVARRIA`, que en `USER_DB` sí tienen `seller: true` pero en `INITIAL_DIRECTORY` están marcados `type: "ESTANDAR"` — **otra inconsistencia menor entre las dos fuentes**, sin impacto funcional porque `getSystemConfig()` decide el módulo "Ventas" leyendo `seller` de `USER_DB`, no `type` de `INITIAL_DIRECTORY` (`TIPO_HOJA` se usa solo para metadatos de visualización del organigrama, no para RBAC).

### 6.5 Historial de reorganización (documentado en `CREDENCIALES.md`, última actualización 2026-06-09)

**Movimientos de departamento aplicados:**
- `LUIS_CARLOS` (ADMINISTRACION → **CEO**), `JUAN_JOSE_SANCHEZ` (VENTAS → **CEO**).
- `ZAIRA_AGUILAR` y `DANIA_GONZALEZ` (FACTURACION → **FINANZAS**).
- `JUDITH_ECHAVARRIA` (VENTAS → **COMPRAS**).
- `EDUARDO_TERAN` (CONSTRUCCION → **PRESUPUESTOS**).
- `RUBI_MORENO` (EHS → **SEGURIDAD**).
- `TERESA_GARZA` (VENTAS → **PRECIOS UNITARIOS**), `GERALDINE_MARTINEZ` (ADMINISTRACION → **PRECIOS UNITARIOS**).
- `ANGEL_SALINAS` (VENTAS → **DISEÑO**).
- `ALFONSO_CORREA` (VENTAS → **CONSTRUCCION**), `CESAR_EDUARDO_GARCIA` (DISEÑO → **CONSTRUCCION**).
- `EDUARDO_BENITEZ` (ADMINISTRACION → **LIMPIEZA**).

**Alta nueva:** `ANTONIA_PINEDA` — Antonia Pineda Lopez (PRESUPUESTOS).

**Bajas documentadas (eliminados de `USER_DB` según `CREDENCIALES.md`):** `CESAR_GOMEZ` (⚠️ ver discrepancia en §6.3 — sigue presente en el código), `GUILLERMO_DAMICO`, `REYNALDO_GARCIA`, `EDGAR_HOLT`, `ALEXIS_TORRES`, `RUBEN_PESQUEDA`, `GISELA_DOMINGUEZ`, `CITLALI_GOMEZ`, `AIMEE_RAMIREZ`, `EDGAR_LOPEZ`, `JUAN_ENRIQUE_PEREZ` — ninguna de estas 10 últimas aparece en el `USER_DB` actual, consistente con la documentación.

**Departamentos creados en esta reorganización:** `CEO`, `PRESUPUESTOS`, `PRECIOS UNITARIOS`, `SEGURIDAD`, `LIMPIEZA`, `ALMACEN Y MAQUINARIA`.

**Conservados a propósito:** `ANTONIA_VENTAS` (rol `TONITA`, permanece en `VENTAS`) y la hoja espejo `ADMINISTRADOR` (control, sin login).

> **Procedimiento operativo para aplicar cambios de organigrama en producción:** entrar como `ADMIN` y ejecutar **Re-sincronizar Directorio** (`apiResyncDirectory`, botón en UI de administración). Esto reescribe `DB_DIRECTORY` con el organigrama vigente en `INITIAL_DIRECTORY` y crea automáticamente cualquier hoja de Tracker faltante (ej. creó `ANTONIA PINEDA LOPEZ` cuando se dio de alta esa cuenta).

---

## 7. Catálogo de Funciones del Backend (`CODIGO.js`)

Agrupado por responsabilidad funcional. El listado línea-por-línea completo está en §17 (Anexo). El código fuente **literal y completo** de las 15 funciones marcadas con 📄 está reproducido en el Anexo A (§19).

### 7.1 Entrada, Auth y Sesión
`doGet(e)` 📄 sirve `index.html` vía `HtmlService.createTemplateFromFile` con `XFrameOptionsMode.ALLOWALL`. `apiLogin(username, password)` 📄 valida contra `USER_DB` con comparación exacta de contraseña (sin hash), audita con `registrarLog`. `apiLogout(username)` 📄. `getSystemConfig(role, username)` 📄 arma el árbol de navegación por rol (§6.2). `getDirectoryFromDB()` 📄 / `apiResyncDirectory()` gestionan el organigrama vivo. `apiAddEmployee(payload)` / `apiDeleteEmployee(name)` CRUD de personal (crea/borra hoja Tracker asociada).

### 7.2 Motor de Trackers y Guardado por Lotes
`internalFetchSheetData(sheetName)` / `apiFetchStaffTrackerData(personName)`: lectura. `apiSaveTrackerBatch(personName, tasks, username)` 📄 (línea 5183, 487 líneas — la función más grande del sistema): guardado masivo, ruteo de "Papa Caliente", auto-sanación de folios `AV-`, reverse-sync, notificación Outlook. `internalBatchUpdateTasks(sheetName, tasksArray, useOwnLock)` 📄 (línea 2156, 444 líneas): el "Gatekeeper" — usa `CacheService` con `_tempId` como llave de bloqueo anti-duplicación, remueve filtros de la hoja antes de escribir, resuelve alias de columnas, y ejecuta el auto-archivado de tareas al 100%. `internalUpdateTask` 📄 (línea 2624, 381 líneas) / `apiUpdateTask` / `apiUpdatePPCV3`: actualización de una sola fila con sanitización estricta contra lista blanca de columnas y reverse-sync individual.

### 7.3 Papa Caliente / Cotizaciones (ver detalle completo en §10.2 y `PAPA_CALIENTE_SDD.md`)
La lógica de la máquina de estados vive **dentro de** `apiSaveTrackerBatch` e `internalUpdateTask` (no son funciones separadas): detecta transición a `100%`/`1`/`HECHO`/`SI`, localiza la entrada `IN_PROGRESS` correspondiente en `PROCESO_LOG`, la marca `DONE`, regenera `MAP COT`, y copia archivos de vuelta a `ANTONIA_VENTAS`.

### 7.4 Módulo PPC (checklist de sitio — distinto de Papa Caliente)
`apiSavePPCData(payload, activeUser)` 📄 (línea 3124, 313 líneas), `apiFetchPPCData()`, `apiFetchDrafts` / `apiSyncDrafts` / `apiClearDrafts` (borradores), `saveChildData` / `ensureSheetWithHeaders` (helpers genéricos de guardado en sub-hojas).

### 7.5 Work Orders
`apiCreateStandardStructure` 📄, `generateWorkOrderFolio` 📄, `generatePrefix` 📄, `apiGetNextWorkOrderSeq`, y el guardado de las 5 sub-tablas relacionales vía `saveChildData` (§5.7).

### 7.6 Proyectos/Sitios (cascada)
`apiSaveSite`, `apiSaveSubProject`, `apiFetchCascadeTree`, `apiFetchProjectTasks` 📄 (⚠️ contiene un `ReferenceError` que la rompe siempre en producción, ver Anexo A §19.12), `apiSaveProjectTask`, `apiFetchWeeklyPlanData` 📄. Código completo de los seis en Anexo A §19.12.

### 7.7 KPIs y Productividad (agentes con IA)
`apiFetchAdminKPIs` 📄 (línea 719, 185 líneas — Dashboard de KPIs, ver `SDD_KPI_ADMIN.md` y §10.5), `apiFetchTrackerProductivityMetrics` / `runTrackerProductivityAgent` / `_sendTrackerProductivityEmail` (agente narrativo del lado de productividad de Trackers, mismo patrón que el de cotizaciones), `apiFetchTeamKPIData`, `apiFetchQuoteAgentMetrics` (motor de métricas mensuales por SLA/clasificación/cotizador — su forma de salida está documentada indirectamente por el prompt de Gemini reproducido en Anexo A §19.17) / `apiWriteQuoteMetricsToSheet` / `runQuoteMetricsAgent` 📄 / `_sendAgentEmail` 📄 / `apiGetLastAgentReport` 📄 (motor de reglas + prompt Gemini + email HTML vía `MailApp`, código completo en Anexo A §19.17), `autoUpdateQuoteMetrics` (trigger diario), `callGeminiAPI` 📄 / `apiSaveGeminiKey` / `apiCheckGeminiKey` (integración Gemini para resúmenes narrativos y transcripción de audio vía `transcribirConGemini` 📄, código completo en Anexo A §19.14).

### 7.8 Agenda, Calendario y Hábitos personales
`apiFetchCombinedCalendarData`, `apiFetchUnifiedAgenda`, `apiSavePersonalEvent`, `apiSaveHabitLog`.

### 7.9 Banco de Información / Archivos
`apiFetchInfoBankCompanies`, `apiFetchInfoBankData`, `apiFetchDistinctClients`, `uploadFileToDrive`, `getOrCreateFolder`, `getBankRootFolder`, `archiveFile`, `processQuoteRow`, `batchArchiveExistingQuotes`, `runFullArchivingBatch`.

### 7.10 Helpers estructurales
`findSheetSmart(name)` 📄 — búsqueda tolerante de hoja. `findHeaderRow(values)` 📄 — búsqueda heurística de fila de encabezados. `registrarLog(user, action, details)` 📄 — auditoría. `getWeekNumber(d)`, `colIndexToLetter(col)`, `generatePrefix(name)` 📄, `generateNumericSequence(key)` 📄 (con `LockService`, fallback a número aleatorio si supera 10,000,000), `generateAppSheetId()` (deprecado), `deduplicateAllSheets()`, `debugSheetHeaders()`.

### 7.11 Formato condicional y semáforos de hoja
`applyTrafficLightToSheet(sheet)`, `setupConditionalFormatting()` — aplican reglas de color nativas de Google Sheets (no solo CSS del frontend) para que las hojas sigan siendo legibles fuera de la app web. Se dispara automáticamente cada vez que `internalBatchUpdateTasks` inserta filas nuevas (no en actualizaciones de filas existentes).

### 7.12 Triggers y menú nativo de Sheets
`onOpen()` — construye el menú custom de la Spreadsheet. `cmdRealizarAlta()`, `cmdActualizar()` — comandos invocados desde ese menú. `instalarDisparador()` 📄 — instala el trigger diario `incrementarContadorDias` (1am–2am), idempotente. `generarFolioAutomatico(e)` 📄 — trigger de edición para folios legados numéricos simples (usa `LockService` con espera de 30s, distinto del sistema `AV-XXXX`).

### 7.13 Integración Outlook (implementación real, no solo diseño — ver corrección en §11.2)
`formatDateForOutlook(dateString, defaultOffsetMillis)` 📄, el objeto `NotifierService.sendToOutlook(payloadData)` 📄, `findUserEmailByLabel(friendlyName)` 📄, `testIntegracionOutlook()` 📄 (función de prueba manual desde el editor de Apps Script).

### 7.14 Suite de pruebas embebida (funciones `test_*` dentro de `CODIGO.js`, distintas de los `test_*.js` de Node en §14)
`test_DataIntegrity`, `test_Generacion_MAP_COT`, `test_Security_Filter_AllowedBase`, `test_Flujo_Completo_Delegacion_y_Sincronizacion`, `test_Cierre_Terminal_RCC`, `test_SavePPCV3_Flow`, `test_WorkOrder_Generation`, `test_Directory_CRUD`, `test_ReverseSync_Flow`, `test_NumericSequence_Generation`, `test_Antonia_Distribution_Manual`, `test_SystemConfig_Label`, `test_avance_100_bug` — diseñadas para ejecutarse manualmente desde el editor de Apps Script (no hay CI que las corra automáticamente, y corren contra servicios reales de Google, no mockeados).

---

## 8. Frontend (`index.html`) — Estado y Vistas

### 8.1 Bootstrap de la app

```js
const { createApp, ref, computed, onMounted, watch, nextTick } = Vue;
const app = createApp({ setup() { /* ~90 variables reactivas ref()/reactive() declaradas entre líneas 5945-9440, ver Anexo C (§21) */ } });
app.mount('#app');
```

Vue se monta sobre `<div id="app">`. No hay Vue Router — la navegación es manual vía la variable `currentView`, mutada directamente dentro de los manejadores de clic (patrón `currentView.value = 'NOMBRE_VISTA'`, ver §8.3).

### 8.2 Categorías de estado reactivo

El estado completo (~90 declaraciones `ref()`/`reactive()`, cada una con su propósito exacto) está en el **Anexo C (§21)**. Aquí el resumen por categoría funcional:

| Categoría | Ejemplos de variables | Rol |
|---|---|---|
| Sesión/Auth | `isLoggedIn`, `loginUser`, `loginPass`, `loggingIn`, `currentUser`, `currentUsername`, `currentRole`, `showPassword` | Ciclo de login/logout y caché de identidad en memoria del navegador |
| Router manual | `currentView`, `currentDept` | Sustituto de Vue Router — controla qué bloque `v-if`/`v-show` se renderiza |
| Config del servidor | `config` | Payload íntegro de `getSystemConfig()`: `{ departments, staff, directory, specialModules }` |
| Data Grid / Tracker | `staffTracker`, `staffTrackerFilters`, `staffTrackerSortAsc`, `activeTrackerTab`, `trackerSubView`, `currentStaffName`, `trackerTable` | Estado del Tracker actualmente abierto (el componente más usado del sistema) |
| Papa Caliente | `hotPotatoData`, `showHotPotatoModal`, `currentHotPotatoRow`, `showProcessFlow` | Estado del timeline Papa Caliente en pantalla y su modal de asignación |
| PPC (checklist) | `ppcData`, `ppcExistingData`, `dynamicPpc`, `ppcDraftTable`, `showPpcSelectorModal`, `ppcMode`, `currentPpcProject`, `ppcMenuTipo` | Estado del módulo PPC (distinto de Papa Caliente, ver §5.1) |
| Work Order | `workorderData`, `currentWorkorderId`, `nextSequence`, `laborTable`, `requiredMaterials`, `toolsRequired`, `specialEquipment`, `additionalCosts`, `projectProgram`, `vehicleData`, `vehicleControlData`, `vehicleControlData2` | Estado del formulario de Work Order (materiales, mano de obra, herramientas, equipo, programa, control vehicular duplicado x2) |
| Proyectos/Sitios | `newProject`, `activeProjectsList`, `showSubProjectModal`, `currentTargetSite`, `newSubProject`, `projectSubFolders`, `projectCards`, `projectTasks`, `projectRespDropdownOpen` | Cascada Sitio→Subproyecto→Tarea |
| Agenda/Calendario | `personalAgenda`, `showNewActivityModal`, `newActivity`, `selectedDailyDay`, `dashboardCalendar`, `calendarLoading`, `calendarUserFilter`, `calendarInterval`, `certActivities`, `certNewActivity`, `showCertModal`, `certStep` | Agenda personal, calendario ejecutivo, hábitos/certificaciones |
| Banco de Información | `infoBankState`, `ibCompanies`, `historySearchQuery`, `cotizadorSearch`, `cotizadorSearchTop` | Navegación Año→Mes→Empresa→Carpeta en Drive |
| KPIs / Productividad IA | `kpiData`, `quoteMetrics`, `qmFilters`, `agentState`, `showGeminiKeyModal`, `geminiKeyInput`, `geminiKeyState`, `executiveSummaryData`, `trackerProductivityData`, `isLoadingTrackerProductivity`, `ecgData`, `filterSpecialty`, `filterCompliance` | Dashboard ejecutivo y agentes narrativos con Gemini |
| Archivos/Uploads | `isUploadingFile`, `uploadSuccess`, `fileInput`, `currentUploadType`, `cellFileInput`, `uploadingCell`, `designUploadContext`, `designFileInput`, `isRecording` | Subida Base64 y grabación/transcripción |
| Empleados/Admin | `showEmployeeModal`, `newEmployee` | Alta/baja de personal (RBAC `ADMIN`) |
| UI/Preferencias | `searchQuery`, `isCompact`, `currentTheme`, `showTimePopup`, `timePopupValue`, `timePopupTarget`, `showExtraModal`, `extraData`, `currentIframeUrl`, `iframeTitle`, `selectedFinancing`, `selectedWeek`, `currentModuleId`, `showLogic`, `sectionVisibility`, `showInstr`, `showWorkOrderLogic` | Estado puramente visual/de interacción, sin persistencia |
| Anti-duplicación | `isSubmitting` | La bandera global obligatoria de §10.3 — bloquea doble-submit en **cualquier** botón de guardado del sistema |
| Otros | `selectedResponsables`, `staffSearch`, `activityQueue`, `currentResourceTab`, `currentActivityContext`, `showResourceModal` | Selección múltiple de personal para distribución/delegación |

### 8.3 Mapa de vistas (`currentView.value = '...'`)

| Valor de `currentView` | Pantalla | Se activa desde |
|---|---|---|
| `DASHBOARD` | Home / selector de departamentos | Login exitoso, botón "Volver al inicio" |
| `DEPT` | Listado de personal dentro de un departamento | Clic en tarjeta de departamento |
| `STAFF_TRACKER` | Data Grid tipo Excel de un Tracker individual (vista principal del sistema) | Clic en un empleado de `DEPT`, o módulo `mirror_staff` |
| `PPC_MENU` | Menú del módulo PPC (elegir Interno/Preoperativo/Cliente) | Módulo especial `ppc_native` |
| `PPC_DINAMICO` | Formulario dinámico de captura PPC | Selección dentro de `PPC_MENU` |
| `PPC_FORM` | Formulario PPC clásico | Ruta alterna al dinámico |
| `WEEKLY_PLAN` | Planeación semanal | Módulo especial `weekly_plan_view` |
| `PROJECT_TASKS_VIEW` | Árbol Sitio→Subproyecto→Tarea | Navegación de Proyectos (`accessProjects: true`) |
| `WORKORDER_FORM` | Formulario de Work Order embebido | Rol `WORKORDER_USER` o navegación desde Proyectos |
| `KPI_DASHBOARD` | Dashboard ejecutivo de KPIs | Módulo especial `kpi_dashboard_view`, solo visible si `role === 'ADMIN'` |
| `ECG_VIEW` | Módulo "Monitor Vivos" | **Comentado/deshabilitado** en `getSystemConfig` (`const ecgModule = {...}` está comentado en el código fuente) — la vista existe en `index.html` pero ningún rol la puede alcanzar actualmente |

### 8.4 Componentes/patrones clave (código literal de los métodos más importantes en el Anexo B, §20)

- **Data Grid (`table-excel`)**: hitbox de celda al 100% (evita "clic de francotirador"), edición inline, cabeceras `sticky`, `vertical-align: middle` obligatorio. Ancho/alineación por columna calculados dinámicamente por `getColumnStyle(h)` (§20.2) — una función de ~45 reglas `if/else if` basadas en el nombre de columna normalizado.
- **Permisos de edición por celda**: `isFieldEditable(h, row)` (§20.1) — replica en el cliente, por rol, las mismas listas blancas que el backend aplica en `internalUpdateTask`/`apiSaveTrackerBatch`. Si estas dos capas se desincronizan (alguien agrega una columna nueva solo en el backend o solo en el frontend), el síntoma es "veo el campo pero no se guarda" o viceversa.
- **Semáforo de fechas**: `getTrafficStyle(row)` / `getFechaInicioTrafficStyle(row)` (§20.3) — colorean la celda de `DIAS`/`RELOJ` o de la fecha de inicio según la `CLASIFICACION` de la fila (`A`: límite 3 días/buffer 1, `AA`: límite 15/buffer 3, `AAA`: límite 30/buffer 5). Verde si está dentro del límite menos el buffer, amarillo en el buffer, rojo si lo excede.
- **Timeline Papa Caliente (`.hp-circle`)**: círculos de 32px conectados por línea, colores por estado (gris=pendiente, amarillo=en progreso, verde=completado). `getProcessTimeline(row)` (§20.5) parsea `PROCESO_LOG` + `MAP COT` y calcula, por cada uno de los 7 pasos, el tiempo transcurrido legible (`Xd Yh` o `< 1h`).
- **Formularios dinámicos**: `<select>`/`<input type="date">` nativos expandidos al 100% de la celda contenedora.
- **Toggle mayúsculas/minúsculas obligatorio**: cabeceras siempre en minúsculas (excepto "Folio"/"ID"), datos siempre en mayúsculas — impuesto vía CSS `text-transform`, no vía JS. `getHeaderLabel(h)` (§20.2) además reescribe algunas etiquetas específicas (ej. `DIAS`→"Días Finaliz. Cotiz" solo para la cuenta `ANTONIA_VENTAS`).
- **`toInitials(name)`** (§20.3): convierte "Sebastián Padilla" → "SP", soportando múltiples nombres separados por coma (`"JUAN PEREZ, ANA LOPEZ"` → `"JP/AL"`) — usado en avatares y en columnas `VENDEDOR`/`RESPONSABLE`/`INVOLUCRADOS`.

---

## 9. Sistema de Diseño (Design Tokens)

Fuente exhaustiva: `SDD_HOLTMONT_WORKSPACE.md` §3. Resumen operativo (variables CSS en `:root` de `index.html`):

```css
:root {
  /* Color base */
  --color-bg-global: #f4f6f8;
  --color-white: #ffffff;
  --color-black: #000000;
  --color-gray-header: #e6e6e6;
  --color-gray-border: #b2b2b2;
  --color-gray-text-sec: #637381;

  /* Interacción */
  --color-interactive: #107c41;   /* verde tipo Excel */
  --color-cell-hover: #F9FAFB;
  --color-focus-ring: #3B82F6;

  /* Semáforo */
  --color-danger-bg: #ffcccc;
  --color-warning-bg: #fff4cc;
  --color-success-bg: #ccffcc;

  /* Tipografía */
  --font-family-base: 'Arial', sans-serif;
  --font-size-table: 11px;
  --font-size-form: 13px;
  --text-transform-header: lowercase;   /* excepto "Folio"/"ID" */
  --text-transform-data: uppercase;
  --font-weight-bold: 700;

  /* Layout */
  --sidebar-w: 250px;
  --sidebar-mini: 70px;
  --row-height-base: 30px;
  --col-width-micro: 40px;   /* ALTA, ESPECIALIDAD, AREA, CORREO, CARPETA */
  --col-width-id: 85px;      /* ID, FOLIO */

  /* Transiciones */
  --transition-fast: 150ms ease;
  --transition-structural: 300ms cubic-bezier(0.25, 0.8, 0.25, 1);
}
```

Paleta semafórica **de negocio** usada específicamente en `getTrafficStyle`/`getFechaInicioTrafficStyle` (§8.4, §20.3) — no son variables CSS sino literales hexadecimales embebidos directamente en JS: rojo `#e74c3c` (texto blanco), amarillo `#ffff00` (texto negro, negrita), verde `#2ecc71` (texto blanco/negro según función). Es una paleta **distinta** de los tokens semánticos de `:root` (`--color-danger-bg: #ffcccc`, etc.) — otra inconsistencia menor documentada aquí para quien clone el sistema y quiera unificar la paleta.

**Regla de oro:** cualquier cambio visual solicitado por el negocio se resuelve modificando estos tokens en `:root`, **nunca** con estilos inline `style="color:red"` en HTML.

---

## 10. Reglas de Negocio Críticas (romperlas = romper producción)

### 10.1 Enrutamiento y el "Caso Antonia"
- Cualquier tarea originada en `ANTONIA_VENTAS` lleva folio con prefijo `AV-` y requiere **Reverse Sync**: cambios hechos por el delegado en su propio Tracker deben reflejarse de vuelta en `ANTONIA_VENTAS`.
- **Prohibido** para cualquier otro usuario enrutar hacia hojas que terminen en `(VENTAS)`. El código elimina ese sufijo globalmente: `targetSheet.replace(/\s*\(VENTAS\)/ig, "").trim()` — presente tanto en `apiSavePPCData` como en `apiSaveTrackerBatch` e `internalUpdateTask` (tres apariciones literales idénticas del mismo regex, ver Anexo A).
- La distribución lateral entre compañeros de equipo (no origen Ventas) usa la columna `INVOLUCRADOS`; la columna `VENDEDOR` es exclusiva de asignaciones que vienen de `ANTONIA_VENTAS`. El código en realidad trata `VENDEDOR`, `RESPONSABLE` e `INVOLUCRADOS` como **sinónimos intercambiables** en la mayoría de los `Object.keys(...).find(k => k.toUpperCase().trim() === "VENDEDOR" || ... === "RESPONSABLE" || ... === "INVOLUCRADOS")` — la distinción de nombre de columna es una convención de negocio/UI, no una diferencia de lógica de programación.
- **Redirección forzosa a `ANTONIA_VENTAS`**: si cualquier usuario que **no** es `ANTONIA_VENTAS` intenta guardar directamente en la hoja `ANTONIA_VENTAS`, `internalUpdateTask` reescribe silenciosamente el destino a `"ANTONIA PINEDA LOPEZ"` (su tracker personal) antes de continuar — nadie más que la propia cuenta `ANTONIA_VENTAS` puede escribir en la hoja maestra de Ventas.
- **PPCV3 es de solo lectura fuera del flujo Semanal**: `internalUpdateTask` rechaza explícitamente (`{success:false, message:"Operación no permitida..."}`) cualquier intento de escribir en la hoja `PPCV3` que no venga del módulo "Planeación Semanal".

### 10.2 Máquina de estados "Papa Caliente" — con ejemplo de payload real

7 etapas secuenciales: `L (Levantamiento) → CD (Cálculo y Diseño) → EP (Elaboración Presupuesto) → CI (Cotización Interna) → EV (Estrategia Ventas) → CEC (Cotización Enviada al Cliente) → RCC (Revisión Cotización Cliente, etapa terminal)`.

- **`PROCESO_LOG`** (JSON): `[{ step, status: "IN_PROGRESS"|"DONE", assignee, timestamp, dateStr, endTimestamp?, endDateStr? }, ...]`.
- **`MAP COT`** (string): `"🟢 L | 🔴 CD | ⚪ EP | ⚪ CI | ⚪ EV | ⚪ CEC | ⚪ RCC"` — espejo legible en la hoja cruda.

**Paso 1 — Estado antes de delegar** (fila recién creada por Antonia, folio `AV-1050`):
```json
{
  "FOLIO": "AV-1050",
  "CLIENTE": "EMPRESA X",
  "CONCEPTO": "Ampliación de nave industrial",
  "PROCESO_LOG": "[]",
  "MAP COT": "🔴 L | ⚪ CD | ⚪ EP | ⚪ CI | ⚪ EV | ⚪ CEC | ⚪ RCC"
}
```

**Paso 2 — Antonia delega la etapa `CD` a "ANGEL SALINAS"** (el frontend arma el payload con `_assignToWorker: "ANGEL SALINAS"` y `_assignStep: "CD"`, y lo envía vía `apiSaveTrackerBatch`). Dentro de la función (Anexo A §19.2, líneas 5315–5354), el sistema:
1. Copia la fila (`distData`, sin `PROCESO_LOG`/`PROCESO`) a la hoja `ANGEL SALINAS`, forzando `ESTATUS: "PENDIENTE"` y `AVANCE: "0%"`.
2. Busca el email de Ángel con `findUserEmailByLabel("ANGEL SALINAS")` y dispara `NotifierService.sendToOutlook(...)` con vencimiento a 2 horas.
3. El `PROCESO_LOG` de `ANTONIA_VENTAS` pasa a:
```json
[{ "step": "CD", "status": "IN_PROGRESS", "assignee": "ANGEL SALINAS", "timestamp": 1780000000000, "dateStr": "01/07/26, 09:00:00" }]
```
y `MAP COT` se regenera a `"🟢 L | 🔴 CD | ⚪ EP | ⚪ CI | ⚪ EV | ⚪ CEC | ⚪ RCC"` (nótese que `L` ya está `🟢` porque se asume completado al delegar el siguiente paso — la regla exacta de transición de `L` vive en el frontend, no en este fragmento de backend).

**Paso 3 — Ángel Salinas termina su parte** (abre su Tracker, sube `LAYOUT`, cambia `AVANCE` a `100%`, presiona Guardar → `saveRow` → `internalUpdateTask("ANGEL SALINAS", {...}, "ANGEL_SALINAS")`). Dentro de `internalUpdateTask` (Anexo A §19.4, líneas 2840–2960), como `personName !== "ANTONIA_VENTAS"`, entra a la rama `else` de reverse-sync:
1. Calcula `isDone` evaluando `ESTATUS`/`AVANCE`/`CUMPLIMIENTO` contra la lista de valores válidos: `estatus ∈ {HECHO, TERMINADO, FINALIZADO, REALIZADO, COMPLETADO, DONE}` **o** `avanceRaw === '100'` **o** `avanceNum === 100` **o** `avanceRaw.toUpperCase() === 'SI'`.
2. Busca en `ANTONIA_VENTAS` la fila con `FOLIO === "AV-1050"`.
3. Recorre `PROCESO_LOG`, encuentra la entrada `{step:"CD", status:"IN_PROGRESS", assignee:"ANGEL SALINAS"}` (con normalización tolerante a `(VENTAS)` y guiones bajos), la muta a:
```json
{ "step": "CD", "status": "DONE", "assignee": "ANGEL SALINAS", "timestamp": 1780000000000, "dateStr": "01/07/26, 09:00:00", "endTimestamp": 1780050000000, "endDateStr": "01/07/26, 23:00:00" }
```
4. Regenera `MAP COT` completo iterando `["L","CD","EP","CI","EV","CEC","RCC"]` y evaluando, para cada paso, si todas sus entradas en el log están `DONE` (🟢), alguna `IN_PROGRESS` (🟡 en la lógica de reverse-sync backend, aunque el frontend puede pintarlo como 🔴 "actual" — ver nota de discrepancia visual abajo), o ninguna (⚪, heredando el color previo desde el `MAP COT` viejo si existía "basura" de versiones anteriores del log).
5. Escribe de vuelta en `ANTONIA_VENTAS` solo `{FOLIO, PROCESO_LOG, MAP COT}` más las columnas de archivo (`ARCHIVO, F2, LAYOUT, COTIZACION, EVIDENCIA`) que Ángel haya llenado — **nunca** sobrescribe `ESTATUS`/`AVANCE` de la fila maestra con los de la fila del delegado (por diseño: el progreso del delegado es interno a su etapa, no el estatus global de la cotización).

**Paso 4 — Cierre terminal en `RCC`**: modal con 3 desenlaces posibles — `GANADA` (verde), `PERDIDA X PRECIO` (rojo), `DESCUENTO` (azul) — escribe directamente en la columna `ESTATUS` de `ANTONIA_VENTAS` y la fila queda sujeta al auto-archivado de §5.3 (se mueve a "TAREAS REALIZADAS" si el estatus resultante coincide con la lista de estados terminales).

- **Lista blanca de seguridad:** solo columnas en `allowedBase` (backend, §5.4) se sobrescriben en cada guardado sobre una fila **ya existente** de `ANTONIA_VENTAS` — `PROCESO_LOG` y `PROCESO` **deben** estar siempre en esa lista o la delegación se rompe silenciosamente (la escritura del timeline dejaría de persistir sin ningún error visible al usuario).
- **Detección de finalización flexible**: la condición `isDone` (arriba) es intencionalmente laxa para absorber "error humano" — el usuario de campo puede escribir `100`, `100%`, `1`, `1.0` (valor crudo de formato porcentaje de Sheets), `HECHO`, `TERMINADO`, `FINALIZADO`, `REALIZADO`, `COMPLETADO`, `DONE`, o `SI` en cualquiera de las columnas candidatas (`ESTATUS`/`STATUS`/`ESTADO`, `AVANCE`/`AVANCE %`/`% AVANCE`/`%`/`CUMPLIMIENTO`) y el sistema lo reconoce como "etapa terminada".

### 10.3 Anti-duplicación y condiciones de carrera — con ejemplo de conflicto resuelto
- **Frontend:** cada fila nueva genera un `_tempId` único (`'temp_' + Date.now() + '_' + Math.floor(Math.random()*1000)`, ver `addNewRow` en Anexo B §20.4) antes de enviarse; todo botón de guardado se liga a `isSubmitting` para bloquear doble-click (patrón exacto en `saveRow`, Anexo B §20.6: `if (row._isSaving || isSubmitting.value) { toast de advertencia; return; }`).
- **Backend Gatekeeper:** `internalBatchUpdateTasks` usa `CacheService.getScriptCache()` con la llave `sheetName + "_" + _tempId` como candado de 120 segundos (`cache.put(cacheKey, "1", 120)`), bloqueando ejecuciones paralelas sobre la misma fila — si dos requests llegan casi simultáneas con el mismo `_tempId` (ej. doble clic que sí logró escapar la bandera del frontend, o una reintentada de red), la segunda se ignora silenciosamente (`return;` dentro del `.forEach`).
- **Resolución de conflictos por desplazamiento de filas:** si el payload trae `_rowIndex` (posición recordada por el frontend desde la última carga) pero la fila en esa posición **ya no tiene el mismo `FOLIO`** (alguien insertó/borró filas mientras tanto), el sistema descarta el índice recordado y activa una **búsqueda robusta por `FOLIO`** en toda la hoja; si tampoco hay `FOLIO`, cae al **último recurso**: emparejar por la combinación exacta `CONCEPTO` (primeros 50 caracteres, normalizado) + `FECHA` (tolerante a formato `DD/MM/YY` vs ISO, y a que ambas fechas estén vacías). Solo si ninguna de las tres estrategias encuentra fila, se crea una fila nueva.
- **Deduplicación también dentro del mismo lote (`rowsToAppend`)**: antes de insertar una fila nueva, `internalBatchUpdateTasks` revisa si ya hay una fila **pendiente de insertar en el mismo batch** con el mismo `FOLIO`, o con el mismo `CONCEPTO`+`FECHA` — si la encuentra, actualiza esa fila pendiente en memoria en vez de crear una segunda.
- Toda función de guardado (`apiSaveTrackerBatch`, `apiSavePPCData`) debe devolver el objeto completo actualizado en `res.data` para que el frontend pueda fusionarlo (`Object.assign(row, res.data)`) y marcar `_isNew = false`.

### 10.4 Las tres acepciones de "Papa Caliente" en el sistema (fuente de confusión frecuente)

| Contexto | Qué significa "Papa Caliente" ahí | Dónde vive |
|---|---|---|
| Pipeline de cotizaciones de Ventas | Las 7 etapas `L→CD→EP→CI→EV→CEC→RCC` (§10.2) | `PROCESO_LOG`/`MAP COT` en `ANTONIA_VENTAS` |
| Distribución lateral general | Delegar cualquier tarea (no solo cotizaciones) a un compañero vía columna `INVOLUCRADOS` | Cualquier hoja Tracker, `AGENTS.md` §3 |
| Aprobación de línea de material/herramienta en Work Orders | Flujo secuencial Residente→Compras→Controller→Almacén→Logística por cada ítem de material/herramienta | Objeto `papaCaliente` embebido en cada item de `DB_WO_MATERIALES`/`DB_WO_HERRAMIENTAS` (§5.7) |

Las tres comparten el nombre porque comparten la metáfora de negocio (algo "caliente" que se pasa de mano en mano bajo presión de tiempo), pero son tres implementaciones de datos completamente independientes. Al clonar o extender el sistema, **nunca asumir que tocar una afecta a las otras dos**.

### 10.5 Fórmulas de negocio exactas del Dashboard de KPIs (`apiFetchAdminKPIs`, Anexo A §19.7)

- **% de Ganadas (tarjeta superior):** `Math.round((ganadas / enviadasCount) * 100)`, donde `enviadasCount` cuenta filas con `ESTATUS` que incluya `"GANAD"`/`"CERRADO"` **o** `"ENVIAD"`/`"COTIZACION ENVIADA"` — es decir, el universo base es "todo lo que llegó a enviarse", no el total de filas.
- **% Cierre por colaborador:** `Math.round((c.ganadas / (c.ganadas + c.canceladas)) * 100)` — el universo base aquí es distinto: solo desenlaces definitivos (ganadas + canceladas/perdidas), excluyendo explícitamente lo que sigue en curso.
- **Eficiencia promedio (días):** promedio aritmético simple de la columna `DIAS`/`RELOJ`/`DÍAS FINALIZ. COTIZ` sobre filas con valor `> 0`.
- **Semaforización de "Estado" por colaborador:** `avgEfic > 2.0` → `"Cuello botella"`; `avgEfic >= 1.5` → `"Riesgo"`; en cualquier otro caso → `"Eficiente"` (incluye implícitamente el caso `avgEfic === 0`, sin filas válidas).
- **Motivo de pérdida (dona):** se agrupa únicamente sobre filas cuyo `ESTATUS` incluya `"PERDID"`, `"CANCELAD"` o `"RECHAZAD"`, usando la columna `MOTIVO`/`RAZON` (o `"OTRO"` si viene vacía).
- **Productividad semanal:** cuenta filas cuya `FECHA` cae dentro de los últimos 7 días (`diffDays <= 7`), agrupadas por día de la semana `Lunes`–`Viernes` (sábado/domingo no se grafican).
- Los 6 vendedores analizados están hardcodeados: `ANGEL_SALINAS, TERESA_GARZA, EDUARDO_TERAN, EDUARDO_MANZANARES, RAMIRO_RODRIGUEZ, SEBASTIAN_PADILLA` — **`ANTONIA_VENTAS` está explícitamente excluida** de este dashboard (comentario literal en el código: `// Antonia removed from select list`), y **`JUDITH_ECHAVARRIA`, `ALFONSO_CORREA` y `JUAN_JOSE_SANCHEZ` también son `seller: true` en `USER_DB` pero no aparecen en esta lista** — el Dashboard de KPIs no cubre a todos los vendedores del sistema, solo a estos 6.

### 10.6 Parseo defensivo de datos de hoja
- **Encabezados no están garantizados en la fila 1** — usar siempre `findHeaderRow()` (Anexo A §19.1), que evalúa hasta las primeras 100 filas contra 7 patrones heurísticos distintos (columnas de sitio, folio+concepto+fecha, id+responsable, cliente+vendedor, agenda personal, hábitos).
- **Comparación insensible a mayúsculas**: todo acceso a claves de objeto que vienen del frontend (pueden llegar en minúsculas, ej. `folio`) debe normalizarse con `.toUpperCase().trim()`.
- **Resolución de alias de columna**: `internalBatchUpdateTasks` mantiene un diccionario `aliases` de 15 entradas (`FECHA`, `CONCEPTO`, `RESPONSABLE`, `HORA`, `RELOJ`, `ESTATUS`, `CUMPLIMIENTO`, `AVANCE`, `ALTA`, `FECHA_RESPUESTA`, `PRIORIDAD`, `RIESGOS`, `ARCHIVO`, `CLASIFICACION`, `COMENTARIOS`, `PREVIOS`, `FECHA_TERMINO`) que mapea decenas de variantes textuales reales encontradas en producción (ej. `RESPONSABLE` también resuelve `INVOLUCRADOS`, `VENDEDOR`, `ENCARGADO`, `ASIGNADO`) a la columna física correcta — código completo en Anexo A §19.3.
- **Interpretación de `AVANCE`**: `100`, `'100'`, `'100%'` y el valor numérico crudo `1` (formato porcentaje nativo de Sheets, detectado con `typeof rawVal === 'number' && Math.abs(rawVal - 1) < 0.001`) son todos "100%". **Nunca** interpretar el string `'1'` o `'1.0'` de esta forma si viene de otra columna — el bug histórico `test_avance_100_bug` documenta este caso exacto.
- **Fechas**: tolerancia dual — ISO 8601 (`YYYY-MM-DDTHH:mm:ss.sssZ`) y formato legado `DD/MM/YY` (parseado manualmente con `new Date(año, mes-1, día)` para evitar el desfase de zona horaria de `new Date("DD-MM-YYYY")`). Los webhooks salientes a Make.com **siempre** usan `.toISOString()` completo excepto en la integración de Outlook, que usa `formatDateForOutlook()` — recorta explícitamente los milisegundos (`.split('.')[0]`) porque el conector de Power Automate/Office 365 los rechaza si están presentes (ver código exacto en Anexo A §19.8). **Estas son dos convenciones de fecha distintas y ninguna es intercambiable con la otra.**

---

## 11. Integraciones Externas

### 11.1 Make.com → (canal de transporte, no de notificación directa)
`WEBHOOK_OUTLOOK_URL` (línea 13, valor real embebido en el código: `https://hook.us2.make.com/fepkg526j29043bkw5imd8r2fhzmv2wq`) apunta a un escenario de Make.com. **Todo** tráfico saliente hacia Outlook pasa primero por este único webhook — Make.com actúa como intermediario/router entre GAS y Power Automate, no hay una llamada directa GAS→Microsoft.

### 11.2 Outlook 365 / Power Automate — ⚠️ Corrección respecto a la v1.0.0 de este documento

> La versión anterior de este documento describía esta integración citando `SDD_OUTLOOK_INTEGRATION.md` como si fuera una **propuesta de diseño aún no implementada** (el SDD original está escrito en tono "a implementar", con el código envuelto en comentarios `//` como fragmentos de referencia). **Al inspeccionar `CODIGO.js` directamente se confirma que la integración está completamente implementada y activa en producción**, no es un diseño pendiente. El código real (idéntico en espíritu al propuesto en el SDD, con mejoras) vive en las líneas 115–209 y se invoca desde tres puntos distintos del sistema. Código fuente completo en el Anexo A §19.8.

Arquitectura *push* vía webhook (GAS no maneja bien OAuth2 multiusuario contra Microsoft Graph directamente):

```
CODIGO.js (UrlFetchApp, función NotifierService.sendToOutlook) → Make.com (webhook fijo)
    → Power Automate ("When an HTTP request is received")
    → Office 365 Outlook: Create event (V4) → Calendario del delegado
```

Payload real construido por `NotifierService.sendToOutlook`:
```json
{
  "folio": "AV-1050",
  "titulo": "Asignación Papa Caliente: CD - EMPRESA X",
  "descripcion": "Se te ha delegado la etapa CD para el folio AV-1050. Revisa tu Tracker.",
  "fechaInicio": "2026-07-02T09:00:00",
  "fechaFin": "2026-07-02T11:00:00",
  "correoDestino": "angel.salinas@holtmont.com",
  "asignadoPor": "ANTONIA_VENTAS"
}
```
Nótese que `fechaInicio`/`fechaFin` pasan por `formatDateForOutlook()`, que **recorta los milisegundos y no añade `Z`** (a diferencia del formato usado hacia Make.com/auditoría interna, que sí usa `.toISOString()` completo — ver §10.6). Si `correoDestino` no se resuelve (`findUserEmailByLabel` devuelve `null`), la notificación simplemente no se envía y queda un `console.warn` — no bloquea el guardado de la tarea.

**Los 3 puntos de disparo reales en `CODIGO.js`:**
1. **Delegación de un paso Papa Caliente** — dentro de `apiSaveTrackerBatch`, rama `if (taskData._assignToWorker && taskData._assignStep)` (línea ~5330).
2. **Asignación general vía `VENDEDOR`/`RESPONSABLE`/`INVOLUCRADOS`** — dentro de `apiSaveTrackerBatch`, al distribuir `distributionTasks` por vendedor (línea ~5420).
3. **Asignación desde el módulo PPC** — dentro de `apiSavePPCData`, al recorrer `responsables` de cada item capturado (línea ~5356 relativo a esa función, ver Anexo A §19.6).

Todas requieren que el usuario destino tenga `email` (o `outlookEmail`, aunque el código real solo usa la clave `email`) poblado en `USER_DB` con su correo corporativo real `@holtmont.com` (o `@empresa.com` en las cuentas más antiguas que aún no fueron migradas — ver §13 para la implicación de que esto también está en el objeto con contraseñas en texto plano).

### 11.3 Gemini AI
`callGeminiAPI(prompt)` (con `apiSaveGeminiKey`/`apiCheckGeminiKey` para gestionar la API key correctamente en `PropertiesService`) se usa para generar los resúmenes narrativos de los reportes automáticos de productividad y de cotizaciones (`_sendTrackerProductivityEmail`, `_sendAgentEmail` — código completo de este último en Anexo A §19.17). La transcripción de audio (`transcribirConGemini(base64Audio, mimeType)`) usa una llamada **independiente** a la misma API de Gemini, pero — a diferencia de `callGeminiAPI` — con la key **hardcodeada en texto plano** en el propio código fuente en vez de leerla de `PropertiesService`; ver la advertencia de seguridad detallada en §13 y el código exacto en Anexo A §19.14. El audio llega ya grabado desde el navegador (no hay streaming en vivo, ver restricción §2.2 punto 4).

### 11.4 `MailApp` — correo nativo de Gmail/Workspace (tercer canal, distinto de Make.com y de Gemini)
El reporte mensual de cotizaciones (`_sendAgentEmail`, Anexo A §19.17) se envía por `MailApp.sendEmail({to, subject, htmlBody})` — el correo nativo de Apps Script, que no pasa por Make.com ni requiere ningún webhook externo. Es el **único** punto de todo el sistema que usa este mecanismo; el resto de las notificaciones automáticas (asignaciones Papa Caliente, distribución general, PPC) usan el webhook de Outlook (§11.2). Los destinatarios están hardcodeados a `ANTONIA_VENTAS` y `LUIS_CARLOS` leyendo su `email` desde `USER_DB` — no hay forma de configurar destinatarios adicionales sin editar el código.

---

## 12. Triggers y Automatizaciones Programadas

| Trigger | Función | Frecuencia | Instalación |
|---|---|---|---|
| Time-driven | `incrementarContadorDias` | Diario, 1am–2am | `instalarDisparador()` (idempotente — verifica si ya existe antes de crear, código completo Anexo A §19.9) |
| Time-driven | `autoUpdateQuoteMetrics` | Diario | `setupDailyQuoteMetricsTrigger()` |
| `onEdit` (implícito vía trigger instalable) | `generarFolioAutomatico(e)` | Al editar `ANTONIA_VENTAS` | Genera folio numérico simple (no `AV-XXXX`) si la última fila no lo tiene, usando `LockService` (30s de espera). Código completo en Anexo A §19.9 — es un sistema de folio **legado**, coexiste con el sistema `AV-XXXX` principal descrito en §5.4 pero opera sobre un mecanismo distinto (columna `Folio` cruda, sin prefijo, buscando el máximo numérico de las filas previas + 1). |
| `onOpen` (simple trigger nativo) | `onOpen()` | Al abrir la Spreadsheet en Sheets UI | Construye menú custom con `cmdRealizarAlta`/`cmdActualizar` |

---

## 13. Seguridad — Estado Actual y Advertencia

> ⚠️ **Advertencia explícita, no exagerada:** este sistema almacena las contraseñas de **41 cuentas de empleados reales**, en **texto plano**, en dos lugares dentro del repositorio versionado en git:
> 1. La constante `USER_DB` dentro de `CODIGO.js` (backend, línea 212).
> 2. El archivo `CREDENCIALES.md` (documentación) — que además, como se documentó en §6.3, **está desincronizado del código real** (lista a `CESAR_GOMEZ` como dado de baja cuando su cuenta sigue activa, y no documenta 3 cuentas activas: `DANIELA_CASTRO`, `ANTONIO_SALAZAR`).
>
> Cualquiera con acceso de lectura a este repositorio (incluyendo el historial de git) puede leer usuario y contraseña de cada empleado. `SDD_HOLTMONT_WORKSPACE.md` §2.2 ya documenta esto como una limitación conocida ("aceptable en un ecosistema privado" según esa nota), pero para un clon nuevo — sobre todo si el repositorio deja de ser estrictamente privado, o si se sube a un proveedor de terceros — esto es una vulnerabilidad real de exposición de credenciales.
>
> **Recomendación si se clona este sistema:** antes de desplegar, migrar `USER_DB` a `PropertiesService`/hash+salt, y **rotar todas las contraseñas actuales**, ya que quedaron expuestas en el historial de este repositorio. Esto no fue solicitado en esta tarea y por lo tanto no se ha modificado — se documenta aquí para que quien clone el proyecto lo decida conscientemente.
>
> **Segunda credencial expuesta, distinta de las contraseñas:** la función `transcribirConGemini` (línea 5809, Anexo A §19.14) tiene una **API key de Google Gemini hardcodeada en texto plano** (`AIzaSyA7Lv551Quq7lMCynU7kRq9T1_MIaK6kkc`), a pesar de que el resto del sistema (`callGeminiAPI`) sí gestiona esa misma credencial correctamente vía `PropertiesService`. Si esta key sigue activa en Google Cloud, cualquiera con acceso de lectura a este repositorio puede usarla para consumir la cuota de la API a nombre de Holtmont. Se recomienda rotarla/revocarla igual que las contraseñas.

Aparte de esto:
- No hay tokens de sesión persistentes verificados en cada request — la sesión vive en memoria del cliente (`ref()` de Vue) mientras la pestaña esté abierta. `apiLogin` compara la contraseña con `===` (comparación exacta de string, sin hash ni tiempo constante — técnicamente vulnerable a timing attacks, aunque de impacto marginal dado que el atacante ya necesitaría acceso de red al endpoint de GAS).
- Autorización de escritura por columna se hace vía listas blancas (`allowedBase`/`allowed`) revisadas en cada guardado — correctamente implementado como defensa en profundidad, pero depende de mantenerse sincronizadas entre frontend (`isFieldEditable`) y backend (`internalUpdateTask`/`apiSaveTrackerBatch`) cada vez que se agrega una columna nueva; ya existe al menos una lista (`restrictedUsers`, §6.2) que solo vive en el backend.
- `doGet` usa `XFrameOptionsMode.ALLOWALL`, lo que permite embeber la app en iframes de cualquier origen — necesario para el uso previsto (embebido en Sheets/Sites), pero amplía la superficie de clickjacking si la URL se filtra.
- El webhook de Make.com (`WEBHOOK_OUTLOOK_URL`) está hardcodeado como constante pública en el código fuente, no en `PropertiesService` — cualquiera con acceso de lectura al repositorio puede enviar eventos de calendario falsos al endpoint si Make.com no valida un secreto compartido en el payload (el payload actual no incluye ningún token de autenticación, solo datos de negocio).

---

## 14. Testing y Verificación

No existe entorno Apps Script local real; las pruebas se hacen extrayendo lógica a Node (con `vm`/`require('fs')` para cargar `CODIGO.js` como texto y mockear los servicios globales de GAS) o con chequeos de sintaxis vía `acorn`.

```bash
npm install                    # instala acorn + jsdom (únicas dependencias, package.json)
node test_departments.js       # valida organigrama/departamentos tras tocar USER_DB o INITIAL_DIRECTORY — sale con código != 0 si no coincide con el organigrama oficial
node check_html2.js            # valida sintaxis JS embebida en index.html (respaldo si check_html.js falla)
node test_deduplication.js     # valida que el motor de guardado no cree filas duplicadas
node test_distribution.js      # valida enrutamiento/distribución de tareas
node test_distribution_subagent.js   # valida que VENDEDOR/RESPONSABLE/INVOLUCRADOS se traten como sinónimos en la distribución
node test_remove_worker.js     # valida el flujo _removeWorker (reasignación con borrado de la tarea en la hoja del trabajador anterior)
# … y el resto de los ~15 test_*.js listados en §3, cada uno cubre un caso puntual histórico de producción
```

Además, dentro de `CODIGO.js` hay funciones `test_*` (§7.14) pensadas para ejecutarse manualmente desde el editor de Apps Script contra la Spreadsheet real (no mockeada) — usar con cuidado en producción, ya que escriben/leen datos reales.

**Patrón común de los tests en Node** (visto en `test_deduplication.js`, `test_remove_worker.js`, `test_subagent.js`): cargan `CODIGO.js` completo como texto (`fs.readFileSync`), lo ejecutan dentro de un sandbox `vm.createContext` inyectando stubs globales de `console`, `Logger`, `SpreadsheetApp`, `CacheService`, `PropertiesService`, `LockService`, y luego invocan directamente las funciones expuestas (ej. `internalBatchUpdateTasks`) contra datos de hoja simulados en memoria. Es el patrón recomendado para escribir nuevas pruebas si se extiende el sistema.

---

## 15. Guía Paso a Paso: Clonar el Proyecto Desde Cero

1. **Crear la Spreadsheet base.** Nueva Google Sheet vacía — será la base de datos. Desde `Extensiones → Apps Script`, se abre el proyecto de Apps Script vinculado (bound script).
2. **Copiar el manifest.** Pegar el contenido de `appsscript.json` (§2.1: timezone `America/Mexico_City`, `runtimeVersion: V8`, y los 6 OAuth scopes).
3. **Copiar el backend.** Crear un archivo de script `CODIGO.gs` (o el nombre que use el proyecto) y pegar el contenido íntegro de `CODIGO.js`. **Antes de desplegar**, reemplazar/rotar todas las contraseñas de `USER_DB` (ver §13) y actualizar `WEBHOOK_OUTLOOK_URL` con un webhook propio de Make.com. Si se clona para una empresa distinta, reescribir también `INITIAL_DIRECTORY` (§6.4) y `USER_DB` (§6.3) con el organigrama real.
4. **Copiar el frontend.** Crear un archivo HTML llamado `Index.html` (el nombre debe coincidir con `HtmlService.createTemplateFromFile('Index')` en `doGet`, Anexo A §19.1) y pegar el contenido de `index.html` — esto **ya incluye** el formulario de Work Order completo (§16), por lo que no es necesario copiar `workorder_form.html` para tener paridad funcional. Si se desea reactivar `workorder_form.html` como página independiente en el clon, hay que añadir explícitamente un `doGet(e)` con ruteo por parámetro (ej. `e.parameter.page === 'workorder'`) que sirva `HtmlService.createTemplateFromFile('workorder_form')` — ese ruteo no existe hoy en `CODIGO.js`.
5. **Verificar dependencias CDN.** Confirmar que el proyecto tiene salida a internet para cargar Vue 3, Bootstrap 5.3.0, SweetAlert2, Chart.js, Anime.js y Animate.css (todas vía CDN, sin instalación) — ver lista exacta de URLs en §2.
6. **Poblar hojas base.** Al primer `doGet`/login, `getDirectoryFromDB()` auto-crea `DB_DIRECTORY` desde `INITIAL_DIRECTORY`. Las hojas Tracker individuales, `ANTONIA_VENTAS`, `PPCV3`, `PPCV4`, `PPC_BORRADOR`, `LOG_SISTEMA`, `ADMINISTRADOR` y las 5 `DB_WO_*` se auto-crean con sus headers por defecto la primera vez que se escriben (ver §5).
7. **Configurar Script Properties.** `PropertiesService.getScriptProperties()` debe tener (se crean solas en el primer uso, pero conviene setearlas explícitamente): `SEQ_ANTONIA_SEQ_V2` (contador de folios `AV-XXXX` de Ventas), `WORKORDER_SEQ` (contador de folios de Work Order), y la API key de Gemini si se usa `callGeminiAPI` (vía `apiSaveGeminiKey`).
8. **Instalar triggers.** Ejecutar manualmente una vez desde el editor: `instalarDisparador()` (contador de días diario) y `setupDailyQuoteMetricsTrigger()` (métricas de KPI diarias). El `onOpen()` simple trigger se activa solo. Si se quiere conservar el sistema de folio legado de `generarFolioAutomatico`, instalar además un trigger `onEdit` instalable apuntando a esa función sobre la hoja `ANTONIA_VENTAS`.
9. **Configurar integraciones externas** (opcionales pero recomendadas para paridad funcional):
   - Crear un escenario en Make.com, apuntar `WEBHOOK_OUTLOOK_URL` a él.
   - Crear el flujo de Power Automate descrito en §11.2 (trigger HTTP → Office 365 Outlook Create Event V4), mapeando los campos exactos del payload de `NotifierService.sendToOutlook` (§11.2, Anexo A §19.8).
   - Poblar el campo `email` de cada usuario en `USER_DB` con su correo corporativo real para que `findUserEmailByLabel` los resuelva.
10. **Desplegar como Web App.** `Implementar → Nueva implementación → Aplicación web`. Ejecutar como el propietario del script, acceso según la política de la organización (para uso interno, "Cualquier usuario dentro de [organización]").
11. **Primer login.** Usar cualquier credencial de `USER_DB` (tras rotarlas en el paso 3) para verificar `apiLogin` y que `getSystemConfig` arma el menú esperado según el rol (§6.2).
12. **Correr la suite de pruebas local** (§14) antes de dar por buena la clonación, especialmente `test_departments.js` y `check_html2.js`.

---

## 16. Deuda Técnica y Archivos que NO son Fuente de Verdad

### 16.1 Hallazgo: `workorder_form.html` es código huérfano, no el formulario en producción

Tanto `AGENTS.md` como `SDD_HOLTMONT_WORKSPACE.md` (§1.1, §7.3) describen `workorder_form.html` como "el formulario independiente de Work Orders", implicando que es un archivo servido de forma separada para uso en campo/tabletas. **La inspección directa del código contradice esa descripción:**

1. `workorder_form.html` **no tiene** `<!DOCTYPE>`, `<html>`, `<head>` ni `<body>` — es un fragmento de plantilla Vue (`v-if="currentView === 'WORKORDER_FORM'"` en su primera línea), no una página HTML autocontenida.
2. `doGet(e)` en `CODIGO.js` (Anexo A §19.1) **solo** sirve `HtmlService.createTemplateFromFile('Index')` — nunca hace referencia a `'workorder_form'`. No existe ningún `<?!= include('workorder_form') ?>` (el patrón estándar de GAS para insertar un archivo HTML dentro de otro) en `index.html`, ni ninguna otra llamada a `createTemplateFromFile('workorder_form')`/`createHtmlOutputFromFile('workorder_form')` en todo `CODIGO.js`.
3. `index.html` contiene su **propia copia independiente** del mismo formulario: las mismas variables (`vehicleControlData2.chofer`, `workorderData.checkList.libreta`, etc.) aparecen tal cual dentro de `index.html`, ligadas al mismo `setup()` de Vue descrito en §8 y Anexo C (§21).

**Conclusión:** `workorder_form.html` es una **copia archivada/huérfana** de una versión del formulario de Work Order — probablemente el punto de partida antes de que su markup se integrara directamente en `index.html`, o un experimento para separarlo que nunca se conectó. La vista `WORKORDER_FORM` que sí funciona en producción (§8.3) renderiza el fragmento que vive **dentro de** `index.html`, no este archivo. Cualquiera que clone el sistema y solo copie `workorder_form.html` esperando obtener el formulario de Work Order **no obtendrá nada visible**, porque ningún `doGet` lo sirve. La forma correcta de clonar el módulo de Work Order es copiar `index.html` completo (que ya lo incluye) — ver ajuste al paso 4 de la guía de despliegue en §15.

### 16.2 Hallazgo: `apiFetchProjectTasks` está rota en producción (bug de variable indefinida)

Ver el código completo y el análisis línea por línea en el Anexo A §19.12. Resumen: la función referencia una variable `sheetName` que nunca se declaró en su alcance (el parámetro se llama `projectName`); el `catch` genérico de la función absorbe el `ReferenceError` resultante y siempre devuelve `{success: false}`. Efecto observable: dentro de la vista `PROJECT_TASKS_VIEW` (cascada Sitio→Subproyecto→Tarea, roles con `accessProjects: true`), el árbol de sitios/subproyectos (`apiFetchCascadeTree`) carga con normalidad, pero al entrar a un subproyecto específico para ver sus tareas, la llamada siempre falla. Este es un bug genuino de producción descubierto al escribir este documento, no una limitación de diseño documentada previamente en `AGENTS.md` ni en ningún otro SDD del repositorio.

| Archivo(s) | Por qué existen | Por qué ignorarlos al clonar |
|---|---|---|
| `workorder_form.html` | Copia archivada/huérfana del formulario de Work Order (ver §16.1) — nunca se sirve desde ningún `doGet` ni se incluye desde `index.html` | El formulario real y funcional está duplicado dentro de `index.html`; usar ese, no este archivo |
| `apiFetchProjectTasks` en `CODIGO.js` (línea 3854) | No es un archivo, es una función activa con un bug real (§16.2, Anexo A §19.12): referencia la variable indefinida `sheetName` | No ignorar — es código en producción que falla silenciosamente; documentado aquí para que se corrija conscientemente si se clona el sistema |
| `_sendTrackerProductivityEmail` en `CODIGO.js` (línea 1180) | No es un archivo, es una función activa con un bug silencioso (Anexo A §19.18): busca `USER_DB['ADMIN_CONTROL']` como si fuera una llave de usuario, cuando las llaves de `USER_DB` son siempre usernames (`JAIME_OLIVO`, `DIMAS_RAMOS`) | No ignorar — el reporte mensual de productividad nunca llega a los roles `ADMIN_CONTROL`; corregir a `USER_DB['JAIME_OLIVO']` (o iterar ambos `ADMIN_CONTROL`) si se clona y se quiere el comportamiento probablemente intencionado |
| `transcribirConGemini` en `CODIGO.js` (línea 5809) | No es un archivo, es una función activa con una API key de Gemini hardcodeada en texto plano (§13, Anexo A §19.14) | No ignorar — rotar la key si se clona este repositorio, y refactorizar para usar `PropertiesService` como `callGeminiAPI` |
| `CODIGO.js.bak`, `CODIGO.js.orig`, `CODIGO.js.rej` | Respaldo manual / residuo de un merge con patch rechazado | Contenido desactualizado respecto a `CODIGO.js`; el `.rej` ni siquiera es JS válido completo (es un fragmento de diff) |
| `*.patch` (`fix_date_temp_id*.patch`, `fix_duplication.patch`) | Registro histórico de parches ya aplicados | Ya están incorporados en `CODIGO.js`; re-aplicarlos duplicaría cambios |
| `tracker_productivity_tool.js` … `_tool3.js`, `tracker_productivity_ui_tool.js` … `_ui_tool7.js` | Iteraciones sucesivas del mismo módulo de productividad durante desarrollo | Solo la lógica ya integrada en `CODIGO.js` (`apiFetchTrackerProductivityMetrics`, `runTrackerProductivityAgent`, etc.) es la vigente |
| `parse_*.js`, `get_issue_info.js`, `fix_anotnia.js`, `check_duplication.js`, `deduplicate_script.js`, `fix_all.js` | Scripts de diagnóstico ad-hoc usados durante incidentes puntuales de producción | Herramientas de un solo uso, no forman parte del flujo normal de la app |
| `SDD_HOLTMONT_WORKSPACE.md` (líneas ~348 en adelante) | El archivo contiene ~700 líneas de comentarios HTML vacíos (`<!-- Reserved expansion line N ... -->`) tras la Sección 9 | Es relleno sin contenido técnico; el contenido real de ese documento termina en la Sección 9 ("Conclusión de Arquitectura") |
| `image.png` | Mock/referencia visual de diseño | No es parte del código ejecutable |
| `plan_productivity.md` | Notas de planeación previas a la implementación | Superado por el código ya integrado |
| `CREDENCIALES.md` (parcialmente) | Documenta el organigrama, pero quedó desactualizado respecto a `USER_DB` | Ver discrepancia documentada en §6.3 (`CESAR_GOMEZ` listado como baja pero activo en código) y §6.4 (3 cuentas activas sin documentar: `DANIELA_CASTRO`, `ANTONIO_SALAZAR`, y el propio `CESAR_GOMEZ`) |
| `SDD_OUTLOOK_INTEGRATION.md` (parcialmente) | Escrito en tono "propuesta a implementar" con código envuelto en comentarios | La integración descrita **ya está implementada en producción** con variaciones respecto al pseudocódigo del documento (ver §11.2) — tratar ese SDD como el registro de la decisión de diseño, y este documento (§11.2 + Anexo A §19.8) como el estado real del código |
| `test_bug.js` | Notas de análisis en comentarios (no código ejecutable con asserts) sobre un bug de reverse-sync en `apiSaveTrackerBatch`, citando números de línea aproximados | Las líneas citadas (5543, 5564, 5606) están muy cerca pero no coinciden exactamente con la ubicación actual de esa misma lógica en `CODIGO.js` (compárese con las líneas reales del bloque de reverse-sync en Anexo A §19.2, alrededor de 5546–5615) — es normal, el archivo se siguió editando después de escribir esta nota; `node test_bug.js` no produce ninguna salida ni valida nada, es documentación en forma de comentario |

**Regla práctica:** si dos archivos parecen describir lo mismo, **`CODIGO.js` e `index.html` (sin sufijo) siempre ganan** sobre cualquier variante numerada o con extensión `.bak/.orig/.rej`, y sobre cualquier SDD narrativo cuando haya conflicto de detalle — los SDD narrativos documentan la intención y el "por qué"; el código es la única fuente de verdad del "qué hace exactamente".

---

## 17. Anexo — Inventario Completo de Funciones (`CODIGO.js`, línea exacta)

```
115  formatDateForOutlook            2624  internalUpdateTask
131  NotifierService.sendToOutlook   3005  apiUpdateTask
172  findUserEmailByLabel            3009  apiLogDateChange
189  testIntegracionOutlook          3025  apiFetchDrafts
257  doGet                           3057  apiSyncDrafts
266  findSheetSmart                  3090  apiClearDrafts
277  findHeaderRow                   3098  ensureSheetWithHeaders
298  registrarLog                    3109  saveChildData
310  apiLogin                        3124  apiSavePPCData
322  apiLogout                       3437  uploadFileToDrive
327  getDirectoryFromDB              3455  apiFetchPPCData
388  apiResyncDirectory              3494  apiFetchWeeklyPlanData
467  apiAddEmployee                  3623  getWeekNumber
529  apiDeleteEmployee               3632  apiSaveSite
560  getSystemConfig                 3679  apiSaveSubProject
706  generarDashboard                3732  apiFetchCascadeTree
719  apiFetchAdminKPIs               3814  apiFetchProjectTasks
909  apiFetchTrackerProductivityMetrics   3880  apiSaveProjectTask
1113 runTrackerProductivityAgent     3909  onOpen
1176 _sendTrackerProductivityEmail   3924  cmdRealizarAlta
1243 apiFetchTeamKPIData             3979  cmdActualizar
1371 apiFetchQuoteAgentMetrics       4023  apiCreateStandardStructure
1571 apiWriteQuoteMetricsToSheet     4041  generatePrefix
1657 setupDailyQuoteMetricsTrigger   4067  generateNumericSequence
1669 autoUpdateQuoteMetrics          4092  generateAppSheetId
1683 callGeminiAPI                   4101  generateWorkOrderFolio
1714 apiSaveGeminiKey                4176  apiGetNextWorkOrderSeq
1724 apiCheckGeminiKey               4191  incrementarContadorDias
1730 runQuoteMetricsAgent            4306  instalarDisparador
1856 apiGetLastAgentReport           4329  generarFolioAutomatico
1867 _sendAgentEmail                 4390  test_Generacion_MAP_COT
1949 test_DataIntegrity              4449  test_Security_Filter_AllowedBase
1988 internalFetchSheetData          4488  test_Flujo_Completo_Delegacion_y_Sincronizacion
2070 apiFetchStaffTrackerData        4581  test_Cierre_Terminal_RCC
2109 apiFetchSalesHistory            4626  test_SavePPCV3_Flow
2156 internalBatchUpdateTasks        4685  test_WorkOrder_Generation
2600 apiUpdatePPCV3                  4714  test_Directory_CRUD
                                     4762  test_ReverseSync_Flow
4799  applyTrafficLightToSheet       5722  apiFetchUnifiedAgenda
4905  setupConditionalFormatting     5782  apiSavePersonalEvent
4937  colIndexToLetter               5792  apiSaveHabitLog
4947  test_NumericSequence_Generation 5807 transcribirConGemini
4982  test_Antonia_Distribution_Manual 5852 forzarPermisos
4995  apiFetchInfoBankCompanies      5864  test_SystemConfig_Label
5059  apiFetchInfoBankData           5894  getOrCreateFolder
5154  apiFetchDistinctClients        5903  getBankRootFolder
5183  apiSaveTrackerBatch            5922  archiveFile
5670  apiFetchCombinedCalendarData   5960  processQuoteRow
                                     6023  batchArchiveExistingQuotes
                                     6047  runFullArchivingBatch
                                     6056  deduplicateAllSheets
                                     6167  debugSheetHeaders
                                     6193  test_avance_100_bug
```

---

## 18. Índice de Documentos Relacionados en este Repositorio

| Documento | Enfoque |
|---|---|
| `AGENTS.md` | Reglas de negocio operativas + "skills" para agentes de IA que editen el código |
| `SDD_HOLTMONT_WORKSPACE.md` | Arquitectura general, Design Tokens, catálogo de API (v2.0.0) — nota: contenido real termina en su Sección 9, el resto es relleno (ver §16) |
| `PAPA_CALIENTE_SDD.md` | Especificación completa de la máquina de estados de cotizaciones (7 etapas) |
| `SDD_OUTLOOK_INTEGRATION.md` | Integración con Outlook/Power Automate — el diseño propuesto ahí ya está implementado en producción (ver §11.2) |
| `SDD_KPI_ADMIN.md` | Dashboard de KPIs para administradores: fórmulas de negocio exactas (% cierre, win rate, semaforización) — reproducidas también en §10.5 |
| `FRONTEND ANTONIA.md` | Especificación de refactor UI/UX del Data Grid (hitboxes, timeline, accordion, A11y) |
| `CREDENCIALES.md` | Organigrama y credenciales vigentes (⚠️ texto plano y parcialmente desactualizado, ver §6.3 y §13) |

---

# PARTE II — Anexos de Código Fuente Literal

## 19. Anexo A — Código Backend Completo (`CODIGO.js`)

> Código reproducido **literalmente** (sin resumir ni parafrasear) de las funciones más críticas del sistema, tal como existen en `CODIGO.js` a la fecha de este documento. Sirve para reconstruir el núcleo funcional del backend sin necesidad de abrir el archivo original.

### 19.1 Núcleo: entrada HTTP, búsqueda de hojas, auditoría y sesión

```js
/* SERVICIO HTML */
function doGet(e) {
  return HtmlService.createTemplateFromFile('Index')
    .evaluate()
    .setTitle('Holtmont Workspace')
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/* HELPERS */
function findSheetSmart(name) {
  if (!name) return null;
  let sheet = SS.getSheetByName(name);
  if (sheet) return sheet;
  const clean = String(name).trim().toUpperCase();
  const all = SS.getSheets();
  for (let s of all) { if (s.getName().trim().toUpperCase() === clean) return s; }
  return null;
}

// DETECTOR DE CABECERAS INTELIGENTE
function findHeaderRow(values) {
  for (let i = 0; i < Math.min(100, values.length); i++) {
    const rowStr = values[i].map(c => String(c).toUpperCase().replace(/\n/g, " ").replace(/\s+/g, " ").trim()).join("|");
    if (rowStr.includes("ID_SITIO") || rowStr.includes("ID_PROYECTO")) return i;
    if (rowStr.includes("FOLIO") && rowStr.includes("CONCEPTO") &&
       (rowStr.includes("ALTA") || rowStr.includes("AVANCE") || rowStr.includes("STATUS") || rowStr.includes("FECHA"))) {
      return i;
    }
    if (rowStr.includes("ID") && rowStr.includes("RESPONSABLE")) return i;
    if ((rowStr.includes("FOLIO") || rowStr.includes("ID")) &&
        (rowStr.includes("DESCRIPCI") || rowStr.includes("RESPONSABLE") || rowStr.includes("CONCEPTO"))) {
      return i;
    }
    if (rowStr.includes("CLIENTE") && (rowStr.includes("VENDEDOR") || rowStr.includes("AREA") || rowStr.includes("CLASIFICACION"))) return i;
    // SOPORTE PARA AGENDA PERSONAL Y HABITOS
    if (rowStr.includes("ID") && rowStr.includes("TITULO") && rowStr.includes("USUARIO")) return i;
    if (rowStr.includes("ID") && rowStr.includes("HABITO") && rowStr.includes("USUARIO")) return i;
  }
  return -1;
}

function registrarLog(user, action, details) {
  try {
    let sheet = SS.getSheetByName(APP_CONFIG.logSheetName);
    if (!sheet) {
      sheet = SS.insertSheet(APP_CONFIG.logSheetName);
      sheet.appendRow(["FECHA", "USUARIO", "ACCION", "DETALLES"]);
    }
    sheet.appendRow([new Date(), user, action, details]);
  } catch (e) { console.error(e); }
}

/* LOGIN */
function apiLogin(username, password) {
  const userKey = String(username).trim().toUpperCase();
  const passTrimmed = String(password).trim();
  const user = USER_DB[userKey];
  if (user && user.pass === passTrimmed) {
    registrarLog(userKey, "LOGIN", `Acceso exitoso (${user.role})`);
    return { success: true, role: user.role, name: user.label, username: userKey };
  }
  registrarLog(userKey || "ANONIMO", "LOGIN_FAIL", "Credenciales incorrectas");
  return { success: false, message: 'Usuario o contraseña incorrectos.' };
}

function apiLogout(username) {
  registrarLog(username || "DESCONOCIDO", "LOGOUT", "Sesión cerrada");
  return { success: true };
}

/* DIRECTORIO VIVO (DB_DIRECTORY) */
function getDirectoryFromDB() {
  const lock = LockService.getScriptLock();
  try {
      if (lock.tryLock(5000)) {
          let sheet = findSheetSmart(APP_CONFIG.directorySheetName);

          // CREAR SI NO EXISTE
          if (!sheet) {
              sheet = SS.insertSheet(APP_CONFIG.directorySheetName);
          }

          // MIGRACIÓN/POBLADO AUTOMÁTICO (Si está vacía o solo tiene encabezados)
          if (sheet.getLastRow() < 2) {
              sheet.clear(); // Limpiar por si acaso el usuario puso encabezados manuales incorrectos
              const headers = ["NOMBRE", "DEPARTAMENTO", "TIPO_HOJA"];
              sheet.appendRow(headers);

              // Populate from INITIAL_DIRECTORY
              const rows = INITIAL_DIRECTORY.map(u => [u.name, u.dept, u.type]);
              if (rows.length > 0) {
                  sheet.getRange(2, 1, rows.length, 3).setValues(rows);
              }
              SpreadsheetApp.flush();
              registrarLog("SISTEMA", "MIGRACION_DB", "Se pobló DB_DIRECTORY (estaba vacía).");
          }

          const data = sheet.getDataRange().getValues();
          if (data.length < 2) return INITIAL_DIRECTORY;

          // Parse Data
          const headers = data[0].map(h => String(h).toUpperCase().trim());
          const nameIdx = headers.indexOf("NOMBRE");
          const deptIdx = headers.indexOf("DEPARTAMENTO");
          const typeIdx = headers.indexOf("TIPO_HOJA");

          if (nameIdx === -1) return INITIAL_DIRECTORY;

          const directory = [];
          for (let i = 1; i < data.length; i++) {
              const row = data[i];
              if (row[nameIdx]) {
                  directory.push({
                      name: String(row[nameIdx]).trim(),
                      dept: (deptIdx > -1) ? String(row[deptIdx]).trim() : "GENERAL",
                      type: (typeIdx > -1) ? String(row[typeIdx]).trim() : "ESTANDAR"
                  });
              }
          }
          return directory;
      }
  } catch (e) {
      console.error(e);
      // Fallback in case of error
      return INITIAL_DIRECTORY;
  } finally {
      lock.releaseLock();
  }
  return INITIAL_DIRECTORY;
}
```

### 19.2 `apiSaveTrackerBatch` — el guardado masivo con ruteo, auto-sanación y reverse-sync (línea 5183, función más grande del sistema)

```js
function apiSaveTrackerBatch(personName, tasks, username) {
  const lock = LockService.getScriptLock();
  if (lock.tryLock(30000)) {
    try {
      const processedTasks = [];
      const distributionTasks = [];
      const isAntonia = String(personName).toUpperCase() === "ANTONIA_VENTAS";

      // Sequence Auto-Healing Logic for Antonia
      let seqKey = 'ANTONIA_SEQ_V2';
      if (isAntonia) {
          const props = PropertiesService.getScriptProperties();
          let currentSeq = Number(props.getProperty(seqKey) || 1000);

          // AUTO-HEALING: Scan batch for higher existing IDs to sync sequence
          let needsHeal = false;
          tasks.forEach(t => {
              const folioVal = String(t['FOLIO'] || t['ID'] || "");
              if (folioVal.startsWith("AV-")) {
                  const numPart = folioVal.replace("AV-", "");
                  const fid = parseInt(numPart);
                  if (!isNaN(fid) && fid > currentSeq) {
                      currentSeq = fid;
                      needsHeal = true;
                  }
              }
          });
          if (needsHeal) {
              props.setProperty(seqKey, String(currentSeq));
          }
      }

      tasks.forEach(task => {
        let taskData = {...task};

        // GHOST BUSTING: Verificar contenido antes de asignar Folio
        const clean = (val) => val ? String(val).trim() : "";
        const c = clean(taskData['CONCEPTO']);
        const d = clean(taskData['DESCRIPCION']);
        const cl = clean(taskData['CLIENTE']);
        const vk = Object.keys(taskData).find(k => k.toUpperCase().trim() === "VENDEDOR" || k.toUpperCase().trim() === "RESPONSABLE" || k.toUpperCase().trim() === "INVOLUCRADOS");
        const v = vk ? clean(taskData[vk]) : "";

        // Ignorar si VENDEDOR es solo el default "ANTONIA_VENTAS" y no hay nada más
        const isVendedorDefault = isAntonia ? v.toUpperCase() === "ANTONIA_VENTAS" : false;

        const hasContent = (c !== "") ||
                           (d !== "") ||
                           (cl !== "") ||
                           (v !== "" && !isVendedorDefault);

        // Buscar de forma insensible a mayúsculas si existe un FOLIO o ID
        let existingTaskFolio = null;
        Object.keys(taskData).forEach(k => {
            if ((k.toUpperCase().trim() === 'FOLIO' || k.toUpperCase().trim() === 'ID') && taskData[k]) {
                existingTaskFolio = taskData[k];
            }
        });

        if (!hasContent && !existingTaskFolio) return; // SKIP EMPTY ROWS (Don't process, don't distribute)

        // CHECK FOR _tempId
        const tempIdKey = taskData['_tempId'];
        if (tempIdKey) {
             // We keep it so index.html can identify the returned row
             // Conservamos el tempId para inyectarlo al final
        }

        // Use robust locked generator to avoid duplicates during mass-inserts
        if (!existingTaskFolio && hasContent) {
            let prefixSource = username || personName;
            if (String(personName).toUpperCase().trim() === "ANTONIA PINEDA LOPEZ" && String(username).toUpperCase().trim() === "ANTONIA_VENTAS") {
                prefixSource = "ANTONIA PINEDA LOPEZ";
            }
            let prefix = isAntonia ? "AV-" : generatePrefix(prefixSource);
            let seqKey = isAntonia ? 'ANTONIA_SEQ_V2' : prefix;
            const seqNum = generateNumericSequence(seqKey);
            taskData['FOLIO'] = prefix + seqNum;
        }

        if (isAntonia) {
             if (existingTaskFolio || taskData['FOLIO']) {
                 // RESTRICTIONS FOR EXISTING TASKS
                 const allowedBase = ['FOLIO', 'ID', 'ESTATUS', 'MAP COT', 'PROCESO_LOG', 'PROCESO', 'STATUS', 'AVANCE', 'AVANCE %', '_rowIndex', 'VENDEDOR', 'RESPONSABLE', 'INVOLUCRADOS', 'ENCARGADO', 'CONCEPTO', 'DESCRIPCION', 'CLIENTE', 'COTIZACION', 'F2', 'LAYOUT', 'TIMELINE', 'AREA', 'CLASIFICACION', 'CLASI', 'DIAS', 'RELOJ', 'ESPECIALIDAD', 'ARCHIVO', 'ARCHIVOS', 'COMENTARIOS', 'PRIORIDAD', 'PRIORIDAD DE COTIZACION', 'PRIO. COT.', 'F. VISITA', 'F. INICIO', 'F. ENTREGA', 'FECHA VISITA', 'FECHA INICIO', 'DÍAS FINALIZ. COTIZ', 'DIAS FINALIZ. COTIZ', 'CORREO', 'CARPETA', 'INFO CLIENTE', 'CORREOS', 'CARPETAS', 'REQUISITOR'];
                 Object.keys(taskData).forEach(key => {
                     const kUp = key.toUpperCase();
                     if (key.startsWith('_')) return;
                     const isBase = allowedBase.includes(kUp);
                     const isDate = kUp.includes('FECHA') || kUp.includes('ALTA');
                     if (!isBase && !isDate) {
                         delete taskData[key];
                     }
                 });
             }
             // Remove worker logic (Reverse Sync)
             if (taskData._removeWorker) {
                 const workerToRemove = taskData._removeWorker;
                 try {
                     let targetSheet = String(workerToRemove).replace(/\s*\(VENTAS\)/ig, "").trim();
                     const workerSheet = findSheetSmart(targetSheet);
                     if (workerSheet) {
                         const targetId = String(existingTaskFolio || taskData['FOLIO'] || taskData['ID'] || "").toUpperCase().trim();
                         if (targetId && targetId !== "NULL") {
                             const data = workerSheet.getDataRange().getValues();
                             if (data.length > 0) {
                                 const sheetHeaders = data[0].map(h => String(h).toUpperCase().trim());
                                 const folioIdx = sheetHeaders.indexOf('FOLIO');
                                 const idIdx = sheetHeaders.indexOf('ID');
                                 for (let i = 1; i < data.length; i++) {
                                     let rowFolio = (folioIdx > -1 ? data[i][folioIdx] : "") || (idIdx > -1 ? data[i][idIdx] : "");
                                     if (String(rowFolio).toUpperCase().trim() === targetId) {
                                         workerSheet.deleteRow(i + 1);
                                         registrarLog("ANTONIA", "REMOVED_WORKER", `Eliminada tarea ${targetId} de ${targetSheet}`);
                                         break;
                                     }
                                 }
                             }
                         }
                     }
                 } catch(e) {
                     registrarLog("ANTONIA", "REMOVE_ERROR", e.toString());
                 }
                 // Avoid re-distributing to this worker during save
                 delete taskData._removeWorker;
                 delete taskData._assignStep;
             }

             // Prepare distribution data
             const distData = JSON.parse(JSON.stringify(taskData));
             delete distData._rowIndex;
             delete distData['PROCESO_LOG'];
                          delete distData['PROCESO'];
             if (taskData._assignToWorker && taskData._assignStep) {
                 try {
                     const workers = Array.isArray(taskData._assignToWorker) ? taskData._assignToWorker : [taskData._assignToWorker];
                     const stepTitle = taskData._assignStep;
                     const folioStr = existingTaskFolio || taskData["FOLIO"] || taskData["ID"] || "SIN-FOLIO";
                     const clienteStr = taskData["CLIENTE"] || "Desconocido";

                     for (let worker of workers) {
                         const cleanWorker = String(worker).replace(/\s*\(VENTAS\)/ig, "").trim();
                         const assignData = JSON.parse(JSON.stringify(distData));
                         assignData['ESTATUS'] = 'PENDIENTE';
                         assignData['AVANCE'] = '0%';
                         internalBatchUpdateTasks(cleanWorker, [assignData]);

                         // INTEGRACIÓN OUTLOOK: Enviar evento al trabajador asignado
                         const userEmail = findUserEmailByLabel(cleanWorker);
                         if (userEmail) {
                             const fInicio = new Date();
                             const fFin = new Date(fInicio.getTime() + (2 * 60 * 60 * 1000));

                             const payloadOutlook = {
                                 folio: folioStr,
                                 titulo: `Asignación Tracker: ${stepTitle} - ${clienteStr}`,
                                 descripcion: `Se te ha asignado la etapa ${stepTitle} para el folio ${folioStr}. Revisa tu Tracker en Holtmont Workspace.`,
                                 fechaInicio: fInicio.toISOString(),
                                 fechaFin: fFin.toISOString(),
                                 correoDestino: userEmail,
                                 asignadoPor: username
                             };

                             const resultOutlook = NotifierService.sendToOutlook(payloadOutlook);
                             if (resultOutlook.success) {
                                 console.log(`Notificación Outlook enviada para Folio: ${folioStr}`);
                             }
                         } else {
                             console.warn(`No se encontró email corporativo para delegado: ${worker}`);
                         }
                     }
                 } catch(e) {}
             }
             distributionTasks.push(distData);
        } else {
             // REVERSE SYNC PREPARATION
             const distData = JSON.parse(JSON.stringify(taskData));
             delete distData._rowIndex;
             delete distData['PROCESO_LOG'];
                          delete distData['PROCESO'];
             distributionTasks.push(distData);
        }
        processedTasks.push(taskData);
      });

      // Sequence handled safely per-task by generateNumericSequence

      // Batch Update Main Sheet
      const res = internalBatchUpdateTasks(personName, processedTasks, false); // Already locked

      processedTasks.forEach((t, i) => {
          const originalTask = tasks[i];
          if (originalTask && originalTask['_tempId']) {
              t['_tempId'] = originalTask['_tempId'];
          }
      });

      if (res.success) {
          // --- SMART ARCHIVING TRIGGER (ANTONIA) ---
          // "Trigger the archiver logic whenever Antonia saves data"
          if (isAntonia || String(personName).toUpperCase().includes("ANTONIA_VENTAS")) {
              try {
                  processedTasks.forEach(row => {
                      // Only process if it has a file
                      if (row['COTIZACION'] || row['ARCHIVO']) {
                          processQuoteRow(row);
                      }
                  });
              } catch (archErr) {
                  console.error("Auto-Archiving Error: " + archErr.toString());
              }
          }
          // -----------------------------------------

          // Handle Distribution for Antonia
          if (isAntonia && distributionTasks.length > 0) {
              // Group by vendor to batch updates
              const byVendor = {};
              distributionTasks.forEach(t => {
                  const vendedorKey = Object.keys(t).find(k => k.toUpperCase().trim() === "VENDEDOR" || k.toUpperCase().trim() === "RESPONSABLE" || k.toUpperCase().trim() === "INVOLUCRADOS");
                  if (vendedorKey && t[vendedorKey]) {
                       const vNames = String(t[vendedorKey]).split(',').map(s => s.trim());
                       vNames.forEach(vName => {
                           if (vName.toUpperCase() !== "ANTONIA_VENTAS") {
                               let target = vName;
                               // Logic to find target sheet (suffix check)
                               let finalTarget = null;
                               if (target.toUpperCase().includes("(VENTAS)")) finalTarget = target;
                               else {
                                   if (findSheetSmart(target + " (VENTAS)")) finalTarget = target + " (VENTAS)";
                                   else if (findSheetSmart(target)) finalTarget = target; // Fallback if no ventas sheet
                               }

                               if (finalTarget) {
                                   if (!byVendor[finalTarget]) byVendor[finalTarget] = [];
                                   byVendor[finalTarget].push(t);
                               }

                               // INTEGRACIÓN OUTLOOK: Enviar evento al trabajador asignado a la fila
                               let existingTaskFolioDist = null;
                               Object.keys(t).forEach(k => {
                                   if ((k.toUpperCase().trim() === 'FOLIO' || k.toUpperCase().trim() === 'ID') && t[k]) {
                                       existingTaskFolioDist = t[k];
                                   }
                               });
                               const folioGen = existingTaskFolioDist || t["FOLIO"] || t["ID"] || "SIN-FOLIO";
                               const clienteGen = t["CLIENTE"] || "Desconocido";
                               const conceptoGen = t["CONCEPTO"] || t["DESCRIPCION"] || "Tarea";

                               const emailGen = findUserEmailByLabel(vName);
                               if (emailGen) {
                                   const fIni = new Date();
                                   const fFi = new Date(fIni.getTime() + (2 * 60 * 60 * 1000));
                                   const pGeneral = {
                                       folio: folioGen,
                                       titulo: `Nueva Asignación: ${conceptoGen} - ${clienteGen}`,
                                       descripcion: `Se te ha asignado una tarea general (${conceptoGen}) en el Tracker. Folio: ${folioGen}.`,
                                       fechaInicio: fIni.toISOString(),
                                       fechaFin: fFi.toISOString(),
                                       correoDestino: emailGen,
                                       asignadoPor: username
                                   };
                                   NotifierService.sendToOutlook(pGeneral);
                               }
                           }
                       });
                  }
              });

              // Execute distribution batches
              for (const [vSheet, vTasks] of Object.entries(byVendor)) {
                   internalBatchUpdateTasks(vSheet, vTasks, false);
              }

              // Sync to ADMIN
              internalBatchUpdateTasks("ADMINISTRADOR", distributionTasks, false);
          }

          // Handle Reverse Sync (Vendor -> Antonia)
          if (!isAntonia && distributionTasks.length > 0) {
               const syncPayloads = [];
               let antDataFetched = false;
               let antDataRows = [];

               distributionTasks.forEach(taskData => {
                   const getTVal = (keys) => {
                       for (let k of keys) {
                           let found = Object.keys(taskData).find(key => key.toUpperCase().trim() === k);
                           if (found && taskData[found]) return taskData[found];
                       }
                       return "";
                   };

                   const estatus = String(getTVal(['ESTATUS', 'STATUS', 'ESTADO'])).toUpperCase().trim();
                   const avanceRaw = String(getTVal(['AVANCE', 'AVANCE %', '% AVANCE', '%', 'CUMPLIMIENTO'])).replace(/%/g, '').trim();
                   const avanceNum = parseFloat(avanceRaw);
                   const isDone = estatus === 'HECHO' || estatus === 'TERMINADO' || estatus === 'FINALIZADO' || estatus === 'REALIZADO' || estatus === 'COMPLETADO' || estatus === 'DONE' || avanceRaw === '100' || avanceNum === 100 || avanceRaw.toUpperCase() === 'SI';
                   const tFolio = String(getTVal(['FOLIO', 'ID'])).toUpperCase().trim();

                   if (tFolio && isDone) {
                       if (!antDataFetched) {
                           const antData = internalFetchSheetData("ANTONIA_VENTAS");
                           if (antData.success && antData.data) antDataRows = antData.data;
                           antDataFetched = true;
                       }

                       const targetRow = antDataRows.find(r => String(r['FOLIO'] || r['ID'] || "").toUpperCase().trim() === tFolio);
                       if (targetRow) {
                           let log = [];
                           try {
                               if (targetRow['PROCESO_LOG']) log = JSON.parse(targetRow['PROCESO_LOG']);
                           } catch(e) {}

                           let updated = false;
                           let updatedLog = [];
                           if (Array.isArray(log)) {
                               updatedLog = log.map(entry => {
                                   let wNorm = String(personName).toUpperCase().trim().replace(/\s*\(VENTAS\)/g, "").replace(/_/g, " ");
                                   let eNorm = entry.assignee ? String(entry.assignee).toUpperCase().trim().replace(/\s*\(VENTAS\)/g, "").replace(/_/g, " ") : "";

                                   if (entry.status === 'IN_PROGRESS' && (eNorm === wNorm || eNorm.includes(wNorm) || wNorm.includes(eNorm) || eNorm === "" || wNorm === "") && isDone) {
                                       entry.status = 'DONE';
                                       entry.endTimestamp = new Date().getTime();
                                       entry.endDateStr = new Date().toLocaleString();
                                       // Se preserva entry.timestamp y entry.dateStr originales (Fecha de Inicio)
                                       updated = true;
                                       registrarLog("SYSTEM", "REVERSE_SYNC_BATCH", `${personName} completed step ${entry.step} for FOLIO ${tFolio}`);
                                   }
                                   return entry;
                               });
                           }

                           if (updated) {
                               const stepsOrder = ["L", "CD", "EP", "CI", "EV", "CEC", "RCC"];
                               let oldParts = (targetRow["MAP COT"] || "").split(/\||>|\//).map(p => p.trim());
                               let mapCotParts = stepsOrder.map(step => {
                                   // Valid entries: step is a known PROCESS_STEPS ID
                                   const stepEntries = updatedLog.filter(e => e.step === step || e.to === step);
                                   if (stepEntries.length > 0) {
                                       const allDone = stepEntries.every(e => e.status === 'DONE');
                                       if (allDone) return '🟢 ' + step;
                                       const anyInProgress = stepEntries.some(e => e.status === 'IN_PROGRESS');
                                       if (anyInProgress) return '🟡 ' + step;
                                       return '🔴 ' + step;
                                   }
                                   // Garbage entries: step field contains the old MAP COT string.
                                   // If it shows 🟡 STEP or 🔴 STEP, this entry was for that step.
                                   const garbageForStep = updatedLog.filter(e =>
                                       !stepsOrder.includes(e.step) &&
                                       (e.step.includes('🟡 ' + step) || e.step.includes('🔴 ' + step))
                                   );
                                   if (garbageForStep.length > 0) {
                                       const allDone = garbageForStep.every(e => e.status === 'DONE');
                                       if (allDone) return '🟢 ' + step;
                                       const anyInProgress = garbageForStep.some(e => e.status === 'IN_PROGRESS');
                                       if (anyInProgress) return '🟡 ' + step;
                                   }
                                   let oldPart = oldParts.find(p => p === '🟢 ' + step || p === '🟡 ' + step || p === '🔴 ' + step || p === '⚪ ' + step || p.includes(' ' + step));
                                   if (oldPart && oldPart.includes('🟢')) return '🟢 ' + step;
                                   if (oldPart && oldPart.includes('🟡')) return '🟡 ' + step;
                                   if (oldPart && oldPart.includes('🔴')) return '🔴 ' + step;
                                   return '⚪ ' + step;
                               });

                               let syncToAntonia = {
                                   'FOLIO': targetRow['FOLIO'] || tFolio,
                                   'PROCESO_LOG': JSON.stringify(updatedLog),
                                   'MAP COT': mapCotParts.join(' | ')
                               };

                               const fileCols = ['ARCHIVO', 'F2', 'LAYOUT', 'COTIZACION', 'EVIDENCIA'];
                               fileCols.forEach(col => {
                                   let wKey = Object.keys(taskData).find(k => k.toUpperCase().trim() === col);
                                   if (wKey && taskData[wKey] && String(taskData[wKey]).trim() !== "") {
                                       syncToAntonia[wKey] = taskData[wKey];
                                   }
                               });

                               syncPayloads.push(syncToAntonia);
                           }
                       }
                   }
               });

               if (syncPayloads.length > 0) {
                   internalBatchUpdateTasks("ANTONIA_VENTAS", syncPayloads, false);
               }

               if (String(personName).toUpperCase().includes("(VENTAS)")) {
                   const safeDistTasks = distributionTasks.map(t => {
                       let st = Object.assign({}, t);
                       const delKeys = ['ESTATUS', 'STATUS', 'ESTADO', 'AVANCE', 'AVANCE %', '% AVANCE', '%', 'CUMPLIMIENTO'];
                       Object.keys(st).forEach(k => {
                           if (delKeys.includes(k.toUpperCase().trim())) delete st[k];
                       });
                       const matchedSync = syncPayloads.find(sp => sp.FOLIO === st.FOLIO || sp.ID === st.FOLIO || sp.FOLIO === st.ID);
                       if (matchedSync) {
                           st['MAP COT'] = matchedSync['MAP COT'];
                           st['PROCESO_LOG'] = matchedSync['PROCESO_LOG'];
                       }
                       return st;
                   });
                   internalBatchUpdateTasks("ANTONIA_VENTAS", safeDistTasks, false);
               }

               // Sincronización Reversa hacia Antonia (NO está completa si no termina en VENTAS ni está DONE)
               const antoniaReverseSyncTasks = [];
               distributionTasks.forEach(t => {
                   let existingTaskFolioRev = null;
                   Object.keys(t).forEach(k => {
                       if ((k.toUpperCase().trim() === 'FOLIO' || k.toUpperCase().trim() === 'ID') && t[k]) {
                           existingTaskFolioRev = t[k];
                       }
                   });
                   const reverseFolio = existingTaskFolioRev || t['FOLIO'] || t['ID'];
                   if (reverseFolio && String(reverseFolio).toUpperCase().startsWith("AV-")) {
                       antoniaReverseSyncTasks.push(t);
                   }
               });
               if (antoniaReverseSyncTasks.length > 0) {
                   const safeRevTasks = antoniaReverseSyncTasks.map(t => {
                       let st = Object.assign({}, t);
                       const delKeys = ['ESTATUS', 'STATUS', 'ESTADO', 'AVANCE', 'AVANCE %', '% AVANCE', '%', 'CUMPLIMIENTO'];
                       Object.keys(st).forEach(k => {
                           if (delKeys.includes(k.toUpperCase().trim())) delete st[k];
                       });
                       const matchedSync = syncPayloads.find(sp => sp.FOLIO === st.FOLIO || sp.ID === st.FOLIO || sp.FOLIO === st.ID);
                       if (matchedSync) {
                           st['MAP COT'] = matchedSync['MAP COT'];
                           st['PROCESO_LOG'] = matchedSync['PROCESO_LOG'];
                       }
                       return st;
                   });
                   internalBatchUpdateTasks("ANTONIA_VENTAS", safeRevTasks, false);
               }

               // Handle Peer-to-Peer Sync (Vendor -> Other Vendor)
               const peerUpdates = {};
               distributionTasks.forEach(t => {
                   const vKey = Object.keys(t).find(k => k.toUpperCase().trim() === "VENDEDOR" || k.toUpperCase().trim() === "RESPONSABLE" || k.toUpperCase().trim() === "INVOLUCRADOS");
                   if(vKey && t[vKey]) {
                       const vList = String(t[vKey]).split(',').map(s => s.trim());
                       vList.forEach(otherVendor => {
                           if (otherVendor.toUpperCase() === "ANTONIA_VENTAS") return;
                           const currentSheetNorm = String(personName).toUpperCase().replace(/\s*\(VENTAS\)/, "").trim();
                           const otherVendorNorm = String(otherVendor).toUpperCase().replace(/\s*\(VENTAS\)/, "").trim();

                           if (currentSheetNorm !== otherVendorNorm) {
                               let targetSheet = otherVendor;
                             if (targetSheet.toUpperCase() === "ANTONIA_VENTAS") {
                                 targetSheet = "ANTONIA PINEDA LOPEZ";
                             }

                             if (username !== 'ANTONIA_VENTAS') {
                                 // REGLA ESTRICTA: Nadie excepto ANTONIA_VENTAS puede enviar a hojas con (VENTAS)
                                 targetSheet = targetSheet.replace(/\s*\(VENTAS\)/ig, "").trim();
                             }

                               // MODIFICADO: No agregar el sufijo "(VENTAS)" automáticamente si no es Antonia.
                               // Se debe escribir exactamente a la tabla que especifican.
                               let finalTarget = targetSheet;
                               if(!peerUpdates[finalTarget]) peerUpdates[finalTarget] = [];
                               peerUpdates[finalTarget].push(t);
                           }
                       });
                   }
               });

               for (const [target, tasks] of Object.entries(peerUpdates)) {
                   internalBatchUpdateTasks(target, tasks, false);
               }
          }

          registrarLog(username, "BATCH_UPDATE", `Actualizadas ${tasks.length} tareas en ${personName}`);
      }

      return { success: true, message: "Guardado exitoso", data: processedTasks };

    } catch (e) {
      return { success: false, message: e.toString() };
    } finally {
      lock.releaseLock();
    }
  } else {
      return { success: false, message: "Sistema ocupado" };
  }
}
```

### 19.3 `internalBatchUpdateTasks` — el "Gatekeeper" (línea 2156, 444 líneas)

```js
function internalBatchUpdateTasks(sheetName, tasksArray, useOwnLock = true) {
  if (!tasksArray || tasksArray.length === 0) return { success: true };
  const lock = LockService.getScriptLock();
  if (useOwnLock) {
    if (!lock.tryLock(10000)) {
        return { success: false, message: "Hoja ocupada, intenta de nuevo."};
    }
  }

  try {
    const sheet = findSheetSmart(sheetName);
    if (!sheet) return { success: false, message: "Hoja no encontrada: " + sheetName };
    const dataRange = sheet.getDataRange();
    let values = dataRange.getValues();
    if (values.length === 0) return { success: false, message: "Hoja vacía" };

    const headerRowIndex = findHeaderRow(values);
    if (headerRowIndex === -1) return { success: false, message: "Sin cabeceras válidas" };
    const cache = CacheService.getScriptCache();
    // 1. SANITIZAR HEADERS Y ELIMINAR FILTROS ROTOS (FIX CRÍTICO)
    let headersChanged = false;
    for(let c = 0; c < values[headerRowIndex].length; c++) {
        if (values[headerRowIndex][c] === "" || values[headerRowIndex][c] === null) {
            values[headerRowIndex][c] = "COL_" + (c + 1);
            headersChanged = true;
        }
    }

    if (headersChanged) {
        const existingFilter = sheet.getFilter();
        if (existingFilter) {
            try { existingFilter.remove(); } catch(e) {}
        }
        sheet.getRange(headerRowIndex + 1, 1, 1, values[headerRowIndex].length).setValues([values[headerRowIndex]]);
        SpreadsheetApp.flush();
    }

    // FIX: HEADERS CON SALTOS DE LINEA (NORMALIZACIÓN ROBUSTA)
    const headers = values[headerRowIndex].map(h => String(h).toUpperCase().replace(/\n/g, ' ').replace(/\s+/g, ' ').trim());
    const maxCols = values.reduce((max, r) => Math.max(max, r.length), 0);
    const totalColumns = Math.max(maxCols, headers.length);

    const colMap = {};
    headers.forEach((h, i) => colMap[h] = i);
    const getColIdx = (key) => {
      const k = key.toUpperCase().trim();
      if (colMap[k] !== undefined) return colMap[k];
      const aliases = {
        'FECHA': ['FECHA', 'FECHAS', 'FECHA ALTA', 'FECHA INICIO', 'FECHA DE INICIO', 'FECHA VISITA', 'FECHA DE ALTA', 'F_INICIO'],
        'CONCEPTO': ['CONCEPTO', 'DESCRIPCION', 'DESCRIPCIÓN DE LA ACTIVIDAD', 'DESCRIPCIÓN', 'ACTIVIDAD'],
        'RESPONSABLE': ['RESPONSABLE', 'RESPONSABLES', 'INVOLUCRADOS', 'VENDEDOR', 'ENCARGADO', 'ASIGNADO'],
        'HORA': ['HORA', 'HORA ASIGNACION', 'HORA DE ASIGNACION'],
        'RELOJ': ['RELOJ', 'HORAS', 'DIAS', 'DÍAS'],
        'ESTATUS': ['ESTATUS', 'STATUS'],
        'CUMPLIMIENTO': ['CUMPLIMIENTO', 'CUMPL.', 'CUMP'],
        'AVANCE': ['AVANCE', 'AVANCE %', '% AVANCE', '%'],
        'ALTA': ['AREA', 'DEPARTAMENTO', 'ESPECIALIDAD', 'ALTA'],
        'FECHA_RESPUESTA': ['FECHA_RESPUESTA', 'FECHA RESPUESTA', 'FECHA FIN', 'FECHA ESTIMADA DE FIN', 'FECHA ESTIMADA', 'FECHA DE ENTREGA', 'FECHA_FIN', 'DEADLINE', 'FEC. EST. FIN'],
        'PRIORIDAD': ['PRIORIDAD', 'PRIORIDADES', 'PRIORIDAD DE COTIZACION', 'PRIO. COT.'],
        'RIESGOS': ['RIESGO', 'RIESGOS'],
        'ARCHIVO': ['ARCHIVO', 'ARCHIVOS', 'CLIP', 'LINK', 'URL', 'EVIDENCIA', 'DOCUMENTO', 'FOTO', 'VIDEO'],
        'CLASIFICACION': ['CLASIFICACION', 'CLASI'],
        'COMENTARIOS': ['COMENTARIOS', 'COMENTARIO', 'COMENTARIOS SEMANA EN CURSO', 'OBSERVACIONES', 'NOTAS', 'DETALLES'],
        'PREVIOS': ['COMENTARIOS PREVIOS', 'PREVIOS', 'COMENTARIOS SEMANA PREVIA'],
        'FECHA_TERMINO': ['FECHA_TERMINO', 'FECHA TERMINO', 'FECHA REAL', 'TERMINO', 'REALIZADO']
      };
      for (let main in aliases) {
        if (main === k || aliases[main].includes(k)) {
             for(let alias of aliases[main]) if(colMap[alias] !== undefined) return colMap[alias];
        }
      }
      return -1;
    };
    const folioIdx = getColIdx('FOLIO') > -1 ? getColIdx('FOLIO') : getColIdx('ID');
    let rowsToAppend = [];
    let singleRowIndex = -1;
    let modified = false;

    // 2. Procesar Tareas
    tasksArray.forEach(task => {
      let rowIndex = -1;

      let tFolio = "";
      Object.keys(task).forEach(k => {
          if (k.toUpperCase().trim() === 'FOLIO' || k.toUpperCase().trim() === 'ID') {
              if (task[k]) tFolio = String(task[k]).toUpperCase().trim();
          }
      });

      const tempIdKey = task['_tempId'];
      if (tempIdKey) {
           const cacheKey = sheetName + "_" + tempIdKey;
           const processed = cache.get(cacheKey);
           if (processed) return; // Skip if already processed for this specific sheet
           cache.put(cacheKey, "1", 120); // 2 minute memory
      }

      if (task._rowIndex) {
        const candidateRowIndex = parseInt(task._rowIndex) - 1;
        // 2.1 VALIDACIÓN DE SEGURIDAD (ANTI-DESPLAZAMIENTO)
        // Verificamos que el Folio en esa fila coincida con el payload.
        // Si hubo movimientos (filas borradas/insertadas), el índice ya no coincidirá.
        if (candidateRowIndex > headerRowIndex && candidateRowIndex < values.length && folioIdx > -1 && tFolio) {
             const rowFolio = String(values[candidateRowIndex][folioIdx] || "").toUpperCase().trim();
             if (rowFolio === tFolio) {
                 rowIndex = candidateRowIndex;
             } else {
                 console.warn(`[SYNC WARNING] Desplazamiento detectado. Folio Payload: ${tFolio} vs Folio Fila: ${rowFolio} (Fila ${candidateRowIndex+1}). Activando búsqueda.`);
             }
        } else if (!tFolio) {
             // Si no hay folio (ej. solo fila), confiamos en el índice si es válido
             if (candidateRowIndex > headerRowIndex && candidateRowIndex < values.length) rowIndex = candidateRowIndex;
        }
      }

      if (rowIndex === -1 && tFolio && folioIdx > -1) {
           // Búsqueda Robusta por Folio
           for (let i = headerRowIndex + 1; i < values.length; i++) {
             const row = values[i];
             if (String(row[folioIdx]).toUpperCase().trim() === tFolio) { rowIndex = i; break; }
          }
      }

      // NO-DUPLICATE GATEKEEPER: Fallback search by CONCEPTO + FECHA if Folio wasn't found
      if (rowIndex === -1) {
          const tConcept = String(task['CONCEPTO'] || task['DESCRIPCION'] || task['TAREA'] || "").trim().toUpperCase().substring(0, 50);
          const tDate = String(task['FECHA'] || task['F. INICIO'] || "").trim();

          if (tConcept) {
             const conceptIdx = getColIdx('CONCEPTO') > -1 ? getColIdx('CONCEPTO') : getColIdx('DESCRIPCION');
             const dateIdx = getColIdx('FECHA') > -1 ? getColIdx('FECHA') : getColIdx('F. INICIO');

             if (conceptIdx > -1) {
                 for (let i = headerRowIndex + 1; i < values.length; i++) {
                     const row = values[i];
                     const rowConcept = String(row[conceptIdx]).trim().toUpperCase().substring(0, 50);
                     const rowDateRaw = row[dateIdx];

                     let rowDateStr = "";
                     if (rowDateRaw instanceof Date) {
                         rowDateStr = Utilities.formatDate(rowDateRaw, SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone(), "dd/MM/yy");
                     } else {
                         rowDateStr = String(rowDateRaw || "").trim();
                     }

                     // Restore date check: If Concept matches exactly, AND Date matches exactly
                     // If both dates are empty or unprovided, we DO NOT match to avoid overwriting random tasks.
                     // They must both have a valid matching date to be considered duplicates without a Folio.

                     const cleanTDate = tDate.replace(/-/g, '/').replace(/20(\d{2})/, '$1');
                     const cleanRowDate = rowDateStr.replace(/-/g, '/').replace(/20(\d{2})/, '$1');

                     // RELAXED GATEKEEPER: If both dates are empty, or if they match, we consider it a duplicate
                     // Since new tasks might be sent without date and generated on the fly, a strict date match causes duplicates.
                     const isDateMatch = (cleanTDate === "" && cleanRowDate === "") ||
                                         ((cleanTDate !== "" && cleanRowDate !== "") && (cleanRowDate.includes(cleanTDate) || cleanTDate.includes(cleanRowDate)));

                     if (rowConcept === tConcept && isDateMatch) {
                         rowIndex = i;
                         console.warn(`[SYNC GATEKEEPER] Duplicado interceptado. Tarea '${tConcept}' asignada a fila existente ${rowIndex+1} ignorando Folio.`);
                         break;
                     }
                 }
             }
          }
      }

      if (rowIndex > -1 && rowIndex < values.length) {
         Object.keys(task).forEach(key => {
            if (key.startsWith('_')) return;
            const cIdx = getColIdx(key);
            // Don't overwrite existing valid folio with a new different folio if we matched by concept
            if ((cIdx === folioIdx) && values[rowIndex][cIdx]) {
                 // Pero asegurarnos de que la tarea que el sistema devuelve mantenga el folio válido de la base de datos
                 task['FOLIO'] = values[rowIndex][cIdx];
                 task['ID'] = values[rowIndex][cIdx];
                 return;
            } else if ((cIdx === folioIdx) && !values[rowIndex][cIdx] && task[key]) {
                 // Si la tabla no tenía folio pero la tarea sí, lo respetamos y NO lo generamos
                 values[rowIndex][cIdx] = task[key];
                 return;
            }
            if (cIdx > -1) values[rowIndex][cIdx] = task[key];
        });

        // AUTO-GENERATE FOLIO FOR EXISTING ROWS IF MISSING
        let hasTaskFolio = false;
        Object.keys(task).forEach(k => {
            if ((k.toUpperCase().trim() === 'FOLIO' || k.toUpperCase().trim() === 'ID') && task[k]) {
                hasTaskFolio = true;
            }
        });

        if (folioIdx > -1 && !values[rowIndex][folioIdx]) {
             let prefix = sheetName.toUpperCase() === "ANTONIA_VENTAS" || sheetName.toUpperCase().includes("(VENTAS)") ? "AV-" : generatePrefix(sheetName);
             let seqKey = sheetName.toUpperCase() === "ANTONIA_VENTAS" || sheetName.toUpperCase().includes("(VENTAS)") ? 'ANTONIA_SEQ_V2' : prefix;
             const seqNum = generateNumericSequence(seqKey);
             values[rowIndex][folioIdx] = prefix + seqNum;
             task['FOLIO'] = values[rowIndex][folioIdx];
             task['ID'] = values[rowIndex][folioIdx];
        } else if (folioIdx > -1 && values[rowIndex][folioIdx] && !hasTaskFolio) {
             task['FOLIO'] = values[rowIndex][folioIdx];
             task['ID'] = values[rowIndex][folioIdx];
        }

        singleRowIndex = rowIndex;
        modified = true;
      }
      else {
          // BATCH DEDUP: Check if already appending this ID in current batch
          let appendedRowIndex = -1;
          let tFolioStr = "";
          Object.keys(task).forEach(k => {
              if (k.toUpperCase().trim() === 'FOLIO' || k.toUpperCase().trim() === 'ID') {
                  if (task[k]) tFolioStr = String(task[k]).toUpperCase().trim();
              }
          });
          const tConceptStr = String(task['CONCEPTO'] || task['DESCRIPCION'] || task['TAREA'] || "").trim().toUpperCase().substring(0, 50);

          for(let k=0; k<rowsToAppend.length; k++) {
              const pendingRow = rowsToAppend[k];
              const pendingFolio = folioIdx > -1 ? String(pendingRow[folioIdx]).toUpperCase().trim() : "";

              if (folioIdx > -1 && tFolioStr && pendingFolio === tFolioStr) {
                  appendedRowIndex = k;
                  break;
              }

              // Secondary batch check by concept AND date AND tempId
              if (tConceptStr) {
                  const cIdx = getColIdx('CONCEPTO') > -1 ? getColIdx('CONCEPTO') : getColIdx('DESCRIPCION');
                  const dIdx = getColIdx('FECHA') > -1 ? getColIdx('FECHA') : getColIdx('F. INICIO');

                  if (cIdx > -1) {
                      const pendingConcept = String(pendingRow[cIdx]).trim().toUpperCase().substring(0, 50);

                      let pendingDateStr = "";
                      if (dIdx > -1) {
                          const pDateRaw = pendingRow[dIdx];
                          if (pDateRaw instanceof Date) pendingDateStr = Utilities.formatDate(pDateRaw, SpreadsheetApp.getActiveSpreadsheet().getSpreadsheetTimeZone(), "dd/MM/yy");
                          else pendingDateStr = String(pDateRaw || "").trim();
                      }

                      const tDateStr = String(task['FECHA'] || task['F. INICIO'] || "").trim();
                      const cleanTDate = tDateStr.replace(/-/g, '/').replace(/20(\d{2})/, '$1');
                      const cleanRowDate = pendingDateStr.replace(/-/g, '/').replace(/20(\d{2})/, '$1');

                      const isDateMatch = (cleanTDate === "" && cleanRowDate === "") ||
                                          ((cleanTDate !== "" && cleanRowDate !== "") && (cleanRowDate.includes(cleanTDate) || cleanTDate.includes(cleanRowDate)));

                      if (pendingConcept === tConceptStr && isDateMatch) {
                          appendedRowIndex = k;
                          break;
                      }
                  }
              }
          }

          if (appendedRowIndex > -1) {
              // Update the pending row instead of creating duplicate
              const targetRow = rowsToAppend[appendedRowIndex];
              Object.keys(task).forEach(key => {
                  if (key.startsWith('_')) return;
                  const cIdx = getColIdx(key);
                  if (cIdx > -1) targetRow[cIdx] = task[key];
              });
          } else {
              const newRow = new Array(totalColumns).fill("");
              Object.keys(task).forEach(key => {
                  if (key.startsWith('_')) return;
                  const cIdx = getColIdx(key);
                  if (cIdx > -1) newRow[cIdx] = task[key];
              });

              let existingTaskFolio = null;
              Object.keys(task).forEach(k => {
                  if ((k.toUpperCase().trim() === 'FOLIO' || k.toUpperCase().trim() === 'ID') && task[k]) {
                      existingTaskFolio = task[k];
                  }
              });

              if (folioIdx > -1 && !newRow[folioIdx] && existingTaskFolio) {
                  newRow[folioIdx] = existingTaskFolio;
              } else if (folioIdx > -1 && !newRow[folioIdx] && !existingTaskFolio) {
                 let prefix = sheetName.toUpperCase() === "ANTONIA_VENTAS" || sheetName.toUpperCase().includes("(VENTAS)") ? "AV-" : generatePrefix(sheetName);
                 let seqKey = sheetName.toUpperCase() === "ANTONIA_VENTAS" || sheetName.toUpperCase().includes("(VENTAS)") ? 'ANTONIA_SEQ_V2' : prefix;
                 const seqNum = generateNumericSequence(seqKey);
                 newRow[folioIdx] = prefix + seqNum;
                 task['FOLIO'] = newRow[folioIdx];
                 task['ID'] = newRow[folioIdx];
              }
              const statusIdx = getColIdx('ESTATUS');
              if(statusIdx > -1 && !newRow[statusIdx]) newRow[statusIdx] = 'ASIGNADO';
              rowsToAppend.push(newRow);
          }
      }
    });
    // 3. AUTO-ARCHIVADO
    let rowsMoved = false;
    const avanceIdx = getColIdx('AVANCE');
    const cumplimientoIdx = getColIdx('CUMPLIMIENTO');
    const estatusIdx = getColIdx('ESTATUS');
    const fechaTerminoIdx = getColIdx('FECHA_TERMINO');

    if (avanceIdx > -1 || cumplimientoIdx > -1 || estatusIdx > -1) {
        let separatorIndex = -1;
        for(let i=0; i<values.length; i++) {
            if(String(values[i][0]).toUpperCase().includes("TAREAS REALIZADAS") ||
               String(values[i].join("|")).toUpperCase().includes("TAREAS REALIZADAS")) {
                separatorIndex = i;
                break;
            }
        }

        let headerAndTop = values.slice(0, headerRowIndex + 1);
        let activeRows = [];
        let separatorRow = [];
        let historyRows = [];
        if (separatorIndex === -1) {
            activeRows = values.slice(headerRowIndex + 1);
        } else {
            activeRows = values.slice(headerRowIndex + 1, separatorIndex);
            separatorRow = [values[separatorIndex]];
            historyRows = values.slice(separatorIndex + 1);
        }

        const newActiveRows = [];
        const movedRows = [];

        activeRows.forEach(row => {
            let isComplete = false;

            const valEstatus = estatusIdx > -1 ? String(row[estatusIdx] || "").toUpperCase().trim() : "";
            const doneStatuses = ['HECHO', 'TERMINADO', 'FINALIZADO', 'REALIZADO', 'COMPLETADO', 'DONE'];
            if (doneStatuses.includes(valEstatus)) {
                isComplete = true;
            }

            [avanceIdx, cumplimientoIdx].forEach(idx => {
                if (idx > -1) {
                    const rawVal = row[idx];
                    const valStr = String(rawVal || "").trim();
                    const strictMatch = valStr === "100" || valStr === "100%" || valStr.toUpperCase() === "SI";
                    if (strictMatch) {
                        isComplete = true;
                    } else if (valStr) {
                        const cleanVal = valStr.replace('%', '').replace(',', '.').trim();
                        const num = parseFloat(cleanVal);
                        if (!isNaN(num) && Math.abs(num - 100) < 0.01) {
                            isComplete = true;
                        } else if (typeof rawVal === 'number' && Math.abs(rawVal - 1) < 0.001) {
                            // Handles Google Sheets native 100% (1.0) percentage formatting
                            isComplete = true;
                        }
                    }
                }
            });

            if (isComplete) {
                // AUTO-TIMESTAMP: FECHA TERMINO REAL
                if (fechaTerminoIdx > -1) {
                   if (!row[fechaTerminoIdx]) {
                       row[fechaTerminoIdx] = Utilities.formatDate(new Date(), SS.getSpreadsheetTimeZone(), "dd/MM/yy");
                   }
                }
                movedRows.push(row);
                rowsMoved = true;
            } else {
                newActiveRows.push(row);
            }
        });
        if (rowsMoved || (rowsToAppend.length > 0 && separatorIndex === -1)) {
            if (separatorRow.length === 0) {
                const sep = new Array(totalColumns).fill("");
                const titleCol = totalColumns > 2 ? 2 : 0;
                sep[titleCol] = "TAREAS REALIZADAS";
                separatorRow = [sep];
            }
            values = [ ...headerAndTop, ...rowsToAppend, ...newActiveRows, ...separatorRow, ...movedRows, ...historyRows ];
            rowsToAppend = [];
            modified = true;
            singleRowIndex = -1;
        }
    }

    // 4. ESCRITURA BLINDADA
    if (modified) {
       const finalMaxCols = values.reduce((max, r) => Math.max(max, r.length), totalColumns);
       const normalizedValues = values.map(r => {
           if (r.length === finalMaxCols) return r;
           const diff = finalMaxCols - r.length;
           return r.concat(new Array(diff).fill(""));
       });
       if (tasksArray.length === 1 && singleRowIndex > -1 && !rowsMoved) {
          let singleRow = values[singleRowIndex];
          if(singleRow.length < finalMaxCols) {
               singleRow = singleRow.concat(new Array(finalMaxCols - singleRow.length).fill(""));
          }
          sheet.getRange(singleRowIndex + 1, 1, 1, finalMaxCols).setValues([singleRow]);
       } else {
          // REMOVE FILTER IF EXISTS TO AVOID "HEADER MUST HAVE VALUE" ERROR
          const existingFilter = sheet.getFilter();
          if (existingFilter) {
              try { existingFilter.remove(); } catch(e) {}
          }

          if(values.length < dataRange.getNumRows()) sheet.clearContents();
          if(headerRowIndex < normalizedValues.length) {
              for(let c=0; c<normalizedValues[headerRowIndex].length; c++){
                  if(!normalizedValues[headerRowIndex][c]) normalizedValues[headerRowIndex][c] = "COL_" + (c+1);
              }
          }
          sheet.getRange(1, 1, normalizedValues.length, finalMaxCols).setValues(normalizedValues);
       }
    }

    if (rowsToAppend.length > 0) {
        const finalMaxCols = values.length > 0 ? values[0].length : totalColumns;
        const normalizedAppend = rowsToAppend.map(r => {
             if (r.length >= finalMaxCols) return r;
             return r.concat(new Array(finalMaxCols - r.length).fill(""));
        });
        const insertPos = headerRowIndex + 2;
        sheet.insertRowsBefore(insertPos, rowsToAppend.length);
        sheet.getRange(insertPos, 1, normalizedAppend.length, finalMaxCols).setValues(normalizedAppend);

        // 5. AUTO-HEALING: FORMATO CONDICIONAL (SEMAFORO)
        // Se ejecuta solo al crear nuevas tareas para garantizar que el rango cubra la nueva fila superior.
        const excludedForFormatting = [APP_CONFIG.logSheetName, APP_CONFIG.draftSheetName, APP_CONFIG.salesSheetName, "DB_SITIOS", "DB_PROYECTOS", "DB_DIRECTORY"];
        if (!excludedForFormatting.includes(sheetName) && !sheetName.startsWith("DB_")) {
             try { applyTrafficLightToSheet(sheet); } catch(e) { console.warn("Auto-Format Error: " + e.toString()); }
        }
    }

    SpreadsheetApp.flush();
    return { success: true, moved: rowsMoved };
  } catch (e) {
    console.error(e);
    return { success: false, message: e.toString() };
  } finally {
    if (useOwnLock) lock.releaseLock();
  }
}
```

### 19.4 `internalUpdateTask` — actualización de una sola fila con reverse-sync individual (línea 2624, 381 líneas)

```js
function internalUpdateTask(personName, taskData, username) {
    try {
        // REGLA ESTRICTA: Redirigir siempre a ANTONIA PINEDA LOPEZ si alguien que no es ella manda a ANTONIA_VENTAS
        if (String(personName).toUpperCase().trim() === "ANTONIA_VENTAS" && String(username).toUpperCase().trim() !== "ANTONIA_VENTAS") {
            personName = "ANTONIA PINEDA LOPEZ";
        }
        // GUARD: PPCV3 Inmutabilidad (Solo modificable por Weekly Plan)
        if (String(personName).trim().toUpperCase() === String(APP_CONFIG.ppcSheetName).trim().toUpperCase()) {
            return { success: false, message: "Operación no permitida: PPCV3 es de solo lectura desde esta vista." };
        }

        const isAntonia = String(personName).toUpperCase() === "ANTONIA_VENTAS";

        // --- RESTRICTION BLOCK: limit editable fields for vendor users on sheets they don't own ---
        const restrictedUsers = ["ANGEL_SALINAS", "TERESA_GARZA", "EDUARDO_TERAN", "EDUARDO_MANZANARES", "RAMIRO_RODRIGUEZ", "SEBASTIAN_PADILLA"];
        const cleanUN = String(username).toUpperCase().trim();
        if (restrictedUsers.includes(cleanUN)) {
             // Allow full access when editing their own tracker sheet
             const ownSheetName = (USER_DB[cleanUN] && USER_DB[cleanUN].staffName) ? USER_DB[cleanUN].staffName.toUpperCase() : '';
             const editingOwnTracker = ownSheetName && String(personName).toUpperCase().trim() === ownSheetName;
             if (!editingOwnTracker) {
                 const allowed = ['ESTATUS', 'STATUS', 'MAP COT', 'PROCESO', 'FOLIO', 'ID', 'AVANCE', 'AVANCE %', 'REQUISITOR', 'INFO CLIENTE', 'F2', 'COTIZACION', 'COT', 'TIMELINE', 'LAYOUT', 'COMENTARIOS', '_rowIndex', 'CORREO', 'CARPETA', 'CORREOS', 'CARPETAS'];
                 const isAllowed = (k) => {
                     const kUp = k.toUpperCase();
                     if (k.startsWith('_')) return true;
                     return allowed.some(a => kUp.includes(a));
                 };
                 Object.keys(taskData).forEach(key => {
                     if (!isAllowed(key)) {
                         delete taskData[key];
                     }
                 });
             }
        }
        // --- END RESTRICTION BLOCK ---

        // 1. AUTO-INCREMENT FOLIO (Before Saving)
        let existingFolio = null;
        Object.keys(taskData).forEach(k => {
            const kUp = k.toUpperCase().trim();
            if ((kUp === 'FOLIO' || kUp === 'ID') && taskData[k]) {
                existingFolio = taskData[k];
            }
        });

        const isNewTask = !existingFolio;
        if (isNewTask) {
             // NEW TASK -> GENERATE ID for any user
             let prefixSource = username || personName;
            if (String(personName).toUpperCase().trim() === "ANTONIA PINEDA LOPEZ" && String(username).toUpperCase().trim() === "ANTONIA_VENTAS") {
                prefixSource = "ANTONIA PINEDA LOPEZ";
            }
            let prefix = isAntonia ? "AV-" : generatePrefix(prefixSource);
             let seqKey = isAntonia ? 'ANTONIA_SEQ_V2' : prefix;
             const seqNum = generateNumericSequence(seqKey);
             taskData['FOLIO'] = prefix + seqNum;
             existingFolio = taskData['FOLIO'];
        }

        if (isAntonia) {
             // Solo aplicar restricciones si NO es una tarea recién creada en la interfaz
             if (!isNewTask) {
                 // 2. EXISTING TASK -> APPLY RESTRICTIONS (User Request)
                 // "Una vez que guarde... los únicos datos que pueda modificar es FECHA VISITA, ESTATUS y AVANCE"

                 const allowedBase = ['FOLIO', 'ID', 'ESTATUS', 'MAP COT', 'PROCESO_LOG', 'PROCESO', 'STATUS', 'AVANCE', 'AVANCE %', '_rowIndex', 'VENDEDOR', 'RESPONSABLE', 'INVOLUCRADOS', 'ENCARGADO', 'CONCEPTO', 'DESCRIPCION', 'CLIENTE', 'COTIZACION', 'F2', 'LAYOUT', 'TIMELINE', 'AREA', 'CLASIFICACION', 'CLASI', 'DIAS', 'RELOJ', 'ESPECIALIDAD', 'ARCHIVO', 'ARCHIVOS', 'COMENTARIOS', 'PRIORIDAD', 'PRIORIDAD DE COTIZACION', 'PRIO. COT.', 'F. VISITA', 'F. INICIO', 'F. ENTREGA', 'FECHA VISITA', 'FECHA INICIO', 'DÍAS FINALIZ. COTIZ', 'DIAS FINALIZ. COTIZ', 'CORREO', 'CARPETA', 'INFO CLIENTE', 'CORREOS', 'CARPETAS', 'REQUISITOR'];

                 Object.keys(taskData).forEach(key => {
                     const kUp = key.toUpperCase();
                     if (key.startsWith('_')) return; // Preserve internal keys

                     const isBase = allowedBase.includes(kUp);
                     const isDate = kUp.includes('FECHA') || kUp.includes('ALTA'); // Allow Date fields

                     if (!isBase && !isDate) {
                         delete taskData[key];
                     }
                 });
             }
        }

        const originalTempId = taskData['_tempId'];
        const res = internalBatchUpdateTasks(personName, [taskData]);

        if (originalTempId) taskData['_tempId'] = originalTempId;

        if (res.success) {
             res.data = taskData;
             if (username) {
                 const action = (taskData['COMENTARIOS'] || taskData['comentarios'] || taskData['COMENTARIOS SEMANA EN CURSO']) ? "ACTUALIZAR/COMENTARIO" : "ACTUALIZAR";
                 registrarLog(username, action, `Update Task ID: ${taskData['ID']||taskData['FOLIO']} en ${personName}`);
             }
        }

        // --- SMART ARCHIVING TRIGGER (SINGLE EDIT) ---
        if ((isAntonia || String(personName).toUpperCase().includes("ANTONIA_VENTAS")) && res.success) {
            try {
                if (taskData['COTIZACION'] || taskData['ARCHIVO']) {
                    processQuoteRow(taskData);
                }
            } catch(e) { console.error("Single-Edit Archiving Error: " + e.toString()); }
        }
        // ---------------------------------------------

        if (isAntonia) {
             // Remove worker logic (Reverse Sync)
             if (taskData._removeWorker) {
                 const workerToRemove = taskData._removeWorker;
                 try {
                     let targetSheet = String(workerToRemove).replace(/\s*\(VENTAS\)/ig, "").trim();
                     const workerSheet = findSheetSmart(targetSheet);
                     if (workerSheet) {
                         const targetId = String(existingFolio || taskData['FOLIO'] || taskData['ID'] || "").toUpperCase().trim();
                         if (targetId && targetId !== "NULL") {
                             const data = workerSheet.getDataRange().getValues();
                             if (data.length > 0) {
                                 const sheetHeaders = data[0].map(h => String(h).toUpperCase().trim());
                                 const folioIdx = sheetHeaders.indexOf('FOLIO');
                                 const idIdx = sheetHeaders.indexOf('ID');
                                 for (let i = 1; i < data.length; i++) {
                                     let rowFolio = (folioIdx > -1 ? data[i][folioIdx] : "") || (idIdx > -1 ? data[i][idIdx] : "");
                                     if (String(rowFolio).toUpperCase().trim() === targetId) {
                                         workerSheet.deleteRow(i + 1);
                                         registrarLog("ANTONIA", "REMOVED_WORKER", `Eliminada tarea ${targetId} de ${targetSheet}`);
                                         break;
                                     }
                                 }
                             }
                         }
                     }
                 } catch(e) {
                     registrarLog("ANTONIA", "REMOVE_ERROR", e.toString());
                 }
                 // Avoid re-distributing to this worker during save
                 delete taskData._removeWorker;
                 delete taskData._assignStep;
             }

             const distData = JSON.parse(JSON.stringify(taskData));
             delete distData._rowIndex;
             delete distData['PROCESO_LOG'];
                          delete distData['PROCESO'];

             if (taskData._assignToWorker && taskData._assignStep) {
                 try {
                     const workers = Array.isArray(taskData._assignToWorker) ? taskData._assignToWorker : [taskData._assignToWorker];
                     for (let worker of workers) {
                         const cleanWorker = String(worker).replace(/\s*\(VENTAS\)/ig, "").trim();
                         const assignData = JSON.parse(JSON.stringify(distData));
                         assignData['ESTATUS'] = 'PENDIENTE';
                         assignData['AVANCE'] = '0%';
                         const tRes = internalBatchUpdateTasks(cleanWorker, [assignData]);
                         if (!tRes.success) registrarLog("ANTONIA", "DIST_FAIL", `Fallo envío a ${cleanWorker}: ${tRes.message}`);
                     }
                 } catch(e) {
                     registrarLog("ANTONIA", "DIST_ERROR", e.toString());
                 }
             }

             // MODIFICADO: Se comenta la distribución a vendedores para evitar duplicidad y tráfico innecesario.
             // "ya no mandará la misma tarea a la hoja de los vendedores"
             // UPDATE: Se reactiva la distribución por reporte de bug (No se reflejaban actividades).

             const vendedorKey = Object.keys(taskData).find(k => k.toUpperCase().trim() === "VENDEDOR" || k.toUpperCase().trim() === "RESPONSABLE" || k.toUpperCase().trim() === "INVOLUCRADOS");
             if (vendedorKey && taskData[vendedorKey]) {
                 const vendedores = String(taskData[vendedorKey]).split(',').map(s => s.trim());

                 vendedores.forEach(vName => {
                     if (vName.toUpperCase() !== "ANTONIA_VENTAS") {
                         try {
                            // TRAFFIC SPLITTING REFACTORIZADO
                            let targetSheet = vName;
                            if (targetSheet.toUpperCase() === "ANTONIA_VENTAS") {
                                targetSheet = "ANTONIA PINEDA LOPEZ";
                            }

                            if (username !== 'ANTONIA_VENTAS') {
                                // REGLA ESTRICTA: Nadie excepto ANTONIA_VENTAS puede enviar a hojas con (VENTAS)
                                targetSheet = targetSheet.replace(/\s*\(VENTAS\)/ig, "").trim();
                            }

                            let finalTarget = null;
                            let hasSuffix = targetSheet.toUpperCase().includes("(VENTAS)");

                            if (hasSuffix) {
                                finalTarget = targetSheet;
                            } else {
                                // Si NO es Antonia, NUNCA debemos agregar (VENTAS) como fallback.
                                if (username === 'ANTONIA_VENTAS') {
                                    let potentialSheet = targetSheet + " (VENTAS)";
                                    if (findSheetSmart(potentialSheet)) {
                                        finalTarget = potentialSheet;
                                    } else if (findSheetSmart(targetSheet)) {
                                        finalTarget = targetSheet;
                                    }
                                } else {
                                    if (findSheetSmart(targetSheet)) {
                                        finalTarget = targetSheet;
                                    }
                                }
                            }

                            if (finalTarget) {
                                 const vRes = internalBatchUpdateTasks(finalTarget, [distData]);
                                 if(!vRes.success) registrarLog("ANTONIA", "DIST_FAIL", "Fallo copia a " + finalTarget + ": " + vRes.message);
                            } else {
                                 registrarLog("ANTONIA", "DIST_SKIP", "Omitido " + vName + " - No se encontró tabla (VENTAS).");
                            }
                         } catch(e){
                            registrarLog("ANTONIA", "DIST_ERROR", e.toString());
                         }
                     }
                 });
             }

             try { internalBatchUpdateTasks("ADMINISTRADOR", [distData]); } catch(e){}
        } else {
             try {
                 const syncData = JSON.parse(JSON.stringify(taskData));
                 delete syncData._rowIndex;
                 delete syncData['PROCESO_LOG'];
                 delete syncData['PROCESO'];

                 const getTVal = (keys) => {
                     for (let k of keys) {
                         let found = Object.keys(syncData).find(key => key.toUpperCase().trim() === k);
                         if (found && syncData[found]) return syncData[found];
                     }
                     return "";
                 };

                 const estatus = String(getTVal(['ESTATUS', 'STATUS', 'ESTADO'])).toUpperCase().trim();
                 const avanceRaw = String(getTVal(['AVANCE', 'AVANCE %', '% AVANCE', '%', 'CUMPLIMIENTO'])).replace(/%/g, '').trim();
                 const avanceNum = parseFloat(avanceRaw);
                 const isDone = estatus === 'HECHO' || estatus === 'TERMINADO' || estatus === 'FINALIZADO' || estatus === 'REALIZADO' || estatus === 'COMPLETADO' || estatus === 'DONE' || avanceRaw === '100' || avanceNum === 100 || avanceRaw.toUpperCase() === 'SI';

                 const tFolio = String(getTVal(['FOLIO', 'ID'])).toUpperCase().trim();

                 if (tFolio) {
                     const antData = internalFetchSheetData("ANTONIA_VENTAS");
                     if (antData.success && antData.data) {
                         const targetRow = antData.data.find(r => String(r['FOLIO'] || r['ID'] || "").toUpperCase().trim() === tFolio);

                         if (targetRow) {
                             let log = [];
                             try {
                                 if (targetRow['PROCESO_LOG']) log = JSON.parse(targetRow['PROCESO_LOG']);
                             } catch(e) {}

                             let updated = false;
                             const updatedLog = log.map(entry => {
                                 let wNorm = String(personName).toUpperCase().trim().replace(/\s*\(VENTAS\)/g, "").replace(/_/g, " ");
                                 let eNorm = entry.assignee ? String(entry.assignee).toUpperCase().trim().replace(/\s*\(VENTAS\)/g, "").replace(/_/g, " ") : "";

                                 if (entry.status === 'IN_PROGRESS' && (eNorm === wNorm || eNorm.includes(wNorm) || wNorm.includes(eNorm) || eNorm === "" || wNorm === "") && isDone) {
                                     entry.status = 'DONE';
                                     entry.endTimestamp = new Date().getTime();
                                     entry.endDateStr = new Date().toLocaleString();
                                     // Se preserva entry.timestamp y entry.dateStr originales (Fecha de Inicio)
                                     updated = true;
                                     registrarLog("SYSTEM", "REVERSE_SYNC", `${personName} completed step ${entry.step} for FOLIO ${tFolio}`);
                                 }
                                 return entry;
                             });

                             if (updated) {
                                 const stepsOrder = ["L", "CD", "EP", "CI", "EV", "CEC", "RCC"];
                                 let oldParts = (targetRow["MAP COT"] || "").split(/\||>|\//).map(p => p.trim());
                                 let mapCotParts = stepsOrder.map(step => {
                                     // Valid entries: step is a known PROCESS_STEPS ID
                                     const stepEntries = updatedLog.filter(e => e.step === step || e.to === step);
                                     if (stepEntries.length > 0) {
                                         const allDone = stepEntries.every(e => e.status === 'DONE');
                                         if (allDone) return '🟢 ' + step;
                                         const anyInProgress = stepEntries.some(e => e.status === 'IN_PROGRESS');
                                         if (anyInProgress) return '🟡 ' + step;
                                         return '🔴 ' + step;
                                     }
                                     // Garbage entries: step field contains the old MAP COT string.
                                     // If it shows 🟡 STEP or 🔴 STEP, this entry was for that step.
                                     const garbageForStep = updatedLog.filter(e =>
                                         !stepsOrder.includes(e.step) &&
                                         (e.step.includes('🟡 ' + step) || e.step.includes('🔴 ' + step))
                                     );
                                     if (garbageForStep.length > 0) {
                                         const allDone = garbageForStep.every(e => e.status === 'DONE');
                                         if (allDone) return '🟢 ' + step;
                                         const anyInProgress = garbageForStep.some(e => e.status === 'IN_PROGRESS');
                                         if (anyInProgress) return '🟡 ' + step;
                                     }
                                     let oldPart = oldParts.find(p => p === '🟢 ' + step || p === '🟡 ' + step || p === '🔴 ' + step || p === '⚪ ' + step || p.includes(' ' + step));
                                     if (oldPart && oldPart.includes('🟢')) return '🟢 ' + step;
                                     if (oldPart && oldPart.includes('🟡')) return '🟡 ' + step;
                                     if (oldPart && oldPart.includes('🔴')) return '🔴 ' + step;
                                     return '⚪ ' + step;
                                 });

                                 let syncToAntonia = {
                                     'FOLIO': targetRow['FOLIO'] || tFolio,
                                     'PROCESO_LOG': JSON.stringify(updatedLog),
                                     'MAP COT': mapCotParts.join(' | ')
                                 };

                                 const fileCols = ['ARCHIVO', 'F2', 'LAYOUT', 'COTIZACION', 'EVIDENCIA'];
                                 fileCols.forEach(col => {
                                     let wKey = Object.keys(taskData).find(k => k.toUpperCase().trim() === col);
                                     if (wKey && taskData[wKey] && String(taskData[wKey]).trim() !== "") {
                                         syncToAntonia[wKey] = taskData[wKey];
                                     }
                                 });

                                 internalBatchUpdateTasks("ANTONIA_VENTAS", [syncToAntonia]);
                             }

                             // Sincronización general a Antonia independientemente del estado
                             let safeSyncData = Object.assign({}, syncData);
                             const delKeys = ['ESTATUS', 'STATUS', 'ESTADO', 'AVANCE', 'AVANCE %', '% AVANCE', '%', 'CUMPLIMIENTO'];
                             Object.keys(safeSyncData).forEach(k => {
                                 if (delKeys.includes(k.toUpperCase().trim())) delete safeSyncData[k];
                             });
                             if (typeof syncToAntonia !== 'undefined' && syncToAntonia['MAP COT']) {
                                 safeSyncData['MAP COT'] = syncToAntonia['MAP COT'];
                                 safeSyncData['PROCESO_LOG'] = syncToAntonia['PROCESO_LOG'];
                             }

                             if (String(personName).toUpperCase().includes("(VENTAS)")) {
                                 internalBatchUpdateTasks("ANTONIA_VENTAS", [safeSyncData]);
                             } else {
                                 const reverseFolio = safeSyncData['FOLIO'] || safeSyncData['ID'];
                                 if (reverseFolio && String(reverseFolio).toUpperCase().startsWith("AV-")) {
                                     internalBatchUpdateTasks("ANTONIA_VENTAS", [safeSyncData]);
                                 }
                             }
                         }
                     }
                 }

                 // Sincronización Lateral (Peer-to-Peer via VENDEDOR field)
                 const vKey = Object.keys(taskData).find(k => k.toUpperCase().trim() === "VENDEDOR" || k.toUpperCase().trim() === "RESPONSABLE" || k.toUpperCase().trim() === "INVOLUCRADOS");
                 if (vKey && taskData[vKey]) {
                     const vList = String(taskData[vKey]).split(',').map(s => s.trim());
                     vList.forEach(otherVendor => {
                         // Ignorar si es el mismo usuario que está editando
                         // "personName" es la hoja actual (e.g. "JUAN (VENTAS)")
                         if (otherVendor.toUpperCase() === "ANTONIA_VENTAS") return;

                         // Normalizar nombres para comparación
                         const currentSheetNorm = String(personName).toUpperCase().replace(/\s*\(VENTAS\)/, "").trim();
                         const otherVendorNorm = String(otherVendor).toUpperCase().replace(/\s*\(VENTAS\)/, "").trim();

                         if (currentSheetNorm !== otherVendorNorm) {
                             // Distribuir a este otro vendedor
                             let targetSheet = otherVendor;
                             if (targetSheet.toUpperCase() === "ANTONIA_VENTAS") {
                                 targetSheet = "ANTONIA PINEDA LOPEZ";
                             }
                             // MODIFICADO: No agregar el sufijo "(VENTAS)" automáticamente si no es Antonia.
                             // El usuario debe asignarse a su tabla base o a la tabla especificada.
                             let finalSheet = null;
                             if (findSheetSmart(targetSheet)) {
                                 finalSheet = targetSheet;
                             } else {
                                 // Fallback opcional: solo si de verdad quiso asignar a "(VENTAS)" y lo escribió mal, pero no por defecto
                                 finalSheet = targetSheet;
                             }

                             internalBatchUpdateTasks(finalSheet, [syncData]);
                         }
                     });
                 }

             } catch (e) {
                 console.error("Error en sincronización inversa: " + e.toString());
             }
        }
        // RETURN UPDATED DATA (Critical for Frontend Folio Update)
        res.data = taskData;
        return res;
    } catch(e) { return {success:false, message:e.toString()}; }
}
```

### 19.5 Generadores de folio: `generatePrefix`, `generateNumericSequence`, `generateWorkOrderFolio`, `apiCreateStandardStructure`

```js
function apiCreateStandardStructure(siteId, user) {
    STANDARD_PROJECT_STRUCTURE.forEach(name => {
        // Determinamos el tipo para que el Front sepa cómo dibujarlo
        let tipo = "GENERAL";
        if (name.includes("PPC")) tipo = "PPC_MASTER";

        apiSaveSubProject({
            parentId: siteId,
            name: name,
            type: tipo,
            createdBy: user || "SISTEMA"
        });
    });
}

/**
 * GENERADOR DE PREFIJOS DE FOLIO BASADO EN NOMBRE
 */
function generatePrefix(name) {
    if (!name) return 'PPC-';

    const upperName = String(name).toUpperCase().trim();

    if (upperName === 'JESUS_CANTU' || upperName === 'JESUS CANTU') return 'JC-';
    if (upperName === 'LUIS_CARLOS' || upperName === 'LUIS CARLOS' || upperName === 'ADMINISTRADOR') return 'LC-';
    if (upperName === 'JAIME_OLIVO' || upperName === 'JAIME OLIVO') return 'JO-';
    if (upperName === 'ANTONIA_VENTAS' || upperName === 'ANTONIA VENTAS') return 'AV-';
    if (upperName === 'RAMIRO_RODRIGUEZ' || upperName === 'RAMIRO RODRIGUEZ') return 'RR-';
    if (upperName === 'SEBASTIAN_PADILLA' || upperName === 'SEBASTIAN PADILLA') return 'SP-';
    if (upperName === 'TERESA_GARZA' || upperName === 'TERESA GARZA') return 'TG-';

    const parts = upperName.split(/[\s_]+/).filter(p => p.length > 0);
    if (parts.length >= 2) {
        return (parts[0].charAt(0) + parts[1].charAt(0)) + '-';
    } else if (parts.length === 1) {
        return parts[0].substring(0, 2) + '-';
    }

    return 'PPC-';
}

/**
 * GENERADOR DE FOLIO NUMÉRICO SECUENCIAL (NUEVO)
 */
function generateNumericSequence(key) {
  const lock = LockService.getScriptLock();
  try {
    if (lock.tryLock(5000)) {
       const props = PropertiesService.getScriptProperties();
       const seqKey = "SEQ_" + key;
       let val = Number(props.getProperty(seqKey) || 0);
       // Check if the value got corrupted
       if (isNaN(val) || val > 10000000) {
           val = 0;
       }
       val++;
       props.setProperty(seqKey, String(val));
       return String(val).padStart(4, '0');
    }
  } catch(e) { console.error(e); } finally { lock.releaseLock(); }
  // Fallback to a random 4-digit number to avoid long timestamps
  return String(Math.floor(1000 + Math.random() * 9000));
}

function generateWorkOrderFolio(clientName, deptName) {
  try {
      const props = PropertiesService.getScriptProperties();
      // Incrementar secuencia
      let seq = Number(props.getProperty('WORKORDER_SEQ') || 0) + 1;
      props.setProperty('WORKORDER_SEQ', String(seq));

      const seqStr = String(seq).padStart(4, '0');

      // Abreviatura Cliente: Iniciales de las primeras 2 palabras o primeras 2 letras
      const cleanClient = (clientName || "XX").toUpperCase().replace(/[^A-Z0-9]/g, ' ').trim();
      const words = cleanClient.split(/\s+/).filter(w => w.length > 0);
      let clientStr = "XX";
      if (words.length >= 2) {
          clientStr = words[0][0] + words[1][0];
      } else if (words.length === 1) {
          clientStr = words[0].substring(0, 2);
      }

      // Simplificar departamento
      const rawDept = (deptName || "General").trim().toUpperCase();
      const ABBR_MAP = {
          "ELECTROMECANICA": "Electro",
          "ELECTROMECÁNICA": "Electro",
          "CONSTRUCCION": "Const",
          "CONSTRUCCIÓN": "Const",
          "MANTENIMIENTO": "Mtto",
          "REMODELACION": "Remod",
          "REMODELACIÓN": "Remod",
          "REPARACION": "Repar",
          "REPARACIÓN": "Repar",
          "RECONFIGURACION": "Reconf",
          "RECONFIGURACIÓN": "Reconf",
          "POLIZA": "Poliza",
          "PÓLIZA": "Poliza",
          "INSPECCION": "Insp",
          "INSPECCIÓN": "Insp",
          "ADMINISTRACION": "Admin",
          "ADMINISTRACIÓN": "Admin",
          "MAQUINARIA": "Maq",
          "DISEÑO": "Diseño",
          "COMPRAS": "Compras",
          "VENTAS": "Ventas",
          "HVAC": "HVAC",
          "FINANZAS": "Finanzas",
          "FACTURACION": "Factura",
          "FACTURACIÓN": "Factura",
          "SEGURIDAD": "EHS",
          "EHS": "EHS"
      };

      let deptStr = ABBR_MAP[rawDept];

      // Si no está en el mapa, intentar capitalizar primera letra y resto minúsculas
      if (!deptStr) {
          if (rawDept.length > 6) {
              deptStr = rawDept.substring(0, 1) + rawDept.substring(1, 5).toLowerCase();
          } else {
              deptStr = rawDept.substring(0, 1) + rawDept.substring(1).toLowerCase();
          }
      }

      const date = new Date();
      const d = String(date.getDate()).padStart(2, '0');
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const y = String(date.getFullYear()).slice(-2);
      const dateStr = `${d}${m}${y}`;

      return `${seqStr}${clientStr} ${deptStr} ${dateStr}`;
  } catch(e) {
      console.error(e);
      return "WO-" + new Date().getTime();
  }
}
```

### 19.6 `apiSavePPCData` — guardado del módulo de checklist PPC (línea 3124, 313 líneas)

```js
function apiSavePPCData(payload, activeUser) {
  const lock = LockService.getScriptLock();
  // Esperar hasta 30 segundos para obtener el candado y evitar condiciones de carrera
  if (lock.tryLock(30000)) {
    try {
      const items = Array.isArray(payload) ? payload : [payload];

      // 1. VERIFICACIÓN CRÍTICA DE PPCV3
      let sheetPPC = findSheetSmart(APP_CONFIG.ppcSheetName);
      if (!sheetPPC) {
        sheetPPC = SS.insertSheet(APP_CONFIG.ppcSheetName);
        // Standardize headers for robustness
        sheetPPC.appendRow(["ID", "ESPECIALIDAD", "DESCRIPCION", "RESPONSABLE", "FECHA", "RELOJ", "CUMPLIMIENTO", "ARCHIVO", "COMENTARIOS", "COMENTARIOS PREVIOS", "ESTATUS", "AVANCE", "CLASIFICACION", "PRIORIDAD", "RIESGOS", "FECHA_RESPUESTA", "DETALLES_EXTRA"]);
      }

      // 1.0.1 AUTO-MIGRACIÓN PARA JESUS_CANTU (Añadir columnas faltantes)
      if (activeUser === 'JESUS_CANTU') {
          const newCols = [
              "RUTA_CRITICA", "ZONA", "CUANT_REQUERIDO", "CUANT_REAL", "CONTRATISTA",
              "DIAS_L", "DIAS_M", "DIAS_X", "DIAS_J", "DIAS_V", "DIAS_S", "DIAS_D"
          ];
          const currentHeaders = sheetPPC.getRange(1, 1, 1, sheetPPC.getLastColumn()).getValues()[0].map(h => String(h).toUpperCase().trim());
          const missing = newCols.filter(c => !currentHeaders.includes(c));

          if (missing.length > 0) {
              const startCol = sheetPPC.getLastColumn() + 1;
              sheetPPC.getRange(1, startCol, 1, missing.length).setValues([missing])
                      .setFontWeight("bold")
                      .setBackground("#e6e6e6");
          }
      }

      // 1.1 VERIFICACIÓN CRÍTICA DE PPCV4 (Para ANTONIA_VENTAS)
      if (String(activeUser).toUpperCase().trim() === 'ANTONIA_VENTAS') {
          let sheetPPC4 = findSheetSmart('PPCV4');
          if (!sheetPPC4) {
             sheetPPC4 = SS.insertSheet('PPCV4');
             sheetPPC4.appendRow(["ID", "ESPECIALIDAD", "DESCRIPCION", "RESPONSABLE", "FECHA", "RELOJ", "CUMPLIMIENTO", "ARCHIVO", "COMENTARIOS", "COMENTARIOS PREVIOS", "ESTATUS", "AVANCE", "CLASIFICACION", "PRIORIDAD", "RIESGOS", "FECHA_RESPUESTA", "DETALLES_EXTRA"]);
          }
      }

      const fechaHoy = new Date();
      const fechaStr = Utilities.formatDate(fechaHoy, SS.getSpreadsheetTimeZone(), "dd/MM/yy");
      const horaStr = Utilities.formatDate(fechaHoy, SS.getSpreadsheetTimeZone(), "HH:mm");

      // Estructuras para Batch Operations
      const tasksBySheet = {};
      const logEntries = [];
      const generatedIds = [];

      const addTaskToSheet = (sheetName, task) => {
          if (!sheetName) return;
          const key = sheetName.trim();
          if (!tasksBySheet[key]) tasksBySheet[key] = [];
          tasksBySheet[key].push(task);
      };

      // 2. PREPARACIÓN DE DATOS EN MEMORIA
      items.forEach(item => {
          // Use existing ID if provided (for updates/tests) or generate new
          let id = item.id;
          if (!id) {
              if (activeUser === 'PREWORK_ORDER') {
                  id = generateWorkOrderFolio(item.cliente, item.especialidad);
              } else {
                  let prefix = generatePrefix(activeUser);
                  id = prefix + generateNumericSequence(prefix);
              }
          }
          generatedIds.push(id);
          const comentarios = item.comentarios || "";

          // --- NUEVO: GUARDADO DE DETALLES EN HOJAS HIJAS ---
          // A. Materiales
          if (item.materiales && item.materiales.length > 0) {
             const matItems = item.materiales.map(m => ({
                 FOLIO: id, ...m,
                 RESIDENTE: m.papaCaliente ? m.papaCaliente.residente : "",
                 COMPRAS: m.papaCaliente ? m.papaCaliente.compras : "",
                 CONTROLLER: m.papaCaliente ? m.papaCaliente.controller : "",
                 ORDEN_COMPRA: m.papaCaliente ? m.papaCaliente.ordenCompra : "",
                 PAGOS: m.papaCaliente ? m.papaCaliente.pagos : "",
                 ALMACEN: m.papaCaliente ? m.papaCaliente.almacen : "",
                 LOGISTICA: m.papaCaliente ? m.papaCaliente.logistica : "",
                 RESIDENTE_OBRA: m.papaCaliente ? m.papaCaliente.residenteObra : ""
             }));
             saveChildData(APP_CONFIG.woMaterialsSheet, matItems, ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "COSTO", "ESPECIFICACION", "TOTAL", "RESIDENTE", "COMPRAS", "CONTROLLER", "ORDEN_COMPRA", "PAGOS", "ALMACEN", "LOGISTICA", "RESIDENTE_OBRA"]);
          }

          // B. Mano de Obra
          if (item.manoObra && item.manoObra.length > 0) {
             const laborItems = item.manoObra.map(l => ({ FOLIO: id, ...l }));
             saveChildData(APP_CONFIG.woLaborSheet, laborItems, ["FOLIO", "CATEGORIA", "SALARIO", "PERSONAL", "SEMANAS", "EXTRAS", "NOCTURNO", "FIN_SEMANA", "OTROS", "TOTAL"]);
          }

          // C. Herramientas
          if (item.herramientas && item.herramientas.length > 0) {
             const toolItems = item.herramientas.map(t => ({
                 FOLIO: id, ...t,
                 RESIDENTE: t.papaCaliente ? t.papaCaliente.residente : "",
                 CONTROLLER: t.papaCaliente ? t.papaCaliente.controller : "",
                 ALMACEN: t.papaCaliente ? t.papaCaliente.almacen : "",
                 LOGISTICA: t.papaCaliente ? t.papaCaliente.logistica : "",
                 RESIDENTE_FIN: t.papaCaliente ? t.papaCaliente.residenteFin : ""
             }));
             saveChildData(APP_CONFIG.woToolsSheet, toolItems, ["FOLIO", "CANTIDAD", "UNIDAD", "DESCRIPCION", "COSTO", "TOTAL", "RESIDENTE", "CONTROLLER", "ALMACEN", "LOGISTICA", "RESIDENTE_FIN"]);
          }

          // D. Equipos
          if (item.equipos && item.equipos.length > 0) {
             const eqItems = item.equipos.map(e => ({ FOLIO: id, ...e }));
             saveChildData(APP_CONFIG.woEquipSheet, eqItems, ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "ESPECIFICACION", "DIAS", "HORAS", "COSTO", "TOTAL"]);
          }

          // E. Programa
          if (item.programa && item.programa.length > 0) {
             const progItems = item.programa.map(p => ({
                 FOLIO: id,
                 ...p,
                 SECCION: p.seccion || "",
                 ESTATUS: p.checkStatus || (p.isActive ? 'APPLY' : 'PENDING')
             }));
             saveChildData(APP_CONFIG.woProgramSheet, progItems, ["FOLIO", "DESCRIPCION", "FECHA", "DURACION", "UNIDAD_DURACION", "UNIDAD", "CANTIDAD", "PRECIO", "TOTAL", "RESPONSABLE", "SECCION", "ESTATUS"]);
          }

          // F. Detalles Extra (Checklist, Costos Adicionales) - JSON
          let detallesExtra = "";
          if (item.checkList || item.additionalCosts) {
              detallesExtra = JSON.stringify({
                  checkList: item.checkList,
                  costs: item.additionalCosts
              });
          }

          // Mapeo Explícito para PPCV3
          const taskData = {
                 'FOLIO': id,
                 'CONCEPTO': item.concepto || item.CONCEPTO,
                 'CLASIFICACION': item.clasificacion || item.CLASIFICACION || "",
                 'AREA': item.especialidad || item.ESPECIALIDAD,
                 'INVOLUCRADOS': item.responsable || item.RESPONSABLE,
                 'FECHA': fechaStr,
                 'HORA': horaStr,
                 'RELOJ': (item.horas !== undefined && item.horas !== "") ? item.horas : ((item.RELOJ !== undefined && item.RELOJ !== "") ? item.RELOJ : 0),
                 'ESTATUS': "ASIGNADO",
                 'PRIORIDAD': item.prioridad || item.prioridades || item.PRIORIDAD,
                 'RESTRICCIONES': item.restricciones,
                 'RIESGOS': item.riesgos || item.RIESGOS,
                 'FECHA_RESPUESTA': item.fechaRespuesta,
                 'AVANCE': "0%",
                 'COMENTARIOS': comentarios,
                 'ARCHIVO': item.archivoUrl,
                 'CUMPLIMIENTO': item.cumplimiento || item.CUMPLIMIENTO,
                 'COMENTARIOS PREVIOS': item.comentariosPrevios || "",
                 'REQUISITOR': item.requisitor,
                 'CONTACTO': item.contacto,
                 'CELULAR': item.celular,
                 'FECHA_COTIZACION': item.fechaCotizacion,
                 'CLIENTE': item.cliente,
                 'TRABAJO': item.TRABAJO,
                 'DETALLES_EXTRA': detallesExtra, // Nueva Columna
                 // CAMPOS ESPECIFICOS JESUS_CANTU (Mapping Uppercase from Front)
                 'RUTA_CRITICA': item.rutaCritica || item.RUTA_CRITICA,
                 'ZONA': item.zona || item.ZONA,
                 'CONTRATISTA': item.contratista || item.CONTRATISTA,
                 'CUANT_REQUERIDO': item.cuantReq || item.CUANT_REQUERIDO,
                 'CUANT_REAL': item.cuantReal || item.CUANT_REAL,
                 'DIAS_L': item.dias ? (item.dias.l ? "x" : "") : (item.DIAS_L || ""),
                 'DIAS_M': item.dias ? (item.dias.m ? "x" : "") : (item.DIAS_M || ""),
                 'DIAS_X': item.dias ? (item.dias.x ? "x" : "") : (item.DIAS_X || ""),
                 'DIAS_J': item.dias ? (item.dias.j ? "x" : "") : (item.DIAS_J || ""),
                 'DIAS_V': item.dias ? (item.dias.v ? "x" : "") : (item.DIAS_V || ""),
                 'DIAS_S': item.dias ? (item.dias.s ? "x" : "") : (item.DIAS_S || ""),
                 'DIAS_D': item.dias ? (item.dias.d ? "x" : "") : (item.DIAS_D || "")
          };

          // A. Persistencia en PPC Maestro (PPCV3)
          addTaskToSheet(APP_CONFIG.ppcSheetName, taskData);

          // A.1. Persistencia Condicional en PPCV4 (Solo ANTONIA_VENTAS)
          if (String(activeUser).toUpperCase().trim() === 'ANTONIA_VENTAS') {
              // Create specific task object for PPCV4 to match headers exactly if aliases fail
              const taskPPC4 = { ...taskData };
              // Ensure critical fields map to Screenshot Headers
              if (taskData['FECHA']) taskPPC4['Fecha de Alta'] = taskData['FECHA'];
              if (taskData['CONCEPTO']) taskPPC4['Descripción de la Actividad'] = taskData['CONCEPTO'];
              if (taskData['ARCHIVO']) taskPPC4['Archivos'] = taskData['ARCHIVO'];
              if (taskData['COMENTARIOS']) taskPPC4['Comentarios Semana en Curso'] = taskData['COMENTARIOS'];
              if (taskData['INVOLUCRADOS']) taskPPC4['RESPONSABLE'] = taskData['INVOLUCRADOS'];

              addTaskToSheet('PPCV4', taskPPC4);
          }

          // B. Respaldo Obligatorio en ADMINISTRADOR (Control)
          addTaskToSheet("ADMINISTRADOR", taskData);

          // C. Distribución al Staff (Tracker Personal)
          const responsables = String(item.responsable || item.RESPONSABLE || "").split(",").map(s => s.trim()).filter(s => s);

          responsables.forEach(personName => {
              // MODIFICADO: Solo Antonia Ventas envía al PPC hacia "(VENTAS)".
              // El resto del equipo manda al Tracker (hoja sin sufijo VENTAS).
              // Ya no ignoramos el nombre, sino que validamos la hoja.
              let targetSheet = personName;
              if (targetSheet.toUpperCase() === "ANTONIA_VENTAS") {
                  targetSheet = "ANTONIA PINEDA LOPEZ";
              }
              if (activeUser !== 'ANTONIA_VENTAS') {
                  // REGLA ESTRICTA: Nadie excepto ANTONIA_VENTAS puede enviar a hojas con (VENTAS)
                  targetSheet = targetSheet.replace(/\s*\(VENTAS\)/ig, "").trim();
              }

              // LOGICA ESPECIAL JESUS_CANTU: Filtrar columnas para evitar rotura en Tracker
              if (activeUser === 'JESUS_CANTU') {
                  const staffData = {
                      'FOLIO': taskData.FOLIO,
                      'CONCEPTO': taskData.CONCEPTO,
                      'AREA': taskData.AREA,
                      'RESPONSABLE': taskData.INVOLUCRADOS,
                      'FECHA': taskData.FECHA,
                      'ESTATUS': taskData.ESTATUS,
                      'AVANCE': taskData.AVANCE,
                      'CLASIFICACION': taskData.CLASIFICACION,
                      'PRIORIDAD': taskData.PRIORIDAD
                      // Se omiten RUTA_CRITICA, ZONA, DIAS_X, etc.
                  };
                  addTaskToSheet(targetSheet, staffData);
              } else {
                  addTaskToSheet(targetSheet, taskData);
              }

            // INTEGRACIÓN OUTLOOK: Enviar evento al responsable asignado desde el formulario PPC
            const emailRes = findUserEmailByLabel(personName);
            if (emailRes) {
                const fIni = new Date();
                const fFi = new Date(fIni.getTime() + (2 * 60 * 60 * 1000));

                const conceptoPPC = taskData.CONCEPTO || "Nueva Tarea PPC";
                const cl = item.cliente || taskData.CLIENTE || "Holtmont";

                const payloadOutlookPPC = {
                    folio: id,
                    titulo: `Asignación PPC: ${conceptoPPC} - ${cl}`,
                    descripcion: `Se te ha asignado una tarea desde el módulo PPC. Concepto: ${conceptoPPC}.`,
                    fechaInicio: fIni.toISOString(),
                    fechaFin: fFi.toISOString(),
                    correoDestino: emailRes,
                    asignadoPor: activeUser || "SISTEMA"
                };

                // Disparamos la notificación sin bloquear el flujo principal
                try {
                    NotifierService.sendToOutlook(payloadOutlookPPC);
                } catch(e) {
                    console.error("Error enviando Outlook desde PPC:", e);
                }
            }
          });

          // D. Preparar Log (En Memoria)
          logEntries.push([new Date(), activeUser || "DESCONOCIDO", "GUARDADO_PPC", `ID: ${id} | Comentarios: ${comentarios}`]);
      });

      // 3. EJECUCIÓN DE ESCRITURA (BATCH)

      // A. Guardado Crítico (PPCV3)
      // Usamos useOwnLock = false porque ya tenemos el lock aquí.
      if (tasksBySheet[APP_CONFIG.ppcSheetName]) {
          const ppcResult = internalBatchUpdateTasks(APP_CONFIG.ppcSheetName, tasksBySheet[APP_CONFIG.ppcSheetName], false);
          if (!ppcResult.success) {
              throw new Error("CRITICAL: Falló guardado en PPCV3. " + ppcResult.message);
          }
          delete tasksBySheet[APP_CONFIG.ppcSheetName];
      }

      // B. Distribución Secundaria (Staff / Admin)
      for (const [targetSheet, tasks] of Object.entries(tasksBySheet)) {
          try {
            const res = internalBatchUpdateTasks(targetSheet, tasks, false);
            if (!res.success) console.warn(`Fallo secundario en ${targetSheet}: ${res.message}`);
          } catch(err) {
             console.warn(`Error en distribución a ${targetSheet}: ${err.toString()}`);
          }
      }

      // C. Escritura de Logs en Lote (Optimización V8)
      if (logEntries.length > 0) {
        try {
            let sheetLog = SS.getSheetByName(APP_CONFIG.logSheetName);
            if (!sheetLog) {
              sheetLog = SS.insertSheet(APP_CONFIG.logSheetName);
              sheetLog.appendRow(["FECHA", "USUARIO", "ACCION", "DETALLES"]);
            }
            const lastRow = sheetLog.getLastRow();
            // batch write logs
            sheetLog.getRange(lastRow + 1, 1, logEntries.length, 4).setValues(logEntries);
        } catch(logErr) {
            console.error("Error escribiendo logs: " + logErr.toString());
        }
      }

      return { success: true, message: "Datos procesados y distribuidos correctamente.", ids: generatedIds };
    } catch (e) {
        console.error(e);
        registrarLog(activeUser || "SYSTEM", "ERROR_CRITICO_PPC", e.toString());
        return { success: false, message: "Error al guardar: " + e.toString() };
    } finally {
        lock.releaseLock();
    }
  }
  return { success: false, message: "Sistema Ocupado, intenta de nuevo." };
}
```

### 19.7 `apiFetchAdminKPIs` — motor de cálculo del Dashboard de KPIs (línea 719, 185 líneas)

```js
function apiFetchAdminKPIs() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  // Vendedores to analyze based on USER_DB (excluding ADMIN roles)
  const sellers = ["ANGEL_SALINAS", "TERESA_GARZA", "EDUARDO_TERAN", "EDUARDO_MANZANARES", "RAMIRO_RODRIGUEZ", "SEBASTIAN_PADILLA"]; // Antonia removed from select list

  let allData = [];

  sellers.forEach(function(seller) {
    const sheetName = seller === "ANTONIA_VENTAS" ? "ANTONIA_VENTAS" : seller.split("_")[0] + " (VENTAS)";
    const sheet = ss.getSheetByName(sheetName);
    if (!sheet) return;

    const data = sheet.getDataRange().getValues();
    if (data.length <= 1) return;

    const headers = data[0].map(function(h) { return String(h).toUpperCase().trim(); });
    const estatusIdx = headers.indexOf("ESTATUS");
    const vendedorIdx = headers.indexOf("VENDEDOR") > -1 ? headers.indexOf("VENDEDOR") : headers.indexOf("RESPONSABLE");

    // Find aliases for date, dias, and value
    const fechaIdx = headers.findIndex(h => h === "FECHA" || h === "F. INICIO" || h === "FECHA INICIO" || h.includes("FECHA"));
    const diasIdx = headers.findIndex(h => h === "DÍAS" || h === "DIAS" || h.includes("RELOJ") || h.includes("DIAS FINALIZ"));
    const valorIdx = headers.findIndex(h => h === "VALOR" || h === "MONTO" || h.includes("IMPORTE"));
    const motivoIdx = headers.findIndex(h => h.includes("MOTIVO") || h.includes("RAZON"));

    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      if (!row[0] && !row[1]) continue; // Skip totally empty rows

      allData.push({
        vendedor: vendedorIdx > -1 ? String(row[vendedorIdx] || seller) : seller,
        estatus: estatusIdx > -1 ? String(row[estatusIdx]).toUpperCase() : "",
        fecha: fechaIdx > -1 ? row[fechaIdx] : null,
        dias: diasIdx > -1 ? parseFloat(row[diasIdx]) || 0 : 0,
        valor: valorIdx > -1 ? parseFloat(String(row[valorIdx]).replace(/[^0-9.-]+/g,"")) || 0 : 0,
        motivo: motivoIdx > -1 ? String(row[motivoIdx]).toUpperCase() : ""
      });
    }
  });

  // Calculate globalMetrics
  const globalMetrics = { totalQuotes: 0, ganadas: 0, ganadasPercentage: 0, perdidasRiesgo: 0, riskAmount: 0, averageEfficiency: 0, collaboratorsCount: 0 };

  const uniqueSellers = new Set();
  let enviadasCount = 0;
  let totalDias = 0;
  let validDiasCount = 0;

  allData.forEach(function(row) {
    globalMetrics.totalQuotes++;
    uniqueSellers.add(row.vendedor);

    if (row.dias > 0) {
      totalDias += row.dias;
      validDiasCount++;
    }

    if (row.estatus.includes("GANAD") || row.estatus === "CERRADO") {
      globalMetrics.ganadas++;
      enviadasCount++; // Si se ganó, asumimos que se envió
    } else if (row.estatus.includes("ENVIAD") || row.estatus === "COTIZACION ENVIADA") {
      enviadasCount++;
    }

    if (row.estatus.includes("PERDID") || row.estatus.includes("RIESGO") || row.estatus === "CANCELADA" || row.estatus.includes("RECHAZAD")) {
      globalMetrics.perdidasRiesgo++;
      globalMetrics.riskAmount += row.valor;
    }
  });

  globalMetrics.collaboratorsCount = uniqueSellers.size;
  if (enviadasCount > 0) {
    globalMetrics.ganadasPercentage = Math.round((globalMetrics.ganadas / enviadasCount) * 100);
  }
  if (validDiasCount > 0) {
    globalMetrics.averageEfficiency = (totalDias / validDiasCount).toFixed(1);
  }

  // Calculate collaboratorStats
  const collabMap = {};
  allData.forEach(function(row) {
    const v = row.vendedor;
    if (!collabMap[v]) {
      collabMap[v] = { name: v, vol: 0, ganadas: 0, canceladas: 0, totalDias: 0, validDiasCount: 0 };
    }
    collabMap[v].vol++;
    if (row.estatus.includes("GANAD") || row.estatus === "CERRADO") collabMap[v].ganadas++;
    if (row.estatus.includes("PERDID") || row.estatus.includes("CANCELAD") || row.estatus.includes("RECHAZAD")) collabMap[v].canceladas++;

    if (row.dias > 0) {
      collabMap[v].totalDias += row.dias;
      collabMap[v].validDiasCount++;
    }
  });

  const collaboratorStats = Object.values(collabMap).map(function(c) {
    let cierrePct = 0;
    const resolved = c.ganadas + c.canceladas;
    if (resolved > 0) {
      cierrePct = Math.round((c.ganadas / resolved) * 100);
    }

    let avgEfic = 0;
    if (c.validDiasCount > 0) {
      avgEfic = parseFloat((c.totalDias / c.validDiasCount).toFixed(1));
    }

    let estado = "Eficiente"; // default
    if (avgEfic > 2.0) estado = "Cuello botella";
    else if (avgEfic >= 1.5) estado = "Riesgo";

    return {
      name: c.name,
      vol: c.vol,
      ganadas: c.ganadas,
      cierrePercentage: cierrePct,
      avgEfic: avgEfic,
      estado: estado
    };
  });

  // Sort collaborators by volume
  collaboratorStats.sort(function(a, b) { return b.vol - a.vol; });

  // Funnel Data
  const funnelData = { recibidas: globalMetrics.totalQuotes, integradas: 0, aTiempo: 0, seguimiento: 0, ganadas: globalMetrics.ganadas };
  allData.forEach(function(row) {
      if (row.estatus !== 'NUEVO' && row.estatus !== '') funnelData.integradas++;
      if (row.estatus.includes('ENVIAD') || row.estatus.includes('TIEMPO')) funnelData.aTiempo++;
      if (row.estatus.includes('SEGUIMIENT') || row.estatus.includes('NEGOCIACION') || row.estatus.includes('REVISION')) funnelData.seguimiento++;
  });

  // Loss Distribution
  const lossDistMap = {};
  allData.forEach(function(row) {
      if (row.estatus.includes("PERDID") || row.estatus.includes("CANCELAD") || row.estatus.includes("RECHAZAD")) {
          const m = row.motivo || "OTRO";
          lossDistMap[m] = (lossDistMap[m] || 0) + 1;
      }
  });
  const lossDistribution = Object.keys(lossDistMap).map(function(k) { return { label: k, value: lossDistMap[k] }; });

  // Weekly Productivity (Last 5 valid days approx)
  // Parse dates defensively
  const dayCounts = { "Lunes": 0, "Martes": 0, "Miércoles": 0, "Jueves": 0, "Viernes": 0 };
  allData.forEach(function(row) {
      if (row.fecha) {
          let d = new Date(row.fecha);
          if (isNaN(d.getTime()) && typeof row.fecha === 'string') {
              const parts = row.fecha.split('/');
              if (parts.length === 3) {
                  d = new Date(parts[2].length === 2 ? "20"+parts[2] : parts[2], parts[1]-1, parts[0]);
              }
          }
          if (!isNaN(d.getTime())) {
              // Only count if it's within the last 7 days for the "current week" simulation,
              // or just map by weekday for demo purposes if dates are sparse.
              const now = new Date();
              const diffDays = (now - d) / (1000 * 60 * 60 * 24);
              if (diffDays <= 7) {
                  const day = d.getDay(); // 0 = Sun, 1 = Mon ...
                  if (day === 1) dayCounts["Lunes"]++;
                  else if (day === 2) dayCounts["Martes"]++;
                  else if (day === 3) dayCounts["Miércoles"]++;
                  else if (day === 4) dayCounts["Jueves"]++;
                  else if (day === 5) dayCounts["Viernes"]++;
              }
          }
      }
  });

  const weeklyProductivity = Object.keys(dayCounts).map(function(k) { return { day: k, count: dayCounts[k] }; });

  return {
    success: true,
    globalMetrics: globalMetrics,
    collaboratorStats: collaboratorStats,
    funnelData: funnelData,
    lossDistribution: lossDistribution,
    weeklyProductivity: weeklyProductivity
  };
}
```

### 19.8 Integración Outlook: `formatDateForOutlook`, `NotifierService`, `findUserEmailByLabel`, `testIntegracionOutlook` (líneas 115–209)

```js
function formatDateForOutlook(dateString, defaultOffsetMillis = 0) {
  if (!dateString) {
    const d = new Date(new Date().getTime() + defaultOffsetMillis);
    return d.toISOString().split('.')[0];
  }
  try {
    const d = new Date(dateString);
    if (isNaN(d.getTime())) {
      return new Date(new Date().getTime() + defaultOffsetMillis).toISOString().split('.')[0];
    }
    return d.toISOString().split('.')[0];
  } catch (e) {
    return new Date(new Date().getTime() + defaultOffsetMillis).toISOString().split('.')[0];
  }
}

const NotifierService = {
  sendToOutlook: function(payloadData) {
    if (!WEBHOOK_OUTLOOK_URL || WEBHOOK_OUTLOOK_URL === "URL_DE_POWER_AUTOMATE_AQUI") {
      return { success: false, message: "Webhook no configurado." };
    }

    const payload = {
      folio: payloadData.folio || "Sin Folio",
      titulo: payloadData.titulo || "Asignación de Tarea",
      descripcion: payloadData.descripcion || "Tienes una nueva tarea asignada en Holtmont Workspace.",
      fechaInicio: formatDateForOutlook(payloadData.fechaInicio, 0),
      fechaFin: formatDateForOutlook(payloadData.fechaFin, 60 * 60 * 1000), // Default to 1 hour later if missing
      correoDestino: payloadData.correoDestino,
      asignadoPor: payloadData.asignadoPor || "SISTEMA"
    };

    const opciones = {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify(payload),
      muteHttpExceptions: true
    };

    try {
      const respuesta = UrlFetchApp.fetch(WEBHOOK_OUTLOOK_URL, opciones);
      const code = respuesta.getResponseCode();

      if (code === 200 || code === 202) {
        console.log(`Evento Outlook enviado exitosamente a ${payload.correoDestino}. (Código: ${code})`);
        return { success: true, code: code };
      } else {
        console.error(`Fallo Webhook. Código: ${code}. Respuesta: ${respuesta.getContentText()}`);
        return { success: false, code: code, message: respuesta.getContentText() };
      }
    } catch (e) {
      console.error(`Excepción HTTP en NotifierService: ${e.toString()}`);
      return { success: false, code: 500, message: e.toString() };
    }
  }
};

function findUserEmailByLabel(friendlyName) {
  if (!friendlyName) return null;
  const nameUpper = String(friendlyName).trim().toUpperCase();

  for (const key in USER_DB) {
    if (USER_DB[key] && USER_DB[key].label) {
      if (USER_DB[key].label.toUpperCase() === nameUpper) {
        return USER_DB[key].email || null;
      }
    }
    if (key.replace(/_/g, " ") === nameUpper) {
       return USER_DB[key].email || null;
    }
  }
  return null;
}

function testIntegracionOutlook() {
  const emailSebastian = findUserEmailByLabel("Sebastian Padilla");

  if (!emailSebastian) {
    console.error("Error: El usuario SEBASTIAN_PADILLA no tiene un correo configurado.");
    return;
  }

  const payload = {
    folio: "TEST-001",
    titulo: "[PRUEBA] Integración Holtmont - Outlook",
    descripcion: "Este es un evento de prueba generado desde Google Apps Script para validar la integración de tareas en el calendario.",
    fechaInicio: new Date().toISOString(),
    fechaFin: new Date(new Date().getTime() + (60 * 60 * 1000)).toISOString(),
    correoDestino: emailSebastian,
    asignadoPor: "SISTEMA_TEST"
  };

  const resultado = NotifierService.sendToOutlook(payload);
  console.log("Resultado de Prueba:", resultado);
}
```

### 19.9 Triggers: `instalarDisparador`, `generarFolioAutomatico` (folio legado)

```js
function instalarDisparador() {
  const funcionObjetivo = "incrementarContadorDias";

  // Verificar si ya existe el disparador para evitar duplicados
  const triggers = ScriptApp.getProjectTriggers();
  for (let i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === funcionObjetivo) {
      console.log(`El disparador para '${funcionObjetivo}' ya existe.`);
      return;
    }
  }

  // Crear nuevo disparador diario entre 1 am y 2 am
  ScriptApp.newTrigger(funcionObjetivo)
      .timeBased()
      .everyDays(1)
      .atHour(1) // 1 am
      .create();

  console.log(`Disparador instalado para '${funcionObjetivo}' (Diario 1am-2am).`);
  registrarLog("ADMIN", "CONFIG_TRIGGER", "Se instaló el disparador automático diario.");
}

function generarFolioAutomatico(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(30000);
  } catch (e) {
    console.error('Could not obtain lock after 30 seconds.');
    return;
  }

  try {
    const ss = e ? e.source : SpreadsheetApp.getActiveSpreadsheet();
    const sheet = ss.getSheetByName(FOLIO_CONFIG.SHEET_NAME);

    if (!sheet) return;

    const lastRow = sheet.getLastRow();
    if (lastRow < 2) return;

    const lastCol = sheet.getLastColumn();
    const headers = sheet.getRange(1, 1, 1, lastCol).getValues()[0];
    const folioIndex = headers.indexOf(FOLIO_CONFIG.COLUMN_NAME);

    if (folioIndex === -1) {
      console.error(`Column '${FOLIO_CONFIG.COLUMN_NAME}' not found in sheet '${FOLIO_CONFIG.SHEET_NAME}'`);
      return;
    }

    const folioColNum = folioIndex + 1;
    const targetCell = sheet.getRange(lastRow, folioColNum);
    const targetValue = targetCell.getValue();

    if (targetValue === "" || targetValue === null) {
      let newFolio = 1;

      if (lastRow > 2) {
        const numRows = lastRow - 2;
        if (numRows > 0) {
            const previousValues = sheet.getRange(2, folioColNum, numRows, 1).getValues().flat();
            const numbers = previousValues.filter(val => typeof val === 'number' && !isNaN(val));
            if (numbers.length > 0) {
              const maxVal = Math.max(...numbers);
              newFolio = maxVal + 1;
            }
        }
      }

      targetCell.setValue(newFolio);
      console.log(`Generated Folio: ${newFolio} for row ${lastRow}`);
    }

  } catch (err) {
    console.error(err);
  } finally {
    lock.releaseLock();
  }
}
```

### 19.10 `getSystemConfig` — árbol de navegación por rol (línea 560, 145 líneas) y CRUD de personal

```js
function getSystemConfig(role, username) {
  const fullDirectory = getDirectoryFromDB();

  const allDepts = {
      "CEO": { label: "Dirección General (CEO)", icon: "fa-crown", color: "#b8860b" },
      "CONSTRUCCION": { label: "Construcción", icon: "fa-hard-hat", color: "#e83e8c" },
      "COMPRAS": { label: "Compras/Almacén", icon: "fa-shopping-cart", color: "#198754" },
      "PRESUPUESTOS": { label: "Presupuestos", icon: "fa-calculator", color: "#6f42c1" },
      "PRECIOS UNITARIOS": { label: "Precios Unitarios", icon: "fa-dollar-sign", color: "#20c997" },
      "SEGURIDAD": { label: "Seguridad", icon: "fa-shield-alt", color: "#dc3545" },
      "EHS": { label: "Seguridad (EHS)", icon: "fa-shield-alt", color: "#dc3545" },
      "DISEÑO": { label: "Diseño & Ing.", icon: "fa-drafting-compass", color: "#0d6efd" },
      "ELECTROMECANICA": { label: "Electromecánica", icon: "fa-bolt", color: "#ffc107" },
      "HVAC": { label: "HVAC", icon: "fa-fan", color: "#fd7e14" },
      "LIMPIEZA": { label: "Limpieza", icon: "fa-broom", color: "#0dcaf0" },
      "ALMACEN Y MAQUINARIA": { label: "Almacén y Maquinaria", icon: "fa-warehouse", color: "#198754" },
      "ADMINISTRACION": { label: "Administración", icon: "fa-briefcase", color: "#6f42c1" },
      "VENTAS": { label: "Ventas", icon: "fa-handshake", color: "#0dcaf0" },
      "MAQUINARIA": { label: "Maquinaria", icon: "fa-truck", color: "#20c997" },
      "FINANZAS": { label: "Finanzas", icon: "fa-coins", color: "#198754" },
      "FACTURACION": { label: "Facturación", icon: "fa-file-invoice-dollar", color: "#0d6efd" },
      "RH": { label: "Recursos Humanos", icon: "fa-users", color: "#6610f2" },
      "CALIDAD": { label: "Calidad", icon: "fa-clipboard-check", color: "#0dcaf0" }
  };

  const ppcModuleMaster = { id: "PPC_MASTER", label: "PPC Maestro", icon: "fa-tasks", color: "#fd7e14", type: "ppc_native" };

  if (String(username).toUpperCase().trim() === 'JESUS_CANTU') {
      ppcModuleMaster.label = "INTERDICIPLINARIA";
  }

  const ppcModuleWeekly = { id: "WEEKLY_PLAN", label: "Planeación Semanal", icon: "fa-calendar-alt", color: "#6f42c1", type: "weekly_plan_view" };
  // const ecgModule = { id: "ECG_SALES", label: "Monitor Vivos", icon: "fa-heartbeat", color: "#d63384", type: "ecg_dashboard" };
  const kpiModule = { id: "KPI_DASHBOARD", label: "KPI Performance", icon: "fa-chart-line", color: "#d63384", type: "kpi_dashboard_view" };

  if (role === 'TONITA') return {
      departments: { "VENTAS": allDepts["VENTAS"] },
      allDepartments: allDepts,
      staff: [ { name: "ANTONIA_VENTAS", dept: "VENTAS" } ],
      directory: fullDirectory,
      specialModules: [
        { id: "MY_TRACKER", label: "Mi Tabla", icon: "fa-table", color: allDepts["PRESUPUESTOS"] ? allDepts["PRESUPUESTOS"].color : "#6f42c1", type: "mirror_staff", target: "ANTONIA PINEDA LOPEZ" },
        ppcModuleMaster,
        ppcModuleWeekly
      ],
      accessProjects: false,
      canSeeBancoJuntas: false
  };

  const ppcModulesEarly = [ ppcModuleMaster, ppcModuleWeekly ];

  // RAMA ESPECIAL: Juany Rodriguez (su role es STAFF_USER pero tiene vista ampliada)
  if (String(username).toUpperCase().trim() === 'JUANY_RODRIGUEZ') {
      const juanyDepts = {
          "COMPRAS": allDepts["COMPRAS"],
          "FACTURACION": allDepts["FACTURACION"],
          "FINANZAS": allDepts["FINANZAS"]
      };
      const juanyDeptKeys = ["COMPRAS", "FACTURACION", "FINANZAS"];
      return {
          departments: juanyDepts,
          allDepartments: allDepts,
          staff: fullDirectory.filter(d => juanyDeptKeys.indexOf(d.dept) > -1),
          directory: fullDirectory,
          specialModules: ppcModulesEarly,
          accessProjects: false,
          canSeeBancoJuntas: false
      };
  }

  if (role === 'STAFF_USER') {
    const u = USER_DB[String(username).toUpperCase().trim()] || {};
    const staffName = u.staffName || u.label;
    const deptColor = (allDepts[u.dept] && allDepts[u.dept].color) || "#0d6efd";
    const modules = [
        { id: "MY_TRACKER", label: "Mi Tabla", icon: "fa-table", color: deptColor, type: "mirror_staff", target: staffName },
        { id: "PPC_MASTER", label: "Agregar Actividad", icon: "fa-tasks", color: "#fd7e14", type: "ppc_native" }
    ];
    if (u.seller) {
        modules.push({ id: "MY_SALES", label: "Ventas", icon: "fa-hand-holding-usd", color: "#0dcaf0", type: "mirror_staff", target: staffName + " (VENTAS)" });
    }
    return {
      departments: {},
      allDepartments: allDepts,
      staff: [ { name: staffName, dept: u.dept } ],
      directory: fullDirectory,
      specialModules: modules,
      accessProjects: false,
      canSeeBancoJuntas: false
    };
  }


  if (role === 'WORKORDER_USER') {
    const woModule = { ...ppcModuleMaster, label: "Pre Work Order" };
    return {
      departments: {},
      allDepartments: allDepts,
      staff: [],
      directory: fullDirectory,
      specialModules: [ woModule ],
      accessProjects: false,
      canSeeBancoJuntas: false
    };
  }

  const ppcModules = [ ppcModuleMaster, ppcModuleWeekly ];

  if (role === 'PPC_ADMIN') return {
      departments: {},
      allDepartments: allDepts,
      staff: [],
      directory: fullDirectory,
      specialModules: ppcModules,
      accessProjects: true,
      canSeeBancoJuntas: true
  };

  if (role === 'ADMIN_CONTROL') {
    return {
      departments: allDepts, allDepartments: allDepts, staff: fullDirectory, directory: fullDirectory,
      specialModules: [
        ...ppcModules,
        { id: "MIRROR_TONITA", label: "Monitor Toñita", icon: "fa-eye", color: "#0dcaf0", type: "mirror_staff", target: "ANTONIA_VENTAS" },
        { id: "ADMIN_TRACKER", label: "Control", icon: "fa-clipboard-list", color: "#6f42c1", type: "mirror_staff", target: "ADMINISTRADOR" }
      ],
      accessProjects: true,
      canSeeBancoJuntas: true
    };
  }

  // Default ADMIN (LUIS_CARLOS falls here with role 'ADMIN')
  const defaultModules = [ ...ppcModules, { id: "MIRROR_TONITA", label: "Monitor Toñita", icon: "fa-eye", color: "#0dcaf0", type: "mirror_staff", target: "ANTONIA_VENTAS" } ];
  if (role === 'ADMIN') {
      defaultModules.push(kpiModule);
  }

  return {
    departments: allDepts, allDepartments: allDepts, staff: fullDirectory, directory: fullDirectory,
    specialModules: defaultModules,
    accessProjects: true,
    canSeeBancoJuntas: true
  };
}
```

`ecgModule` está literalmente comentado en el código fuente (`// const ecgModule = {...}`) — es la confirmación en código de por qué la vista `ECG_VIEW` (§8.3) nunca aparece en el menú de ningún rol, aunque su HTML siga presente en `index.html`.

### 19.11 CRUD de personal: `apiAddEmployee`, `apiDeleteEmployee` (líneas 467–558)

```js
function apiAddEmployee(payload) {
    const lock = LockService.getScriptLock();
    try {
        if (lock.tryLock(10000)) {
            const { name, dept, type } = payload;
            const cleanName = String(name).toUpperCase().trim();
            if (!cleanName) return { success: false, message: "Nombre inválido" };

            let sheet = findSheetSmart(APP_CONFIG.directorySheetName);
            if (!sheet) {
                // Should have been created by getDirectoryFromDB, but ensure it exists
                getDirectoryFromDB();
                sheet = findSheetSmart(APP_CONFIG.directorySheetName);
            }

            // Check duplicate
            const data = sheet.getDataRange().getValues();
            for(let i=1; i<data.length; i++) {
                if (String(data[i][0]).toUpperCase().trim() === cleanName) {
                    return { success: false, message: "El usuario ya existe." };
                }
            }

            // Add to DB
            sheet.appendRow([cleanName, dept, type]);

            // Create Sheets based on Type
            const createSheetIfMissing = (sName, headers) => {
                let s = findSheetSmart(sName);
                if (!s) {
                    s = SS.insertSheet(sName);
                    s.appendRow(headers);
                    s.getRange(1, 1, 1, headers.length).setFontWeight("bold").setBackground("#e6e6e6");
                    // Conditional Formatting (Basic)
                    try {
                        const rule = SpreadsheetApp.newConditionalFormatRule()
                            .whenTextEqualTo("100")
                            .setBackground("#d4edda")
                            .setRanges([s.getRange("F:F")]) // Assuming Avance is commonly around F
                            .build();
                        s.setConditionalFormatRules([rule]);
                    } catch(e){}
                }
            };

            if (type === 'ESTANDAR' || type === 'HIBRIDO') {
                createSheetIfMissing(cleanName, DEFAULT_TRACKER_HEADERS);
            }
            if (type === 'VENTAS' || type === 'HIBRIDO') {
                createSheetIfMissing(cleanName + " (VENTAS)", DEFAULT_SALES_HEADERS);
            }

            registrarLog("ADMIN", "ADD_EMPLOYEE", `Usuario: ${cleanName}, Tipo: ${type}`);
            return { success: true };
        }
    } catch(e) {
        return { success: false, message: e.toString() };
    } finally {
        lock.releaseLock();
    }
}

function apiDeleteEmployee(name) {
    const lock = LockService.getScriptLock();
    try {
        if (lock.tryLock(10000)) {
            const cleanName = String(name).toUpperCase().trim();
            const sheet = findSheetSmart(APP_CONFIG.directorySheetName);
            if (!sheet) return { success: false, message: "No existe DB_DIRECTORY" };

            const data = sheet.getDataRange().getValues();
            let rowIndex = -1;
            for(let i=1; i<data.length; i++) {
                if (String(data[i][0]).toUpperCase().trim() === cleanName) {
                    rowIndex = i + 1; // 1-based
                    break;
                }
            }

            if (rowIndex > -1) {
                sheet.deleteRow(rowIndex);
                registrarLog("ADMIN", "DELETE_EMPLOYEE", `Usuario eliminado: ${cleanName}`);
                return { success: true };
            }
            return { success: false, message: "Usuario no encontrado." };
        }
    } catch(e) {
        return { success: false, message: e.toString() };
    } finally {
        lock.releaseLock();
    }
}
```

> **Nota importante para clonar:** `apiAddEmployee` crea la hoja Tracker nueva pero **no** la inserta en la posición correcta relativa al separador `"TAREAS REALIZADAS"` (§5.3) ni le aplica `applyTrafficLightToSheet` — la primera fila real que se guarde en esa hoja disparará el auto-formato normalmente vía `internalBatchUpdateTasks`. También nótese que **`apiDeleteEmployee` borra la fila de `DB_DIRECTORY` pero no elimina la hoja Tracker asociada** — el Tracker de una persona dada de baja permanece en la Spreadsheet indefinidamente, simplemente deja de aparecer en la navegación. Esto es consistente con lo observado en §6.3 (`CESAR_GOMEZ` documentado como baja pero con `USER_DB`/hoja aún presentes) — es el comportamiento esperado del sistema, no un bug.

### 19.12 Módulo Proyectos/Cascada: `apiFetchWeeklyPlanData`, `getWeekNumber`, `apiSaveSite`, `apiSaveSubProject`, `apiFetchCascadeTree`, `apiFetchProjectTasks` (⚠️ contiene un bug real, ver nota), `apiSaveProjectTask`

```js
function apiFetchWeeklyPlanData(username) {
  try {
    const isJesus = String(username).toUpperCase().trim() === 'JESUS_CANTU';
    const sheetName = (String(username).toUpperCase().trim() === 'ANTONIA_VENTAS') ? 'PPCV4' : APP_CONFIG.ppcSheetName;
    const sheet = findSheetSmart(sheetName);
    if (!sheet) return { success: false, message: "No existe la hoja " + sheetName };
    const data = sheet.getDataRange().getValues();
    if (data.length < 2) return { success: true, headers: [], data: [] };
    const headerRowIdx = findHeaderRow(data);
    if (headerRowIdx === -1) return { success: false, message: "Cabeceras no encontradas en PPCV3." };
    const originalHeaders = data[headerRowIdx].map(h => String(h).trim());

    // CUSTOM VIEW FOR JESUS_CANTU
    if (isJesus) {
        // Define fixed header structure for the customized view
        const jesusHeaders = [
            'RUTA_CRITICA', 'ZONA', 'ESPECIALIDAD', 'CONCEPTO',
            'CUANT_REQUERIDO', 'CUANT_REAL', 'RESPONSABLE', 'CONTRATISTA',
            'DIAS_L', 'DIAS_M', 'DIAS_X', 'DIAS_J', 'DIAS_V', 'DIAS_S', 'DIAS_D',
            'CUMPLIMIENTO'
        ];

        // Map data rows to these headers based on column matching
        const rows = data.slice(headerRowIdx + 1);
        const result = rows.map((r, i) => {
            const rowObj = { _rowIndex: headerRowIdx + i + 2 };
            // Helper to find value in row by fuzzy header match
            const getVal = (candidates) => {
                for (let c of candidates) {
                    const idx = originalHeaders.findIndex(h => h.toUpperCase().trim() === c.toUpperCase().trim() || h.toUpperCase().trim().includes(c.toUpperCase().trim()));
                    if (idx > -1) return r[idx];
                }
                return "";
            };

            rowObj['RUTA_CRITICA'] = getVal(['RUTA_CRITICA', 'RUTA CRITICA', 'CRITICA']);
            rowObj['ZONA'] = getVal(['ZONA', 'UBICACION', 'AREA GEOGRAFICA']);
            rowObj['ESPECIALIDAD'] = getVal(['ESPECIALIDAD', 'AREA', 'DISCIPLINA']);
            rowObj['CONCEPTO'] = getVal(['CONCEPTO', 'DESCRIPCION', 'DEFINIDA', 'ATERRIZADA', 'ACTIVIDAD']);

            // CUANTIFICACION LOGIC (Handle Merged Headers)
            rowObj['CUANT_REQUERIDO'] = getVal(['CUANT_REQUERIDO', 'REQUERIDO']);
            rowObj['CUANT_REAL'] = getVal(['CUANT_REAL', 'REAL']);

            if (!rowObj['CUANT_REQUERIDO']) {
                const qIdx = originalHeaders.findIndex(h => h.toUpperCase().includes('CUANTIFICACIÓN') || h.toUpperCase().includes('CUANTIFICACION'));
                if (qIdx > -1) {
                    rowObj['CUANT_REQUERIDO'] = r[qIdx];
                    rowObj['CUANT_REAL'] = r[qIdx + 1];
                }
            }

            rowObj['RESPONSABLE'] = getVal(['RESPONSABLE', 'ENCARGADO', 'PERSONA RESPONSABLE']);
            rowObj['CONTRATISTA'] = getVal(['CONTRATISTA', 'PROVEEDOR']);
            rowObj['DIAS_L'] = getVal(['DIAS_L', 'LUNES', 'L']);
            rowObj['DIAS_M'] = getVal(['DIAS_M', 'MARTES', 'M']);
            rowObj['DIAS_X'] = getVal(['DIAS_X', 'MIERCOLES', 'MIÉRCOLES', 'X', 'MI']);
            rowObj['DIAS_J'] = getVal(['DIAS_J', 'JUEVES', 'J']);
            rowObj['DIAS_V'] = getVal(['DIAS_V', 'VIERNES', 'V']);
            rowObj['DIAS_S'] = getVal(['DIAS_S', 'SABADO', 'SÁBADO', 'S']);
            rowObj['DIAS_D'] = getVal(['DIAS_D', 'DOMINGO', 'D']);
            rowObj['CUMPLIMIENTO'] = getVal(['CUMPLIMIENTO']);

            // Add ID if available for saving
            rowObj['ID'] = getVal(['ID', 'FOLIO']);
            rowObj['FOLIO'] = rowObj['ID'];

            // HIDDEN FIELDS PRESERVATION (CRITICAL FOR SYNC)
            rowObj['FECHA'] = getVal(['FECHA', 'ALTA', 'FECHA INICIO', 'F. INICIO', 'FECHA_INICIO', 'FECHA VISITA', 'F. VISITA']);
            rowObj['ESTATUS'] = getVal(['ESTATUS', 'STATUS']);
            rowObj['AVANCE'] = getVal(['AVANCE', 'AVANCE %']);
            rowObj['CLASIFICACION'] = getVal(['CLASIFICACION']);
            rowObj['PRIORIDAD'] = getVal(['PRIORIDAD']);

            return rowObj;
        }).filter(r => r["CONCEPTO"] || r["ID"]);

        return { success: true, headers: jesusHeaders, data: result.reverse() };
    }

    const mappedHeaders = originalHeaders.map(h => {
        const up = h.toUpperCase();
        if (up.includes("ESPECIALIDAD") || up.includes("AREA") || up.includes("DEPARTAMENTO")) return "ESPECIALIDAD";
        if (up.includes("DESCRIPCI") || up.includes("CONCEPTO")) return "CONCEPTO";
        if (up.includes("INVOLUCRADOS") || up.includes("RESPONSABLE") || up.includes("VENDEDOR") || up.includes("ENCARGADO")) return "RESPONSABLE";
        if (up.includes("ALTA") || up.includes("FECHA")) return "FECHA";
        if (up.includes("RELOJ") || up.includes("HORAS")) return "RELOJ";
        if (up.includes("ARCHIV") || up.includes("CLIP") || up.includes("LINK") || up.includes("EVIDENCIA")) return "ARCHIVO";
        if (up.includes("CUMPLIMIENTO")) return "CUMPLIMIENTO";
        if (up === "COMENTARIOS" || up === "COMENTARIOS SEMANA EN CURSO" || up.includes("OBSERVACIONES")) return "COMENTARIOS SEMANA EN CURSO";
        if (up === "COMENTARIOS PREVIOS" || up === "COMENTARIOS SEMANA PREVIA" || up === "PREVIOS") return "COMENTARIOS SEMANA PREVIA";
        return up;
    });
    const displayHeaders = ["SEMANA", ...mappedHeaders];
    const rows = data.slice(headerRowIdx + 1);
    const result = rows.map((r, i) => {
      const rowObj = { _rowIndex: headerRowIdx + i + 2 };
      mappedHeaders.forEach((h, colIdx) => {
        let val = r[colIdx];
        if (val instanceof Date) {
           if (val.getFullYear() < 1900) {
              val = Utilities.formatDate(val, SS.getSpreadsheetTimeZone(), "HH:mm");
           } else {
              val = Utilities.formatDate(val, SS.getSpreadsheetTimeZone(), "dd/MM/yy");
           }
        }
        rowObj[h] = val;
      });
      const fechaVal = rowObj["FECHA"];
      let semanaNum = "-";
      if (fechaVal) {
        let dateObj = null;
        if (String(fechaVal).includes("/")) {
          const parts = String(fechaVal).split("/");
          if(parts.length === 3) dateObj = new Date(parts[2], parts[1]-1, parts[0]);
        } else if (fechaVal instanceof Date) { dateObj = fechaVal; } else { dateObj = new Date(fechaVal); }
        if (dateObj && !isNaN(dateObj.getTime())) semanaNum = getWeekNumber(dateObj);
      }
      rowObj["SEMANA"] = semanaNum;

      return rowObj;
    }).filter(r => r["CONCEPTO"] || r["ID"] || r["FOLIO"]);
    return { success: true, headers: displayHeaders, data: result.reverse() };
  } catch (e) {
    console.error(e);
    return { success: false, message: e.toString() };
  }
}

function getWeekNumber(d) {
  d = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  d.setUTCDate(d.getUTCDate() + 4 - (d.getUTCDay()||7));
  var yearStart = new Date(Date.UTC(d.getUTCFullYear(),0,1));
  var weekNo = Math.ceil(( ( (d - yearStart) / 86400000) + 1)/7);
  return weekNo;
}

// 1. Guardar Nuevo Sitio (Padre)
function apiSaveSite(siteData) {
  const lock = LockService.getScriptLock();
  if (lock.tryLock(5000)) {
    try {
      let sheet = findSheetSmart("DB_SITIOS");
      if (!sheet) {
        sheet = SS.insertSheet("DB_SITIOS");
        sheet.appendRow(["ID_SITIO", "NOMBRE", "CLIENTE", "TIPO", "ESTATUS", "FECHA_CREACION", "CREADO_POR"]);
      }

      const data = sheet.getDataRange().getValues();
      const cleanName = siteData.name.toUpperCase().trim();
      const nameColIdx = data.length > 0 ? data[0].indexOf("NOMBRE") : 1;
      for(let i=1; i<data.length; i++) {
         if (data[i][nameColIdx] && String(data[i][nameColIdx]).toUpperCase().trim() === cleanName) {
             return { success: false, message: "Ya existe un sitio con ese nombre."};
         }
      }

      const id = "SITE-" + new Date().getTime();
      sheet.appendRow([
        id,
        cleanName,
        siteData.client.toUpperCase().trim(),
        siteData.type || "CLIENTE",
        "ACTIVO",
        new Date(),
        siteData.createdBy ? siteData.createdBy.toUpperCase().trim() : "ANONIMO"
      ]);
      SpreadsheetApp.flush();

      // AUTOMATIZACIÓN: CREAR ESTRUCTURA ESTÁNDAR AUTOMÁTICAMENTE
      apiCreateStandardStructure(id, siteData.createdBy);

      registrarLog(siteData.createdBy || "ANONIMO", "NUEVO SITIO", `Sitio: ${cleanName} (${id})`);

      return { success: true, id: id, message: "Sitio creado correctamente con estructura PPC completa." };
    } catch (e) {
      return { success: false, message: e.toString() };
    } finally {
      lock.releaseLock();
    }
  }
  return { success: false, message: "El sistema está ocupado." };
}

// 2. Guardar Nuevo Subproyecto (Hijo)
function apiSaveSubProject(subProjectData) {
  const lock = LockService.getScriptLock();
  if (lock.tryLock(5000)) {
    try {
      let sheet = findSheetSmart("DB_PROYECTOS");
      if (!sheet) {
        sheet = SS.insertSheet("DB_PROYECTOS");
        sheet.appendRow(["ID_PROYECTO", "ID_SITIO", "NOMBRE_SUBPROYECTO", "TIPO", "ESTATUS", "FECHA_CREACION", "CREADO_POR"]);
      }

      const cleanName = subProjectData.name.toUpperCase().trim();
      const data = sheet.getDataRange().getValues();
      let idSitioIdx = 1;
      let nameIdx = 2;
      const headerRow = findHeaderRow(data);
      if (headerRow > -1) {
          const headers = data[headerRow].map(h=>String(h).toUpperCase());
          idSitioIdx = headers.indexOf("ID_SITIO");
          nameIdx = headers.indexOf("NOMBRE_SUBPROYECTO");
      }

      for(let i=1; i<data.length; i++) {
          if (data[i][idSitioIdx] == subProjectData.parentId &&
              String(data[i][nameIdx]).toUpperCase().trim() === cleanName) {
              return { success: false, message: "Ya existe ese subproyecto en este sitio."};
          }
      }

      const id = "PROJ-" + new Date().getTime() + "-" + Math.floor(Math.random()*1000);
      sheet.appendRow([
        id,
        subProjectData.parentId,
        cleanName,
        subProjectData.type || "GENERAL",
        "ACTIVO",
        new Date(),
        subProjectData.createdBy ? subProjectData.createdBy.toUpperCase().trim() : "ANONIMO"
      ]);
      SpreadsheetApp.flush();

      registrarLog(subProjectData.createdBy || "ANONIMO", "NUEVO SUBPROYECTO", `Subproyecto: ${cleanName} (${id})`);

      return { success: true, id: id, message: "Subproyecto agregado." };
    } catch (e) {
      return { success: false, message: e.toString() };
    } finally {
      lock.releaseLock();
    }
  }
  return { success: false, message: "El sistema está ocupado." };
}

// 3. Obtener Árbol Completo
function apiFetchCascadeTree() {
  try {
    const sites = [];
    const sheetSites = findSheetSmart("DB_SITIOS");
    if (sheetSites) {
      const values = sheetSites.getDataRange().getValues();
      const headerRowIdx = findHeaderRow(values);
      if (headerRowIdx !== -1 && values.length > headerRowIdx + 1) {
        const headers = values[headerRowIdx].map(h => String(h).toUpperCase().trim());
        const colMap = {
           id: headers.findIndex(h => h.includes("ID")),
           name: headers.findIndex(h => h.includes("NOMBRE")),
           client: headers.findIndex(h => h.includes("CLIENTE")),
           type: headers.findIndex(h => h.includes("TIPO")),
           status: headers.findIndex(h => h.includes("ESTATUS")),
           date: headers.findIndex(h => h.includes("FECHA"))
        };
        for (let i = headerRowIdx + 1; i < values.length; i++) {
          const row = values[i];
          if (colMap.id > -1 && colMap.name > -1 && row[colMap.id]) {
             let dateStr = "";
             if (colMap.date > -1 && row[colMap.date]) {
                 try { dateStr = Utilities.formatDate(new Date(row[colMap.date]), SS.getSpreadsheetTimeZone(), "dd/MM/yy HH:mm");
                 } catch(e) {}
             }
             sites.push({
               id: String(row[colMap.id]).trim(),
               name: String(row[colMap.name]).trim(),
               client: (colMap.client > -1) ? String(row[colMap.client]) : "",
               type: (colMap.type > -1) ? String(row[colMap.type]) : "CLIENTE",
               status: (colMap.status > -1) ? String(row[colMap.status]) : "ACTIVO",
               createdAt: dateStr,
               subProjects: [],
               expanded: false
             });
          }
        }
      }
    }

    const sheetProjs = findSheetSmart("DB_PROYECTOS");
    if (sheetProjs) {
      const values = sheetProjs.getDataRange().getValues();
      const headerRowIdx = findHeaderRow(values);
      if (headerRowIdx !== -1 && values.length > headerRowIdx + 1) {
        const headers = values[headerRowIdx].map(h => String(h).toUpperCase().trim());
        const colMap = {
           parentId: headers.findIndex(h => h.includes("SITIO") || h.includes("PADRE")),
           name: headers.findIndex(h => h.includes("NOMBRE") || h.includes("SUBPROYECTO")),
           type: headers.findIndex(h => h.includes("TIPO") || h.includes("ESPECIALIDAD")),
           status: headers.findIndex(h => h.includes("ESTATUS"))
        };
        for (let i = headerRowIdx + 1; i < values.length; i++) {
          const row = values[i];
          if (colMap.parentId > -1 && colMap.name > -1 && row[colMap.parentId]) {
             const parentId = String(row[colMap.parentId]).trim();
             const parent = sites.find(s => String(s.id).trim() === parentId);
             if (parent) {
               // CAMBIO: Si es PPC, asignamos el icono correcto
               const pName = String(row[colMap.name]).trim().toUpperCase();
               let icon = "fa-clipboard-list";
               if (pName.includes("PPC")) icon = "fa-tasks";

               parent.subProjects.push({
                 id: row[0],
                 name: String(row[colMap.name]).trim(),
                 type: (colMap.type > -1) ? String(row[colMap.type]) : "GENERAL",
                 status: (colMap.status > -1) ? String(row[colMap.status]) : "ACTIVO",
                 icon: icon
               });
             }
          }
        }
      }
    }
    return { success: true, data: sites };
  } catch (e) {
    console.error(e);
    return { success: false, message: "Error leyendo DB: " + e.toString() };
  }
}

function apiFetchProjectTasks(projectName) {
  try {
    const sheet = findSheetSmart("ADMINISTRADOR");
    if (!sheet) return { success: false, message: "No se encuentra la hoja ADMINISTRADOR" };

    const values = sheet.getDataRange().getValues();
    if (values.length < 2) return { success: true, data: [], headers: [] };

    const headerRowIdx = findHeaderRow(values);
    if (headerRowIdx === -1) return { success: false, message: "Sin cabeceras válidas" };

    const headers = values[headerRowIdx].map(h => String(h).toUpperCase().trim());
    const projectTag = `[PROY: ${String(projectName).toUpperCase().trim()}]`;

    // Indices clave
    let colIdx = {
       concepto: headers.indexOf("CONCEPTO"),
       comentarios: headers.indexOf("COMENTARIOS")
    };
    if (colIdx.concepto === -1) colIdx.concepto = headers.findIndex(h => h.includes("CONCEPTO") || h.includes("DESCRIPCI"));
    if (colIdx.comentarios === -1) colIdx.comentarios = headers.findIndex(h => h.includes("COMENTARIOS"));
    const dataRows = values.slice(headerRowIdx + 1);
    const filteredTasks = [];
    for (let i = 0; i < dataRows.length; i++) {
        const row = dataRows[i];
        const comText = (colIdx.comentarios > -1 && row[colIdx.comentarios]) ? String(row[colIdx.comentarios]).toUpperCase() : "";
        const descText = (colIdx.concepto > -1 && row[colIdx.concepto]) ? String(row[colIdx.concepto]).toUpperCase() : "";
        if (comText.includes(projectTag) || descText.includes(projectTag)) {
            let rowObj = { _rowIndex: headerRowIdx + i + 2 };
            headers.forEach((h, k) => {
                let val = row[k];
                if (val instanceof Date) {
                    val = Utilities.formatDate(val, SS.getSpreadsheetTimeZone(), "dd/MM/yy");
                }
                rowObj[h] = val;
            });
            filteredTasks.push(rowObj);
        }
    }

    if (sheetName.includes('ANTONIA_VENTAS')) {
        const estatusIdx = headers.indexOf('ESTATUS');
        const avanceIdx = headers.indexOf('AVANCE');
        const mapCotIdx = headers.indexOf('MAP COT');

        if (mapCotIdx !== -1) {
            headers.splice(mapCotIdx, 1); // remove

            // Recalculate positions
            const estIdx2 = headers.indexOf('ESTATUS');
            if (estIdx2 !== -1) {
                headers.splice(estIdx2 + 1, 0, 'MAP COT');
            } else {
                headers.push('MAP COT');
            }
        }
    }
    return { success: true, data: filteredTasks.reverse(), headers: headers };

  } catch (e) {
    console.error(e);
    return { success: false, message: e.toString() };
  }
}

// *** MODIFICADO PARA INCLUIR ETIQUETAS DE LOS NUEVOS PPCs ***
function apiSaveProjectTask(taskData, projectName, username) {
    try {
        const nameUpper = String(projectName).toUpperCase().trim();
        const tag = `[PROY: ${nameUpper}]`;

        let coms = taskData['COMENTARIOS'] || "";

        // Verificamos si ya tiene la etiqueta para no duplicar
        if (!String(coms).toUpperCase().includes(tag)) {
            taskData['COMENTARIOS'] = (coms + " " + tag).trim();
        }

        const res = internalBatchUpdateTasks("ADMINISTRADOR", [taskData]);
        if(res.success) {
            registrarLog(username || "DESCONOCIDO", "ACTUALIZAR PROYECTO", `Proyecto: ${projectName}, ID: ${taskData['ID']||taskData['FOLIO']}`);
            res.data = taskData;
        }
        return res;
    } catch (e) {
        return { success: false, message: e.toString() };
    }
}
```

> ## 🐛 Bug real confirmado en `apiFetchProjectTasks` (línea 3854)
>
> La línea `if (sheetName.includes('ANTONIA_VENTAS')) {` referencia una variable `sheetName` que **no existe en ningún alcance de esta función**: el parámetro se llama `projectName`, la constante local que sí apunta a una hoja es `sheet` (el objeto `Sheet`, sin método `.includes()`), y no hay ninguna variable global `sheetName` en todo `CODIGO.js` (verificado — cero declaraciones `var/let/const sheetName` a nivel de archivo). Esto es un **`ReferenceError: sheetName is not defined`** garantizado, en JavaScript estricto de V8, cada vez que se llama a esta función.
>
> Como toda la función está envuelta en `try { ... } catch (e) { return { success: false, message: e.toString() }; }`, el error se captura silenciosamente: `apiFetchProjectTasks` **siempre devuelve `success: false`** con el mensaje `"ReferenceError: sheetName is not defined"`, perdiendo todo el trabajo de filtrado por etiqueta `[PROY: ...]` ya realizado en `filteredTasks`, y el frontend nunca recibe las tareas del proyecto solicitado.
>
> **Impacto:** la vista `PROJECT_TASKS_VIEW` (§8.3) — el listado de tareas dentro de un subproyecto en la cascada Sitio→Subproyecto→Tarea — está rota en producción a la fecha de este documento. `apiFetchCascadeTree` (el árbol) sí funciona porque no comparte esa función; solo el detalle de tareas por subproyecto falla.
>
> **Fix mínimo si se clona y se corrige:** reemplazar `sheetName.includes('ANTONIA_VENTAS')` por `String(sheet.getName()).toUpperCase().includes('ANTONIA_VENTAS')`, que es casi con certeza la intención original del autor (comparar el nombre real de la hoja `ADMINISTRADOR` — que nunca contendría literalmente "ANTONIA_VENTAS" salvo que se edite la condición para el caso correcto, ej. comparar contra `projectName` en su lugar). No se aplicó esta corrección en este documento porque no fue solicitada — se reporta para que quien mantenga el sistema lo decida.

### 19.13 Formato condicional (semáforo nativo de Sheets): `applyTrafficLightToSheet`, `setupConditionalFormatting`

```js
function applyTrafficLightToSheet(sheet) {
  if (!sheet) return false;
  const sNameUpper = sheet.getName().toUpperCase().trim();

  // Exclusiones Internas (Seguridad)
  const excludedSubstrings = ["LOG_", "DB_", "DATOS", "BORRADOR"];
  if (excludedSubstrings.some(ex => sNameUpper.includes(ex))) return false;

  const lastRow = sheet.getLastRow();
  const lastCol = sheet.getLastColumn();
  if (lastRow < 2) return false;

  // 1. Encontrar Cabeceras
  const values = sheet.getRange(1, 1, Math.min(20, lastRow), lastCol).getValues();
  const headerRowIdx = findHeaderRow(values);
  if (headerRowIdx === -1) return false;

  const headers = values[headerRowIdx].map(h => String(h).toUpperCase().trim());

  // 2. Identificar Columnas
  const fechaAliases = ['FECHA', 'FECHA ALTA', 'FECHA INICIO', 'ALTA', 'FECHA DE INICIO', 'FECHA VISITA', 'FECHA DE ALTA', 'FECHA_ALTA', 'F. INICIO', 'F. VISITA', 'F. ENTREGA'];
  const colFechaIndices = [];
  headers.forEach((h, i) => {
      if (fechaAliases.includes(h) || h.startsWith("FECHA ")) {
          colFechaIndices.push(i);
      }
  });

  const colClasiIdx = headers.findIndex(h => h.includes("CLASIFICACION") || h.includes("CLASI"));
  const colDiasIdx = headers.findIndex(h => h === "DIAS" || h === "RELOJ" || h.includes("DIAS FINALIZ") || h.includes("DÍAS FINALIZ"));

  if (colFechaIndices.length === 0 || colClasiIdx === -1) return false;

  const rowHeader = headerRowIdx + 1; // 1-based (Fila de Titulos)
  const colClasiLet = colIndexToLetter(colClasiIdx + 1);

  // Identify PRIMARY Date Column (for linking DIAS coloring)
  let primaryFechaIdx = -1;
  for(let alias of fechaAliases) {
      const idx = headers.indexOf(alias);
      if(idx > -1) { primaryFechaIdx = idx; break; }
  }
  if(primaryFechaIdx === -1 && colFechaIndices.length > 0) primaryFechaIdx = colFechaIndices[0];

  // 3. Limpieza Inteligente de Reglas Antiguas
  const rules = sheet.getConditionalFormatRules();
  const cleanRules = rules.filter(r => {
      const formula = (r.getBooleanCondition() && r.getBooleanCondition().getCriteriaType() === SpreadsheetApp.BooleanCriteria.CUSTOM_FORMULA)
                      ? r.getBooleanCondition().getCriteriaValues()[0]
                      : "";
      // Eliminamos reglas de semáforo viejas (detectadas por referencia a CLASI + TODAY)
      if (formula.includes("TODAY") && formula.includes(colClasiLet) && formula.includes("ISNUMBER")) return false;
      return true;
  });

  const newRules = [];

  // 4. Iterar sobre TODAS las columnas de fecha encontradas
  colFechaIndices.forEach(idx => {
      const colFechaLet = colIndexToLetter(idx + 1);

      const rangesToColor = [sheet.getRange(rowHeader, idx + 1, sheet.getMaxRows() - rowHeader + 1, 1)];
      if (idx === primaryFechaIdx && colDiasIdx > -1) {
          rangesToColor.push(sheet.getRange(rowHeader, colDiasIdx + 1, sheet.getMaxRows() - rowHeader + 1, 1));
      }

      const addRulePair = (clase, dias, buffer) => {
          const formulaBase = `AND(UPPER(TRIM($${colClasiLet}${rowHeader}))="${clase}", ISNUMBER($${colFechaLet}${rowHeader}), ROW()>${rowHeader})`;
          const diffFormula = `(TODAY() - INT($${colFechaLet}${rowHeader}))`;

          // VENCIDO (ROJO): > dias
          newRules.push(SpreadsheetApp.newConditionalFormatRule()
              .whenFormulaSatisfied(`=AND(${formulaBase}, ${diffFormula} > ${dias})`)
              .setBackground("#FF0000")
              .setFontColor("#FFFFFF")
              .setRanges(rangesToColor)
              .build());

          // POR VENCER (AMARILLO): Entre (dias - buffer) y dias
          const warningStart = dias - buffer;
          newRules.push(SpreadsheetApp.newConditionalFormatRule()
              .whenFormulaSatisfied(`=AND(${formulaBase}, ${diffFormula} >= ${warningStart}, ${diffFormula} <= ${dias})`)
              .setBackground("#FFFF00")
              .setFontColor("#000000")
              .setRanges(rangesToColor)
              .build());

          // A TIEMPO (VERDE): < warningStart
          newRules.push(SpreadsheetApp.newConditionalFormatRule()
              .whenFormulaSatisfied(`=AND(${formulaBase}, ${diffFormula} < ${warningStart})`)
              .setBackground("#00FF00")
              .setFontColor("#000000")
              .setRanges(rangesToColor)
              .build());
      };

      // Configuración: Clase, Límite, Buffer (Días de aviso antes del límite)
      addRulePair("A", 3, 1);    // Verde < 2, Amarillo 2-3, Rojo > 3
      addRulePair("AA", 15, 3);  // Verde < 12, Amarillo 12-15, Rojo > 15
      addRulePair("AAA", 30, 5); // Verde < 25, Amarillo 25-30, Rojo > 30
  });

  sheet.setConditionalFormatRules(newRules.concat(cleanRules));
  return true;
}

function setupConditionalFormatting() {
  const ui = SpreadsheetApp.getUi();
  const excludedSheets = [
      APP_CONFIG.logSheetName.toUpperCase(),
      APP_CONFIG.salesSheetName.toUpperCase(),
      APP_CONFIG.draftSheetName.toUpperCase()
  ];

  const allSheets = SS.getSheets();
  let logMsg = "";
  let count = 0;

  allSheets.forEach(sheet => {
    const sName = sheet.getName().trim();
    const sNameUpper = sName.toUpperCase();

    if (excludedSheets.includes(sNameUpper)) return;

    // Delegamos a la nueva función robusta
    if (applyTrafficLightToSheet(sheet)) {
       logMsg += `✅ ${sName}\n`;
       count++;
    }
  });

  if (count > 0) {
      ui.alert(`Semaforización aplicada a ${count} hojas:\n${logMsg}`);
  } else {
      ui.alert("⚠️ No se encontraron hojas aptas (con columnas CLASIFICACION y FECHA) para aplicar formato.");
  }
}
```

> **Nota:** `applyTrafficLightToSheet` colorea la hoja de Google Sheets **nativamente** (reglas de formato condicional reales de Sheets, visibles incluso fuera de la Web App) usando los mismos umbrales por `CLASIFICACION` (`A`=3 días/buffer 1, `AA`=15/3, `AAA`=30/5) que `getTrafficStyle` en el frontend (§20.3) — son dos implementaciones independientes del mismo semáforo de negocio, una en fórmulas de Sheets y otra en JS de cliente, que **deben mantenerse sincronizadas manualmente** si el negocio cambia los umbrales.

### 19.14 Integración con Gemini AI: `callGeminiAPI`, `transcribirConGemini` (⚠️ API key hardcodeada, ver nota) y deduplicación masiva `deduplicateAllSheets`

```js
function callGeminiAPI(prompt) {
  const apiKey = PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY') || '';
  if (!apiKey) return { success: false, text: '', message: 'GEMINI_API_KEY no configurada.' };

  const url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=' + apiKey;
  const payload = JSON.stringify({
    contents: [{ parts: [{ text: prompt }] }],
    generationConfig: { temperature: 0.4, maxOutputTokens: 512 }
  });

  try {
    const response = UrlFetchApp.fetch(url, {
      method: 'post',
      contentType: 'application/json',
      payload: payload,
      muteHttpExceptions: true
    });
    const code = response.getResponseCode();
    if (code !== 200) {
      return { success: false, text: '', message: 'Gemini HTTP ' + code + ': ' + response.getContentText() };
    }
    const json = JSON.parse(response.getContentText());
    const text = (json.candidates && json.candidates[0] && json.candidates[0].content &&
                  json.candidates[0].content.parts && json.candidates[0].content.parts[0].text) || '';
    return { success: true, text: text.trim() };
  } catch (e) {
    return { success: false, text: '', message: e.toString() };
  }
}
```

```js
function transcribirConGemini(base64Audio, mimeType) {
  // IMPORTANTE: Reemplazar con la API Key real del proyecto
  const API_KEY = "AIzaSyA7Lv551Quq7lMCynU7kRq9T1_MIaK6kkc";

  const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${API_KEY}`;

  const payload = {
    contents: [{
      parts: [
        { text: "Transcribe el siguiente audio exactamente como se escucha. Corrige ortografía básica. Solo dame el texto limpio en español." },
        {
          inline_data: {
            mime_type: mimeType || "audio/mp3",
            data: base64Audio
          }
        }
      ]
    }]
  };

  const options = {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  };

  try {
    const response = UrlFetchApp.fetch(url, options);
    const json = JSON.parse(response.getContentText());

    if (json.candidates && json.candidates[0].content) {
      return json.candidates[0].content.parts[0].text;
    } else {
      return "Error: No pude escuchar el audio claramente.";
    }
  } catch (e) {
    return "Error en el sistema: " + e.toString();
  }
}
```

> ## 🔑 Credencial expuesta confirmada: API key de Gemini hardcodeada en texto plano (línea 5809)
>
> A diferencia de `callGeminiAPI` (arriba), que correctamente lee la key desde `PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY')`, la función `transcribirConGemini` tiene una **API key de Google Gemini escrita literalmente en el código fuente**, comentada con `// IMPORTANTE: Reemplazar con la API Key real del proyecto` — es decir, el comentario indica que debería ser un placeholder, pero el valor presente (`AIzaSyA7Lv551Quq7lMCynU7kRq9T1_MIaK6kkc`) tiene el formato exacto de una key real de Google Cloud/Generative Language API (prefijo `AIzaSy`, 39 caracteres). Este valor queda expuesto a cualquiera con acceso de lectura al repositorio, igual que las contraseñas de `USER_DB` (§13).
>
> **Recomendación si se clona este sistema:** tratar esta key como comprometida — rotarla/revocarla en Google Cloud Console antes de desplegar, y refactorizar `transcribirConGemini` para leer de `PropertiesService` igual que `callGeminiAPI`, eliminando la duplicación de dos mecanismos distintos de gestión de credenciales para el mismo proveedor dentro del mismo archivo.

```js
function deduplicateAllSheets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheets = ss.getSheets();
  let totalDeleted = 0;

  // Mover el Set afuera del loop permite borrar duplicados cruzados entre hojas si así se desea,
  // pero el usuario especificó "de todas las hojas", y vimos que el bug replicó la misma tarea en la MISMA hoja repetidas veces.

  // We only want to run this on actual data sheets, not system/config sheets
  const excludeSheets = ["DB_DIRECTORY", "ESTATUS", "APP_CONFIG", "DASHBOARD", "PPC_BORRADOR"];

  for (let i = 0; i < sheets.length; i++) {
    const sheet = sheets[i];
    const sheetName = sheet.getName();

    if (excludeSheets.some(ex => sheetName.includes(ex))) {
      continue;
    }

    const data = sheet.getDataRange().getValues();
    if (data.length <= 1) continue; // Skip empty sheets or just headers

    let headerRowIndex = -1;
    let headers = [];
    let folioIdx = -1;
    let conceptoIdx = -1;
    let fechaIdx = -1;

    // Buscar la fila de encabezados en las primeras 20 filas
    for (let r = 0; r < Math.min(20, data.length); r++) {
      const currentHeaders = data[r].map(h => String(h).toUpperCase().trim());
      const fIdx = currentHeaders.findIndex(h => h === "FOLIO" || h === "ID");
      const cIdx = currentHeaders.findIndex(h => h === "CONCEPTO" || h === "DESCRIPCION" || h === "TAREA" || h === "DESCRIPCIÓN");

      if (fIdx > -1 && cIdx > -1) {
        headerRowIndex = r;
        headers = currentHeaders;
        folioIdx = fIdx;
        conceptoIdx = cIdx;
        fechaIdx = currentHeaders.findIndex(h => h === "FECHA" || h === "F. INICIO" || h.includes("FECHA"));
        break;
      }
    }

    // Si no encuentra columnas clave, es mejor omitir la hoja que borrar a ciegas
    if (headerRowIndex === -1 || conceptoIdx === -1) continue;

    const seenFolios = new Set();
    const seenCombos = new Set();
    const rowsToDelete = [];

    // Go from top to bottom to identify duplicates starting AFTER the header row
    for (let r = headerRowIndex + 1; r < data.length; r++) {
      const row = data[r];
      let isDuplicate = false;

      const folio = folioIdx > -1 ? row[folioIdx] : "";
      const folioStr = String(folio).trim();

      // ALWAYS check by concept + date FIRST to catch duplicates with DIFFERENT folios
      const concept = conceptoIdx > -1 ? row[conceptoIdx] : "";
      const dateRaw = fechaIdx > -1 ? row[fechaIdx] : "";

      let dateStr = "";
      if (dateRaw instanceof Date) {
          // just standard format for comparison
          dateStr = dateRaw.toISOString().split('T')[0];
      } else {
          dateStr = String(dateRaw).trim();
      }

      const conceptStr = String(concept).trim().toUpperCase().substring(0, 50);

      if (conceptStr !== "") {
          const comboKey = conceptStr + "|||" + dateStr;
          if (seenCombos.has(comboKey)) {
              isDuplicate = true;
          } else {
              seenCombos.add(comboKey);
          }
      }

      // If not marked as duplicate by concept, check by FOLIO
      if (!isDuplicate && folioStr !== "" && folioStr !== "SIN-FOLIO") {
        if (seenFolios.has(folioStr)) {
          isDuplicate = true;
        } else {
          seenFolios.add(folioStr);
        }
      }

      if (isDuplicate) {
        // Row to delete is r + 1 (1-based index in sheets)
        rowsToDelete.push(r + 1);
      }
    }

    // Delete rows from bottom to top to preserve indices
    if (rowsToDelete.length > 0) {
      Logger.log(`Found ${rowsToDelete.length} duplicates in sheet ${sheetName}`);
      for (let j = rowsToDelete.length - 1; j >= 0; j--) {
        sheet.deleteRow(rowsToDelete[j]);
        totalDeleted++;
      }
    }
  }

  Logger.log(`Total duplicate rows deleted across all sheets: ${totalDeleted}`);
  return totalDeleted;
}
```

> **Nota:** `deduplicateAllSheets` es una herramienta de **reparación manual retroactiva** (se ejecuta a mano desde el editor de Apps Script cuando ya ocurrió una duplicación, ej. por el bug histórico que documentan `test_deduplication.js`/`test_duplication_issue.js`, §14) — no es un guardia preventivo que corra automáticamente. La prevención real en tiempo de escritura es el Gatekeeper de `internalBatchUpdateTasks` (§10.3, Anexo A §19.3). Nótese que su criterio de "duplicado" (mismo `CONCEPTO`+`FECHA`, o mismo `FOLIO`) es el mismo patrón usado en el Gatekeeper — es intencional, para que la limpieza retroactiva sea consistente con la regla de prevención hacia adelante.

### 19.15 Banco de Información: `apiFetchInfoBankCompanies`, `apiFetchInfoBankData`, `apiFetchDistinctClients` (líneas 4995–5181)

```js
function apiFetchInfoBankCompanies(year, monthName) {
  try {
    const sheetName = "ANTONIA_VENTAS";
    const res = internalFetchSheetData(sheetName);
    if (!res.success) return { success: false, message: res.message };

    const monthMap = {
        'ENERO': 0, 'FEBRERO': 1, 'MARZO': 2, 'ABRIL': 3, 'MAYO': 4, 'JUNIO': 5,
        'JULIO': 6, 'AGOSTO': 7, 'SEPTIEMBRE': 8, 'OCTUBRE': 9, 'NOVIEMBRE': 10, 'DICIEMBRE': 11
    };
    const targetMonth = monthMap[String(monthName).toUpperCase().trim()];
    const targetYear = parseInt(year) || new Date().getFullYear();

    if (targetMonth === undefined) return { success: false, message: "Mes inválido" };

    const clients = new Set();
    const allData = [...res.data, ...(res.history || [])];

    allData.forEach(row => {
       // Helper para buscar valores insensible a mayúsculas
       const keys = Object.keys(row);
       const upperKeys = keys.map(k => k.toUpperCase().trim());
       const getVal = (targetKeys) => {
           for (const t of targetKeys) {
               const idx = upperKeys.indexOf(t);
               if (idx > -1) return row[keys[idx]];
           }
           return null;
       };

       const dateVal = getVal(['FECHA INICIO', 'F. INICIO', 'F. VISITA', 'F. ENTREGA', 'FECHA_INICIO', 'FECHA DE INICIO', 'FECHA', 'ALTA', 'FECHA ALTA', 'FECHA_ALTA', 'FECHA VISITA']);

       if (!dateVal) return;

       let dObj = null;
       if (dateVal instanceof Date) {
           dObj = dateVal;
       } else {
           // Try parsing string dd/mm/yy
           const parts = String(dateVal).split('/');
           if (parts.length === 3) {
               let y = parseInt(parts[2]);
               if (y < 100) y += 2000;
               dObj = new Date(y, parseInt(parts[1])-1, parseInt(parts[0]));
           } else {
               const parsed = new Date(dateVal);
               if (!isNaN(parsed.getTime())) dObj = parsed;
           }
       }

       if (!dObj || isNaN(dObj.getTime())) return;
       if (dObj.getMonth() !== targetMonth) return;
       if (dObj.getFullYear() !== targetYear) return;

       const c = String(getVal(['CLIENTE']) || '').toUpperCase().trim();
       if (c) clients.add(c);
    });

    return { success: true, data: Array.from(clients).sort() };
  } catch(e) {
    return { success: false, message: e.toString() };
  }
}

function apiFetchInfoBankData(year, monthName, companyName, folderName) {
  try {
    const sheetName = "ANTONIA_VENTAS";
    const res = internalFetchSheetData(sheetName);
    if (!res.success) return { success: false, message: res.message };

    const monthMap = {
        'ENERO': 0, 'FEBRERO': 1, 'MARZO': 2, 'ABRIL': 3, 'MAYO': 4, 'JUNIO': 5,
        'JULIO': 6, 'AGOSTO': 7, 'SEPTIEMBRE': 8, 'OCTUBRE': 9, 'NOVIEMBRE': 10, 'DICIEMBRE': 11
    };
    const targetMonth = monthMap[String(monthName).toUpperCase().trim()];
    const targetYear = parseInt(year) || 2025;
    const targetCompany = String(companyName).toUpperCase().trim();

    if (targetMonth === undefined) return { success: false, message: "Mes inválido" };

    const allData = [...res.data, ...(res.history || [])];

    // Filtrar datos
    const filtered = allData.filter(row => {
       // Helper para buscar valores insensible a mayúsculas
       const keys = Object.keys(row);
       const upperKeys = keys.map(k => k.toUpperCase().trim());
       const getVal = (targetKeys) => {
           for (const t of targetKeys) {
               const idx = upperKeys.indexOf(t);
               if (idx > -1) return row[keys[idx]];
           }
           return null;
       };

       // 1. Company Match (Loose)
       const rowClient = String(getVal(['CLIENTE']) || '').toUpperCase().trim();
       if (!rowClient) return false;

       // Check bidirectional inclusion to handle variations
       if (!rowClient.includes(targetCompany) && !targetCompany.includes(rowClient)) return false;

       // 2. Date Match (Prioridad: FECHA INICIO)
       // Se prioriza 'FECHA INICIO' tal cual pidió el usuario, luego fallbacks.
       const dateVal = getVal(['FECHA INICIO', 'F. INICIO', 'F. VISITA', 'F. ENTREGA', 'FECHA_INICIO', 'FECHA DE INICIO', 'FECHA', 'ALTA', 'FECHA ALTA', 'FECHA_ALTA', 'FECHA VISITA']);

       if (!dateVal) return false;

       let dObj = null;
       if (dateVal instanceof Date) {
           dObj = dateVal;
       } else {
           // Try parsing string dd/mm/yy
           const parts = String(dateVal).split('/');
           if (parts.length === 3) {
               let y = parseInt(parts[2]);
               if (y < 100) y += 2000;
               dObj = new Date(y, parseInt(parts[1])-1, parseInt(parts[0]));
           } else {
               const parsed = new Date(dateVal);
               if (!isNaN(parsed.getTime())) dObj = parsed;
           }
       }

       if (!dObj || isNaN(dObj.getTime())) return false;
       if (dObj.getMonth() !== targetMonth) return false;
       if (dObj.getFullYear() !== targetYear) return false;

       return true;
    });

    // NORMALIZACION DE DATOS PARA EL FRONTEND (SOLICITUD USUARIO)
    const mappedData = filtered.map(row => {
       const keys = Object.keys(row);
       const upperKeys = keys.map(k => k.toUpperCase().trim());
       const getVal = (targetKeys) => {
           for (const t of targetKeys) {
               const idx = upperKeys.indexOf(t);
               if (idx > -1) return row[keys[idx]];
           }
           return "";
       };

       return {
           'FECHA_INICIO': getVal(['FECHA INICIO', 'FECHA_INICIO', 'FECHA DE INICIO', 'FECHA', 'ALTA', 'FECHA ALTA', 'FECHA_ALTA', 'FECHA VISITA']),
           'AREA': getVal(['AREA', 'DEPARTAMENTO', 'ESPECIALIDAD']),
           'CONCEPTO': getVal(['CONCEPTO', 'DESCRIPCION', 'DESCRIPCIÓN', 'ACTIVIDAD']),
           'VENDEDOR': getVal(['VENDEDOR', 'RESPONSABLE', 'ENCARGADO', 'INVOLUCRADOS']),
           'ESTATUS': getVal(['ESTATUS', 'STATUS', 'ESTADO']),
           'FOLIO': getVal(['FOLIO', 'ID']),
           'COTIZACION': getVal(['COTIZACION', 'ARCHIVO', 'LINK', 'URL', 'PDF'])
       };
    });

    return { success: true, data: mappedData };
  } catch(e) {
    return { success: false, message: e.toString() };
  }
}

function apiFetchDistinctClients() {
  try {
    const sheetName = "ANTONIA_VENTAS";
    const res = internalFetchSheetData(sheetName);
    if (!res.success) return { success: false, message: res.message };

    const clients = new Set();

    const allData = [...res.data, ...(res.history || [])];

    allData.forEach(row => {
        if (row['CLIENTE']) {
            const c = String(row['CLIENTE']).trim().toUpperCase();
            if (c) clients.add(c);
        }
    });

    const sortedClients = Array.from(clients).sort();
    return { success: true, data: sortedClients };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}
```

> **Nota:** las tres funciones leen **exclusivamente** de `ANTONIA_VENTAS` (nunca de las hojas individuales de los vendedores) — el Banco de Información es, por diseño, una vista analítica centrada en el histórico consolidado de Ventas, no un buscador global de archivos de todo el sistema. `internalFetchSheetData` (usada internamente) ya separa filas activas (`res.data`) de las archivadas bajo el separador `"TAREAS REALIZADAS"` (`res.history`, §5.3) — estas tres funciones concatenan ambas listas para no perder cotizaciones ya cerradas.

### 19.16 Agenda personal y hábitos: `apiFetchCombinedCalendarData`, `apiFetchUnifiedAgenda`, `apiSavePersonalEvent`, `apiSaveHabitLog` (líneas 5670–5802)

```js
function apiFetchCombinedCalendarData(sheetName) {
  try {
      const results = [];
      const baseName = String(sheetName).replace(/\s*\(VENTAS\)/i, "").trim();
      // Si es ANTONIA_VENTAS, solo buscamos ahí (ella distribuye)
      const targets = (baseName.toUpperCase() === "ANTONIA_VENTAS") ? ["ANTONIA_VENTAS"] : [baseName, baseName + " (VENTAS)"];

      targets.forEach(t => {
          const res = internalFetchSheetData(t);
          if (res.success && res.data) {
              results.push(...res.data);
          }
      });

      // --- ADDED: Personal Agenda Integration for Dashboard ---
      const personalRes = internalFetchSheetData("AGENDA_PERSONAL");
      if (personalRes.success && personalRes.data) {
          const myEvents = personalRes.data.filter(e => String(e.USUARIO).trim().toUpperCase() === baseName.toUpperCase());
          const mappedEvents = myEvents.map(e => ({
              ...e,
              CONCEPTO: e.TITULO || e.CONCEPTO,
              CLIENTE: "PERSONAL"
          }));
          results.push(...mappedEvents);
      }
      // --------------------------------------------------------

      // Deduplicate by ID/FOLIO
      const uniqueTasks = {};
      results.forEach(r => {
          const id = r.ID || r.FOLIO || (r.CONCEPTO ? r.CONCEPTO + r.FECHA : null);
          if (id) uniqueTasks[id] = r;
      });

      const finalData = Object.values(uniqueTasks);

      return { success: true, data: finalData };
  } catch(e) {
      return { success: false, message: e.toString() };
  }
}

function apiFetchUnifiedAgenda(username) {
  // 1. Fetch Work Tasks (Existing Logic)
  let workTasks = [];
  try {
     // Determine target for work tasks based on role/user
     let target = username;
     if (String(username).toUpperCase() === 'ANTONIA_VENTAS') target = "ANTONIA_VENTAS";

     const workRes = apiFetchCombinedCalendarData(target);
     if (workRes.success) {
         // Filter out Personal Events to avoid duplication (fetched separately below)
         workTasks = workRes.data.filter(t => t.CLIENTE !== "PERSONAL");
     }
  } catch(e) { console.error("Error fetching work tasks", e); }

  // 2. Fetch Personal Events
  let personalEvents = [];
  try {
     const sheet = findSheetSmart("AGENDA_PERSONAL");
     if (sheet) {
        const res = internalFetchSheetData("AGENDA_PERSONAL");
        if(res.success) {
            // Filter by user if possible, for now return all found
            personalEvents = res.data.filter(r => !r.USUARIO || r.USUARIO === username);
        }
     } else {
        // MOCK DATA FOR DEMO IF SHEET DOESN'T EXIST
        const today = new Date();
        const y = today.getFullYear();
        const m = today.getMonth(); // 0-indexed
        const d = today.getDate();

        personalEvents = [
            { ID: 'P-1', TITULO: 'Rutina Mañana', TIPO: 'PERSONAL', HORA_INICIO: '06:00', HORA_FIN: '07:00', DETALLES: 'Meditación y Café', FECHA: new Date(y, m, d), CLASIFICACION: 'PERSONAL' },
            { ID: 'P-2', TITULO: 'Gimnasio', TIPO: 'PERSONAL', HORA_INICIO: '07:30', HORA_FIN: '08:30', DETALLES: 'Cardio', FECHA: new Date(y, m, d), CLASIFICACION: 'SALUD' },
            { ID: 'P-3', TITULO: 'Comida', TIPO: 'COMIDA', HORA_INICIO: '14:00', HORA_FIN: '15:00', DETALLES: 'Pollo y Arroz', FECHA: new Date(y, m, d), CLASIFICACION: 'SALUD' }
        ];
     }
  } catch(e) { console.error("Error fetching personal events", e); }

  // 3. Fetch Habits
  let habits = [];
  try {
      const sheet = findSheetSmart("HABITOS_LOG");
      if (sheet) {
         const res = internalFetchSheetData("HABITOS_LOG");
         if (res.success) habits = res.data.filter(r => !r.USUARIO || r.USUARIO === username);
      } else {
         // MOCK DATA
         habits = [
             { ID: 'H1', HABITO: 'Leer 30min', META: 5, LOG_JSON: JSON.stringify([true, true, false, true, false, false, false]) },
             { ID: 'H2', HABITO: 'Ejercicio', META: 4, LOG_JSON: JSON.stringify([false, true, true, false, false, false, false]) },
             { ID: 'H3', HABITO: 'Meditar', META: 7, LOG_JSON: JSON.stringify([true, true, true, true, true, false, false]) }
         ];
      }
  } catch(e) { console.error("Error fetching habits", e); }

  return { success: true, workTasks: workTasks, personalEvents: personalEvents, habits: habits };
}

function apiSavePersonalEvent(eventData) {
    // Ensure sheet exists
    let sheet = findSheetSmart("AGENDA_PERSONAL");
    if (!sheet) {
        sheet = SS.insertSheet("AGENDA_PERSONAL");
        sheet.appendRow(["ID", "USUARIO", "TITULO", "TIPO", "FECHA", "HORA_INICIO", "HORA_FIN", "DETALLES", "CLASIFICACION", "ESTATUS"]);
    }
    return internalBatchUpdateTasks("AGENDA_PERSONAL", [eventData]);
}

function apiSaveHabitLog(habitData) {
    // Ensure sheet exists
    let sheet = findSheetSmart("HABITOS_LOG");
    if (!sheet) {
        sheet = SS.insertSheet("HABITOS_LOG");
        sheet.appendRow(["ID", "USUARIO", "HABITO", "META", "LOG_JSON", "FECHA_ACTUALIZACION"]);
    }
    // If saving a habit update, we might need to find the existing row.
    // internalBatchUpdateTasks handles updates by ID/FOLIO.
    return internalBatchUpdateTasks("HABITOS_LOG", [habitData]);
}
```

### 19.17 Agente narrativo de cotizaciones con Gemini: `runQuoteMetricsAgent`, `apiGetLastAgentReport`, `_sendAgentEmail` (líneas 1730–1946)

Este es el pipeline completo del "agente de IA" más elaborado del sistema: calcula métricas → aplica un motor de reglas propio → arma un prompt en español para Gemini → envía el reporte por correo con `MailApp` (un **tercer canal de notificación**, nativo de Google Workspace, distinto tanto del webhook de Make.com/Outlook §11.2 como de cualquier llamada a Gemini para transcripción). Se invoca automáticamente desde el trigger diario `autoUpdateQuoteMetrics` (§12) o manualmente desde la UI.

```js
function runQuoteMetricsAgent(params) {
  try {
    const p = params || {};
    const now = new Date();
    const month = (p.month !== undefined) ? parseInt(p.month) : (now.getMonth() + 1);
    const year  = (p.year  !== undefined) ? parseInt(p.year)  : now.getFullYear();

    // ── 1. OBTENER MÉTRICAS ────────────────────────────────────────
    const mResult = apiFetchQuoteAgentMetrics({ month, year });
    if (!mResult.success) return { success: false, message: 'No se pudieron obtener métricas: ' + mResult.message };
    const m = mResult.metrics;

    // ── 2. MOTOR DE REGLAS ─────────────────────────────────────────
    const alerts = [];

    // Regla 1: SLA por clasificación < 70% (con mínimo 3 casos)
    ['A', 'AA', 'AAA'].forEach(k => {
      const s = m.slaSummary[k];
      if (s.count >= 3 && s.pctOk < 70) {
        alerts.push({
          type: 'SLA_BAJO',
          severity: 'ALTA',
          icon: '🔴',
          mensaje: 'Clase ' + k + ': solo ' + s.pctOk + '% de cumplimiento SLA (' + s.ok + '/' + s.count + ' a tiempo, límite ' + s.slaLimit + ' días)'
        });
      }
    });

    // Regla 2: Cotizador con tasa de pérdida > 50% (con mínimo 3 cot.)
    m.byCotizadorArr.forEach(c => {
      if (c.total >= 3 && (c.perdidas / c.total) > 0.5) {
        const pct = Math.round(c.perdidas / c.total * 100);
        alerts.push({
          type: 'ALTA_PERDIDA',
          severity: 'MEDIA',
          icon: '🟡',
          mensaje: c.name + ': ' + pct + '% de cotizaciones perdidas este mes (' + c.perdidas + ' de ' + c.total + ')'
        });
      }
    });

    // Regla 3: Tasa de cierre global < 30% (con mínimo 5 cot.)
    if (m.winLoss.total >= 5) {
      const globalPct = Math.round(m.winLoss.ganada / m.winLoss.total * 100);
      if (globalPct < 30) {
        alerts.push({
          type: 'CIERRE_BAJO',
          severity: 'ALTA',
          icon: '🔴',
          mensaje: 'Tasa de cierre global muy baja: ' + globalPct + '% (' + m.winLoss.ganada + ' ganadas de ' + m.winLoss.total + ' terminadas)'
        });
      }
    }

    // Regla 4: AAA sin cierre definido (ni ganada ni perdida)
    const aaaAbiertos = (m.byClasi && m.byClasi['AAA']) ? m.byClasi['AAA'].count - m.slaSummary.AAA.ok - m.slaSummary.AAA.fail + m.slaSummary.AAA.ok : 0;
    m.aaaByClientArr.forEach(cl => {
      const enProceso = cl.projects.filter(p => !p.isGanada && !p.isPerdida).length;
      if (enProceso > 0) {
        alerts.push({
          type: 'AAA_SIN_RESULTADO',
          severity: 'INFO',
          icon: '🔵',
          mensaje: 'Cliente ' + cl.cliente + ': ' + enProceso + ' proyecto(s) AAA terminados sin marcar GANADA/PERDIDA'
        });
      }
    });

    // ── 3. CONSTRUIR PROMPT PARA GEMINI ───────────────────────────
    const MONTHS_ES = ['enero','febrero','marzo','abril','mayo','junio','julio','agosto','septiembre','octubre','noviembre','diciembre'];
    const monthName = MONTHS_ES[month - 1];
    const top5 = m.byCotizadorArr.slice(0, 5);

    const prompt = [
      'Eres analista de ventas de Holtmont, empresa mexicana de construcción e ingeniería.',
      'Redacta un reporte ejecutivo CONCISO (máx 180 palabras) en español profesional para el mes de ' + monthName + ' ' + year + '.',
      '',
      'DATOS DEL MES:',
      '- Total cotizaciones terminadas: ' + m.totalCount,
      '- Ganadas: ' + m.winLoss.ganada + ' | Perdidas: ' + m.winLoss.perdida + ' | % Cierre: ' + (m.winLoss.total > 0 ? Math.round(m.winLoss.ganada / m.winLoss.total * 100) : 0) + '%',
      '',
      'SLA por clasificación:',
      '  Clase A  (límite 3d):  ' + m.slaSummary.A.count  + ' cot., ' + m.slaSummary.A.pctOk  + '% a tiempo, prom. ' + (m.slaSummary.A.avgDays  || 'N/D') + 'd',
      '  Clase AA (límite 14d): ' + m.slaSummary.AA.count + ' cot., ' + m.slaSummary.AA.pctOk + '% a tiempo, prom. ' + (m.slaSummary.AA.avgDays || 'N/D') + 'd',
      '  Clase AAA(límite 30d): ' + m.slaSummary.AAA.count+ ' cot., ' + m.slaSummary.AAA.pctOk+ '% a tiempo, prom. ' + (m.slaSummary.AAA.avgDays|| 'N/D') + 'd',
      '',
      'Top cotizadores:',
      top5.map(c => '  ' + c.name + ': ' + c.total + ' cot., ' + c.ganadas + ' ganadas, ' + c.slaOk + ' SLA OK').join('\n'),
      '',
      alerts.length > 0
        ? 'Alertas detectadas:\n' + alerts.map(a => '  ' + a.icon + ' ' + a.mensaje).join('\n')
        : 'Sin alertas críticas este mes.',
      '',
      'Instrucciones: sé directo, sin saludos. Menciona lo más importante (desempeño general, mejor cotizador, punto débil) y termina con UNA recomendación concreta.'
    ].join('\n');

    // ── 4. LLAMAR A GEMINI ────────────────────────────────────────
    const geminiResult = callGeminiAPI(prompt);
    const geminiSummary = geminiResult.success ? geminiResult.text : '(Gemini no disponible: ' + geminiResult.message + ')';

    // ── 5. ENVIAR EMAIL DE REPORTE ────────────────────────────────
    const emailResult = _sendAgentEmail(m, alerts, geminiSummary, monthName, year);

    // ── 6. GUARDAR ÚLTIMO REPORTE EN PROPIEDADES ──────────────────
    const lastRun = {
      timestamp  : now.getTime(),
      timestampStr: Utilities.formatDate(now, 'America/Mexico_City', 'dd/MM/yyyy HH:mm'),
      month, year,
      alerts,
      geminiSummary,
      totalCount  : m.totalCount,
      ganadas     : m.winLoss.ganada,
      perdidas    : m.winLoss.perdida,
      emailSent   : emailResult.success
    };
    PropertiesService.getScriptProperties().setProperty('LAST_AGENT_RUN', JSON.stringify(lastRun));
    registrarLog('AGENT', 'RUN_COMPLETE', 'Agente ejecutado. Alertas: ' + alerts.length + '. Email: ' + (emailResult.success ? 'OK' : 'FALLO'));

    return { success: true, lastRun };
  } catch (e) {
    console.error('runQuoteMetricsAgent Error: ' + e.toString());
    return { success: false, message: e.toString() };
  }
}

/* Devuelve el último reporte del agente (para mostrarlo en el panel) */
function apiGetLastAgentReport() {
  try {
    const raw = PropertiesService.getScriptProperties().getProperty('LAST_AGENT_RUN') || '';
    if (!raw) return { success: true, hasReport: false };
    return { success: true, hasReport: true, lastRun: JSON.parse(raw) };
  } catch (e) {
    return { success: false, message: e.toString() };
  }
}

/* Genera y envía el email HTML del reporte */
function _sendAgentEmail(m, alerts, geminiSummary, monthName, year) {
  try {
    // Destinatarios: ANTONIA_VENTAS + ADMIN
    const recipients = [];
    if (USER_DB['ANTONIA_VENTAS'] && USER_DB['ANTONIA_VENTAS'].email) recipients.push(USER_DB['ANTONIA_VENTAS'].email);
    if (USER_DB['LUIS_CARLOS']    && USER_DB['LUIS_CARLOS'].email)    recipients.push(USER_DB['LUIS_CARLOS'].email);

    if (recipients.length === 0) return { success: false, message: 'Sin destinatarios configurados.' };

    const closePct = m.winLoss.total > 0 ? Math.round(m.winLoss.ganada / m.winLoss.total * 100) : 0;
    const alertRows = alerts.length > 0
      ? alerts.map(a => '<tr><td style="padding:6px 12px;">' + a.icon + '</td><td style="padding:6px 12px;color:#333;">' + a.mensaje + '</td><td style="padding:6px 12px;"><span style="background:' + (a.severity==='ALTA'?'#dc3545':a.severity==='MEDIA'?'#fd7e14':'#17a2b8') + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;">' + a.severity + '</span></td></tr>').join('')
      : '<tr><td colspan="3" style="padding:8px 12px;color:#28a745;">✅ Sin alertas críticas este mes</td></tr>';

    const cotizRows = m.byCotizadorArr.slice(0, 8).map(c => {
      const pct = c.total > 0 ? Math.round(c.ganadas / c.total * 100) : 0;
      return '<tr style="border-bottom:1px solid #eee;"><td style="padding:5px 10px;">' + c.name + '</td><td style="text-align:center;padding:5px 10px;">' + c.total + '</td><td style="text-align:center;padding:5px 10px;color:#28a745;">' + c.ganadas + '</td><td style="text-align:center;padding:5px 10px;color:#dc3545;">' + c.perdidas + '</td><td style="text-align:center;padding:5px 10px;font-weight:bold;">' + pct + '%</td><td style="text-align:center;padding:5px 10px;">' + c.slaOk + ' / ' + c.slaFail + '</td></tr>';
    }).join('');

    const html = [
      '<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;background:#fff;">',
      '<div style="background:#1E3A5F;color:#fff;padding:24px;">',
      '<h1 style="margin:0;font-size:22px;">📊 Reporte de Cotizaciones — ' + monthName.charAt(0).toUpperCase() + monthName.slice(1) + ' ' + year + '</h1>',
      '<p style="margin:4px 0 0;font-size:13px;opacity:0.8;">Generado automáticamente por el Agente de Métricas · Holtmont Workspace</p>',
      '</div>',
      '<div style="padding:24px;">',
      // KPI cards
      '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px;">',
      '<div style="flex:1;min-width:140px;background:#f8f9fa;border-top:4px solid #00d2ff;padding:12px;border-radius:8px;text-align:center;"><div style="font-size:28px;font-weight:bold;color:#00d2ff;">' + m.totalCount + '</div><div style="font-size:12px;color:#666;">Terminadas</div></div>',
      '<div style="flex:1;min-width:140px;background:#f8f9fa;border-top:4px solid #28a745;padding:12px;border-radius:8px;text-align:center;"><div style="font-size:28px;font-weight:bold;color:#28a745;">' + m.winLoss.ganada + '</div><div style="font-size:12px;color:#666;">✅ Ganadas</div></div>',
      '<div style="flex:1;min-width:140px;background:#f8f9fa;border-top:4px solid #dc3545;padding:12px;border-radius:8px;text-align:center;"><div style="font-size:28px;font-weight:bold;color:#dc3545;">' + m.winLoss.perdida + '</div><div style="font-size:12px;color:#666;">❌ Perdidas</div></div>',
      '<div style="flex:1;min-width:140px;background:#f8f9fa;border-top:4px solid #ffc107;padding:12px;border-radius:8px;text-align:center;"><div style="font-size:28px;font-weight:bold;color:#ffc107;">' + closePct + '%</div><div style="font-size:12px;color:#666;">🎯 % Cierre</div></div>',
      '</div>',
      // Gemini summary
      '<div style="background:#f0f7ff;border-left:4px solid #00d2ff;padding:16px;border-radius:4px;margin-bottom:24px;">',
      '<p style="font-size:12px;font-weight:bold;color:#00d2ff;margin:0 0 8px;">🤖 ANÁLISIS IA (Gemini)</p>',
      '<p style="margin:0;color:#333;line-height:1.6;">' + geminiSummary.replace(/\n/g, '<br>') + '</p>',
      '</div>',
      // Alertas
      '<h3 style="color:#1E3A5F;margin-bottom:12px;">⚠️ Alertas del Agente</h3>',
      '<table style="width:100%;border-collapse:collapse;font-size:13px;background:#f8f9fa;border-radius:8px;overflow:hidden;margin-bottom:24px;">',
      alertRows,
      '</table>',
      // SLA
      '<h3 style="color:#1E3A5F;margin-bottom:12px;">⏱️ SLA por Clasificación</h3>',
      '<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:24px;">',
      '<thead><tr style="background:#1E3A5F;color:#fff;"><th style="padding:8px 12px;text-align:left;">Clase</th><th style="padding:8px 12px;text-align:center;">Total</th><th style="padding:8px 12px;text-align:center;">✅ A tiempo</th><th style="padding:8px 12px;text-align:center;">❌ Tarde</th><th style="padding:8px 12px;text-align:center;">% Cumpl.</th><th style="padding:8px 12px;text-align:center;">Prom. días</th></tr></thead>',
      '<tbody>',
      ['A','AA','AAA'].map(k => {
        const s = m.slaSummary[k];
        const color = s.pctOk >= 80 ? '#28a745' : s.pctOk >= 60 ? '#fd7e14' : '#dc3545';
        return '<tr style="border-bottom:1px solid #eee;"><td style="padding:7px 12px;font-weight:bold;">' + k + ' (≤' + s.slaLimit + 'd)</td><td style="text-align:center;padding:7px 12px;">' + s.count + '</td><td style="text-align:center;padding:7px 12px;color:#28a745;">' + s.ok + '</td><td style="text-align:center;padding:7px 12px;color:#dc3545;">' + s.fail + '</td><td style="text-align:center;padding:7px 12px;font-weight:bold;color:' + color + ';">' + s.pctOk + '%</td><td style="text-align:center;padding:7px 12px;">' + (s.avgDays || 'N/D') + 'd</td></tr>';
      }).join(''),
      '</tbody></table>',
      // Por cotizador
      '<h3 style="color:#1E3A5F;margin-bottom:12px;">👤 Desempeño por Cotizador</h3>',
      '<table style="width:100%;border-collapse:collapse;font-size:13px;">',
      '<thead><tr style="background:#1E3A5F;color:#fff;"><th style="padding:8px 10px;text-align:left;">Cotizador</th><th style="padding:8px 10px;text-align:center;">Total</th><th style="padding:8px 10px;text-align:center;">Ganadas</th><th style="padding:8px 10px;text-align:center;">Perdidas</th><th style="padding:8px 10px;text-align:center;">% Cierre</th><th style="padding:8px 10px;text-align:center;">SLA OK/Fail</th></tr></thead>',
      '<tbody>' + cotizRows + '</tbody>',
      '</table>',
      '</div>',
      '<div style="background:#f8f9fa;padding:12px 24px;font-size:11px;color:#999;border-top:1px solid #eee;">',
      'Holtmont Workspace — Agente Automático de Métricas · ' + Utilities.formatDate(new Date(), 'America/Mexico_City', 'dd/MM/yyyy HH:mm'),
      '</div></div>'
    ].join('');

    recipients.forEach(email => {
      MailApp.sendEmail({
        to: email,
        subject: '📊 Reporte Cotizaciones ' + monthName.charAt(0).toUpperCase() + monthName.slice(1) + ' ' + year + (alerts.length > 0 ? ' — ⚠️ ' + alerts.length + ' alerta(s)' : ''),
        htmlBody: html
      });
    });

    return { success: true, sentTo: recipients };
  } catch (e) {
    console.error('_sendAgentEmail Error: ' + e.toString());
    return { success: false, message: e.toString() };
  }
}
```

**Reglas del motor de alertas (ejecutan en este orden, todas pueden dispararse en la misma corrida):**

| # | Regla | Umbral | Severidad |
|---|---|---|---|
| 1 | SLA bajo por clasificación | `pctOk < 70%` con `count >= 3` casos, por cada clase `A`/`AA`/`AAA` | 🔴 ALTA |
| 2 | Cotizador con alta pérdida | `perdidas/total > 50%` con `total >= 3` cotizaciones | 🟡 MEDIA |
| 3 | Cierre global bajo | Tasa de cierre `< 30%` con `total >= 5` cotizaciones terminadas | 🔴 ALTA |
| 4 | AAA sin resultado | Cliente con proyectos clasificación `AAA` "terminados" pero sin marcar `GANADA` ni `PERDIDA` | 🔵 INFO |

`_sendAgentEmail` envía el reporte HTML **solo** a `ANTONIA_VENTAS` y `LUIS_CARLOS` (sus correos en `USER_DB`) vía `MailApp.sendEmail` — este es el **único** punto del sistema que usa `MailApp` (correo nativo de Gmail/Workspace); todo lo demás relacionado a notificaciones pasa por el webhook de Make.com/Outlook (§11.2). Si ninguno de los dos tiene `email` configurado en `USER_DB`, la función retorna `{success: false, message: 'Sin destinatarios configurados.'}` sin lanzar excepción.

### 19.18 Agente narrativo de productividad de Trackers: `apiFetchTrackerProductivityMetrics`, `runTrackerProductivityAgent`, `_sendTrackerProductivityEmail` (⚠️ contiene un bug silencioso, ver nota) (líneas 909–1240)

Es la contraparte de §19.17 pero para el volumen/puntualidad de tareas en los Trackers individuales (no cotizaciones de Ventas): mismo patrón — motor de métricas → reglas de alerta → prompt a Gemini → email HTML vía `MailApp`.

```js
function apiFetchTrackerProductivityMetrics(params) {
  try {
    const p = params || {};
    const now = new Date();
    const targetMonth = (p.month !== undefined && p.month !== null) ? parseInt(p.month) : (now.getMonth() + 1);
    const targetYear  = (p.year  !== undefined && p.year  !== null) ? parseInt(p.year)  : now.getFullYear();

    // Directory lookup to filter only ESTANDAR and HIBRIDO and exclude VENTAS sheets
    const allowedStaff = [];
    const deptMap = {};
    INITIAL_DIRECTORY.forEach(emp => {
      if (emp.type === 'ESTANDAR' || emp.type === 'HIBRIDO') {
        if (emp.name) {
          const uName = emp.name.toUpperCase().trim();
          allowedStaff.push(uName);
          deptMap[uName] = emp.dept || 'SIN DEPT';
        }
      }
    });

    const deptStats = {};
    const collabStats = {};
    const priorityStats = { 'ALTA': 0, 'MEDIA': 0, 'BAJA': 0, 'SIN_PRIORIDAD': 0 };

    let totalTasks = 0;
    let onTimeTasks = 0;
    let lateTasks = 0;
    let tasksWithRestrictions = 0;
    let tasksWithRisks = 0;
    let totalDurationDays = 0;
    let tasksWithDuration = 0;

    // Helper Date Parser
    const parseDate = (d) => {
      if (!d) return null;
      if (d instanceof Date) return isNaN(d.getTime()) ? null : d;
      if (typeof d === 'number') return new Date(d);
      const s = String(d).trim();
      if (!s) return null;
      if (s.includes('/')) {
        const pts = s.split('/');
        if (pts.length === 3) {
          const yr = pts[2].length === 2 ? '20' + pts[2] : pts[2];
          const dt = new Date(parseInt(yr), parseInt(pts[1]) - 1, parseInt(pts[0]));
          return isNaN(dt.getTime()) ? null : dt;
        }
      }
      const parsed = new Date(s);
      return isNaN(parsed.getTime()) ? null : parsed;
    };

    // Helper Duration
    const getDurationDaysAndDates = (row, estimatedDateFallback) => {
      // FECHA as Start Date
      const startDate = parseDate(row['FECHA'] || row['F.INICIO'] || row['F. INICIO'] || null);

      // End Date from Process Log or Estimated
      let realEndDate = null;
      try {
        const logStr = String(row['PROCESO_LOG'] || row['proceso_log'] || '').trim();
        if (logStr && logStr.startsWith('[')) {
          const log = JSON.parse(logStr);
          if (Array.isArray(log)) {
            let lastEnd = null;
            log.forEach(step => {
              if (step.endTimestamp && step.status === 'DONE') {
                if (!lastEnd || step.endTimestamp > lastEnd) lastEnd = step.endTimestamp;
              }
            });
            if (lastEnd) realEndDate = new Date(lastEnd);
          }
        }
      } catch (e) {}

      const estimatedDate = parseDate(row['FECHA ESTIMADA DE FIN'] || row['FEC. EST. FIN'] || row['FECHA_RESPUESTA'] || estimatedDateFallback);

      if (!realEndDate) realEndDate = new Date();

      let isLate = false;
      let durationDays = 0;

      if (estimatedDate) {
         // Comparing dates (ignoring time)
         const rEnd = new Date(realEndDate.getFullYear(), realEndDate.getMonth(), realEndDate.getDate());
         const estEnd = new Date(estimatedDate.getFullYear(), estimatedDate.getMonth(), estimatedDate.getDate());
         isLate = rEnd > estEnd;
      }

      if (startDate && realEndDate) {
        const diff = realEndDate.getTime() - startDate.getTime();
        durationDays = diff < 0 ? 0 : Math.ceil(diff / (1000 * 60 * 60 * 24));
      }

      return { isLate, durationDays, realEndDate };
    };

    Object.keys(USER_DB).forEach(k => {
      const u = USER_DB[k];
      if (!u.staffName) return;
      const uName = u.staffName.toUpperCase().trim();

      // Filter out VENTAS and those not in allowedStaff
      if (u.seller || k === 'ANTONIA_VENTAS' || !allowedStaff.includes(uName)) return;

      const result = internalFetchSheetData(u.staffName);
      if (!result.success) return;

      const history = result.history || [];
      const dept = deptMap[uName] || 'SIN DEPT';

      history.forEach(row => {
        // Date filtering based on Start Date or Estimated End Date
        const startDate = parseDate(row['FECHA'] || row['F.INICIO'] || row['F. INICIO']);
        const estimatedDate = parseDate(row['FECHA ESTIMADA DE FIN'] || row['FEC. EST. FIN'] || row['FECHA_RESPUESTA']);

        const dateToUse = startDate || estimatedDate;
        if (!dateToUse) return;

        if ((dateToUse.getMonth() + 1) === targetMonth && dateToUse.getFullYear() === targetYear) {
          totalTasks++;

          const durStats = getDurationDaysAndDates(row, estimatedDate);

          if (durStats.isLate) lateTasks++;
          else onTimeTasks++;

          if (durStats.durationDays > 0) {
             totalDurationDays += durStats.durationDays;
             tasksWithDuration++;
          }

          // Restrictions & Risks
          const rest = String(row['RESTRICCIONES'] || '').trim().toUpperCase();
          if (rest && rest !== 'NINGUNO' && rest !== 'NINGUNA' && rest !== 'NO') tasksWithRestrictions++;

          const risk = String(row['RIESGO'] || '').trim().toUpperCase();
          if (risk && risk !== 'BAJO' && risk !== 'NINGUNO' && risk !== 'NO' && risk !== '') tasksWithRisks++;

          // Priorities
          const prio = String(row['PRIORIDAD'] || '').trim().toUpperCase();
          if (['ALTA', 'MEDIA', 'BAJA'].includes(prio)) {
            priorityStats[prio]++;
          } else {
            priorityStats['SIN_PRIORIDAD']++;
          }

          // Dept Stats
          if (!deptStats[dept]) deptStats[dept] = { count: 0, late: 0, onTime: 0 };
          deptStats[dept].count++;
          if (durStats.isLate) deptStats[dept].late++;
          else deptStats[dept].onTime++;

          // Collab Stats
          if (!collabStats[uName]) collabStats[uName] = { name: uName, dept, count: 0, late: 0, onTime: 0, totalDuration: 0, durCount: 0 };
          collabStats[uName].count++;
          if (durStats.isLate) collabStats[uName].late++;
          else collabStats[uName].onTime++;
          if (durStats.durationDays > 0) {
             collabStats[uName].totalDuration += durStats.durationDays;
             collabStats[uName].durCount++;
          }
        }
      });
    });

    const onTimePct = totalTasks > 0 ? Math.round((onTimeTasks / totalTasks) * 100) : 0;
    const avgDuration = tasksWithDuration > 0 ? parseFloat((totalDurationDays / tasksWithDuration).toFixed(1)) : 0;
    const restrictionsPct = totalTasks > 0 ? Math.round((tasksWithRestrictions / totalTasks) * 100) : 0;
    const risksPct = totalTasks > 0 ? Math.round((tasksWithRisks / totalTasks) * 100) : 0;

    const byCollabArr = Object.values(collabStats).sort((a,b) => b.count - a.count);
    byCollabArr.forEach(c => {
      c.avgDays = c.durCount > 0 ? parseFloat((c.totalDuration / c.durCount).toFixed(1)) : 0;
      c.onTimePct = c.count > 0 ? Math.round((c.onTime / c.count) * 100) : 0;
    });

    const byDeptArr = Object.keys(deptStats).map(k => ({ dept: k, count: deptStats[k].count })).sort((a,b) => b.count - a.count);

    return {
      success: true,
      metrics: {
        totalTasks,
        onTimeTasks,
        lateTasks,
        onTimePct,
        avgDurationDays: avgDuration,
        tasksWithRestrictions,
        restrictionsPct,
        tasksWithRisks,
        risksPct,
        priorityStats,
        byCollabArr,
        byDeptArr,
        month: targetMonth,
        year: targetYear
      }
    };

  } catch (e) {
    console.error("apiFetchTrackerProductivityMetrics Error: " + e.toString());
    return { success: false, message: e.toString() };
  }
}

function runTrackerProductivityAgent(params) {
  try {
    const p = params || {};
    const now = new Date();
    const month = (p.month !== undefined) ? parseInt(p.month) : (now.getMonth() + 1);
    const year  = (p.year  !== undefined) ? parseInt(p.year)  : now.getFullYear();
    const MONTHS = ['Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'];
    const monthName = MONTHS[month - 1];

    const mResult = apiFetchTrackerProductivityMetrics({ month, year });
    if (!mResult.success) return { success: false, message: 'No se pudieron obtener métricas: ' + mResult.message };
    const m = mResult.metrics;

    // Rules
    const alerts = [];
    if (m.onTimePct < 80 && m.totalTasks > 0) {
      alerts.push({ type: 'ENTREGAS_ATRASADAS', severity: 'ALTA', icon: '🔴', mensaje: 'Porcentaje de entregas a tiempo crítico: ' + m.onTimePct + '%' });
    }
    if (m.restrictionsPct > 20) {
       alerts.push({ type: 'ALTAS_RESTRICCIONES', severity: 'MEDIA', icon: '🟡', mensaje: 'Alta proporción de tareas con restricciones: ' + m.restrictionsPct + '%' });
    }
    const topCollab = m.byCollabArr[0];
    if (topCollab && topCollab.onTimePct < 50 && topCollab.count >= 5) {
       alerts.push({ type: 'PRODUCTIVIDAD_COLAB', severity: 'ALTA', icon: '🔴', mensaje: 'Colaborador ' + topCollab.name + ' tiene ' + topCollab.onTimePct + '% a tiempo de ' + topCollab.count + ' tareas.' });
    }

    // Gemini
    const mStr = JSON.stringify({
      volumen_total: m.totalTasks,
      a_tiempo_pct: m.onTimePct,
      atrasadas: m.lateTasks,
      promedio_dias_resolucion: m.avgDurationDays,
      porcentaje_restricciones: m.restrictionsPct,
      porcentaje_riesgos: m.risksPct,
      prioridades: m.priorityStats,
      top_colaboradores: m.byCollabArr.slice(0,3).map(c => ({ nombre: c.name, volumen: c.count, a_tiempo_pct: c.onTimePct, promedio_dias: c.avgDays }))
    }, null, 2);

    const prompt = 'Eres un Analista de Productividad y Operaciones Senior. Analiza las siguientes métricas del equipo correspondientes al mes de ' + monthName + '. Tu objetivo es redactar un reporte ejecutivo muy conciso (máximo 180 palabras) en español. Debes destacar el porcentaje de tareas entregadas a tiempo, identificar si hay un cuello de botella con las prioridades altas o restricciones, y mencionar al colaborador o departamento más productivo. Termina siempre con UNA recomendación operativa concreta para mejorar los tiempos de entrega.\n\nMétricas:\n' + mStr;

    let geminiSummary = 'No se pudo generar reporte con IA.';
    const gRes = callGeminiAPI(prompt);
    if (gRes.success && gRes.text) {
      geminiSummary = gRes.text;
    }

    const emailResult = _sendTrackerProductivityEmail(m, alerts, geminiSummary, monthName, year);

    return {
      success: true,
      data: {
        metrics: m,
        alerts: alerts,
        geminiReport: geminiSummary,
        emailSent: emailResult.success
      }
    };
  } catch(e) {
    console.error('runTrackerProductivityAgent Error: ' + e.toString());
    return { success: false, message: e.toString() };
  }
}

function _sendTrackerProductivityEmail(m, alerts, geminiSummary, monthName, year) {
  try {
    const recipients = [];
    if (USER_DB['LUIS_CARLOS']    && USER_DB['LUIS_CARLOS'].email)    recipients.push(USER_DB['LUIS_CARLOS'].email);
    if (USER_DB['ADMIN_CONTROL'] && USER_DB['ADMIN_CONTROL'].email) recipients.push(USER_DB['ADMIN_CONTROL'].email);
    if (USER_DB['JESUS_CANTU'] && USER_DB['JESUS_CANTU'].email) recipients.push(USER_DB['JESUS_CANTU'].email);

    if (recipients.length === 0) return { success: false, message: 'Sin destinatarios configurados.' };

    const alertRows = alerts.length > 0
      ? alerts.map(a => '<tr><td style="padding:6px 12px;">' + a.icon + '</td><td style="padding:6px 12px;color:#333;">' + a.mensaje + '</td><td style="padding:6px 12px;"><span style="background:' + (a.severity==='ALTA'?'#dc3545':a.severity==='MEDIA'?'#fd7e14':'#17a2b8') + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;">' + a.severity + '</span></td></tr>').join('')
      : '<tr><td colspan="3" style="padding:8px 12px;color:#28a745;">✅ Sin alertas críticas este mes</td></tr>';

    const collabRows = m.byCollabArr.slice(0, 8).map(c => {
      return '<tr style="border-bottom:1px solid #eee;"><td style="padding:5px 10px;">' + c.name + '</td><td style="text-align:center;padding:5px 10px;">' + c.count + '</td><td style="text-align:center;padding:5px 10px;color:' + (c.onTimePct >= 80 ? '#28a745' : '#dc3545') + ';">' + c.onTimePct + '%</td><td style="text-align:center;padding:5px 10px;">' + c.avgDays + '</td></tr>';
    }).join('');

    const html = [
      '<div style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;background:#fff;">',
      '<div style="background:#2c3e50;color:#fff;padding:24px;">',
      '<h1 style="margin:0;font-size:22px;">📊 Reporte de Productividad — ' + monthName.charAt(0).toUpperCase() + monthName.slice(1) + ' ' + year + '</h1>',
      '</div>',
      '<div style="padding:24px;border:1px solid #eee;">',
      '<h2 style="font-size:16px;color:#444;border-bottom:2px solid #2c3e50;padding-bottom:5px;">Resumen Ejecutivo (AI)</h2>',
      '<div style="background:#f8f9fa;padding:15px;border-radius:6px;color:#333;font-size:14px;line-height:1.6;border-left:4px solid #3b82f6;">' + geminiSummary.replace(/\n/g, '<br>') + '</div>',
      '<div style="display:flex;gap:15px;margin-top:24px;">',
      '<div style="flex:1;background:#fff;border:1px solid #ddd;border-radius:8px;padding:15px;text-align:center;">',
      '<div style="font-size:12px;color:#666;text-transform:uppercase;">Total Completadas</div>',
      '<div style="font-size:24px;font-weight:bold;color:#333;margin-top:5px;">' + m.totalTasks + '</div>',
      '</div>',
      '<div style="flex:1;background:#fff;border:1px solid #ddd;border-radius:8px;padding:15px;text-align:center;">',
      '<div style="font-size:12px;color:#666;text-transform:uppercase;">% A Tiempo</div>',
      '<div style="font-size:24px;font-weight:bold;color:' + (m.onTimePct >= 80 ? '#28a745' : '#dc3545') + ';margin-top:5px;">' + m.onTimePct + '%</div>',
      '</div>',
      '<div style="flex:1;background:#fff;border:1px solid #ddd;border-radius:8px;padding:15px;text-align:center;">',
      '<div style="font-size:12px;color:#666;text-transform:uppercase;">Promedio Días</div>',
      '<div style="font-size:24px;font-weight:bold;color:#17a2b8;margin-top:5px;">' + m.avgDurationDays + ' d</div>',
      '</div>',
      '</div>',
      '<h2 style="font-size:16px;color:#444;border-bottom:2px solid #2c3e50;padding-bottom:5px;margin-top:24px;">Alertas Operativas</h2>',
      '<table style="width:100%;border-collapse:collapse;font-size:13px;background:#fdfdfd;border:1px solid #eee;">',
      alertRows,
      '</table>',
      '<h2 style="font-size:16px;color:#444;border-bottom:2px solid #2c3e50;padding-bottom:5px;margin-top:24px;">Top Colaboradores (Volumen)</h2>',
      '<table style="width:100%;border-collapse:collapse;font-size:13px;">',
      '<tr style="background:#f4f4f4;color:#555;"><th style="text-align:left;padding:8px 10px;">Nombre</th><th style="padding:8px 10px;">Volumen</th><th style="padding:8px 10px;">% A Tiempo</th><th style="padding:8px 10px;">Prom. Días</th></tr>',
      collabRows,
      '</table>',
      '</div>',
      '<div style="background:#f1f1f1;color:#777;text-align:center;padding:12px;font-size:11px;">Generado automáticamente por el Agente de Productividad Holtmont</div>',
      '</div>'
    ].join('');

    MailApp.sendEmail({
      to: recipients.join(','),
      subject: '📊 Reporte Ejecutivo de Productividad - ' + monthName + ' ' + year,
      htmlBody: html
    });

    return { success: true };
  } catch(e) {
    console.error('_sendTrackerProductivityEmail Error: ' + e.toString());
    return { success: false, message: e.toString() };
  }
}
```

> ## 🐛 Segundo bug confirmado: `_sendTrackerProductivityEmail` nunca notifica a `ADMIN_CONTROL` (línea 1180)
>
> `USER_DB['ADMIN_CONTROL']` busca una entrada cuya **llave** sea literalmente el string `"ADMIN_CONTROL"` — pero las llaves de `USER_DB` son siempre nombres de usuario (`JAIME_OLIVO`, `DIMAS_RAMOS`, etc.), nunca nombres de rol (§6.3). `USER_DB['ADMIN_CONTROL']` es `undefined` en todo momento, así que `USER_DB['ADMIN_CONTROL'] && USER_DB['ADMIN_CONTROL'].email` siempre evalúa a `undefined` (falsy) y esa línea nunca agrega ningún destinatario. A diferencia del bug de §16.2/Anexo A §19.12, este **no lanza excepción** (está protegido por `&&`), así que el correo sí se envía — pero silenciosamente **sin ninguno de los dos usuarios `ADMIN_CONTROL` reales** (`JAIME_OLIVO`, `DIMAS_RAMOS`) en la lista de destinatarios. El reporte mensual de productividad, en la práctica, solo llega a `LUIS_CARLOS` y `JESUS_CANTU` (si tienen `email` configurado), nunca a los administradores de control. Probable intención original: `USER_DB['JAIME_OLIVO']` (el `ADMIN_CONTROL` original antes de que se agregara `DIMAS_RAMOS`).

### 19.19 `apiFetchTeamKPIData` (línea 1243) — referenciada narrativamente

No se reproduce en extenso por seguir un patrón de agregación equivalente al ya mostrado íntegro en `apiFetchAdminKPIs` (§19.7) y `apiFetchTrackerProductivityMetrics` (arriba): lee las hojas de Tracker/Ventas del equipo, agrupa por colaborador, calcula porcentajes de cumplimiento — la diferencia es que expone los datos para un `username` específico en vez de la organización completa, usado en la vista de detalle de un colaborador dentro del Dashboard de KPIs.

---

## 20. Anexo B — Código Frontend Completo (`index.html`)

> Código reproducido **literalmente** de los métodos Vue más críticos del Data Grid, dentro del bloque `setup()` de `createApp`.

### 20.1 `isFieldEditable` — permisos de edición por celda en el cliente (línea 7141)

```js
const isFieldEditable = (h, row) => {
    const restrictedRoles = ['ANGEL_USER', 'TERESA_USER', 'EDUARDO_USER', 'MANZANARES_USER', 'RAMIRO_USER', 'SEBASTIAN_USER', 'EDGAR_USER'];
    if (restrictedRoles.includes(currentRole.value)) {
        const hUp = String(h).toUpperCase();
        const allowed = ['ESTATUS', 'STATUS', 'MAP COT', 'PROCESO', 'AVANCE', 'REQUISITOR', 'INFO CLIENTE', 'F2', 'COTIZACION', 'COT', 'TIMELINE', 'LAYOUT', 'CORREO', 'CARPETA', 'COMENTARIOS', 'CORREOS', 'CARPETAS'];
        return allowed.some(a => hUp.includes(a));
    }

    if (currentRole.value === 'TONITA') {
        if (row._isNew) return true;
        if (!row['FOLIO'] && !row['ID']) return true;

        const hUp = String(h).toUpperCase();
        const allowed = ['FECHA', 'FECHA VISITA', 'FECHA ALTA', 'FECHA INICIO', 'ALTA', 'F. VISITA', 'F. INICIO', 'ESTATUS', 'STATUS', 'AVANCE', 'AVANCE %', 'ARCHIVO', 'COTIZACION', 'F2', 'LAYOUT', 'TIMELINE', 'ENTREGA', 'VENDEDOR', 'RESPONSABLE', 'CORREO', 'CARPETA', 'INFO CLIENTE', 'CORREOS', 'CARPETAS', 'AREA', 'COMENTARIOS', 'REQUISITOR'];
        return allowed.some(a => hUp.includes(a));
    }
    return true;
};
```

> **Nota:** el nombre de roles usado aquí (`ANGEL_USER`, `TERESA_USER`, etc.) es **distinto** del nombre de rol real que emite el backend (`STAFF_USER` para todos ellos, ver §6.2). Esto sugiere que en algún momento del desarrollo existieron roles diferenciados por persona (`ANGEL_USER`, `TERESA_USER`...) que luego se consolidaron en `STAFF_USER` en el backend — pero el frontend conserva este `restrictedRoles` como código muerto: `currentRole.value` nunca será igual a `'ANGEL_USER'` porque `apiLogin` siempre devuelve el `role` literal de `USER_DB`, que para estas personas es `STAFF_USER`. La restricción real y efectiva para estos 6 usuarios ocurre del lado del **backend** (`restrictedUsers` en `internalUpdateTask`, Anexo A §19.4), no de este bloque de frontend. Quien clone o depure este sistema no debe asumir que esta rama de `isFieldEditable` se ejecuta en producción.

### 20.2 `calculateDiasCounter`, `getColumnStyle`, `getHeaderLabel`, `isMediaColumn` (líneas 7160–7254)

```js
const calculateDiasCounter = (row) => {
    if (!staffTracker.value.name) return;
    const sheetName = String(staffTracker.value.name).toUpperCase();
    // const isExcludedSheet = sheetName.includes('(VENTAS)') || sheetName === 'ANTONIA_VENTAS';
    const isExcludedSheet = false; // Enabled for everyone now

    // Removed if (isExcludedSheet) return; to allow dynamic days calculation for Antonia and Ventas

    const hDias = staffTracker.value.headers.find(h => isCol(h, ['DIAS','RELOJ','DÍAS FINALIZ. COTIZ','DIAS FINALIZ. COTIZ']));
    if (!hDias) return;

    const hFecha = staffTracker.value.headers.find(h => isCol(h, ['FECHA','FECHA ALTA','FECHA DE ALTA','FECHA INICIO','FECHA DE INICIO','F. INICIO']));
    if (!hFecha || !row[hFecha]) return;

    let dObj = null;
    const val = row[hFecha];
    if (val instanceof Date) dObj = val;
    else if (typeof val === 'string') {
        const parts = val.split('/');
        if (parts.length === 3) {
             let y = parts[2];
             if (y.length === 2) y = '20' + y;
             // Javascript Date parsing with hyphens is very error prone due to UTC vs Local Time
             // It's safer to use the Date(year, monthIndex, day) constructor
             dObj = new Date(parseInt(y), parseInt(parts[1]) - 1, parseInt(parts[0]));
        } else {
             const parsed = new Date(val);
             if (!isNaN(parsed.getTime())) dObj = parsed;
        }
    }
    if (dObj && !isNaN(dObj.getTime())) {
        const now = new Date();
        dObj.setHours(0,0,0,0);
        now.setHours(0,0,0,0);
        const diffTime = now - dObj;
        const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
        row[hDias] = Math.max(0, diffDays);
    }
};

const getColumnStyle = (h) => {
    const up = String(h).toUpperCase().trim(); let w = '120px'; let fs = '12px'; let pad = '8px 4px'; let align = 'left'; let colColor = '#333';
    if (up === 'CONCEPTO' || up.includes('DESCRIP')) {
        if (currentView.value === 'WEEKLY_PLAN') {
            w = '150px';
        } else {
            w = (currentUsername.value === 'ANTONIA_VENTAS') ? '350px' : '380px';
        }
    }
    else if (currentUsername.value === 'ANTONIA_VENTAS' && (up === 'F. ENTREGA' || up === 'F. VISITA' || up === 'FECHA VISITA' || up === 'F. INICIO')) { w = '60px'; fs = '10px'; colColor = '#000'; }


    else if (up.includes('COMENTARIO') || up.includes('PREVIOS') || up.includes('OBSERVACIONES')) { w = '200px'; }
    else if (isCol(h, ['ESPECIALIDAD', 'AREA', 'DEPTO', 'ALTA'])) { w = '40px'; fs = '11px'; align = 'center'; }
    else if (isCol(h, ['ID', 'FOLIO'])) { w = '85px'; fs = '10px'; align = 'center'; }
    else if (up.includes('CUMPLIMIENTO')) { w = '50px'; align = 'center'; fs = '11px'; }
    else if (up.includes('ARCHIVO') || up.includes('CLIP') || up === 'CORREO' || up === 'CARPETA') { w = '40px'; align = 'center'; }
    else if (up === 'SEMANA') { w = '50px'; align = 'center'; }
    else if (up === 'HORA') { w = '50px'; fs = '10px'; }
    else if (up === 'FECHA ESTIMADA DE FIN' || up === 'FECHA DE ENTREGA') { w = '75px'; fs = '10px'; }
    else if (up === 'HORA ESTIMADA DE FIN') { w = '60px'; fs = '10px'; }
    else if (up.includes('PRIORIDAD')) { w = '70px'; fs = '10px'; }
    else if (up.includes('RIESGO')) { w = '70px'; fs = '10px'; }
    else if (up === 'REQUISITOR') { w = '90px'; fs = '11px'; }
    else if (up === 'INFO CLIENTE') { w = '70px'; fs = '10px'; align='center'; }
    else if (isCol(h, ['DIAS','RELOJ','CLASIFICACION','DÍAS FINALIZ. COTIZ','DIAS FINALIZ. COTIZ'])) { w = '40px'; fs = '10px'; pad = '8px 1px'; }
    else if (up.includes('AVANCE')) { w = '40px'; fs = '10px'; pad = '8px 1px'; }
    else if (isCol(h, ['ESTATUS','STATUS'])) { w = currentUsername.value === 'ANTONIA_VENTAS' || (staffTracker.value && staffTracker.value.name && staffTracker.value.name.includes('VENTAS')) ? '320px' : '65px'; fs = '10px'; pad = '8px 1px'; }
    else if (up.includes('FECHA') || up.includes('RESPUESTA')) { w = '65px'; fs = '10px'; }
    else if (up === 'F2') { w = '35px'; fs = '10px'; align='center'; }
    else if (up.includes('COTIZACION') || up.includes('COT')) { w = '70px'; fs = '10px'; align='center'; }
    else if (up.includes('TIMEOUT') || up.includes('TIME OUT')) { w = '70px'; fs = '10px'; align='center'; }
    else if (up.includes('LAYOUT') || up.includes('TIMELINE')) { w = '70px'; fs = '10px'; align='center'; }
    else if (up.includes('VENDEDOR') || (currentUsername.value === 'ANTONIA_VENTAS' && up.includes('RESPONSABLE'))) { w = '50px'; fs = '10px'; align='center'; colColor = '#000'; }
    else if (up === 'CLIENTE') w = '100px';

    // OVERRIDE FOR PPCV3 (WEEKLY_PLAN)
    if (currentView.value === 'WEEKLY_PLAN') {
        if (['ESPECIALIDAD', 'RESPONSABLE', 'FECHA', 'RELOJ', 'CUMPLIMIENTO'].includes(up)) {
            w = 'auto';
        }
    }

    return { width: w, fontSize: fs, padding: pad, textAlign: align, overflow: 'hidden', textOverflow: 'ellipsis', color: colColor };
};

const getHeaderLabel = (h) => {
    const up = String(h).toUpperCase().trim();
    if (up === 'DIAS' && currentUsername.value === 'ANTONIA_VENTAS') return 'Días Finaliz. Cotiz';
    if (up === 'CLASIFICACION') return 'CLASI';
    if (up === 'FECHA ESTIMADA DE FIN') return 'FEC. EST. FIN';
    if (up === 'HORA ESTIMADA DE FIN') return 'HR. EST. FIN';
    return h;
};
const isMediaColumn = (h) => ['F2','COTIZACION','COT','COTIZACIÓN','TIMEOUT','TIME OUT','LAYOUT','TIMELINE','INFO CLIENTE','CORREO','CARPETA','CORREOS','CARPETAS'].includes(String(h).toUpperCase());
```

### 20.3 Semáforos de fecha y `toInitials` (líneas 7255–7317)

```js
const getTrafficStyle = (row) => {
    const clasiKey = Object.keys(row).find(k => ['CLASIFICACION', 'CLASI'].includes(String(k).toUpperCase().trim()));
    const t = clasiKey ? String(row[clasiKey]).trim().toUpperCase() : '';

    const diasKey = Object.keys(row).find(k => ['DIAS','RELOJ','DÍAS FINALIZ. COTIZ','DIAS FINALIZ. COTIZ'].includes(String(k).toUpperCase().trim()));
    const d = diasKey ? parseInt(row[diasKey]||0) : 0;

    if (isNaN(d)) return {};

    let limit = 0, buffer = 0;
    if(t==='A') { limit=3; buffer=1; }
    else if(t==='AA') { limit=15; buffer=3; }
    else if(t==='AAA') { limit=30; buffer=5; }
    else return {};

    if(d > limit) return {backgroundColor:'#e74c3c', color:'white'}; // Rojo
    if(d >= (limit - buffer)) return {backgroundColor:'#ffff00', color:'black', fontWeight:'bold'}; // Amarillo
    return {backgroundColor:'#2ecc71', color:'white'}; // Verde
};

const getFechaInicioTrafficStyle = (row) => {
    const startKey = Object.keys(row).find(k => ['FECHA','FECHA INICIO','FECHA DE INICIO','ALTA','F. INICIO','F. VISITA'].includes(String(k).toUpperCase().trim()));
    if (!startKey) return {};
    const val = row[startKey];
    if (!val) return {};
    let dObj = null;
    if (val instanceof Date) dObj = val;
    else if (typeof val === 'string') {
        const p = val.split('/');
        if (p.length === 3) dObj = new Date(p[2].length===2?'20'+p[2]:p[2], p[1]-1, p[0]);
    }
    if (!dObj || isNaN(dObj.getTime())) return {};

    // Calculate elapsed days
    const now = new Date();
    now.setHours(0,0,0,0);
    dObj.setHours(0,0,0,0);
    const diff = now - dObj;
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    const clasiKey = Object.keys(row).find(k => ['CLASIFICACION', 'CLASI'].includes(String(k).toUpperCase().trim()));
    const t = clasiKey ? String(row[clasiKey]).trim().toUpperCase() : '';
    let limit = 0, buffer = 0;
    if(t==='A') { limit=3; buffer=1; }
    else if(t==='AA') { limit=15; buffer=3; }
    else if(t==='AAA') { limit=30; buffer=5; }
    else return {};

    if(days > limit) return {backgroundColor:'#e74c3c', color:'black'};
    if(days >= (limit - buffer)) return {backgroundColor:'#ffff00', color:'black', fontWeight:'bold'};
    return {backgroundColor:'#2ecc71', color:'black'};
};

const toInitials = (name) => {
  if (!name) return '';
  // Soporta múltiples nombres separados por coma
  return String(name).split(',').map(n => {
      const parts = n.trim().split(/\s+/);
      if (parts.length === 0 || (parts.length === 1 && parts[0] === '')) return '';
      return parts.map(p => p.charAt(0)).join('').toUpperCase().substring(0, 2);
  }).join('/');
};
```

### 20.4 `addNewRow` — creación de fila con `_tempId` (línea 8195)

```js
const addNewRow = () => {
    if(!staffTracker.value.headers.length) return;
    const tempId = 'temp_' + Date.now() + '_' + Math.floor(Math.random() * 1000);
    const row={_isNew:true, _tempId: tempId};

    const sheetName = String(staffTracker.value.name).toUpperCase();
    // const isExcludedSheet = sheetName.includes('(VENTAS)') || sheetName === 'ANTONIA_VENTAS';
    const isExcludedSheet = false; // Enabled for everyone now
    const now = new Date();
    const d = String(now.getDate()).padStart(2, '0');
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const y = String(now.getFullYear()).slice(-2);
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');

    staffTracker.value.headers.forEach(h => {
        const hUp = String(h).toUpperCase().trim();
        if (isCol(h, ['DIAS','RELOJ','DÍAS FINALIZ. COTIZ','DIAS FINALIZ. COTIZ'])) {
            row[h] = 0;
        } else if (!isExcludedSheet && (hUp === 'FECHA' || hUp === 'FECHA ALTA' || hUp === 'FECHA INICIO')) {
            row[h] = `${d}/${m}/${y}`;
        } else if (!isExcludedSheet && hUp === 'HORA') {
            row[h] = `${hh}:${mm}`;
        } else {
            row[h] = "";
        }
    });
    calculateDiasCounter(row);
    staffTracker.value.data.unshift(row);
    pulseNewRow('trackerTable', 'first');
};
```

### 20.5 `getProcessTimeline` — renderizado del timeline Papa Caliente (línea 9729, extracto de la sección relevante)

```js
const getProcessTimeline = (row) => {
    let log = [];
    try {
        if (row.PROCESO_LOG) log = JSON.parse(row.PROCESO_LOG);
    } catch(e) {}

    let mapCot = row["MAP COT"] || row.PROCESO || "";
    let parsedParts = mapCot.split(/\||>|\//).map(p => p.trim()).filter(p => p);

    let startDate = new Date();
    const dateKeys = ['FECHA', 'FECHA INICIO', 'ALTA', 'FECHA DE INICIO', 'FECHA VISITA', 'FECHA_ALTA', 'F. INICIO', 'F. VISITA'];
    for (const k of dateKeys) {
        if (row[k]) {
            const val = row[k];
            if (val instanceof Date) startDate = val;
            else if (typeof val === 'string') {
                const parts = val.split('/');
                if (parts.length === 3) {
                    let y = parts[2];
                    if (y.length === 2) y = '20' + y;
                    startDate = new Date(y, parts[1]-1, parts[0]);
                } else {
                    const parsed = new Date(val);
                    if (!isNaN(parsed.getTime())) startDate = parsed;
                }
            }
            break;
        }
    }

    const formatDiff = (diffMs) => {
        const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));
        const hours = Math.floor((diffMs % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
        if (days > 0) return `${days}d ${hours}h`;
        if (hours > 0) return `${hours}h`;
        return '< 1h';
    };

    return PROCESS_STEPS.map((stepId, idx) => {
        let statusChar = '⚪';
        let matchingPart = parsedParts.find(p => p.includes(stepId));
        if (matchingPart) {
            if (matchingPart.includes('🟢')) statusChar = '🟢';
            else if (matchingPart.includes('🔴')) statusChar = '🔴';
            else if (matchingPart.includes('🟡')) statusChar = '🟡';
        } else {
            const currentStatus = getProcessStatus(row);
            const currentIdx = PROCESS_STEPS.indexOf(currentStatus);
            if (idx < currentIdx) statusChar = '🟢';
            else if (idx === currentIdx) statusChar = '🔴';
        }

        let isDone = statusChar === '🟢';
        let isCurrent = statusChar === '🔴';
        let isInProgress = statusChar === '🟡';

        let stepEntry = log.find(l => l.step === stepId || l.to === stepId);
        let timeLabel = '';

        const formatShortDate = (ts) => {
            const d = new Date(ts);
            const pad = (n) => n.toString().padStart(2, '0');
            const yy = d.getFullYear().toString().slice(2);
            return `${pad(d.getDate())}/${pad(d.getMonth()+1)}/${yy} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
        };

        if (isDone || isInProgress) {
            if (stepEntry && stepEntry.timestamp) {
                timeLabel = formatShortDate(stepEntry.timestamp);
            } else if (stepEntry && stepEntry.dateStr) {
                timeLabel = stepEntry.dateStr;
            } else {
                timeLabel = '';
            }
        } else if (isCurrent) {
            let prevTime = startDate.getTime();
            if (idx > 0) {
                let prevEntry = log.find(l => l.step === PROCESS_STEPS[idx-1] || l.to === PROCESS_STEPS[idx-1]);
                if (prevEntry && prevEntry.timestamp) prevTime = prevEntry.timestamp;
            }
            const diff = new Date().getTime() - prevTime;
            timeLabel = formatDiff(diff);
        } else {
            timeLabel = '-';
        }

        return {
            id: stepId,
            isDone: isDone,
            isCurrent: isCurrent || isInProgress,
            // ... continúa con más propiedades del objeto de retorno (label, timeLabel, etc.)
        };
    });
};
```

### 20.6 `saveRow` — el patrón de guardado con anti-doble-click (línea 8226)

```js
const saveRow = (row, event) => {
    if (row._isSaving || isSubmitting.value) {
         Swal.fire({
              toast: true,
              position: 'top-end',
              icon: 'warning',
              title: 'Guardando, espere un momento...',
              showConfirmButton: false,
              timer: 1500
         });
         return;
    }
    row._isSaving = true;
    isSubmitting.value = true;

    const sheetName = String(staffTracker.value.name).toUpperCase();
    const isExcludedSheet = false;

    if (!isExcludedSheet) {
        const now = new Date();
        const d = String(now.getDate()).padStart(2, '0');
        const m = String(now.getMonth() + 1).padStart(2, '0');
        const y = String(now.getFullYear()).slice(-2);
        const hh = String(now.getHours()).padStart(2, '0');
        const mm = String(now.getMinutes()).padStart(2, '0');

        staffTracker.value.headers.forEach(h => {
            const hUp = String(h).toUpperCase().trim();
            if ((hUp === 'FECHA' || hUp === 'FECHA ALTA' || hUp === 'FECHA INICIO') && !row[h]) {
                row[h] = `${d}/${m}/${y}`;
            }
            if (hUp === 'HORA' && !row[h]) {
                row[h] = `${hh}:${mm}`;
            }
        });
    }

    if (event && event.clientX) {
       const isCompleted = Object.entries(row).some(([k, v]) => (String(k).toUpperCase().includes('AVANCE') && String(v) === '100') || (String(k).toUpperCase().includes('CUMPLIMIENTO') && String(v).toUpperCase() === 'SI'));
       if (isCompleted) triggerConfetti(event.clientX, event.clientY);
    }
    Swal.showLoading();
    google.script.run.withSuccessHandler(res => {
        row._isSaving = false;
        isSubmitting.value = false;
        Swal.close();
        if(res.success){
            if (res.data) {
                Object.assign(row, res.data);
            }
            row._isNew=false;
            row._isSaving = false;
            if (res.data && (res.data.FOLIO || res.data.ID)) {
                row.FOLIO = res.data.FOLIO || res.data.ID;
                if (row.ID === undefined) row.ID = row.FOLIO;
            }
            if(res.moved){
                reloadStaffTracker();
                Swal.fire({icon: 'success', title: 'Archivado', text: 'Tarea movida a Realizadas (100%)', timer: 1500, showConfirmButton: false});
            } else {
                Swal.fire({icon: 'success', title: 'Guardado', timer: 1000, showConfirmButton: false});
            }
        } else {
            Swal.fire('Error', res.message, 'error');
        }
    }).withFailureHandler(err => { row._isSaving = false; isSubmitting.value = false; handleErr(err); }).internalUpdateTask(staffTracker.value.name, JSON.parse(JSON.stringify(row)), currentUsername.value);
};
```

---

## 21. Anexo C — Inventario Completo de Estado Reactivo (`index.html`, ~90 declaraciones `ref()`/`reactive()`)

> Línea aproximada de declaración (bloque `setup()`, 5945–9440) y propósito de cada variable. Es el inventario completo referenciado en §8.2.

| Línea | Variable | Valor inicial / forma | Propósito |
|---|---|---|---|
| 5945 | `isRecording` | `false` | Bandera de grabación de audio para transcripción Gemini |
| 5947 | `isLoggedIn` | `false` | Controla si se muestra el overlay de login o la app |
| 5948 | `trackerProductivityData` | `null` | Payload del dashboard de productividad IA |
| 5948 | `isLoadingTrackerProductivity` | `false` | Loader del dashboard de productividad |
| 5948 | `loginPass` / `loginUser` | `''` | Campos del formulario de login |
| 5948 | `loggingIn` | `false` | Loader del botón de login |
| 5948 | `currentUser` / `currentUsername` | `''` | Nombre para mostrar / username técnico de la sesión activa |
| 5949 | `currentRole` | `''` | Rol RBAC de la sesión activa (§6.2) |
| 5950 | `currentView` | `'DASHBOARD'` | Router manual (§8.3) |
| 5950 | `currentDept` | `''` | Departamento actualmente navegado en `DEPT` |
| 5951 | `config` | `{departments, staff, directory, specialModules}` | Payload completo de `getSystemConfig()` |
| 5952 | `staffTracker` | `{name, data, history, headers, isLoading, previousView}` | Estado del Tracker actualmente abierto |
| 5955 | `hotPotatoData` | objeto | Estado del timeline Papa Caliente en pantalla |
| 6057 | `staffTrackerFilters` | `{}` | Filtros activos sobre las columnas del Data Grid |
| 6058 | `staffTrackerSortAsc` | `false` | Orden ascendente/descendente de la tabla de cotizaciones |
| 6059 | `activeTrackerTab` | `'OPERATIVO'` | Sub-pestaña activa dentro de un Tracker |
| 6060 | `trackerSubView` | `'TASKS'` | Sub-vista dentro del Tracker (tareas vs. historial, etc.) |
| 6061 | `currentStaffName` | `''` | Nombre de la persona cuyo tracker está abierto |
| 6062 | `weeklyPlanData` | `{headers, data, isLoading}` | Datos de la vista "Planeación Semanal" (PPCV3) |
| 6065 | `personalAgenda` | objeto | Agenda personal del usuario logueado |
| 6075 | `showNewActivityModal` | `false` | Visibilidad del modal de nueva actividad de agenda |
| 6076 | `newActivity` | `{title, date, startTime, endTime, category}` | Formulario de nueva actividad |
| 6077 | `selectedDailyDay` | `''` | Día seleccionado en la vista diaria de agenda |
| 6080 | `dashboardCalendar` | `{currentDate, tasks}` | Calendario ejecutivo del dashboard |
| 6081 | `calendarLoading` | `false` | Loader del calendario |
| 6082 | `calendarUserFilter` | `''` | Filtro por usuario en el calendario ejecutivo |
| 6083 | `calendarInterval` | `null` | Handle del `setInterval` de refresco del calendario |
| 6085 | `searchQuery` | `''` | Búsqueda global de texto en tablas |
| 6085 | `isCompact` | `false` | Modo de UI compacta (densidad de filas) |
| 6086 | `showPassword` | `false` | Toggle de visibilidad de contraseña en el login |
| 6087 | `currentTheme` | `'light'` | Tema claro/oscuro |
| 6090 | `infoBankState` | `{view, selectedYear, selectedMonth, selectedCompany, selectedFolder, files, isLoading}` | Navegación Año→Mes→Empresa→Carpeta del Banco de Información |
| 6093 | `ibCompanies` | `[]` | Lista de empresas/clientes del Banco de Información |
| 6181 | `certActivities` | `[]` | Actividades de certificación/hábitos |
| 6182 | `certNewActivity` | `{concepto, descripcion}` | Formulario de nueva actividad de certificación |
| 6183 | `showCertModal` | `false` | Visibilidad del modal de certificaciones |
| 6184 | `certStep` | `1` | Paso actual del wizard de certificación |
| 6228 | `trackerTable` | `null` | Referencia DOM (`ref`) a la tabla del Tracker, usada por `pulseNewRow` |
| 6229 | `projectTable` | `null` | Referencia DOM a la tabla de Proyectos |
| 6230 | `ppcDraftTable` | `null` | Referencia DOM a la tabla de borradores PPC |
| 6284 | `ppcData` | `{cumplimiento, cliente, comentarios, comentariosPrevios, zona, contratista, rutaCritica, cuantReq, cuantReal, dias:{l,m,x,j,v,s,d}}` | Formulario principal del módulo PPC (checklist Jesús Cantú) |
| 6286 | `isSubmitting` | `false` | **Bandera global anti-doble-submit** (§10.3), compartida por todos los botones de guardado del sistema |
| 6287 | `selectedResponsables` | `[]` | Selección múltiple de personal para distribución/delegación |
| 6287 | `staffSearch` | `''` | Búsqueda dentro del selector de personal |
| 6287 | `activityQueue` | `[]` | Cola de actividades pendientes de asignar |
| 6299 | `ppcExistingData` | `[]` | Registros PPC ya guardados, para el historial |
| 6301 | `historySearchQuery` | `''` | Búsqueda dentro del historial |
| 6303 | `cotizadorSearch` | `''` | Búsqueda dentro del módulo de cotizador |
| 6308 | `cotizadorSearchTop` | `''` | Búsqueda superior del cotizador (barra separada) |
| 6313 | `workorderData` | objeto | Estado maestro del formulario de Work Order |
| 6323 | `currentWorkorderId` | `null` | Folio de la Work Order actualmente abierta |
| 6324 | `nextSequence` | `'0000'` | Preview del siguiente folio de Work Order antes de guardar |
| 6377 | `isUploadingFile` | `false` | Loader de subida de archivo genérica |
| 6377 | `uploadSuccess` | `false` | Feedback visual de subida exitosa |
| 6377 | `fileInput` | `null` | Referencia DOM al `<input type="file">` genérico |
| 6378 | `currentUploadType` | `''` | Tipo de adjunto que se está subiendo (determina carpeta destino) |
| 6379 | `currentIframeUrl` / `iframeTitle` | `''` | URL y título del iframe embebido (visor de documentos) |
| 6380 | `showExtraModal` | `false` | Visibilidad del modal de "Detalles Extra" (restricciones/prioridades/riesgos) |
| 6381 | `showTimePopup` | `false` | Visibilidad del selector de hora custom |
| 6382 | `timePopupValue` | `''` | Valor temporal del selector de hora |
| 6383 | `timePopupTarget` | `null` | Referencia a la celda/campo que abrió el selector de hora |
| 6398 | `extraData` | `{restricciones, prioridades, riesgos, fechaRespuesta, clasificacion}` | Datos del modal "Detalles Extra" |
| 6400 | `cellFileInput` | `null` | Referencia DOM al input de archivo por celda del Data Grid |
| 6400 | `uploadingCell` | `{row, col}` | Coordenada de la celda actualmente subiendo un archivo |
| 6401 | `dynamicPpc` | `{especialidad, clasificacion, concepto, riesgos, prioridad, fechaFin, comentarios, archivoUrl}` | Formulario del PPC dinámico (`PPC_DINAMICO`) |
| 6402 | `vehicleData` | `{}` | Datos de inspección vehicular (Work Order) |
| 6403 | `vehicleControlData` | `{}` | Sub-sección de control vehicular #1 (duplicada, ver nota abajo) |
| 6404 | `vehicleControlData2` | `{}` | Sub-sección de control vehicular #2 — copia independiente de `vehicleControlData` para un segundo vehículo/checklist en el mismo formulario |
| 6405 | `showWorkOrderLogic` | `true` | Visibilidad de la lógica/ayuda contextual del formulario de Work Order |
| 6408 | `showLogic` | objeto | Mapa de visibilidad de bloques de "lógica" de ayuda por sección |
| 6418 | `sectionVisibility` | objeto | Mapa de secciones colapsadas/expandidas del formulario |
| 6424 | `showInstr` | objeto | Mapa de visibilidad de instrucciones contextuales por sección |
| 6459 | `projectProgram` | objeto | Datos del sub-formulario "Programa" de Work Order (`DB_WO_PROGRAMA`) |
| 6469 | `currentActivityContext` | `null` | Contexto de la actividad actualmente seleccionada para recursos |
| 6470 | `showResourceModal` | `false` | Visibilidad del modal de recursos (materiales/mano de obra/etc.) |
| 6471 | `currentResourceTab` | `'MATERIALES'` | Pestaña activa dentro del modal de recursos |
| 6524 | `projectRespDropdownOpen` | `null` | Id del dropdown de responsables actualmente abierto en Proyectos |
| 6546 | `laborTable` | `{items:[...]}` | Tabla de mano de obra de Work Order (`DB_WO_MANO_OBRA`), fila inicial precargada |
| 6603 | `requiredMaterials` | `{items:[...]}` | Tabla de materiales requeridos (`DB_WO_MATERIALES`) |
| 6616 | `toolsRequired` | `{items:[...]}` | Tabla de herramientas requeridas (`DB_WO_HERRAMIENTAS`) |
| 6629 | `designUploadContext` | `{row, col, type}` | Contexto de subida de archivos de diseño |
| 6630 | `designFileInput` | `null` | Referencia DOM al input de archivo de diseño |
| 6667 | `specialEquipment` | `{items:[...]}` | Tabla de equipo especial (`DB_WO_EQUIPOS`) |
| 6673 | `additionalCosts` | `{insumos, viaticos, transporte}` | Costos adicionales del Work Order |
| 6700 | `selectedFinancing` | `null` | Toggle de tipo de financiamiento (visual) |
| 6701 | `selectedWeek` | `''` | Semana seleccionada en Planeación Semanal |
| 6702 | `currentModuleId` | `''` | Id del módulo especial actualmente activo (de `config.specialModules`) |
| 6756 | `filterSpecialty` | `''` | Filtro por especialidad en el Data Grid |
| 6757 | `filterCompliance` | `''` | Filtro por cumplimiento en el Data Grid |
| 6760 | `ecgData` | `{}` | Datos del módulo "Monitor Vivos" (deshabilitado, §8.3) |
| 6764 | `kpiData` | objeto | Estado del dashboard de KPIs (tarjetas superiores) |
| 6783 | `quoteMetrics` | objeto | Métricas del agente de cotizaciones (`apiFetchQuoteAgentMetrics`) |
| 6807 | `qmFilters` | objeto | Filtros del dashboard de métricas de cotizaciones |
| 6813 | `agentState` | `{running, lastRun}` | Estado de ejecución del agente narrativo IA |
| 6814 | `showGeminiKeyModal` | `false` | Visibilidad del modal para configurar la API key de Gemini |
| 6815 | `geminiKeyInput` | `''` | Campo de captura de la API key |
| 6816 | `geminiKeyState` | `{hasKey, preview}` | Estado enmascarado de si ya hay una key guardada |
| 6820 | `executiveSummaryData` | objeto | Resumen ejecutivo narrativo generado por Gemini |
| 6837 | `showPpcSelectorModal` | `false` | Visibilidad del selector de tipo de PPC (Interno/Preoperativo/Cliente) |
| 6838 | `ppcMode` | `'SELECT'` | Modo del flujo PPC (selección vs. captura) |
| 6839 | `currentPpcProject` | `null` | Proyecto/sitio asociado al PPC en captura |
| 6840 | `ppcMenuTipo` | `''` | Tipo de PPC elegido en el menú (`PPC_MENU`) |
| 6841 | `newProject` | `{name, client, type, creationMode, parentId, createdBy}` | Formulario de alta de nuevo Sitio/Proyecto |
| 6845 | `activeProjectsList` | `[]` | Lista de proyectos activos (cascada) |
| 6846 | `showSubProjectModal` | `false` | Visibilidad del modal de alta de subproyecto |
| 6847 | `currentTargetSite` | `{}` | Sitio padre seleccionado al crear un subproyecto |
| 6848 | `newSubProject` | `{name, type, createdBy}` | Formulario de alta de subproyecto |
| 6851 | `showEmployeeModal` | `false` | Visibilidad del modal de alta/baja de empleado (RBAC `ADMIN`) |
| 6852 | `newEmployee` | `{name, dept, type}` | Formulario de alta de empleado (`apiAddEmployee`) |
| 6900 | `projectSubFolders` | `[...]` | Lista de subcarpetas estándar (espejo de `STANDARD_PROJECT_STRUCTURE`) |
| 6910 | `projectCards` | `[]` | Tarjetas de proyecto renderizadas en la vista de cascada |
| 6911 | `projectTasks` | `{data, headers, isLoading}` | Tareas del proyecto actualmente abierto |
| 9438 | `showProcessFlow` | `false` | Visibilidad del diagrama de flujo del proceso Papa Caliente |
| 9439 | `showHotPotatoModal` | `false` | Visibilidad del modal de asignación de etapa Papa Caliente |
| 9440 | `currentHotPotatoRow` | `null` | Fila actualmente seleccionada para delegar en Papa Caliente |

**Referencias DOM adicionales usadas por el sistema de animación de filas nuevas** (`pulseNewRow`, invocado desde `addNewRow`, §20.4): `trackerTable`, `projectTable`, `ppcDraftTable` — son las tres tablas que soportan el efecto visual de "parpadeo" al insertar una fila.

---

# PARTE III — Verificación de Migración a Python/FastAPI

## 22. Checklist de Verificación de Paridad (Holtmont Workspace GAS → FastAPI)

> **Propósito de esta sección:** este SSD no solo documenta el sistema original — está pensado para que **otra sesión de Claude (u otro desarrollador), con acceso al repositorio de la migración en Python/FastAPI pero sin haber leído `CODIGO.js`/`index.html`**, pueda verificar de forma sistemática si esa migración es funcionalmente equivalente al sistema descrito aquí, ítem por ítem.
>
> **Cómo usar este checklist:**
> 1. Por cada ítem `☐`, buscar en el repo de FastAPI el endpoint/módulo/regla equivalente.
> 2. Marcar `✅ OK` si el comportamiento coincide con el criterio de aceptación citado (y la sección del SSD donde está la spec completa/el código fuente original).
> 3. Marcar `❌ FALTA` si no se encontró ninguna implementación equivalente.
> 4. Marcar `⚠️ DIFERENTE` si existe algo similar pero el comportamiento diverge del criterio — anotar en qué.
> 5. Los ítems marcados **🐛 BUG CONOCIDO** son comportamientos rotos o inconsistentes del sistema **original** (documentados en §16 y en el Anexo A) — la recomendación por defecto es **corregirlos en la migración, no replicarlos tal cual**; si se prefiere paridad exacta primero y corrección después, dejarlo anotado explícitamente en el reporte de auditoría.
> 6. Al terminar, producir un reporte con: total de ítems, cuántos `✅`/`❌`/`⚠️`, y el detalle de cada `❌`/`⚠️` con la sección del SSD que se está incumpliendo.

### 22.1 Autenticación y Sesión (spec: §6.2–6.3, §7.1, Anexo A §19.1)

- ☐ Endpoint de login que reciba `username`/`password` y devuelva `{success, role, name, username}` — comparación de credenciales equivalente a `apiLogin` (línea 310).
- ☐ Login registra auditoría en el equivalente de `LOG_SISTEMA` con acción `LOGIN` (éxito) o `LOGIN_FAIL` (fallo) — mismo criterio que `registrarLog`.
- ☐ Logout registra auditoría `LOGOUT`.
- ☐ Existen los 6 roles exactos: `ADMIN`, `ADMIN_CONTROL`, `PPC_ADMIN`, `TONITA`, `WORKORDER_USER`, `STAFF_USER` — sin renombrar ni fusionar ninguno (§6.2).
- ☐ Endpoint equivalente a `getSystemConfig(role, username)` que arme el árbol de navegación exacto por rol (19 departamentos, módulos especiales) — ver árbol completo en Anexo A §19.10.
- ☐ **Caso especial `JUANY_RODRIGUEZ`**: verificar que la migración preserva la excepción hardcodeada de acceso ampliado a `COMPRAS`/`FACTURACION`/`FINANZAS` (§6.2) — es fácil perderla al migrar porque no está en ninguna tabla, solo en un `if` de código.
- ☐ Relabel dinámico: si el usuario es `JESUS_CANTU`, el módulo "PPC Maestro" se muestra como "INTERDICIPLINARIA" (§6.2, preservar aunque sea un typo histórico, o decidir conscientemente corregirlo).
- ☐ Lista `restrictedUsers` (6 vendedores: `ANGEL_SALINAS`, `TERESA_GARZA`, `EDUARDO_TERAN`, `EDUARDO_MANZANARES`, `RAMIRO_RODRIGUEZ`, `SEBASTIAN_PADILLA`) con permisos de edición reducidos sobre hojas/tablas ajenas — criterio exacto de columnas permitidas en §6.2 y Anexo A §19.4.
- ☐ ⚠️ **Decisión de diseño requerida**: `apiLogin` compara contraseña con `===` en texto plano (§13) — la migración a Python **debería** usar hash+salt (bcrypt/argon2) en vez de replicar texto plano; confirmar que se tomó esta decisión conscientemente y no por omisión.

### 22.2 Organigrama y Directorio (spec: §5.2, §6.3–6.5, Anexo A §19.1/§19.11)

- ☐ Modelo de datos equivalente a `DB_DIRECTORY`: campos `NOMBRE`, `DEPARTAMENTO`, `TIPO_HOJA` (valores `ESTANDAR`/`HIBRIDO`/`VENTAS`).
- ☐ Semilla de datos con las 36 entradas de `INITIAL_DIRECTORY` (tabla completa en §6.4) — verificar que el organigrama migrado coincide persona por persona, departamento por departamento.
- ☐ Las 41 cuentas de `USER_DB` (tabla completa sin contraseñas en §6.3) migradas con: `role`, `label`, `email`, `staffName`, `dept`, `seller`.
- ☐ Endpoint equivalente a `apiResyncDirectory` (solo rol `ADMIN`) que re-sincronice el directorio desde la fuente de verdad de código/config y cree automáticamente cualquier Tracker faltante.
- ☐ Endpoints equivalentes a `apiAddEmployee`/`apiDeleteEmployee` — alta crea automáticamente el Tracker (y la tabla de Ventas si `type` es `VENTAS`/`HIBRIDO`); baja **no** borra el Tracker asociado (comportamiento intencional, no bug, ver Anexo A §19.11).
- ☐ ⚠️ **Decisión de diseño requerida**: `CESAR_GOMEZ` está documentado como "baja" en `CREDENCIALES.md` pero sigue activo en `USER_DB` (§6.3) — decidir explícitamente si la migración lo trata como activo o inactivo, no dejarlo a que la ambigüedad se resuelva por accidente.

### 22.3 Motor de Trackers: lectura, guardado por lotes, anti-duplicación (spec: §5.3, §10.3, Anexo A §19.2–19.4)

- ☐ Endpoint de lectura equivalente a `internalFetchSheetData`/`apiFetchStaffTrackerData`: separa filas activas de filas archivadas (bajo el equivalente del separador `"TAREAS REALIZADAS"`).
- ☐ Endpoint de guardado por lotes equivalente a `apiSaveTrackerBatch` (Anexo A §19.2) que reproduzca, como mínimo:
  - ☐ Generación de `_tempId` en cliente + bloqueo anti-duplicación de 120s en servidor (Gatekeeper, §10.3).
  - ☐ Búsqueda de fila por folio existente, con fallback a búsqueda por `CONCEPTO`+`FECHA` si el folio no se encuentra o hay desplazamiento de filas.
  - ☐ Generación atómica de folios (`generateNumericSequence`, con lock, fallback a número aleatorio si supera 10,000,000).
  - ☐ Auto-sanación de secuencia de folios `AV-XXXX` para `ANTONIA_VENTAS` (escaneo del batch por folios más altos que el contador guardado).
  - ☐ Auto-archivado de filas al 100% (evaluando `ESTATUS` en la lista de estados terminales, o `AVANCE`/`CUMPLIMIENTO` en `100`/`100%`/`SI`/valor numérico `1`).
- ☐ Endpoint de edición de una sola fila equivalente a `internalUpdateTask` (Anexo A §19.4), incluyendo la redirección forzosa: escribir en la hoja/tabla maestra de Ventas si el usuario no es la cuenta de Ventas se redirige al Tracker de la persona en cuestión, no a la tabla maestra.
- ☐ Guardia de inmutabilidad: el equivalente de la hoja `PPCV3` es de solo lectura fuera del flujo "Planeación Semanal" (rechazo explícito, no silencioso).
- ☐ Resolución de alias de columna (15 grupos, ver diccionario completo en Anexo A §19.3) — si la migración usa columnas de base de datos con nombres fijos en vez de texto libre, este punto puede resolverse estructuralmente en el modelo de datos en vez de replicar el alias-matching, **pero debe documentarse esa decisión de diseño**.
- ☐ Interpretación de `AVANCE`/`CUMPLIMIENTO`: `100`, `'100'`, `'100%'`, `'SI'` y el equivalente del valor porcentual crudo de Sheets (`1.0`) tratados todos como "100%" — o, si la migración usa un tipo de dato numérico real (recomendado), documentar que este parcheo defensivo ya no aplica y por qué.

### 22.4 Papa Caliente — máquina de estados de cotizaciones (spec: §10.2, `PAPA_CALIENTE_SDD.md`)

- ☐ Modelo de datos para las 7 etapas `L, CD, EP, CI, EV, CEC, RCC` en orden fijo.
- ☐ Estructura equivalente a `PROCESO_LOG`: por cada paso, `step`, `status` (`IN_PROGRESS`/`DONE`), `assignee`, `timestamp`/`dateStr`, `endTimestamp`/`endDateStr`.
- ☐ Endpoint de delegación: asigna un paso a un trabajador, copia la tarea a su Tracker con estado inicial `PENDIENTE`/`0%`, dispara notificación (ver §22.11).
- ☐ Endpoint/lógica de reverse-sync: cuando el delegado marca su tarea como terminada (criterio flexible: `100`, `100%`, `1`, `1.0`, `HECHO`, `TERMINADO`, `FINALIZADO`, `REALIZADO`, `COMPLETADO`, `DONE`, `SI`), la etapa correspondiente en `PROCESO_LOG` pasa a `DONE` y se copian los archivos adjuntos de vuelta a la tabla maestra — **sin** sobrescribir `ESTATUS`/`AVANCE` de la fila maestra con los del delegado.
- ☐ Regeneración del string visual equivalente a `MAP COT` (o su reemplazo estructurado) sincronizada con `PROCESO_LOG`.
- ☐ Cierre terminal en `RCC` con las 3 resoluciones: `GANADA`, `PERDIDA X PRECIO`, `DESCUENTO`.
- ☐ Ejemplo de payload/estado completo reproducido en §10.2 — usarlo como caso de prueba end-to-end literal (crear folio → delegar `CD` → completar como delegado → verificar reverse-sync).

### 22.5 Enrutamiento y "Caso Antonia" (spec: §10.1)

- ☐ Prefijo de folio `AV-` exclusivo de la cuenta de Ventas maestra.
- ☐ Redirección forzosa: cualquier usuario que no sea la cuenta de Ventas nunca puede escribir directamente en la tabla maestra de Ventas.
- ☐ Filtro de sufijo `(VENTAS)`: ningún usuario excepto la cuenta de Ventas puede enrutar hacia tablas que representen "Ventas" de otra persona.
- ☐ `VENDEDOR`, `RESPONSABLE`, `INVOLUCRADOS` tratados como sinónimos intercambiables en la lógica de distribución (no como 3 campos con lógica distinta) — confirmar que la migración no los separó accidentalmente en 3 flujos diferentes.
- ☐ Lista blanca (`allowedBase`) de columnas editables sobre una fila ya existente de la tabla maestra de Ventas — 45 columnas exactas listadas en §5.4, más cualquier columna con "FECHA"/"ALTA" en el nombre.

### 22.6 Módulo PPC — checklist de sitio (spec: §5.5, §7.4, Anexo A §19.6)

- ☐ Distinción clara en el código/documentación de la migración entre "módulo PPC" (checklist de sitio) y "Papa Caliente" (pipeline de cotizaciones) — **no fusionarlos**, son sistemas independientes (§10.4).
- ☐ Endpoint equivalente a `apiSavePPCData`: guarda en la tabla maestra PPC, distribuye a cada `responsable` (múltiples, separados por coma) a su Tracker personal, respalda en la tabla de control, y (si el usuario es la cuenta de Ventas) también en la variante `PPCV4` con mapeo de encabezados alterno.
- ☐ Auto-migración de columnas específicas para `JESUS_CANTU` (`RUTA_CRITICA`, `ZONA`, `CUANT_REQUERIDO`, `CUANT_REAL`, `CONTRATISTA`, `DIAS_L`...`DIAS_D`) — si el modelo de datos de la migración ya tiene columnas fijas, confirmar que existen sin necesidad de "auto-migración" en caliente.
- ☐ Filtrado de columnas específico para `JESUS_CANTU` al distribuir a Tracker personal (solo 9 campos, no todo el objeto).
- ☐ `CUMPLIMIENTO` con fallback estricto a `'NO'` si viene vacío.
- ☐ Los 3 subtipos de PPC (`PPC INTERNO`, `PPC PREOPERATIVO`, `PPC CLIENTE`) como parte de la estructura estándar de subproyectos.

### 22.7 Work Orders (spec: §5.7, §16.1)

- ☐ Modelo de datos equivalente a las 5 tablas relacionales `DB_WO_MATERIALES`, `DB_WO_MANO_OBRA`, `DB_WO_HERRAMIENTAS`, `DB_WO_EQUIPOS`, `DB_WO_PROGRAMA`, todas ligadas por `FOLIO` — columnas exactas en §5.7.
- ☐ Algoritmo de folio equivalente a `generateWorkOrderFolio`: secuencia de 4 dígitos + iniciales de cliente + abreviatura de departamento (mapa de 19 entradas) + fecha `DDMMYY` — o un esquema de folio nuevo, documentado explícitamente como cambio de diseño.
- ☐ Sub-objeto de flujo de aprobación (`papaCaliente` en materiales/herramientas: Residente→Compras→Controller→Almacén→Logística) — tercera acepción de "papa caliente" del sistema (§10.4), verificar que no se confundió con las otras dos al migrar.
- ☐ Control vehicular duplicado (dos bloques independientes de inspección/checklist en el mismo formulario) — confirmar si la migración preserva la duplicación o la resolvió a una lista de N vehículos (cambio de diseño razonable, pero debe documentarse).
- ☐ 🐛 **No hace falta replicar**: en el sistema original, `workorder_form.html` es código huérfano nunca servido (§16.1) — la migración no necesita un artefacto equivalente separado, el formulario de Work Order es una vista más dentro de la SPA/API principal.

### 22.8 Proyectos / Cascada Sitio→Subproyecto→Tarea (spec: §5.8, Anexo A §19.12)

- ☐ Modelo de datos equivalente a `DB_SITIOS` (`ID_SITIO`, `NOMBRE`, `CLIENTE`, `TIPO`, `ESTATUS`, `FECHA_CREACION`, `CREADO_POR`) y `DB_PROYECTOS` (`ID_PROYECTO`, `ID_SITIO`, `NOMBRE_SUBPROYECTO`, `TIPO`, `ESTATUS`, `FECHA_CREACION`, `CREADO_POR`).
- ☐ Al crear un sitio, auto-generación de los 10 subproyectos estándar (`NAVE`, `AMPLIACION`, `PPC INTERNO`, `PPC PREOPERATIVO`, `PPC CLIENTE`, `DOCUMENTOS`, `PLANOS Y DISEÑOS`, `FOTOGRAFIAS`, `CORRESPONDENCIA`, `REPORTES`).
- ☐ Endpoint equivalente a `apiFetchCascadeTree` que arma el árbol completo Sitio→Subproyectos.
- ☐ 🐛 **BUG CONOCIDO — corregir, no replicar**: el endpoint equivalente a `apiFetchProjectTasks` en el sistema original **siempre falla** (`ReferenceError` por variable indefinida, §16.2, Anexo A §19.12) — la migración debe implementar correctamente el filtrado de tareas por proyecto (por la etiqueta `[PROY: <nombre>]` en comentarios/concepto, o mejor, por una relación estructurada `project_id` en el modelo de datos de Python), **no** replicar la falla.
- ☐ Etiquetado de tareas por proyecto: en el original, se inyecta un tag de texto `[PROY: <nombre>]` dentro del campo de comentarios como mecanismo de relación (`apiSaveProjectTask`) — la migración debería reemplazar esto por una relación de base de datos real (foreign key), documentado como mejora intencional.

### 22.9 KPIs — Dashboard ejecutivo (spec: §5.10, §10.5, Anexo A §19.7)

- ☐ Endpoint equivalente a `apiFetchAdminKPIs` que recalcule en vivo (no desde snapshot) sobre las tablas de Ventas de los 6 vendedores exactos: `ANGEL_SALINAS`, `TERESA_GARZA`, `EDUARDO_TERAN`, `EDUARDO_MANZANARES`, `RAMIRO_RODRIGUEZ`, `SEBASTIAN_PADILLA` (`ANTONIA_VENTAS` excluida deliberadamente).
- ☐ Fórmula `% de Ganadas` = ganadas / (ganadas + enviadas-sin-ganar), **no** ganadas/total (§10.5).
- ☐ Fórmula `% Cierre por colaborador` = ganadas / (ganadas + canceladas), excluyendo explícitamente lo que sigue en curso.
- ☐ Semaforización de colaborador: `avgEfic > 2.0` → "Cuello botella"; `>= 1.5` → "Riesgo"; si no, "Eficiente".
- ☐ Productividad semanal solo cuenta los últimos 7 días, agrupados Lunes-Viernes (sin fin de semana).
- ☐ ⚠️ **Decisión de diseño**: en el original, `JUDITH_ECHAVARRIA`, `ALFONSO_CORREA` y `JUAN_JOSE_SANCHEZ` son `seller: true` pero **no** están en la lista de 6 vendedores analizados por el Dashboard de KPIs — confirmar si la migración corrige esta inconsistencia (incluir a los 9 `seller: true`) o la preserva; cualquiera de las dos es válida pero debe ser una decisión explícita, no un olvido.

### 22.10 Agentes narrativos con IA (spec: Anexo A §19.17–19.19)

- ☐ Motor de métricas de cotizaciones (`apiFetchQuoteAgentMetrics`) con SLA por clasificación `A`/`AA`/`AAA` (límites 3/14/30 días respectivamente) y agrupación por cotizador.
- ☐ Motor de reglas de alerta de cotizaciones — 4 reglas exactas con sus umbrales, tabla completa en Anexo A §19.17.
- ☐ Motor de métricas de productividad de Trackers (`apiFetchTrackerProductivityMetrics`) — excluye vendedores (`seller: true`) y la cuenta de Ventas; solo cuenta personal `ESTANDAR`/`HIBRIDO`.
- ☐ Motor de reglas de alerta de productividad — 3 reglas exactas, ver Anexo A §19.18.
- ☐ Integración con Gemini para generar el resumen narrativo — usar la key desde configuración/secretos (no hardcodeada, ver §22.11).
- ☐ Envío de reporte HTML por correo — decidir el canal en Python (SMTP/SendGrid/etc., equivalente a `MailApp`).
- ☐ 🐛 **BUG CONOCIDO — corregir, no replicar**: en el original, el reporte de productividad nunca llega a los roles `ADMIN_CONTROL` porque busca una llave de usuario inexistente (`USER_DB['ADMIN_CONTROL']`, Anexo A §19.18) — la migración debe resolver correctamente los destinatarios por rol (ej. iterar todos los usuarios con `role == 'ADMIN_CONTROL'`), no replicar la lista de destinatarios incompleta.

### 22.11 Integraciones externas (spec: §11, Anexo A §19.8/§19.14)

- ☐ Notificación de asignación de tarea hacia Outlook/Microsoft 365 — vía el canal que la migración elija (webhook a Make.com/Power Automate igual que el original, Microsoft Graph API directo, u otro) — payload mínimo: folio, título, descripción, fecha inicio/fin, correo destino, quién asignó.
- ☐ Los 3 puntos de disparo exactos de esa notificación: delegación de paso Papa Caliente, asignación general vía `VENDEDOR`/`RESPONSABLE`/`INVOLUCRADOS`, asignación desde el módulo PPC (lista completa en §11.2).
- ☐ Resolución de email de usuario por nombre visible (`findUserEmailByLabel`) — tolerante a variaciones de formato de nombre.
- ☐ Integración con Gemini API para resúmenes narrativos y (opcionalmente) transcripción de audio.
- ☐ 🐛 **BUG CONOCIDO — corregir, no replicar**: la API key de Gemini hardcodeada en texto plano en `transcribirConGemini` (§13, Anexo A §19.14) — la migración debe leer **todas** las credenciales de Gemini desde variables de entorno/secret manager, sin excepción, y la key expuesta (`AIzaSyA7Lv551Quq7lMCynU7kRq9T1_MIaK6kkc`) debe darse por comprometida y rotarse en Google Cloud independientemente de la migración.
- ☐ ⚠️ **Decisión de diseño**: si la migración a FastAPI ya no usa Google Sheets, decidir si el flujo de transcripción de audio se conserva igual (Gemini) o se resuelve con otro proveedor — no es parte del comportamiento de negocio central, es infraestructura.

### 22.12 Triggers y automatizaciones (spec: §12)

- ☐ Job diario equivalente a `incrementarContadorDias` (recalcula el contador de días transcurridos por fila) — en Python probablemente ya no hace falta si el cálculo se hace on-the-fly en cada request en vez de mantenerse cacheado en una celda, documentar la decisión.
- ☐ Job diario equivalente a `autoUpdateQuoteMetrics` (refresco de métricas agregadas de cotizaciones).
- ☐ Menú/comandos administrativos nativos de Sheets (`onOpen`, `cmdRealizarAlta`, `cmdActualizar`) — sin equivalente necesario en una API REST pura; confirmar que la funcionalidad que exponían (alta/actualización rápida de fila) está cubierta por otro medio (endpoint admin, panel, etc.).
- ☐ Sistema de folio legado (`generarFolioAutomatico`, numérico simple, distinto de `AV-XXXX`) — evaluar si sigue siendo necesario o es deuda técnica que no debe migrarse (§12).

### 22.13 Banco de Información y Agenda personal (spec: §5.9, §5.11, Anexo A §19.15–19.16)

- ☐ Estructura de archivos equivalente a `[Año]/[Mes]/[Cliente]` (o su equivalente en el storage elegido para Python — S3, filesystem, etc.) para cotizaciones archivadas.
- ☐ Archivado automático disparado al guardar una fila con `COTIZACION`/`ARCHIVO` no vacío, tanto en el flujo batch como en edición individual.
- ☐ Endpoints equivalentes a `apiFetchInfoBankCompanies`/`apiFetchInfoBankData`/`apiFetchDistinctClients`, leyendo **solo** de la tabla maestra de Ventas (histórico consolidado, no todas las tablas).
- ☐ Modelo de datos equivalente a `AGENDA_PERSONAL` y `HABITOS_LOG` (columnas en §5.11) — notar que en el original **no** están en la configuración central (`APP_CONFIG`), es un módulo aparte.
- ☐ ⚠️ **Decisión de diseño**: el original devuelve datos de ejemplo hardcodeados si las tablas de agenda/hábitos no existen aún (§5.11) — decidir si la migración preserva ese fallback de demo o simplemente devuelve listas vacías (ambas son válidas, pero afecta la primera experiencia de un tenant/usuario nuevo).

### 22.14 Frontend / Paridad de UI (spec: §8–§9, §20, Anexo C §21)

- ☐ Las ~90 variables de estado documentadas en el Anexo C tienen su equivalente funcional en el estado del frontend de Python (React/Vue/lo que sea) — no es necesario que sean literalmente `ref()` de Vue, pero sí que exista cobertura funcional 1 a 1 (ningún módulo "perdido" en la migración).
- ☐ Mapa de vistas (§8.3): las 10 vistas activas migradas (excluyendo `ECG_VIEW`, que ya estaba deshabilitada en el original — no hace falta migrarla salvo que se quiera reactivar el módulo).
- ☐ Reglas tipográficas obligatorias: cabeceras en minúsculas (excepto "Folio"/"ID"), datos en mayúsculas, tabla base 11px Arial (§9, `AGENTS.md` §7).
- ☐ Semáforo de fechas por `CLASIFICACION` (`A`=3d/buffer 1, `AA`=15d/buffer 3, `AAA`=30d/buffer 5) — lógica exacta en Anexo B §20.3, reproducida también server-side en el original vía `applyTrafficLightToSheet` (Anexo A §19.13); en la migración probablemente basta con una sola implementación (server o client), no las dos duplicadas.
- ☐ Timeline visual de Papa Caliente con los 7 pasos y sus 3 estados de color (pendiente/en progreso/completado) — lógica de cálculo de tiempo transcurrido en Anexo B §20.5.
- ☐ Permisos de edición por celda equivalentes a `isFieldEditable` — confirmar que la fuente de verdad de permisos vive **solo** en el backend de Python (el original tiene una duplicación frontend/backend parcialmente inconsistente, ver nota en Anexo B §20.1; la migración es una oportunidad de tener una sola fuente de verdad consultada por el frontend, no una copia).

### 22.15 Seguridad (spec: §13)

- ☐ Contraseñas migradas con hash+salt, **nunca** en texto plano en base de datos ni en el repositorio de código de la migración.
- ☐ Las 41 contraseñas actuales (expuestas en el historial de este repo GAS) tratadas como comprometidas y rotadas antes de dar acceso a los usuarios reales en el sistema Python.
- ☐ La API key de Gemini hardcodeada (§13, §22.11) rotada independientemente de cuándo se complete la migración.
- ☐ Autorización por columna/campo con una única fuente de verdad server-side (no duplicada cliente/servidor como en el original).
- ☐ Si se expone algún endpoint tipo webhook (equivalente al de Make.com/Outlook), validar que tenga algún mecanismo de autenticación/secreto compartido — el original no lo tiene (§13).

---

## 23. Buenas Prácticas Recomendadas para la Migración (anti-patrones reales detectados y su remedio)

> Esta sección no es una lista genérica de "buenas prácticas de software" — cada ítem cita el **anti-patrón real y específico** encontrado al leer `CODIGO.js`/`index.html` línea por línea para este SSD, casi siempre explicable por "se hizo así por velocidad de entrega", y propone el remedio concreto aplicable en FastAPI/Python. Las contraseñas en texto plano y la API key hardcodeada ya están cubiertas en §13 y §22.11/§22.15 — aquí van los demás.

### 23.1 Lógica de negocio hardcodeada por nombre de persona, no por atributo/rol

**Evidencia:** el código tiene decenas de condicionales del tipo `if (username === 'JESUS_CANTU')`, `if (String(username).toUpperCase().trim() === 'JUANY_RODRIGUEZ')`, `if (personName === "ANTONIA PINEDA LOPEZ" && username === "ANTONIA_VENTAS")`, dispersos en `getSystemConfig`, `apiSaveTrackerBatch`, `apiSavePPCData`, `generatePrefix`. Cada vez que alguien cambia de puesto o se contrata a reemplazar a esa persona, hay que **editar y redesplegar el código fuente**, no cambiar un dato.

**Por qué es un problema:** acopla reglas de negocio a identidades específicas en vez de a los atributos que esas identidades representan (rol, permiso, tipo de cuenta). Es exactamente el motivo por el que la excepción de `JUANY_RODRIGUEZ` (§6.2) es fácil de perder en una migración — nadie la va a encontrar buscando "roles" o "permisos", solo leyendo cada función una por una, como tuve que hacer yo para este documento.

**Remedio en FastAPI/Python:**
- Modelar permisos como **datos**, no como código: una tabla `role_overrides` o un campo `extra_departments: list[str]` en el modelo de usuario, en vez de un `if` con el username literal.
- Los relabels dinámicos (ej. "PPC Maestro" → "INTERDICIPLINARIA" solo para `JESUS_CANTU`) deberían ser un campo de configuración por usuario/rol (`custom_module_labels: dict`), no una rama de código.
- Regla general: si al leer una función de negocio aparece un nombre propio entre comillas, es una señal de que ese dato debería vivir en la base de datos.

### 23.2 Listas de "quién es vendedor"/"quién tiene restricciones" hardcodeadas y duplicadas, en vez de un atributo consultado dinámicamente

**Evidencia:** el array `sellers`/`restrictedUsers` de 6 nombres aparece **repetido y ligeramente distinto** en al menos 3 lugares (`apiFetchAdminKPIs`, `internalUpdateTask`) — y es la causa raíz de la inconsistencia documentada en §22.9: 9 usuarios tienen `seller: true` en `USER_DB`, pero solo 6 aparecen en la lista hardcodeada del Dashboard de KPIs.

**Por qué es un problema:** dos fuentes de verdad para el mismo concepto ("¿quién es vendedor?") que pueden divergir — y de hecho ya divergieron en producción. Cada función que necesita "la lista de vendedores" la reinventa.

**Remedio en FastAPI/Python:** una sola función/query (`get_sellers()` → `SELECT * FROM users WHERE seller = true`) consultada por **todo** el código que necesite esa lista. Nunca una lista literal de usernames dentro de una función de negocio. Si un vendedor se da de baja o se contrata uno nuevo, un solo `UPDATE` en la base de datos basta — cero despliegues de código.

### 23.3 Doble fuente de verdad para el mismo estado (string visual vs. JSON estructurado)

**Evidencia:** el timeline de Papa Caliente se representa simultáneamente en `PROCESO_LOG` (JSON estructurado, la fuente "real") y en `MAP COT` (string con emojis, regenerado a mano por 3 implementaciones casi idénticas del mismo algoritmo de reconstrucción — en `apiSaveTrackerBatch`, `internalUpdateTask` y el propio `getProcessTimeline` del frontend). El código incluso tiene manejo especial para "entradas basura" (`garbageForStep`) del `MAP COT` que quedaron desincronizadas de `PROCESO_LOG` en algún momento — evidencia directa de que la duplicación ya causó bugs de datos en producción.

**Por qué es un problema:** cualquier vista derivada (un string legible) que se persiste por separado del dato estructurado del que deriva, tarde o temprano se desincroniza. El código de "reconciliación" (`garbageForStep`) es deuda técnica pagando intereses sobre esa decisión original.

**Remedio en FastAPI/Python:** persistir **solo** el JSON estructurado (`proceso_log` como columna JSONB, o mejor, una tabla `pipeline_steps` normalizada con `step`, `status`, `assignee_id`, `started_at`, `ended_at`). La representación visual (el equivalente al `MAP COT`) se **calcula al vuelo** en el endpoint de lectura o en el frontend a partir del dato estructurado — nunca se persiste una copia. Elimina por completo la clase de bug que representa `garbageForStep`.

### 23.4 Enums de negocio repetidos como arrays literales en cada función, en vez de una constante única

**Evidencia:** la lista de "estados que cuentan como completado" —`['HECHO', 'TERMINADO', 'FINALIZADO', 'REALIZADO', 'COMPLETADO', 'DONE']`— aparece **copiada y pegada, idéntica, al menos 4 veces** (`apiSaveTrackerBatch`, `internalUpdateTask` ×2, `internalBatchUpdateTasks`). Lo mismo con la lista de columnas a excluir al hacer reverse-sync (`['ESTATUS', 'STATUS', 'ESTADO', 'AVANCE', 'AVANCE %', '% AVANCE', '%', 'CUMPLIMIENTO']`), repetida 3 veces.

**Por qué es un problema:** si mañana el negocio agrega un octavo valor válido para "completado" (ej. `'CERRADO'`), hay que recordar actualizar las 4 copias — y ya vimos con `MAP COT`/`garbageForStep` qué pasa cuando el sistema depende de mantener copias sincronizadas a mano.

**Remedio en FastAPI/Python:** un único `Enum`/`Literal` de Python (`class TaskStatus(str, Enum): DONE = "HECHO"; ...`) o una constante `COMPLETED_STATUSES: frozenset[str]`, importado donde se necesite. Es el ejemplo de libro de texto de por qué DRY importa: no es estética, es que **el bug de sincronización ya ocurrió en este código** (§10.2, `garbageForStep`).

### 23.5 Nombres de hoja/tabla como strings literales dispersos, solo parcialmente centralizados

**Evidencia:** `APP_CONFIG` centraliza *algunos* nombres de tabla (`ppcSheetName`, `logSheetName`, etc., §5.1) — pero `"ANTONIA_VENTAS"`, `"ADMINISTRADOR"`, `"PPCV4"`, `"AGENDA_PERSONAL"`, `"HABITOS_LOG"`, `"DB_SITIOS"`, `"DB_PROYECTOS"` aparecen como literales de texto sueltos por todo `CODIGO.js`, sin pasar por ninguna constante (§5.11 documenta esto explícitamente para las dos últimas).

**Por qué es un problema:** centralización a medias es peor que ninguna, porque da una falsa sensación de que "ya está resuelto" — un `grep` rápido de `"ANTONIA_VENTAS"` en el código encuentra decenas de apariciones literales que un refactor de nombre tendría que tocar una por una.

**Remedio en FastAPI/Python:** un único módulo `constants.py` (o, mejor aún, nombres de tabla reales de SQL que nunca se referencian por string en absoluto, sino a través del ORM) con **cero** excepciones — si hace falta referenciar el nombre de una tabla/entidad más de una vez, es una constante, sin importar cuán "obvio" parezca el nombre en el momento de escribirlo.

### 23.6 Funciones gigantes que hacen 5 cosas a la vez ("God functions")

**Evidencia:** `apiSaveTrackerBatch` (Anexo A §19.2) tiene 487 líneas y hace, en una sola función: generación de folios, saneamiento de datos, distribución a hojas de otros usuarios, envío de notificaciones a Outlook, archivado de cotizaciones, y reverse-sync completo con reconciliación de `MAP COT`. `internalBatchUpdateTasks` (444 líneas) mezcla resolución de alias de columnas, tres estrategias distintas de matching de filas, deduplicación intra-batch, y auto-archivado.

**Por qué es un problema:** son imposibles de testear unitariamente (los tests existentes en `test_*.js`, §14, tienen que mockear el archivo *completo* con `vm`/regex-patching porque no hay forma de aislar una sola responsabilidad) y cualquier cambio pequeño en una de las 5 responsabilidades arriesga romper las otras 4 sin que ningún test lo detecte a tiempo — que es, con alta probabilidad, cómo se originaron los bugs documentados en §16.2/§19.18.

**Remedio en FastAPI/Python:** descomponer en servicios de responsabilidad única inyectables (`FolioService`, `DistributionService`, `ReverseSyncService`, `NotificationService`, `ArchivingService`), orquestados por un caso de uso delgado (`SaveTrackerBatchUseCase`) que los llama en secuencia. Cada servicio se testea unitariamente con mocks reales de sus dependencias (no regex sobre texto fuente), y un cambio en `NotificationService` no puede romper `FolioService` porque no comparten estado mutable implícito.

### 23.7 Estado global mutable a nivel de módulo, sin inyección de dependencias

**Evidencia:** `const SS = SpreadsheetApp.getActiveSpreadsheet();` (línea 10) es una variable global de módulo que **todas** las funciones del backend usan implícitamente. Es la razón por la que los tests en Node (§14) tienen que hacer `code.replace(/const SS = SpreadsheetApp\.getActiveSpreadsheet\(\);/g, ...)` sobre el **texto fuente** antes de poder ejecutar nada — un `sed` sobre el código como estrategia de testing es la señal más clara posible de que falta inyección de dependencias.

**Por qué es un problema:** acoplamiento fuerte a un recurso global hace que testear cualquier función aislada requiera trucos frágiles (parchear texto fuente) en vez de simplemente pasar un mock.

**Remedio en FastAPI/Python:** usar el sistema de dependencias de FastAPI (`Depends()`) para inyectar la sesión de base de datos (o cualquier repositorio) en cada endpoint/servicio. En testing, se sobreescribe la dependencia (`app.dependency_overrides`) con una implementación en memoria o una base de datos de prueba — sin tocar una sola línea del código de producción ni parchear texto fuente.

### 23.8 Errores silenciados o indiferenciados (`catch(e) {}` y `catch(e) { return {success:false, message: e.toString()} }` genérico en todas partes)

**Evidencia:** hay bloques `catch(e) {}` completamente vacíos (ej. dentro del loop de distribución de `apiSaveTrackerBatch`, Anexo A §19.2) que tragan cualquier excepción sin registrar nada. Y el patrón dominante en el resto del código es capturar **cualquier** excepción — desde un error de red esperable hasta un `ReferenceError` de programación como el de §16.2 — y devolver el mismo `{success: false, message: e.toString()}` genérico. Así fue como el bug de `apiFetchProjectTasks` (una falla de programación, no una condición de negocio) pasó desapercibido: el `catch` no distingue "el usuario no tiene permiso" de "hay un typo en el código".

**Por qué es un problema:** un `catch` que no distingue tipos de error hace indetectables los bugs de programación — se ven idénticos a errores de negocio esperables, y no hay ninguna alerta/log estructurado que dispare una notificación cuando ocurre algo que **no debería poder pasar nunca** (como una `ReferenceError`).

**Remedio en FastAPI/Python:** usar excepciones tipadas (`class BusinessRuleError(Exception)` vs. dejar que los `TypeError`/`AttributeError`/etc. de programación **se propaguen** sin capturarlos genéricamente) + un manejador de excepciones global de FastAPI que traduzca errores de negocio a respuestas HTTP controladas (400/409) y **reporte a un sistema de monitoreo** (Sentry, logging estructurado con nivel `ERROR`) cualquier excepción no anticipada, en vez de devolverla silenciosamente como un JSON `{success:false}` indistinguible de un caso de negocio normal.

### 23.9 Validación de entrada manual y defensiva en vez de esquemas declarativos

**Evidencia:** todo el código está lleno de patrones `item.concepto || item.CONCEPTO`, `taskData['ESTATUS'] || 'PENDIENTE'`, `Object.keys(taskData).find(k => k.toUpperCase().trim() === 'FOLIO')` — validación y normalización de payloads hecha a mano, campo por campo, en cada función (ver `apiSavePPCData`, Anexo A §19.6, como ejemplo extremo: ~25 campos mapeados manualmente con fallbacks `||`).

**Por qué es un problema:** no hay ningún punto único donde se garantice la forma de un payload — cada función reimplementa su propia validación ad hoc, con inconsistencias entre funciones (una espera `folio` en minúscula, otra `FOLIO` en mayúscula) que son precisamente la razón por la que existe toda la infraestructura de "insensibilidad a mayúsculas" documentada en §10.6.

**Remedio en FastAPI/Python:** modelos Pydantic explícitos en cada endpoint (`class SaveTrackerTaskRequest(BaseModel): folio: str | None = None; estatus: TaskStatus = TaskStatus.PENDIENTE; ...`). FastAPI valida automáticamente en el borde de la API, devuelve 422 con el detalle exacto del campo inválido, y **elimina por completo** la necesidad de la capa de "resolución de alias de columna insensible a mayúsculas" (§10.6, Anexo A §19.3) — esa capa entera es un parche sobre la falta de un esquema, no una funcionalidad de negocio que deba migrarse.

### 23.10 Sin paginación: cada lectura carga la hoja/tabla completa en memoria

**Evidencia:** literalmente todas las funciones de lectura (`internalFetchSheetData`, `apiFetchInfoBankData`, `deduplicateAllSheets`, etc.) hacen `sheet.getDataRange().getValues()` — traen **toda** la hoja a memoria, sin importar si tiene 50 o 50,000 filas, y filtran/agregan en JavaScript después.

**Por qué es un problema:** es razonable en Google Sheets (no hay otra API), pero es un anti-patrón grave si se replica contra una base de datos real — no escala, y desperdicia round-trips de red trayendo datos que se van a descartar de inmediato.

**Remedio en FastAPI/Python:** filtrar y paginar en la consulta SQL (`WHERE`, `LIMIT`/`OFFSET` o cursor-based pagination), nunca traer la tabla completa para filtrar en Python. Los cálculos de agregación (KPIs, métricas de productividad) deberían resolverse con `GROUP BY`/funciones de ventana en SQL cuando sea posible, no iterando arrays en memoria como hace todo el código actual (`apiFetchAdminKPIs`, Anexo A §19.7, es el ejemplo más claro: agregación manual en JS sobre datos ya cargados por completo).

### 23.11 Esquema de "base de datos" sin migraciones versionadas — se crea la hoja "si no existe" en tiempo de ejecución

**Evidencia:** el patrón `let sheet = findSheetSmart(name); if (!sheet) { sheet = SS.insertSheet(name); sheet.appendRow([...headers]); }` se repite en más de 10 funciones distintas — el "esquema" de cada tabla vive implícito en el primer lugar del código que la usa, no en un solo sitio versionado.

**Por qué es un problema:** no hay forma de saber, sin leer todo `CODIGO.js`, cuál es el esquema completo y actual de una tabla — y si dos funciones distintas crean la misma tabla con headers ligeramente distintos en algún momento de la historia del código, se generan inconsistencias silenciosas.

**Remedio en FastAPI/Python:** migraciones versionadas con Alembic (o el equivalente del ORM elegido) como única fuente de verdad del esquema, aplicadas explícitamente en deploy — nunca "crear la tabla la primera vez que alguien la usa" como efecto secundario de un endpoint de negocio.

### 23.12 Aprovechar lo que FastAPI da gratis y el sistema original no tenía

Esto no es un anti-patrón a corregir sino una oportunidad a **no desperdiciar** en la migración:
- **Documentación OpenAPI automática**: el sistema original no tiene ningún contrato de API formal — `google.script.run` es RPC implícito sin schema. FastAPI genera `/docs` automáticamente a partir de los modelos Pydantic; usarlo como la única fuente de verdad de la API en vez de escribir documentación de endpoints a mano (que se desactualiza).
- **`Depends()` para autorización centralizada**: reemplaza la lógica de permisos duplicada y parcialmente inconsistente entre frontend (`isFieldEditable`, Anexo B §20.1) y backend (`allowedBase`, `restrictedUsers`) por un único `Depends(require_role(...))`/`Depends(check_field_permission(...))` consultado en cada endpoint — una sola fuente de verdad de autorización, nunca duplicada en el cliente.
- **`response_model` tipado**: garantiza que la forma de la respuesta sea siempre consistente, eliminando la necesidad de que el frontend tolere campos en mayúsculas/minúsculas variables como hace hoy (§10.6).
- **Testing con `TestClient` + fixtures reales de base de datos** en vez de regex-patchear el código fuente (§14, §23.7) — pytest + una base de datos de prueba (SQLite en memoria o un contenedor) permite tests de integración reales y rápidos, algo que el sistema original nunca pudo tener por estar atado a servicios de Google no mockeables limpiamente.

---

*Fin del documento. Este SSD se generó por inspección directa y literal del código fuente (`CODIGO.js`, `index.html`, `appsscript.json`, `CREDENCIALES.md`) y de todos los SDD existentes en el repositorio a la fecha indicada — no es una fuente independiente del código, es su mapa y, en los Anexos A/B, su copia literal de las partes más críticas. El §22 es la capa de verificación pensada específicamente para auditar la migración a Python/FastAPI; el §23 es la capa de mejora consciente (qué NO replicar tal cual, y por qué). Úsalos como checklists activos, no como lectura pasiva. Si el código GAS original cambia, este documento debe re-derivarse.*
