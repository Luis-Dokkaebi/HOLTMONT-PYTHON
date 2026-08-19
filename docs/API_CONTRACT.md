# Especificación de API / Contratos (SDD)

Este documento es la **especificación narrativa** del contrato de datos y endpoints de Holtmont
Workspace. La versión formal y validable está en [`openapi.yaml`](openapi.yaml).

---

## 1. Modelo de transporte: RPC sobre Google Apps Script

El sistema **no expone REST**. El frontend invoca funciones del backend (`CODIGO.js`) mediante el
puente RPC de Apps Script:

```js
google.script.run
  .withSuccessHandler(respuesta => { /* respuesta = objeto retornado por la función */ })
  .withFailureHandler(err => { /* excepción del servidor */ })
  .apiSaveTrackerBatch(personName, tasks, username);   // llamada RPC
```

**Reglas del contrato de transporte:**

- Toda función invocable por el FE debe estar en el **scope global** de `CODIGO.js`.
- Los argumentos se pasan **por posición** (no hay body JSON nombrado).
- Los tipos que cruzan el puente deben ser **serializables** (objetos planos, arreglos, strings,
  números, booleanos, `Date`). No se pueden pasar funciones ni objetos de servicio GAS.
- El único endpoint HTTP real es `GET /exec` → `doGet(e)`, que devuelve el HTML de la SPA.

### Envoltura de respuesta estándar

Casi todas las funciones retornan un objeto con esta forma:

```jsonc
{
  "success": true,               // obligatorio
  "message": "texto opcional",   // presente en errores y confirmaciones
  "data":  { /* … */ },          // en lecturas/guardados: payload de negocio
  "headers": [ /* … */ ],        // en lecturas de hoja: encabezados detectados
  "history": [ /* … */ ]         // en algunas lecturas: filas históricas
}
```

En error, típicamente: `{ "success": false, "message": "Error al guardar: …" }`.
Si el sistema está bloqueado por `LockService`: `{ "success": false, "message": "Sistema Ocupado, intenta de nuevo." }`.

---

## 2. Autenticación y control de acceso (RBAC)

La autenticación es **por credenciales en `USER_DB`** (no usa OAuth de Google para identidad de app,
aunque sí requiere los scopes para operar Sheets/Drive).

### `apiLogin(username, password)`
- **Entrada:** `username` (se normaliza a `MAYÚSCULAS.trim()`), `password` (`.trim()`).
- **Salida OK:** `{ success:true, role, name, username }`.
- **Salida error:** `{ success:false, message:'Usuario o contraseña incorrectos.' }`.
- **Efecto:** registra `LOGIN` / `LOGIN_FAIL` en `LOG_SISTEMA`.

### `apiLogout(username)` → `{ success:true }` y log `LOGOUT`.

### Roles (`role`)

| Rol | Quién | Alcance |
|---|---|---|
| `ADMIN` | `LUIS_CARLOS` (CEO) | Todo + KPI Dashboard. |
| `ADMIN_CONTROL` | `JAIME_OLIVO`, `DIMAS_RAMOS` | Todo + monitores Toñita/Control. |
| `PPC_ADMIN` | `JESUS_CANTU` | PPC maestro + proyectos + banco de juntas. |
| `TONITA` | `ANTONIA_VENTAS` | Ventas + tracker espejo de Antonia. |
| `STAFF_USER` | Personal | Su tracker; los `seller:true` también su hoja `NOMBRE (VENTAS)`. |
| `WORKORDER_USER` | `PREWORK_ORDER` | Solo Pre Work Order. |

### `getSystemConfig(role, username)`
Devuelve los menús/departamentos/permisos según rol (ver `SystemConfig` en `openapi.yaml`).
Incluye ramas especiales cableadas por `username` (p. ej. `JUANY_RODRIGUEZ` obtiene vista ampliada
Compras/Facturación/Finanzas; `JESUS_CANTU` renombra el módulo PPC a "INTERDICIPLINARIA").

---

## 3. Endpoints por dominio

> Convención: los argumentos se listan **en orden posicional**.

### 3.1 Directorio / Organigrama

