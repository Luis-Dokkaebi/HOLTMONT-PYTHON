# Prompt: Fase 1 — capa de datos relacional para `tasks`

> Copia todo lo que sigue a partir de la línea divisoria y pégalo como primer
> mensaje en la sesión que va a construir la Fase 1.
>
> Este documento lo escribió la sesión que hizo la Fase 0 y 0.5. Todo lo que
> afirma está **verificado contra el repositorio y contra la base de datos
> real**, no repetido de un resumen previo. Si algo no se pudo comprobar, se
> dice explícitamente.

---

## Contexto

Trabajo en **Holtmont Workspace**, un sistema interno de gestión de obra y
cotizaciones. Hoy es una Web App sobre Google:

- **Frontend**: `index.html`, SPA en Vue 3 por CDN, sin build, ~690 KB en un
  solo archivo. **No lo toques.**
- **Backend legado**: `CODIGO.js`, Google Apps Script V8, ~4.850 líneas.
- **Base de datos legada**: las pestañas de un Google Spreadsheet.
- **Base de datos nueva**: Supabase (Postgres), ya poblada y verificada.

Estoy reemplazando `CODIGO.js` por un backend Python. Ya se completaron dos
fases; **te toca la Fase 1**, que es la pieza central.

Lee `docs/PLAN_BACKEND_PYTHON.md` antes de escribir código: contiene la
auditoría completa del sistema real y el porqué de cada decisión ya tomada.

## Qué está hecho (verificado, no asumas más)

### Fase 0 — reducción de daño

- Las 10 escrituras de `api_service.js` que devolvían `{success: true}` sin
  persistir nada ahora fallan de forma visible (`_noPortado`).
- Se eliminaron credenciales de producción del fuente, que estaban en **dos**
  sitios: `MOCK_USER_DB` en `api/main.py` y la hoja `USERS` del
  `MockSpreadsheet` en `api/services/sheets.py`. El login de desarrollo se
  define ahora por `DEV_LOGIN_USERS` en el entorno.
- CORS ya no permite credenciales con origen comodín.

### Fase 0.5 — `SupabaseSync` (escritura doble)

`CODIGO.js` tiene un módulo `SupabaseSync` que replica en Supabase cada
escritura que la app hace en Sheets. Se invoca después del `flush` y **nunca
puede romper un guardado**: todo va en `try/catch` con `muteHttpExceptions`.

**Importante:** está construido y probado, pero **puede que aún no esté
desplegado**. Solo replica si `SUPABASE_URL` y `SUPABASE_KEY` están en
Propiedades del Script de Apps Script. Pregunta antes de asumir que Supabase
está al día.

### Lectura de columnas

`api/services/sheets.py::build_header_map()` construye el mapa de columnas
dinámicamente: las curadas primero y detrás todas las que traigan los datos.
Cobertura actual **37/37 en `quotes` y 28/28 en `tasks`**. Antes se mantenía a
mano y se quedaba corto.

También resuelve el nombre de hoja sin distinguir mayúsculas ni espacios
(`resolve_source_sheet`), porque `source_sheet` no está normalizado.

### Normalización de estatus

`tasks.status` pasó de 45 valores distintos a 12, y `quotes.estatus` de 26 a
11. La regla vive en `api/services/tracker_rules.py::normalize_status()` y
está espejada en `SupabaseSync.normalizeStatus()` de `CODIGO.js`, con paridad
verificada 57/57.

## El estado real de la base

Credenciales en `.env` (ignorado por git). Conteos verificados:

| Tabla | Filas | Notas |
|---|---|---|
| `tasks` | 4.626 | 28 columnas. **Es tu objetivo.** |
| `task_involucrados` | 7.246 | Existe pero **nadie la lee ni la escribe** |
| `quotes` | 661 | 37 columnas |
| `people` | 54 | |
| `system_log` | 16.196 | |
| `plan_semanal` | 1.180 | |
| `profiles` | 0 | Creada, sin poblar |
| `sites` / `projects` | 1 / 4 | |
| `catalogos` | 75 | |
| `personal_agenda` | 27 | |
| `kpi_cotizaciones` | 24 | |
| `ppc_borradores` | 11 | |
| `banco_datos` | 3 | |
| `work_orders` + 5 tablas `wo_*` | 1 c/u | |

