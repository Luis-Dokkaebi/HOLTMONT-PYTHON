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

## 3. Decisiones que requieren tu input

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

### E. Acceso a la base

Para las Fases 0 y 1 hace falta o bien credenciales de Supabase en el entorno, o
bien un `pg_dump --schema-only` que puedas pegar. Sin eso trabajo a ciegas sobre
un esquema que no puedo verificar.

---

## 4. Acción inmediata sugerida

Independiente de las decisiones anteriores, dos cosas que se pueden hacer hoy
y reducen daño:

1. **Que los stubs fallen en vez de mentir** (§1.9). Diez operaciones de
   escritura reportan éxito sin guardar.
2. **Quitar `MOCK_USER_DB`** de `api/main.py:309-313`: son credenciales
   funcionales en un repo.