| Función | Args | Retorno | Notas |
|---|---|---|---|
| `getDirectoryFromDB()` | — | `DirectoryEntry[]` | Lee/crea `DB_DIRECTORY`. Usa `LockService`. |
| `apiResyncDirectory()` | — | `{success, message}` | Reescribe `DB_DIRECTORY` con `INITIAL_DIRECTORY` y crea hojas de tracker faltantes. |
| `apiAddEmployee(payload)` | `{name, dept, type}` | `{success, message}` | Valida duplicados; crea hojas según `type`. |
| `apiDeleteEmployee(name)` | `name` | `{success}` | Elimina del directorio. |

### 3.2 Tracker (tareas personales)

| Función | Args | Retorno |
|---|---|---|
| `apiFetchStaffTrackerData(personName)` | `personName` | `SheetDataResult` |
| `apiSaveTrackerBatch(personName, tasks, username)` | ↓ | `SaveResult` (con `data` fusionable) |
| `apiUpdateTask(personName, taskData, username)` | ↓ | `SaveResult` |
| `apiLogDateChange(payload, username)` | ↓ | `{success}` |

`tasks` es un arreglo de `TrackerTask` (ver esquema). Cada fila nueva trae `_tempId`. El backend:
1. **Gatekeeper** (`internalBatchUpdateTasks`): candado en `CacheService` por `_tempId` + hoja.
2. **Resolución de identidad:** busca por `FOLIO`/`ID`; si falla, por combinación `CONCEPTO`+`FECHA`;
   generar folio nuevo es el último recurso.
3. **Filtro de enrutamiento:** para usuarios que no son Antonia, elimina el sufijo `(VENTAS)` del
   destino: `.replace(/\s*\(VENTAS\)/ig, "").trim()`.
4. **Retorno:** la fila completa actualizada en `res.data` para que el FE haga `_isNew=false`.

### 3.3 PPC (captura y distribución)

| Función | Args | Retorno |
|---|---|---|
| `apiSavePPCData(payload, activeUser)` | `payload` (objeto o arreglo de `PPCItem`) | `{success, message, ids[]}` |
| `apiUpdatePPCV3(taskData, username)` | ↓ | `SaveResult` |
| `apiFetchPPCData()` | — | `SheetDataResult` |
| `apiFetchDrafts()` | — | `SheetDataResult` |
| `apiSyncDrafts(drafts)` | `Draft[]` | `{success}` |
| `apiClearDrafts()` | — | `{success}` |

`apiSavePPCData` escribe en `PPCV3`, **distribuye** cada actividad a la hoja de personal destino
(respetando la Ley de Antonia y el filtro `(VENTAS)`), escribe logs en lote y toma un `LockService`
de 30 s. Columnas de `PPCV3`: ver §4 de Arquitectura.

### 3.4 Ventas

| Función | Args | Retorno |
|---|---|---|
| `apiFetchSalesHistory()` | — | `SheetDataResult` |
| `apiFetchDistinctClients()` | — | `{success, data:string[]}` |

**Reverse Sync (prefijo `AV-`):** las tareas originadas en `ANTONIA_VENTAS` llevan folio `AV-…`.
Cualquier actualización lateral hecha por otro trabajador debe reflejarse de vuelta a la hoja maestra
de Antonia. La columna `VENDEDOR` es exclusiva para asignaciones desde `ANTONIA_VENTAS`.

### 3.5 Proyectos

| Función | Args | Retorno |
|---|---|---|
| `apiSaveSite(siteData)` | `{name, client, type?}` | `{success, message}` |
| `apiSaveSubProject(subProjectData)` | `{siteId, name, type?}` | `{success}` |
| `apiFetchCascadeTree()` | — | árbol sitios→subproyectos |
| `apiFetchProjectTasks(projectName)` | `projectName` | `SheetDataResult` |
| `apiSaveProjectTask(taskData, projectName, username)` | ↓ | `SaveResult` |
| `apiCreateStandardStructure(siteId, user)` | ↓ | crea `STANDARD_PROJECT_STRUCTURE` |

### 3.6 Work Orders