Restricciones comprobadas empíricamente:

- `tasks.dedupe_key` → **tiene restricción única**. Es la clave de upsert.
- `tasks.folio` → **no** es única. Correcto: el mismo folio vive en varias
  filas por difusión ("papa caliente").
- `tasks.id` → clave primaria (uuid).
- `tasks.status` → **`NOT NULL`**. Escribir nulo aborta el upsert con `23502`.
- `quotes.folio` → clave primaria. `quotes.estatus` sí admite nulo.

## Lo que tienes que construir

Una capa de datos relacional real para `tasks`, con **escritura**.

### El problema que resuelve

`api/services/sheets.py` convierte las tablas relacionales en una matriz 2D de
strings para que el motor de reglas las trate como si fueran una hoja. Eso trae
dos consecuencias graves:

1. **No hay escritura.** `GSheetsManager.write_values()` no tiene ruta a
   Supabase, pese a que su docstring afirma tenerla. Sin `credentials.json`
   cae a `is_mock = True` y escribe en un `dict` en memoria del proceso. En
   Vercel (serverless) cada petición es un proceso nuevo. **Hoy todo guardado
   a través del backend Python se pierde.**
2. **Se pierden los tipos.** Todo sale por `str()`, así que la distinción
   entre el número `1` y el string `"1"` desaparece — y de ella depende la
   regla de `AVANCE`.

### Entregables

1. **Paquete `backend/`** nuevo, junto a `api/` (no encima). Separación clara:
   `routers`, `services`, `repositories`, `schemas`, `models`, `core`.
2. **SQLAlchemy 2.x** con pool de conexiones vía `DATABASE_URL`. Si el entorno
   no tiene TCP al 5432, hace falta una ruta alternativa por REST — verifícalo
   antes de decidir.
3. **Repositorio de `tasks`** que trabaje con las 28 columnas y **preserve
   tipos**. Modelos Pydantic como contrato, no arreglos de strings.
4. **Escritura transaccional** en las operaciones por lotes. Hoy no hay
   transacciones.
5. **Auto-archivado como cambio de estado**, no como reordenamiento de filas.
6. **Tests** que corran sin base real.

`api/services/tracker_rules.py` (~1.150 líneas) es el activo más valioso del
repo: es el port de las reglas de negocio con paridad probada contra
`CODIGO.js`. **Consérvalo.** Refactorízalo para operar sobre objetos de dominio
en vez de la matriz de la hoja, usando los tests existentes como red.

## Reglas de negocio que no puedes romper

Verificadas contra los datos reales. Varias contradicen lo que parecería
razonable, así que léelas con atención.

### 1. `dedupe_key` — identidad de fila

**Paridad exacta 4.626/4.626 verificada.** El orden de evaluación importa:

```
1. El folio ya contiene "::"  -> sintético ("HOJA::ROW123"), se usa tal cual
2. Prefijo de secuencia global (PPC-, AV-, TG-, WO-, SITE-, PROJ-) -> folio
3. Folio tipo timestamp: /^\d{10,}(\.0+)?$/ -> folio
4. Cualquier otro -> "<hoja>::<folio>"
```

Dos trampas que costaron descubrir:

- **Los folios con iniciales de persona NO son globales.** `JO-0009`,
  `SP-0007`, `GM-0123` caen en el caso 4. `JO-0009` vive en **10 trackers
  distintos** y cada copia es una fila legítima. Tratarlos como globales las
  colapsaría en una sola.
