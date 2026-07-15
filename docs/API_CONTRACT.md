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
| `apiFetchCombinedCalendarData(sheetName)` | `sheetName` | calendario |
| `apiSavePersonalEvent(eventData)` | ↓ | `{success}` |
| `apiSaveHabitLog(habitData)` | ↓ | `{success}` |
| `apiFetchInfoBankCompanies(year, monthName)` | ↓ | empresas del banco |
| `apiFetchInfoBankData(year, monthName, company, folder)` | ↓ | datos del banco |

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
