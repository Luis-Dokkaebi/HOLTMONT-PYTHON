-- ---------------------------------------------------------------------------
-- DDL pendiente de aplicar en Supabase
-- ---------------------------------------------------------------------------
-- Este archivo NO es el esquema del proyecto: es la lista de lo que falta
-- crear para que funcionalidad ya escrita en Python deje de fallar.
--
-- Por qué está aquí y no aplicado: desde el entorno de desarrollo no hay TCP
-- al 5432 ni credenciales, así que no se puede ejecutar ni verificar. Se deja
-- versionado para que quien tenga acceso lo aplique y para que el repo diga la
-- verdad sobre lo que le falta a la base.
--
-- Al aplicarlo, correr `scripts/verificar_base_tasks.py` para confirmar.


-- ===========================================================================
-- 1. habits_log  — REQUERIDA por apiSaveHabitLog
-- ===========================================================================
-- Estado: la tabla está mapeada en `api/services/sheets.py:TABLAS_POR_HOJA`
-- ("HABITOS_LOG" -> "habits_log") pero NO aparece en el inventario de tablas
-- reales de `scripts/verificar_base_tasks.py`. La lectura tolera su ausencia
-- (devuelve vacío con aviso); la escritura falla con un mensaje que apunta
-- aquí.
--
-- Columnas tomadas del esquema del original
-- (REAL-HOLTMONT/docs/ARQUITECTURA_Y_BASE_DE_DATOS.md §2.2, "Hábitos"):
--   ID, USUARIO, HABITO, META, LOG_JSON, FECHA_ACTUALIZACION
--
-- `usuario_raw` en vez de `usuario` para ser coherente con `personal_agenda`,
-- que ya usa ese nombre (ver el docstring de `fetch_unified_agenda`).

CREATE TABLE IF NOT EXISTS public.habits_log (
    id                   TEXT PRIMARY KEY,
    usuario_raw          TEXT,
    habito               TEXT,
    meta                 NUMERIC,
    log_json             TEXT,
    fecha_actualizacion  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS habits_log_usuario_idx
    ON public.habits_log (usuario_raw);


-- ===========================================================================
-- 2. Índices de unicidad para Proyectos  — RECOMENDADO
-- ===========================================================================
-- `backend/repositories/proyectos.py` comprueba los duplicados leyendo antes de
-- insertar, que es lo que hacía el original con un LockService de 5 s. Sin
-- candado ni restricción en la base, dos altas simultáneas del mismo nombre
-- pueden colarse las dos. Estos índices lo vuelven imposible.
--
-- Ajustar los nombres de columna si el esquema real difiere: el repositorio los
-- resuelve entre varios candidatos porque no se pudieron verificar.

-- CREATE UNIQUE INDEX IF NOT EXISTS sites_nombre_uniq
--     ON public.sites (upper(btrim(nombre)));

-- CREATE UNIQUE INDEX IF NOT EXISTS projects_sitio_nombre_uniq
--     ON public.projects (id_sitio, upper(btrim(nombre_subproyecto)));


-- ===========================================================================
-- 3. profiles  — poblar, no crear
-- ===========================================================================
-- La tabla existe y está VACÍA (0 filas). `api/services/organigrama.py` trae
-- las 41 cuentas como semilla y `perfil()` prefiere la base cuando hay datos,
-- así que el sistema funciona sin esto; poblarla es lo que permite al dueño
-- cambiar un rol o un `seller` sin desplegar.
--
-- Columnas que `_perfil_desde_base` lee:
--   username, role, label, email, staff_name, dept, seller
--
-- Las contraseñas siguen en texto plano por decisión explícita del dueño
-- (2026-07): se migran cuando se haga la migración completa. NO se versionan
-- aquí ni en ningún otro archivo del repo.
--
-- Para poblarla: `python scripts/migrar_perfiles.py --aplicar`, que lee las 41
-- cuentas del CODIGO.js de Apps Script y las escribe. Se corre en la máquina de
-- quien tiene el repo; las contraseñas no pasan por el fuente ni se imprimen.
--
-- OJO — el CREATE TABLE de abajo NO es la tabla que está desplegada.
--
-- Se comprobó contra la base real el 2026-07-30 (vía el OpenAPI de PostgREST,
-- que es la única forma de ver el esquema con la tabla vacía). Lo que hay es:
--
--   id          uuid   PRIMARY KEY      <- la PK es `id`, no `username`
--   username    text
--   role        text
--   label       text
--   dept        text
--   seller      boolean
--   person_id   uuid   FK -> people.id
--   email       text
--   created_at  timestamptz
--
-- Es decir: **no existe la columna `password`**, ni `staff_name`. Sin `password`
-- no hay dónde guardar las credenciales y `/api/login` rechaza a todo el mundo,
-- que es exactamente el síntoma que se estaba investigando. `staff_name` no hace
-- falta: `organigrama` lo resuelve contra la semilla cuando la base no lo trae.
--
-- Para habilitar el login sobre la tabla que ya existe, correr esto en el SQL
-- Editor de Supabase. Es aditivo: no toca ninguna columna ni fila existente.

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS password TEXT;

-- `migrar_perfiles.py` hace upsert con on_conflict=username, y PostgREST exige
-- un índice único sobre esa columna para resolverlo.
CREATE UNIQUE INDEX IF NOT EXISTS profiles_username_key
    ON public.profiles (username);

-- El CREATE TABLE original queda como referencia de instalación desde cero. Si
-- se usa, `username` es único por ser PK y el índice de arriba sobra.

CREATE TABLE IF NOT EXISTS public.profiles (
    username    TEXT PRIMARY KEY,
    password    TEXT,
    role        TEXT NOT NULL DEFAULT 'STAFF_USER',
    label       TEXT,
    email       TEXT,
    staff_name  TEXT,
    dept        TEXT,
    seller      BOOLEAN NOT NULL DEFAULT false
);

-- La tabla NO se expone por /api/data: el endpoint la rechaza con 403 y, además,
-- filtra cualquier columna de credenciales de cualquier tabla. Mientras las
-- contraseñas estén en texto plano, no aflojar ninguna de las dos barreras.


-- ===========================================================================
-- 4. tasks.project_id  — MEJORA, no requerido
-- ===========================================================================
-- Hoy las tareas de un proyecto se identifican por la etiqueta
-- `[PROY: NOMBRE]` dentro de CONCEPTO o COMENTARIOS, que es la convención del
-- original y la que el frontend escribe. Funciona, pero obliga a buscar por
-- subcadena y se rompe si alguien renombra un proyecto.
--
-- Con una clave foránea real, `fetch_project_tasks` sería una igualdad indexada
-- y el renombrado dejaría de importar. Requiere además una migración de datos
-- que traduzca las etiquetas existentes a `project_id`.

-- ALTER TABLE public.tasks
--     ADD COLUMN IF NOT EXISTS project_id TEXT REFERENCES public.projects (id_proyecto);

-- CREATE INDEX IF NOT EXISTS tasks_project_id_idx
--     ON public.tasks (project_id);