| Función | Args | Retorno |
|---|---|---|
| `apiGetNextWorkOrderSeq()` | — | folio siguiente |
| `generateWorkOrderFolio(clientName, deptName)` | ↓ | folio: `<INI-CLIENTE>-<Abrev-Depto>-<####>` |

El contador vive en Script Property `WORKORDER_SEQ`, con secuencia `padStart(4,'0')`.

### 3.7 KPIs y agente Gemini

| Función | Args | Retorno |
|---|---|---|
| `apiFetchAdminKPIs()` | — | KPIs (ADMIN_CONTROL) |
| `apiFetchTeamKPIData(username)` | `username` | KPIs de equipo |
| `apiFetchQuoteAgentMetrics(params)` | `{year, monthName}` | métricas de cotizaciones |
| `apiFetchTrackerProductivityMetrics(params)` | `{year, monthName}` | métricas de productividad |
| `apiWriteQuoteMetricsToSheet(params)` | ↓ | escribe `KPI_COTIZACIONES` |
| `apiSaveGeminiKey(key)` / `apiCheckGeminiKey()` | ↓ | gestiona `GEMINI_API_KEY` |
| `apiGetLastAgentReport()` | — | último reporte (`LAST_AGENT_RUN`) |

`callGeminiAPI(prompt)` usa `GEMINI_API_KEY` de Script Properties; si falta, retorna
`{success:false, message:'GEMINI_API_KEY no configurada.'}`.

### 3.8 Agenda / hábitos / banco

| Función | Args | Retorno |
|---|---|---|
| `apiFetchUnifiedAgenda(username)` | `username` | agenda combinada |
| `apiFetchCombinedCalendarData(sheetName)` | `sheetName` | calendario (ver abajo) |
| `apiSavePersonalEvent(eventData)` | ↓ | `{success}` |
| `apiSaveHabitLog(habitData)` | ↓ | `{success}` |
| `apiFetchInfoBankCompanies(year, monthName)` | ↓ | empresas del banco |
| `apiFetchInfoBankData(year, monthName, company, folder)` | ↓ | datos del banco |

`apiFetchCombinedCalendarData(sheetName)` devuelve **solo lo que esa persona
trabaja**: la fila sale si es RESPONSABLE/INVOLUCRADOS (tracker) o VENDEDOR
(cotizaciones), nunca por haberla asignado. Une los tres orígenes de la persona
—su tracker, su tabla `(VENTAS)` si la tiene y su agenda personal— y agrega dos
columnas calculadas a cada fila:

| Columna | Valores | Para qué |
|---|---|---|
| `ORIGEN` | `TRACKER`, `COTIZACIONES`, `PERSONAL` | la vista distingue una cotización de una actividad |
| `FECHA_CALENDARIO` | `YYYY-MM-DD` o `""` | día en el que se pinta: FECHA en el tracker, F. INICIO en cotizaciones |

### 3.9 Prospección geoespacial (DENUE) — REST real

> **Excepción al §1 de este documento.** Todo lo anterior son funciones RPC
> modeladas como pseudo-rutas. Estas dos **sí son rutas HTTP REST** servidas por
> FastAPI: nacen en la plataforma Python, no vienen de `CODIGO.js`, y no tienen
> equivalente en Apps Script.

| Método y ruta | Entrada | Salida |
|---|---|---|
| `GET /api/geo/catalogo` | — | `{success, alcaldias: [16], giros: [99]}` |
| `GET /api/geo/establecimientos` | `alcaldia`, `giros` (repetible), `personal_min`, `solo_con_contacto`, `bbox`, `limite`, `desplazamiento` | `{success, total, mostrados, items: [...]}` |

**De dónde sale el dato.** De `api/data/denue.sqlite`, un SQLite de solo lectura
que viaja en el bundle con los 20,957 establecimientos de la cadena de valor de
la construcción en CDMX. Se consulta con el `sqlite3` de la biblioteca estándar:
leerlo desde el Parquet original exigiría `pandas` + `pyarrow` + `numpy`, que
desempaquetadas suman 251 MB y rebasan solas el límite de 250 MB de una función
serverless. **Este módulo no añade ninguna dependencia a `api/requirements.txt`.**

