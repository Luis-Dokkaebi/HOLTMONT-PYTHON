# Plan: backend Python que reemplaza `CODIGO.js`

Documento de arranque. Contiene (1) la auditoría de lo que realmente hay en el
repo frente a lo que se describió, (2) el plan de implementación por fases y
(3) las decisiones que requieren input del dueño del sistema.

**Estado: propuesta. No se ha escrito código de implementación.**

Baseline verificado en este análisis:

```
python -m pytest tests/test_tracker_rules.py tests/test_api_contract.py   ->  99 passed
node tests/gas/run_tests.js                                              ->  70 PASAN / 0 FALLAN
```

---

## 1. Auditoría: lo que contradice el resumen de partida

### 1.1 No existe la carpeta `migration/`

Ni la carpeta ni ninguno de los siete archivos citados (`schema.sql`,
`schema_patch_v2.sql`, `schema_auth.sql`, `lib.py`, `migrate.py`,
`migrate_rest.py`, `migrate_auth.py`, `README.md`).

```
$ ls migration/
ls: cannot access 'migration/': No such file or directory

$ git log --all --oneline -- migration/
(vacío)
```

Nunca estuvo en el historial de esta rama ni de `main`. Los demás documentos de
apoyo sí existen (`docs/ARQUITECTURA_Y_BASE_DE_DATOS.md`, `docs/API_CONTRACT.md`,
`docs/openapi.yaml`, `docs/PIPELINE_Y_DESPLIEGUE.md`, `AGENTS.md`); el único
ausente es `migration/README.md`.

**Consecuencia:** el DDL del esquema, el pipeline de carga y el script de
migración de Auth no son verificables desde aquí. No puedo confirmar que las
18 tablas y los conteos de filas descritos existan en Supabase, ni el mapeo
hoja→tabla. Todo el plan asume que los datos sí están cargados; hay que
confirmarlo antes de la Fase 1.

### 1.2 `CODIGO.js` no tiene módulo `SupabaseSync`

```
$ grep -c "SupabaseSync" CODIGO.js
0
```

No hay escritura doble desde Apps Script hacia Supabase. **No existe el puente**
que se describió como ya construido. Hoy Sheets no es "la fuente de verdad
mientras tanto": es la *única* fuente de verdad, y Supabase es una copia
estática que se desactualiza desde el momento de la carga.

Esto cambia la estrategia de transición de forma importante (ver §3, decisión A).

### 1.3 Cifras del backend GAS

| Dato | Descrito | Real |
|---|---|---|
| Líneas de `CODIGO.js` | ~6,600 | **4,537** |
| `USER_DB` | 41 usuarios, línea ~223 | **12 usuarios, línea 115** |
| `getSystemConfig` | `(role, username)`, línea ~571 | **`(role)`, línea 409** |
| Funciones `api*` | 34 | **37 definidas** |
| Símbolos que invoca `index.html` | 34 | **39** |

Los "41 usuarios" probablemente confunden `USER_DB` (12 credenciales de login)
con `INITIAL_DIRECTORY` (54 entradas persona×departamento, `CODIGO.js:33-89`),
que es lo que alimenta la tabla `people`. Son cosas distintas: el directorio no
tiene contraseñas ni rol.

**Roles reales** (12, no 6): `ADMIN`, `ADMIN_CONTROL`, `PPC_ADMIN`, `TONITA`,
`WORKORDER_USER`, `ANGEL_USER`, `TERESA_USER`, `EDUARDO_USER`,
`MANZANARES_USER`, `RAMIRO_USER`, `SEBASTIAN_USER`, `EDGAR_USER`.
**`STAFF_USER` no existe.** Los siete roles `*_USER` son de una sola persona
cada uno y le dan al usuario exactamente dos módulos espejo (`MY_TRACKER` y
`MY_SALES` con sufijo `(VENTAS)`). Eso no es un rol genérico de staff: es RBAC
cableado por individuo, y hay que reproducirlo tal cual o siete personas pierden
su vista.

### 1.4 Faltan cinco símbolos en la lista de 34

`index.html` invoca 39 símbolos de backend. La lista de 34 omite:
`getSystemConfig`, `runQuoteMetricsAgent`, `runTrackerProductivityAgent`,
`runPaperclipAgents` y `uploadFileToDrive`. Los cinco son necesarios: sin
`getSystemConfig` la SPA no puede pintar el menú tras el login.

Además `CODIGO.js` define tres funciones `api*` que la lista no menciona:
`apiFetchTeamKPIData` (línea 597), `apiCreateStandardStructure` (2223) y
`apiFetchDistinctClients` (3006).

### 1.5 La regla de `AVANCE` descrita rompería el auto-archivado

La regla propuesta —"si el valor está entre 0 y 1, se multiplica por 100"—
contradice el código vivo y `AGENTS.md` §4:

> **Evaluación de Progreso (AVANCE):** 100% debe evaluarse como `'100'`,
> `'100%'` o, muy importante, el valor numérico `1` que retorna GAS para celdas
> con formato de porcentaje. **Nunca evalúes el string `'1'` o `'1.0'` como 100%.**

`api/services/tracker_rules.py:245` lo implementa así, con un caso explícito:

```python
if clean in ("1", "1.0", "1.00"):
    return False
```

La distinción es entre el **número nativo** `1` (celda con formato porcentual →
100%) y el **string** `"1"` (el usuario tecleó 1 → 1%). Aplicar la regla
descrita archivaría como terminadas todas las tareas al 1%. La normalización a
escala 0–100 para *almacenar* sí es correcta; lo que no se puede colapsar es la
distinción de tipo en la *entrada*.

### 1.6 `dedupe_key` no existe en el código vivo

```
$ grep -rn "dedupe" CODIGO.js api/
(vacío)
```

Es un concepto exclusivo del pipeline de migración ausente. El código en
producción resuelve identidad de fila por `FOLIO`/`ID`, con fallback a
`CONCEPTO` + `FECHA` (`AGENTS.md` §2: *"Si un FOLIO no se encuentra, el sistema
siempre debe intentar hacer coincidir las filas por la combinación de CONCEPTO y
FECHA. Generar un nuevo FOLIO es el último recurso."*). Si `tasks.dedupe_key`
existe en Supabase, hoy nadie lo lee ni lo mantiene: el backend nuevo tendría
que empezar a poblarlo, no solo "no cambiar la lógica".

### 1.7 `INVOLUCRADOS` no es N:M en el código vivo

Es una columna de texto y, además, un **alias de `RESPONSABLE`**:

```javascript
// CODIGO.js:926
'RESPONSABLE': ['RESPONSABLE', 'RESPONSABLES', 'INVOLUCRADOS', 'VENDEDOR', 'ENCARGADO', 'ASIGNADO'],
```

La "papa caliente" parte ese string por comas para repartir
(`tracker_rules.py:460-462`). La tabla `task_involucrados` (7,246 filas) no la
lee ni la escribe nadie. Pasar a N:M es un cambio de modelo real, con impacto en
el frontend, no una traducción directa.

### 1.8 El backend Python no está por construir: ya existe (y tiene un fallo grave)

| Archivo | Líneas | Qué es |
|---|---|---|
| `api/main.py` | 576 | FastAPI, 27 endpoints |
| `api/services/tracker_rules.py` | 1,032 | Port de las reglas de negocio de `CODIGO.js` |
| `api/services/tracker_store.py` | 388 | Orquestación y persistencia |
| `api/services/sheets.py` | 360 | Adaptador relacional → forma de hoja |
| `api/services/work_order.py` | 456 | Work orders y secuencias |
| `api/services/supabase_manager.py` | 137 | Cliente Supabase |
| `api_service.js` | 306 | **Capa de compatibilidad `google.script.run` → REST** |

`index.html:16` ya carga `api_service.js`, que sustituye `window.google.script.run`
por un adaptador que habla REST. La capa de compatibilidad que se planteaba como
decisión futura **ya está construida y cableada**.

#### El fallo que bloquea todo lo demás

`GSheetsManager.write_values()` (`api/services/sheets.py:256-284`) **no tiene
ruta de escritura a Supabase**, aunque su docstring afirme lo contrario:

```python
"""
  1. Google Sheets real (gspread) -> clear + update.
  2. Modo mock -> reemplazo en memoria.
  3. Supabase relacional -> aún no soporta reemplazo de matriz; se
     insertan solo las filas nuevas y se avisa por consola.
"""
```

El punto 3 no está implementado; el cuerpo de la función solo contempla mock y
gspread. Sin `credentials.json` → `is_mock = True` → las escrituras van a un
`dict` en memoria del proceso y **se pierden al reiniciar**. En `vercel.json` el
despliegue es serverless: cada invocación es un proceso nuevo.

**El backend Python lee de Supabase pero no escribe en Supabase. Hoy, todo
guardado a través de él es una ilusión.** Esta es la primera cosa que hay que
arreglar y condiciona el orden de las fases.

#### El adaptador de lectura además es con pérdida

`TASK_HEADER_MAP` (`sheets.py:99-116`) proyecta **16 de las 29 columnas** de
`tasks`. Se pierden `id`, `assignee_id`, `dedupe_key`, `folio_sintetico`,
`comentarios_semana`, `comentarios_semana_previa`, `carpeta`, `correo`, `hora_alta`,
`hora_estimada_fin`, `source_sheet`, `created_at`. `QUOTE_HEADER_MAP` proyecta 13
de 37 columnas de `quotes`. Y `_rows_to_values` (`sheets.py:141`) convierte todo
a `str`, borrando la distinción numérico/string de la que depende la regla de
`AVANCE` (§1.5).

Un ciclo leer → modificar → escribir a través de este adaptador destruiría
datos. **Corolario: no se debe activar la escritura a Supabase sobre el
adaptador actual.** Hay que sustituirlo por repositorios relacionales primero.

### 1.9 Diez operaciones de escritura mienten al usuario

`api_service.js` tiene 16 métodos stub que devuelven `{success: true}` sin
llamar a nada. Diez de ellos son escrituras:

`uploadFileToDrive`, `apiAddEmployee`, `apiDeleteEmployee`, `apiSaveSite`,
`apiSaveSubProject`, `apiSaveProjectTask`, `apiSavePersonalEvent`,
`apiSaveHabitLog`, `apiSyncDrafts`, `apiClearDrafts`.

El frontend recibe éxito, marca `_isNew = false`, limpia el borrador local y el
usuario ve su fila guardada. No se guardó nada. Los seis restantes son lecturas
que devuelven `data: []` (una tabla vacía es más honesta, pero igual de
silenciosa).

### 1.10 Concurrencia: los tres mecanismos son inseguros hoy

- **Gatekeeper** (`tracker_rules.py:596`): `dict` en memoria del proceso. Con
  más de un worker no bloquea nada; en serverless no sobrevive a la invocación.
- **Secuencias de folio** (`work_order.py:8-24`): lectura + escritura de
  `sequences.json` **sin bloqueo** y en un filesystem efímero. Dos usuarios
  concurrentes obtienen el mismo folio. Es exactamente el problema que se quería
  evitar.
- **Batch update**: no hay transacción ni `SELECT ... FOR UPDATE`.

### 1.11 Auditoría y auth: no existen en Python

- `system_log`: **cero** escrituras desde el backend Python. El equivalente de
  `registrarLog()` no está portado.
- `/api/login` (`main.py:281`) compara contraseñas **en texto plano** contra una
  tabla `USERS` que no está en el esquema descrito, y si falla cae a un
  `MOCK_USER_DB` **hardcodeado en el fuente** (`main.py:309-313`) con
  `admin2025` / `tonita2025` / `workorder2026`. Es precisamente lo que el
  requisito prohíbe.
- No hay JWT, ni dependencia de FastAPI que resuelva usuario+rol, ni
  autorización por rol. `GET /api/config?role=X` acepta el rol **como parámetro
  de query del cliente**: cualquiera pide `role=ADMIN` y obtiene la config de
  administrador.
- CORS es `allow_origins=["*"]` con `allow_credentials=True` (`main.py:50-56`).
- RLS sin configurar, como se indicó.

---

## 2. Plan de implementación por fases

Principio: cada fase deja el sistema operando. Apps Script + Sheets siguen
sirviendo a producción hasta la Fase 7; el backend nuevo se valida en paralelo.

### Fase 0 — Reconstruir la base verificable

Sin esto no se puede avanzar con confianza, porque el esquema no está en el repo.

- Recuperar o regenerar `migration/schema.sql` y `schema_patch_v2.sql` desde la
  base real (`pg_dump --schema-only`) y versionarlos.
- Verificar los conteos de filas descritos contra la base real.
- Congelar dependencias: hoy `requirements.txt` no tiene versiones y la suite no
  corre sin instalar a mano `fastapi`, `gspread`, `supabase`, `mcp`, `pytest`.
  Pinnear versiones y añadir un `requirements-dev.txt`.
- Completar `.env.example` (hoy solo tiene `SUPABASE_URL` y `SUPABASE_KEY`;
  faltan `MAKE_WEBHOOK_URL`, `GEMINI_API_KEY`, `DATABASE_URL`, secretos de JWT).
- **Documentar en el repo que `SupabaseSync` no existe**, para que nadie más
  planifique sobre esa premisa.

*Entregable:* esquema versionado, suite reproducible con un comando.
*Riesgo para producción:* ninguno.

### Fase 1 — Capa de datos relacional real (desbloquea todo)

Es la fase crítica: hoy no hay escritura.

- Paquete `backend/` nuevo, junto a `api/` (no encima). Estructura:
  `backend/{routers,services,repositories,schemas,models,core}`.
- SQLAlchemy 2.x + pool de conexiones contra Postgres directo, con
  `migrate_rest`-style por API REST como respaldo si no hay TCP al 5432.
- Un repositorio por entidad (`tasks`, `quotes`, `people`, `projects`, …) que
  trabaje con **todas** las columnas y **preserve tipos**. Modelos Pydantic como
  contrato, no arreglos 2D de strings.
- Retirar `sheets.py` como capa de datos. `tracker_rules.py` se conserva: es el
  activo más valioso del repo y ya tiene paridad probada con GAS; se refactoriza
  para operar sobre objetos de dominio en vez de la matriz de la hoja, con los
  tests existentes como red.
- Transacciones reales en las operaciones por lotes.
- El auto-archivado pasa a ser cambio de `status`, no reordenamiento de filas.

*Entregable:* lectura y escritura reales contra Supabase, con tipos intactos.
*Validación:* los 99 tests siguen pasando + tests nuevos de round-trip
(leer → escribir → releer sin pérdida).

### Fase 2 — Concurrencia e idempotencia en la base

- Tabla `idempotency_keys (key, scope, response_json, expires_at)` con índice
  único → Gatekeeper durable y multi-worker.
- Secuencias Postgres para `ANTONIA_SEQ_V2` (`AV-`) y `WORKORDER_SEQ`; se elimina
  `sequences.json`. Formato de work order `<INI-CLIENTE>-<Abrev-Depto>-####`
  intacto.
- `SELECT ... FOR UPDATE` / advisory locks en los batch.
- Se conserva el fallback `CONCEPTO`+`FECHA` de `AGENTS.md` §2.

*Validación:* test de concurrencia real que dispare N escrituras paralelas con
el mismo `_tempId` y verifique una sola fila.

### Fase 3 — Auditoría

- `log_evento(usuario, accion, detalles)` escribiendo en `system_log` (16,196
  filas existentes; se respeta el formato).
- Aplicado en toda mutación, como dependencia de FastAPI para que no se olvide.

### Fase 4 — Autenticación y RBAC

- Escribir `schema_auth.sql` y `migrate_auth.py` (**no existen**): 12 cuentas de
  `USER_DB`, no 41.
- Supabase Auth + JWT. Dependencia `get_current_user()` que resuelve
  usuario+rol **del token**, nunca de un parámetro de query.
- Portar `getSystemConfig` con los 12 roles reales, incluidos los siete
  individuales.
- Eliminar `MOCK_USER_DB` y las contraseñas en texto plano.
- CORS restringido a los orígenes reales.
- Definir políticas RLS **antes** de exponer la key `anon`.

*Nota de corte:* mientras GAS siga en producción, `USER_DB` y Supabase Auth
coexisten. Las contraseñas se migran tal cual (hasheadas por Supabase) para que
nadie tenga que cambiarla el día del corte.

### Fase 5 — Cerrar los stubs

Los 16 métodos de `api_service.js`, empezando por las diez escrituras que hoy
mienten. Prioridad por daño: proyectos/sitios y directorio primero (pérdida
silenciosa de datos estructurales), luego agenda/hábitos/borradores.

Un stub debe fallar ruidosamente, no devolver `success: true`. Cambio de una
línea por método, aplicable **ya** en Fase 0 si se quiere frenar el sangrado.

### Fase 6 — Archivos (decisión pendiente, ver §3.B)

### Fase 7 — Corte

Por módulo, no big bang. Orden sugerido de menor a mayor riesgo: KPI/métricas →
banco de información → agenda → proyectos → tracker → ventas. Cada módulo con
ventana de rollback (reapuntar `api_service.js` a GAS).

---

## 3. Decisiones

**Estado: A, B, C y D acordadas. E sigue abierta y bloquea la Fase 1.**

| # | Decisión | Acordado |
|---|---|---|
| A | Puente durante la transición | **Construir `SupabaseSync` primero** en `CODIGO.js` |
| B | Archivos de Drive | **Supabase Storage para lo nuevo, Drive de solo lectura para lo histórico** |
| C | Frontend | **Mantener `api_service.js`** como capa de compatibilidad |
| D | `INVOLUCRADOS` | **Conservar el string**; `task_involucrados` queda derivada |
| E | Acceso a la base | *pendiente* |

Consecuencias sobre el plan:

- **A** antepone una fase nueva (**Fase 0.5**) antes de la capa de datos: escribir
  el módulo `SupabaseSync` en `CODIGO.js` con escritura doble Sheets → Supabase.
  Es JavaScript sobre GAS, se prueba con los mocks de `tests/gas/` y no requiere
  tocar el backend Python. A partir de su despliegue, Supabase deja de
  desactualizarse y el resto de la migración pierde la presión de tiempo.
- **B** convierte la Fase 6 en dos piezas: un servicio de subida contra Supabase
  Storage para lo nuevo, y la conservación intacta de las URLs de Drive
  existentes. No hay reescritura masiva de URLs. Conviene arreglar
  `APP_CONFIG.folderIdUploads`, hoy vacío (`CODIGO.js:14`), para que lo que aún
  vaya a Drive deje de caer en la raíz.
- **C** confirma que no se toca `index.html`. El mapeo función-vieja →
  endpoint-nuevo se documenta en `api_service.js`.
- **D** mantiene el contrato de `INVOLUCRADOS` como string con comas en ambos
  sentidos. El backend puede poblar `task_involucrados` como proyección para
  consultas, pero la fuente de verdad sigue siendo la columna de texto. Evita
  tocar el frontend.

### E. Acceso a la base (pendiente)

Para las Fases 0 y 1 hace falta o bien credenciales de Supabase en el entorno, o
bien un `pg_dump --schema-only`. Sin eso el trabajo va a ciegas sobre un esquema
que no se puede verificar, y dado que `migration/` no existe (§1.1), no hay otra
fuente para el DDL.

---

## 3-bis. Decisiones tal como se plantearon (referencia)

### A. Puente durante la transición — la más urgente

No existe `SupabaseSync`. Sin doble escritura, Supabase se desactualiza cada día
que pasa. Opciones:

1. **Construir el `SupabaseSync` en `CODIGO.js`** (2–3 días) y luego migrar sin
   prisa. Es la opción segura: mantiene ambas bases vivas.
2. **Corte por módulo sin puente**: cada módulo migrado deja de escribir en
   Sheets el día de su corte. Más rápido, pero durante la transición la verdad
   está repartida entre dos bases.
3. **Re-migrar justo antes del corte** y aceptar que Supabase esté obsoleta
   hasta entonces. Barato ahora, pero exige una ventana de congelación.

### B. Archivos de Drive

Cotizaciones, layouts, timelines y F2 viven en Drive; la base solo tiene URLs.
`uploadFileToDrive` usa `DriveApp` con la identidad del usuario de GAS y
`ANYONE_WITH_LINK`, lo cual FastAPI no puede replicar sin credenciales propias.

1. **Seguir en Drive** con una service account dedicada. Los enlaces existentes
   siguen sirviendo; hay que dar acceso a la carpeta a esa cuenta.
2. **Supabase Storage** para lo nuevo, Drive de solo lectura para lo histórico.
   Sin dependencia de Google a futuro; conviven dos sistemas un tiempo.
3. **Migrar todo a Supabase Storage** y reescribir las URLs de la base. Lo más
   limpio, lo más caro, y hay que verificar que ningún enlace externo apunte a
   los archivos viejos.

Nota: `APP_CONFIG.folderIdUploads` está **vacío** (`CODIGO.js:14`), así que hoy
todo cae en la raíz del Drive del propietario. Conviene arreglarlo en cualquier
escenario.

### C. Frontend

`api_service.js` ya existe y ya está cableado en `index.html:16`. Recomendación:
**mantenerlo** como capa de compatibilidad y completar los stubs, en vez de
reescribir la SPA de 676 KB. El mapeo función-vieja → endpoint-nuevo se
documenta ahí mismo, que es donde vive. Migrar a REST idiomático puede hacerse
después, componente por componente, sin bloquear nada.

Confirmar si se acepta, o si se prefiere REST idiomático desde el principio.

### D. `INVOLUCRADOS` N:M

La tabla `task_involucrados` existe con 7,246 filas pero nadie la usa. ¿El
backend nuevo pasa a N:M real (implica tocar el frontend, que hoy manda y
espera un string con comas), o se conserva el string y `task_involucrados` queda
como estructura derivada para consultas?

---

## 4. Fase 0 — ejecutada

Reducción de daño y suite reproducible. No depende de ninguna decisión abierta.

| Cambio | Detalle |
|---|---|
| Escrituras que mentían | Los 10 stubs de `api_service.js` que devolvían `{success: true}` sin persistir ahora responden la envoltura de error (`_noPortado`). `uploadFileToDrive` ya no inventa una `fileUrl`. |
| Lecturas no portadas | Siguen devolviendo vacío para no bloquear el render, pero marcadas con `_notImplemented` y aviso en consola (`_lecturaVacia`). |
| Credenciales en el fuente | Eliminadas de **dos** sitios: el `MOCK_USER_DB` de `api/main.py` y la hoja `USERS` del `MockSpreadsheet` en `api/services/sheets.py`. |
| Login de desarrollo | Sustituido por `DEV_LOGIN_USERS` (variable de entorno), con `secrets.compare_digest`. |
| CORS | `allow_credentials` solo si hay `CORS_ORIGINS` explícitos; se acabó `*` con credenciales. |
| Dependencias | `requirements.txt` con mínimos verificados y núcleo separado de opcionales; `requirements-dev.txt` nuevo. |
| `.env.example` | Completo: `DATABASE_URL`, `MAKE_WEBHOOK_URL`, `GEMINI_API_KEY`, `CORS_ORIGINS`, `PORT`, `DEV_LOGIN_USERS`. |

Sobre las credenciales: quitar solo el `MOCK_USER_DB` **no habría bastado**. Sin
base de datos, la búsqueda de la hoja `USERS` caía al `MockSpreadsheet`, donde
estaban las mismas contraseñas de producción. Se verificó que `admin2025` y
`tonita2025` ya no autentican.

Tests nuevos que impiden la regresión (`tests/test_api_contract.py`):
`test_escrituras_no_portadas_no_fingen_exito` (10 casos),
`test_upload_a_drive_no_inventa_una_url`,
`test_no_hay_credenciales_hardcodeadas` (2 módulos),
`test_cors_no_permite_credenciales_con_origen_comodin`.

```
python -m pytest tests/test_tracker_rules.py tests/test_api_contract.py  ->  113 passed
node tests/gas/run_tests.js                                             ->  70 PASAN / 0 FALLAN
```

**Nota operativa:** estos cambios solo afectan al despliegue FastAPI. En el
despliegue de Apps Script, `<script src="api_service.js">` no resuelve y
`window.google.script.run` real permanece intacto, así que la operación diaria
sobre GAS no se ve tocada.

## 5. Diagnóstico: por qué no se ven todas las columnas de ANTONIA_VENTAS

Síntoma reportado, reproducido contra la base real. Solo afecta al despliegue
FastAPI; en Apps Script la hoja se lee completa.

```
GET /api/data?sheet=ANTONIA_VENTAS
  -> 583 filas, 14 encabezados
     FOLIO, VENDEDOR, CLIENTE, AREA, CLASIFICACION, CONCEPTO, F_VISITA,
     F_INICIO, F_ENTREGA, DIAS, AVANCE, ESTATUS, COMENTARIOS, MONTO
```

La tabla `quotes` tiene **37 columnas**. Se devuelven **14**. Son tres causas
independientes, y las tres viven en `api/services/sheets.py`.

### Causa 1 — `QUOTE_HEADER_MAP` solo proyecta 14 de 37 columnas

`sheets.py:118-133` enumera a mano las columnas que se exponen. Las otras 23 no
salen nunca, aunque tengan datos:

| Columna omitida | Filas con datos |
|---|---|
| `cotizacion` | 227 / 661 |
| `requisitor` | 222 / 661 |
| `info_cliente` | 219 / 661 |
| `timeline` | 106 / 661 |
| `f2` | 98 / 661 |
| `layout` | 69 / 661 |
| `map_cot` | 34 / 661 |
| `prioridad_cot` | 33 / 661 |
| `comentario` | 28 / 661 |
| `estatus_2` | 24 / 661 |
| `proceso_log` | 21 / 661 |
| `vendedor_id` | 564 / 661 |

Seis de ellas son parte del contrato que el frontend espera para una hoja de
ventas (`DEFAULT_SALES_HEADERS`, `CODIGO.js:92`): **`FECHA`, `ARCHIVO`, `F2`,
`COTIZACION`, `TIMELINE`, `LAYOUT`**. `COTIZACION`, `TIMELINE`, `LAYOUT` y `F2`
son precisamente las columnas de archivos de Drive, así que la vista de ventas
se queda sin sus enlaces.

### Causa 2 — el filtro por hoja distingue mayúsculas

`sb_manager.select("quotes", {"source_sheet": sheet_name})` hace un `eq` exacto.
Los nombres guardados en `source_sheet` no están normalizados:

```
ANTONIA_VENTAS                 583
Sebastian Padilla (VENTAS)      19     <- capitalización mixta
Eduardo Manzanares (VENTAS)     19
Ramiro Rodriguez (VENTAS)       17
TERESA GARZA (VENTAS)           13     <- mayúsculas
Juan Jose Sanchez (VENTAS)       9
Edgar Lopez (VENTAS)             1
```

`ANTONIA_VENTAS` coincide por casualidad. Los trackers de ventas individuales
no: el frontend pide `SEBASTIAN PADILLA (VENTAS)` en mayúsculas y la base tiene
`Sebastian Padilla (VENTAS)`.

```
GET /api/data?sheet=SEBASTIAN PADILLA (VENTAS)   -> 0 filas
GET /api/data?sheet=Sebastian Padilla (VENTAS)   -> 19 filas
```

Es decir: **cinco de las siete hojas de ventas devuelven cero filas**, no solo
columnas incompletas. Contradice la regla de encabezados tolerantes
(`AGENTS.md` §4) y la de comparación insensible a mayúsculas.

Peor: cuando el `select` no encuentra nada, `get_sheet_values` cae a la ruta
legacy y consulta una tabla llamada literalmente `SEBASTIAN PADILLA (VENTAS)`,
que no existe. El error se imprime en consola y la respuesta sale vacía con
`success: true`.

### Causa 3 — todo se convierte a texto

`_rows_to_values` (`sheets.py:141`) hace `str(row.get(col, "") or "")` sobre cada
celda. Efectos:

- `monto = 0` y `avance = 0` se vuelven `""`, porque `0 or ""` es `""` en Python.
  Un avance de 0 % se pierde y se muestra vacío.
- Se borra la distinción numérico/texto de la que depende la regla de `AVANCE`
  (§1.5): tras pasar por aquí, el número `1` y el string `"1"` son
  indistinguibles.
- Las fechas quedan como texto sin formato definido.

### Estado tras los PR #98 y #99 (arreglo parcial, ya corregido aquí)

Mientras se hacía esta auditoría entraron a `main` dos PR que atacaban el mismo
síntoma. Ampliaron `QUOTE_HEADER_MAP` de 14 a 20 columnas, pero dejaron el
problema a medias e introdujeron dos defectos nuevos:

| Qué pasaba | Estado |
|---|---|
| `PRIO. COT.` mapeaba a `prio_cot`, **columna que no existe** (la real es `prioridad_cot`, con datos en 33 filas) | corregido |
| `MONTO` se **eliminó** del mapa, aunque `DEFAULT_SALES_HEADERS` lo exige | restaurado |
| Causa 2 (mayúsculas) sin tocar: 5 de 7 hojas de ventas seguían en cero filas | corregido |
| Causa 3 (`str(v or "")`): 198 cotizaciones al 0 % seguían mostrándose vacías | corregido |
| `map_cot` y `proceso_log`, que alimentan el timeline de Papa Caliente, sin exponer | expuestos |
| El cambio en `supabase_manager.py` es **código muerto** para ventas: `sheets.py` retorna antes por `_rows_to_values` y nunca llega ahí | documentado |

Correcciones aplicadas en esta rama, verificadas contra la base real:

```
ANTONIA_VENTAS               583 filas, 23 columnas
SEBASTIAN PADILLA (VENTAS)    19 filas   (antes 0)
EDUARDO MANZANARES (VENTAS)   19 filas   (antes 0)
RAMIRO RODRIGUEZ (VENTAS)     17 filas   (antes 0)
TERESA GARZA (VENTAS)         13 filas
JUAN JOSE SANCHEZ (VENTAS)     9 filas   (antes 0)
LILIANA AYLIN MARTINEZ IBARRA 187 filas  (antes 0, hoja con espacio inicial)
```

`EDGAR LOPEZ (VENTAS)` devuelve 0 filas y **es correcto**: su única fila en
`quotes` es un encabezado mal migrado (`folio = "FOLIO"`, `cliente = "CLIENTE"`),
que el endpoint filtra bien. Es un residuo del pipeline de migración, no un
fallo de lectura; conviene depurarlo en la base.

La resolución del nombre de hoja se hace con un índice de `source_sheet`
cacheado en proceso, comparando sin distinguir mayúsculas ni espacios. Si no
hay coincidencia se consulta el nombre pedido tal cual, para no inventar hojas.

Cubierto por `tests/test_ventas_columns.py` (23 casos, sin necesidad de base).

### Corrección de raíz: el mapa deja de mantenerse a mano

Ampliar la lista curada resolvía el síntoma del día y garantizaba repetirlo: es
exactamente lo que ya había pasado dos veces (`QUOTE_HEADER_MAP` se quedó corto,
y `prio_cot` se escribió mal sin que nadie lo notara).

`build_header_map()` construye ahora el mapa en dos tramos:

1. Las columnas **curadas** primero, con el nombre y el orden que el frontend
   espera (`FOLIO`, `CLIENTE`, `F. VISITA`, …).
2. Detrás, **todas** las columnas que traigan los datos y no estén ya cubiertas,
   con su nombre en mayúsculas. Las técnicas (`source_sheet`, `created_at`,
   `vendedor_id`, `id`, `dedupe_key`…) van al final para no estorbar.

Las columnas se descubren recorriendo **todas** las filas, no solo la primera:
una columna que llegue nula en el primer registro habría desaparecido para
todos los demás.

Cobertura resultante, verificada contra la base real:

| Tabla | Antes | Ahora |
|---|---|---|
| `quotes` | 23 de 37 | **37 de 37** |
| `tasks` | 16 de 28 | **28 de 28** |

```
ANTONIA_VENTAS               583 filas, 37 columnas
SEBASTIAN PADILLA (VENTAS)    19 filas, 37 columnas
EDUARDO MANZANARES (VENTAS)   19 filas, 37 columnas
RAMIRO RODRIGUEZ (VENTAS)     17 filas, 37 columnas
TERESA GARZA (VENTAS)         13 filas, 37 columnas
JUAN JOSE SANCHEZ (VENTAS)     9 filas, 37 columnas
tracker JAIME OLIVO           38 filas, 28 columnas
```

A partir de aquí, una columna nueva en Postgres aparece sola y un nombre mal
escrito en el mapa curado se nota enseguida, porque la columna real sale
igualmente con su nombre crudo.

### Lo que sigue pendiente para la Fase 1

Con esto la vista ya muestra todo, pero el adaptador continúa convirtiendo una
tabla relacional en una matriz de strings. Eso implica que la distinción entre
el número `1` y el string `"1"` —de la que depende la regla de `AVANCE`— se
pierde igual al serializar.

Corresponde a la **Fase 1**: repositorios que devuelvan las columnas con sus
tipos y modelos Pydantic en la frontera. Se hace junto con la escritura, porque
son el mismo cambio.

Nota para cuando llegue: ahora se exponen también `id`, `dedupe_key` y
`assignee_id`. Hoy es inocuo porque las escrituras no llegan a Supabase, pero al
activar la escritura hay que tratarlas como **solo lectura** y no aceptarlas
desde el cliente.

Mientras tanto, lo que el usuario ve en ventas está incompleto pero **no
corrupto**: es una lectura parcial, y las escrituras de esa vista no llegan a
persistir en Supabase de todos modos (§1.8).

## 6. Normalización de estatus — ejecutada

La columna venía de captura libre en la hoja y había acumulado **45 valores
distintos en `tasks`** y **26 en `quotes`** para lo que son ~11 estatus reales.

Cuatro clases de suciedad conviviendo:

| Clase | Ejemplos reales |
|---|---|
| Mayúsculas y género | `ASIGNADO` / `Asignado` / `asignado` / `ASIGNADA` / `asignada` |
| Erratas | `ASIGANDO`, `ASIGANDA`, `ASIGADO`, `ASIGANDOA`, `asigndo`, `PEDIENTE`, `BIERTO` |
| Marcadores de vacío | `-`, `-\n-`, `-\n-\n-` |
| Texto que no es estatus | `RAM`, `TG`, `MANZ`, `Nickey Torres`, `100.0`, `es referente al primer correo enviado` |

Solo `ASIGNADO` tenía **19 formas distintas** de escribirse.

### La regla

`normalize_status()` en `api/services/tracker_rules.py`, con lista de alias
**explícita**. Nada de coincidencia difusa: aquí un error cambia si una tarea
se archiva o no, y adivinar no es aceptable.

Un valor no reconocido devuelve `None` en vez de mapearse a `PENDIENTE`:
`RAM` o un comentario entero no son estatus, e inventarlo fabricaría
información que nadie capturó.

**Invariante que hizo segura la migración:** cada alias apunta a un canónico de
su misma familia, así que `is_terminal_status()` da el mismo resultado antes y
después. Verificado contra las 5.287 filas reales: **0 cambian de estado
terminal**, es decir, ninguna tarea se archivó ni se desarchivó.

### El resultado

```
tasks.status    45 valores -> 12   (11 canónicos + vacío)
quotes.estatus  26 valores -> 11   (10 canónicos + vacío)
sin normalizar: 0 en ambas          conteos intactos: 4.626 / 661
```

Los 24 textos que no eran estatus se **preservaron** en `comentarios` con el
prefijo `[ESTATUS ORIGINAL]` antes de vaciar la columna. Todas esas filas
tenían `comentarios` vacío, así que no se pisó nada.

### Un detalle del esquema que costó un intento

`tasks.status` tiene **`NOT NULL`** y `quotes.estatus` no. El primer intento
falló con `23502` al escribir nulo en `tasks`. `tasks` se vacía con cadena
vacía; `quotes` con nulo. El frontend lee ambos igual.

El fallo abortó la tabla **antes de escribir**, así que no hubo estado a medias.

### Que no se vuelva a ensuciar

De nada sirve limpiar si la siguiente captura reintroduce las variantes.
`SupabaseSync.normalizeStatus()` en `CODIGO.js` aplica la misma regla en el
camino de escritura, con **paridad verificada 57/57** contra la implementación
de Python.

Diferencia deliberada con el script de limpieza: en vivo, un valor **no
reconocido se conserva tal cual** en vez de descartarse. Si mañana el equipo
empieza a usar un estatus nuevo, tirarlo en silencio perdería el dato;
aparecerá en la siguiente revisión.

### Reejecutable

`scripts/normalizar_estatus.py` simula por defecto y solo escribe con
`--aplicar`. Deja un respaldo en `scripts/respaldos/` (ignorado por git: son
datos de producción) suficiente para revertir, y es idempotente.

## 7. Siguiente paso

Fase 0.5: construir `SupabaseSync` en `CODIGO.js` (decisión A). Bloqueado
parcialmente por la decisión E: hace falta el esquema real para saber a qué
columnas escribir.
