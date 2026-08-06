-- ---------------------------------------------------------------------------
-- Los tres bloques de Work Order que no tenían tabla
-- ---------------------------------------------------------------------------
-- El formulario (`workorder_form.html`) captura viáticos, transporte e
-- ingeniería, y `process_and_save_work_order` los prepara para guardar. Pero
-- las tablas no existen en Supabase: PostgREST responde PGRST205 y el bloque se
-- quedaba solo en la nota de Obsidian, con un aviso visible en la respuesta.
--
-- Columnas tomadas de los encabezados que arma `api/services/work_order.py`
-- (bloques F, G y H, líneas 511-550), que a su vez son los del formulario.
--
-- El patrón lo marcan las cinco tablas hermanas que sí existen
-- (`wo_materiales`, `wo_mano_obra`, `wo_herramientas`, `wo_equipos`,
-- `wo_programa`): `id` sintético, `folio` como referencia a la orden, y el
-- resto en texto salvo lo que es claramente numérico.
--
-- Los importes van en NUMERIC y no en TEXT a propósito: el formulario ya manda
-- números y guardarlos como texto obliga a convertir en cada lectura, que es
-- de donde salieron los problemas de `avance` en `tasks`.
--
-- Cómo aplicarlo: pégalo en el editor SQL de Supabase, o corre
--   psql "$DATABASE_URL" -f docs/DDL_WO_BLOQUES.sql
--
-- Después: `python scripts/verificar_base_work_orders.py` lo comprueba.


-- ===========================================================================
-- 1. wo_viaticos  — bloque F del formulario
-- ===========================================================================
CREATE TABLE IF NOT EXISTS public.wo_viaticos (
    id              BIGSERIAL PRIMARY KEY,
    folio           TEXT NOT NULL,
    concepto        TEXT,
    cantidad        NUMERIC,
    costo_unitario  NUMERIC,
    total           NUMERIC
);

CREATE INDEX IF NOT EXISTS wo_viaticos_folio_idx ON public.wo_viaticos (folio);


-- ===========================================================================
-- 2. wo_transporte  — bloque G
-- ===========================================================================
CREATE TABLE IF NOT EXISTS public.wo_transporte (
    id              BIGSERIAL PRIMARY KEY,
    folio           TEXT NOT NULL,
    vehiculo        TEXT,
    chofer          TEXT,
    tiempo          TEXT,
    lts_gasolina    NUMERIC,
    costo_total     NUMERIC,
    notas_control   TEXT
);

CREATE INDEX IF NOT EXISTS wo_transporte_folio_idx ON public.wo_transporte (folio);


-- ===========================================================================
-- 3. wo_ingenieria  — bloque H
-- ===========================================================================
-- `horas_diseno` sin eñe: el encabezado del formulario es `HORAS_DISENO`, ya
-- transliterado. Se conserva tal cual para que el mapa de columnas sea una
-- traducción directa y no haya que recordar una excepción.
CREATE TABLE IF NOT EXISTS public.wo_ingenieria (
    id              BIGSERIAL PRIMARY KEY,
    folio           TEXT NOT NULL,
    entregable      TEXT,
    horas_diseno    NUMERIC,
    costo_hora      NUMERIC,
    total           NUMERIC
);

CREATE INDEX IF NOT EXISTS wo_ingenieria_folio_idx ON public.wo_ingenieria (folio);