El artefacto lo genera `scripts/construir_sqlite.py` del repositorio `ModeloGeo`.
El dato es público del INEGI y solo cambia cuando el instituto publica (cada
semestre); lo que la empresa genere encima —prospecto contactado, asignado,
cotizado— es otra cosa y va a Supabase.

**Las 10 columnas de `items`**, y ninguna más:

`id`, `nom_estab`, `nombre_act`, `per_ocu`, `telefono`, `correoelec`, `www`,
`municipio`, `latitud`, `longitud`.

El SQLite guarda 14 y el DENUE publica 42. El domicilio (`cod_postal`,
`nom_vial`, `numero_ext`) y `codigo_act` se quedan dentro: una fila completa son
~1.5 KB y 3,000 marcadores serían 4.5 MB de JSON por cada paneo del mapa.

**Tres reglas del contrato que no se deducen de la firma:**

1. **`personal_min` filtra por el piso del rango.** `per_ocu` es texto
   (`"11 a 30 personas"`), no un número. Se incluyen los rangos cuyo **piso**
   alcanza el mínimo: `personal_min=11` deja fuera a `"6 a 10 personas"` aunque
   un negocio de ese rango pudiera tener 10. Es la lectura conservadora — nadie
   puede afirmar que ese negocio tiene 11.
2. **`bbox` pone la latitud primero** (`lat_min,lon_min,lat_max,lon_max`), como
   el INEGI y como Leaflet. **GeoJSON pone la longitud primero**; la conversión
   vive en un solo sitio (`prospeccion.anillo_de_geojson`).
3. **`total` y `mostrados` son números distintos.** `total` son los que cumplen
   los filtros; `mostrados` los que caben en `limite` (default 500, techo 3000).
   Sirve para que la interfaz diga "3,000 de 8,412" en vez de recortar en
   silencio, que es lo que hacía el notebook con su tope de 2,000 marcadores.

**Errores.** Un parámetro inválido —bbox de tres números, bbox invertido, texto
donde iba un número— devuelve `{success: false, message: "..."}` con HTTP 200,
igual que `/api/plano_2d`. Nunca un 500: un mapa en blanco sin motivo se lee
como "aquí no hay negocios", que es una respuesta falsa. Si el artefacto no está
desplegado, el `message` dice cómo regenerarlo.

#### El puente con el negocio

| Método y ruta | Entrada | Salida |
|---|---|---|
| `POST /api/geo/prospecto` | `{establecimiento_id, estado, vendedor, nota}` | `{success, prospecto}` |
| `POST /api/geo/seleccion` | `{poligono, personal_min, solo_con_contacto, formato}` | JSON, CSV o XLSX |
| `POST /api/geo/solicitar_cotizacion` | `{establecimiento_id, destinatario, asunto, mensaje}` | `{success, motivo, vista_previa}` |

**Dos bases, a propósito.** El catálogo del INEGI es de terceros, público e
inmutable entre publicaciones, y vive en el SQLite del bundle. Lo que la empresa
produce encima —prospecto contactado, asignado a un vendedor, notas— es nuestro y
mutable, y va a `geo_prospectos` en Supabase por el `DataEngine` que ya existe
(`backend/core/engine.py`). No se mezclan: el dato del INEGI no entra a los
respaldos de la empresa y no se suben 21,000 filas ajenas solo para leerlas.

El DDL de `geo_prospectos` está en [`DDL_PENDIENTE.sql`](DDL_PENDIENTE.sql) §8 y
lo aplica el dueño. Mientras no exista la tabla, `POST /api/geo/prospecto`
degrada con `success: false` y el motivo.

**El estado del prospecto** sale de `{ NUEVO, CONTACTADO, COTIZANDO, DESCARTADO }`
y la clave es `denue_id`: un establecimiento tiene **un solo** estado comercial.
Alta y cambio son la misma llamada (upsert). Tres reglas que no se ven en la firma:

1. **Un estado desconocido se rechaza con 422**, no se corrige a `NUEVO`.
   Degradarlo diría que a ese negocio nunca lo contactó nadie, borrando trabajo
   que alguien ya hizo.