- **El nombre de hoja va SIN `trim`.** Hay hojas reales con espacio inicial
  (`" LILIANA AYLIN MARTINEZ IBARRA"`) y la migración lo conservó dentro de la
  clave. Recortarlo genera una clave distinta y el upsert **inserta un
  duplicado** en vez de actualizar.

La implementación de referencia está en `SupabaseSync.computeDedupeKey()`
(`CODIGO.js`). **Pórtala a Python y verifícala contra los 4.626 registros
reales antes de confiar en ella.**

### 2. `AVANCE` — el número 1 y el string "1" no son lo mismo

`AGENTS.md` §4 es explícito: el **número** `1` viene de una celda con formato
porcentual y significa **100 %**; el **string** `"1"` lo tecleó una persona y
significa **1 %**. Colapsarlos archivaría como terminadas las tareas al 1 %.

En la base, `avance` está en escala 0–100 (verificado: mínimo 0, máximo 100,
ningún valor en el intervalo (0,1]).

Ver `is_progress_complete()` en `tracker_rules.py`.

### 3. Un mismo folio en varias filas es legítimo

382 folios aparecen en más de una fila. `JO-0009` en 10, `SG-0065` en 9. Es
delegación lateral ("papa caliente"). **No las colapses.**

### 4. `INVOLUCRADOS` no es N:M en el código vivo

Es una columna de texto y además un **alias de `RESPONSABLE`**
(`CODIGO.js:926`). La "papa caliente" parte ese string por comas.

La tabla `task_involucrados` existe con 7.246 filas pero **nadie la lee ni la
escribe**. Decisión ya tomada por el dueño: **conservar el string**;
`task_involucrados` queda como estructura derivada. No cambies esto: el
frontend manda y espera un string con comas.

Al resolver `assignee_id`, toma **la primera** persona del string. Nunca
guardes el compuesto como si fuera una persona (ya hubo un bug así, que
ensuciaba `people` con filas tipo `"RAMIRO RODRIGUEZ, ALFONSO CORREA"`).

### 5. Auto-archivado

Una tarea pasa a "TAREAS REALIZADAS" cuando llega a 100 %, o su estatus es
terminal (`HECHO/TERMINADO/FINALIZADO/REALIZADO/COMPLETADO/DONE/CERRADO`), o
`CUMPLIMIENTO = SI`. **En el modelo nuevo esto debe ser un cambio de estado, no
mover filas.**

Si tocas la normalización de estatus, mantén el invariante: cada alias debe
apuntar a un canónico de su misma familia, de modo que `is_terminal_status()`
dé el mismo resultado antes y después. Una tarea no puede archivarse ni
desarchivarse por un cambio de formato.

### 6. "Ley de Antonia"

Hay ruteo por usuario cableado: las actividades de `ANTONIA_VENTAS` no se
mezclan con las de `ANTONIA PINEDA LOPEZ` aunque sean la misma persona física,
y el sufijo `(VENTAS)` se filtra según quién sea el usuario activo. Ver
`AGENTS.md` §3 y `apiSavePPCData` en `CODIGO.js`. Es lo más delicado del
sistema; el corte de ventas va al final por esto.

### 7. Identidad de fila en el fallback

Si un `FOLIO` no se encuentra, hay que buscar por la combinación de `CONCEPTO`
y `FECHA` antes de generar uno nuevo (`AGENTS.md` §2). Generar folio es el
último recurso.

## Lo que sigue roto y NO es tu alcance (pero conviene que sepas)

- **Gatekeeper en memoria**: `tracker_rules.py::Gatekeeper` es un `dict` del
  proceso. Con más de un worker no bloquea nada. Es la Fase 2.
- **Secuencias de folio sin bloqueo**: `api/services/work_order.py` lee y
  escribe `sequences.json` sin candado, en un filesystem efímero. Dos usuarios
  concurrentes obtienen el mismo folio. Fase 2.