2. **`created_at` solo se escribe en el alta.** Es lo único con lo que se puede
   medir cuánto tarda un negocio en pasar de `NUEVO` a `COTIZANDO`.
3. **`web_cache` no se puede mandar desde el navegador** (`extra="forbid"`). La
   escribe el job de enriquecimiento fuera de línea, y el upsert fusiona, así que
   omitirla la conserva.

**La exportación** (`formato=csv` o `xlsx`) devuelve el archivo con
`Content-Disposition`, con las mismas 10 columnas del mapa y encabezados
legibles. Se arma con la biblioteca estándar (`api/services/exportacion.py`):
meter `openpyxl` al runtime es justo lo que evita todo este diseño. El CSV lleva
BOM porque su destino es Excel en Windows, que sin él lee "Cuauhtémoc" como
"CuauhtÃ©moc".

**La solicitud de cotización está bloqueada a propósito.** El DENUE es dato
público; usar sus correos para contacto comercial cae bajo la **LFPDPPP**, que
exige identificar a la empresa y ofrecer una vía de baja. Ese texto es decisión
del dueño (plan de prospección §11, punto 5) y todavía no existe, así que la ruta
devuelve `motivo: "aviso_legal_pendiente"` y el correo ya redactado en
`vista_previa` para mandarlo a mano. Hay dos cerrojos —la constante
`AVISO_LFPDPPP` vacía y la variable `GEO_CORREO_HABILITADO`— porque encender solo
la variable no debe alcanzar. El envío usa `api/services/correo.py`; no hay un
segundo camino.


---

## 4. Integraciones externas

### 4.1 Make.com → Outlook (`NotifierService.sendToOutlook(payloadData)`)

Webhook `POST` a `WEBHOOK_OUTLOOK_URL`. Payload:

```jsonc
{
  "folio": "AV-1234",
  "titulo": "Asignación de Tarea",
  "descripcion": "…",
  "fechaInicio": "2026-07-14T10:00:00",   // ISO, ver nota
  "fechaFin":    "2026-07-14T11:00:00",
  "correoDestino": "usuario@holtmont.com",
  "asignadoPor": "SISTEMA"
}
```

- **Integridad de fechas:** las fechas se formatean con `toISOString()`. El contrato exige mantener
  el estándar ISO 8601 con "Z" UTC en los webhooks de negocio (no truncar milisegundos donde aplique).
- **Contexto de origen:** el payload debe indicar si la tarea proviene de `ANTONIA_VENTAS` (tabla de
  ventas) o del tracker general, para que Make formatee el correo correctamente.
- Códigos `200`/`202` = éxito.

### 4.2 Google Gemini (`callGeminiAPI(prompt)`)
Llamada `UrlFetchApp` a la API de Gemini con `GEMINI_API_KEY`. Se usa para resúmenes ejecutivos de
KPIs incrustados en los correos de los agentes (`_sendAgentEmail`, `_sendTrackerProductivityEmail`).

---

## 5. Invariantes de datos (validaciones críticas)

Estas reglas forman parte del contrato y **deben** respetarse en cualquier reimplementación:

1. **Case-insensitivity:** las claves del FE pueden venir en minúsculas (`folio`); todas las
   comparaciones de `FOLIO`/`ID`/encabezados usan `.toUpperCase().trim()`.
2. **Encabezados dinámicos:** las hojas de personal tienen UI sobre los datos; los encabezados **no**
   están garantizados en la fila 1. Se detectan con `findHeaderRow(values)`.
3. **Evaluación de 100%:** en `AVANCE`, `100%` equivale a `'100'`, `'100%'` o al número `1` (celda con
   formato de porcentaje). Nunca interpretar `'1'`/`'1.0'` string como 100%.
4. **Fallbacks de validación:** `ESTATUS` vacío/ inválido ⇒ `'PENDIENTE'`; `CUMPLIMIENTO` vacío ⇒ `'NO'`.
5. **Anti-duplicación:** FE bloquea con `isSubmitting`; BE bloquea con `CacheService` por `_tempId`.
6. **Auditoría:** toda mutación relevante debe llamar `registrarLog(user, action, details)`.