- **Sin auditoría desde Python**: cero escrituras a `system_log`. Fase 3.
- **Sin auth real**: no hay JWT ni RBAC; `GET /api/config?role=X` acepta el rol
  como parámetro de query del cliente. Fase 4.
- **RLS sin configurar** en todas las tablas. Fase 4.
- **`monto` está vacío en las 661 cotizaciones.** Sin confirmar si el equipo no
  lo usa o si la migración lo perdió.
- **Una fila basura en `quotes`**: `folio = "FOLIO"`, un encabezado mal
  migrado, es la única fila de `Edgar Lopez (VENTAS)`.
- **Al menos una fecha corrupta en `tasks`**: el rango arranca en el año
  `0202`.

## Advertencias

- **No rompas la operación.** El sistema está en uso diario. Sheets y la app
  actual deben seguir funcionando; el corte se hace al final y a propósito.
- **No toques `index.html`.** La migración del frontend es una fase aparte.
  `api_service.js` es la capa de compatibilidad `google.script.run` → REST, y
  ya está cableada en `index.html:16`. Decisión ya tomada: se mantiene.
- **Nunca credenciales en el fuente**, ni como valor por defecto de
  `os.environ.get(...)`. Hay tests que lo verifican.
- **Archivos de Drive**: decisión ya tomada — Supabase Storage para lo nuevo,
  Drive de solo lectura para lo histórico. **Fuera del alcance de la Fase 1**:
  deja las URLs como texto y no toques las subidas.
- Al exponer `id`, `dedupe_key` y `assignee_id` en la lectura, **trátalas como
  solo lectura** al activar la escritura. No las aceptes desde el cliente.

## Cómo verificar

```bash
pip install -r requirements.txt -r requirements-dev.txt

python -m pytest tests/test_tracker_rules.py tests/test_api_contract.py \
                 tests/test_ventas_columns.py tests/test_normalizacion_estatus.py -q
node tests/gas/run_tests.js
```

Estado base al empezar: **325 en pytest y 85/85 en el backend GAS**. No los
rompas.

Nota: `python -m pytest tests/` completo falla al recolectar 5 módulos por
dependencias opcionales de IA (`langchain`, `pypdf`, `streamlit`) que no están
instaladas. Es preexistente y no tiene que ver con el backend del tracker.

La verificación que más valor dio en las fases anteriores fue **contrastar la
lógica contra los datos reales de producción**, no solo contra fixtures. Ahí
aparecieron dos errores de especificación y el problema del espacio inicial en
el nombre de hoja. Hazlo.

## Documentación de apoyo

| Archivo | Qué tiene |
|---|---|
| `docs/PLAN_BACKEND_PYTHON.md` | **Empieza aquí.** Auditoría completa y plan por fases |
| `AGENTS.md` | Convenciones del repo y reglas de negocio |
| `docs/ARQUITECTURA_Y_BASE_DE_DATOS.md` | Modelo de datos y flujos actuales |
| `docs/API_CONTRACT.md` y `docs/openapi.yaml` | Contrato de API |
| `scripts/normalizar_estatus.py` | Ejemplo de migración de datos segura (respaldo, simulación, idempotencia) |

Ojo: `docs/ARQUITECTURA_Y_BASE_DE_DATOS.md` y `docs/API_CONTRACT.md` describen
el sistema **legado sobre Apps Script**, no el backend Python. No están
actualizados con la migración.

## Cómo quiero que arranques

1. Lee `docs/PLAN_BACKEND_PYTHON.md`, `AGENTS.md` y `api/services/tracker_rules.py`.
2. Confirma contra la base real que los conteos y restricciones de arriba
   siguen siendo ciertos. **No te fíes de este documento sin verificar**: fue
   escrito en un momento concreto y la operación sigue viva.
3. Preséntame un plan de implementación antes de escribir código, señalando
   qué decisiones necesitan mi input.
4. Dime explícitamente qué encuentres que **contradiga** este documento.

Empieza solo por `tasks`. `quotes` va después, en su propia tanda.
