-- ---------------------------------------------------------------------------
-- `quotes`: la identidad de una fila pasa de `folio` a `(folio, source_sheet)`
-- ---------------------------------------------------------------------------
--
-- POR QUÉ
--
-- Una cotización repartida tiene que existir en dos tablas: la de quien la
-- reparte (Toñita) y la de quien la trabaja. Con `folio` como clave primaria
-- eso es imposible: el upsert de la copia colapsa contra el original y solo
-- sobrevive una fila.
--
-- No es teórico. La migración ya lo pagó: 25 folios `AV-`, nacidos en la tabla
-- de Antonia, acabaron viviendo **solo** en la hoja del vendedor porque la
-- llave obligó a que ganara una de las dos filas. Antonia dejó de verlos.
--
-- CUÁNDO CORRERLO
--
--   ⚠️  ANTES de desplegar el código que lo acompaña.
--
-- El código manda `on_conflict=folio,source_sheet`. Si la restricción única no
-- existe todavía, Postgres responde 42P10 ("there is no unique or exclusion
-- constraint matching the ON CONFLICT specification") y **todo guardado de
-- cotización falla**. El orden correcto es: correr esto, comprobar, desplegar.
--
-- El orden inverso también es seguro para los datos —ninguna fila se pierde,
-- solo se rechazan las escrituras— pero deja la aplicación sin poder guardar
-- cotizaciones hasta que el DDL corra.
--
-- CÓMO CORRERLO
--
-- Supabase → SQL Editor → pegar y ejecutar. La clave de servicio de la API no
-- puede ejecutar DDL, por eso no lo hace la aplicación.
--
-- REVERSIBLE
--
-- Sí, mientras no exista todavía ninguna cotización duplicada entre hojas. El
-- bloque de reversión está al final, comentado.
-- ---------------------------------------------------------------------------

BEGIN;

-- 1. Comprobación previa. Si esto devuelve algo, hay filas que ya violarían la
--    forma esperada y hay que mirarlas antes de seguir.
--    (Con la llave actual no puede devolver nada; se deja por higiene.)
SELECT folio, source_sheet, count(*)
FROM   public.quotes
GROUP  BY folio, source_sheet
HAVING count(*) > 1;

-- 2. `source_sheet` pasa a formar parte de la identidad, así que no puede ser
--    nula. Ya es NOT NULL en el esquema actual; el ALTER es idempotente y deja
--    constancia de que la condición es deliberada.
ALTER TABLE public.quotes
    ALTER COLUMN source_sheet SET NOT NULL;

-- 3. Fuera la clave primaria vieja y dentro la compuesta.
--    El nombre por defecto que da Postgres a la PK de `quotes` es `quotes_pkey`.
ALTER TABLE public.quotes
    DROP CONSTRAINT quotes_pkey;

ALTER TABLE public.quotes
    ADD CONSTRAINT quotes_pkey PRIMARY KEY (folio, source_sheet);

-- 4. El folio sigue siendo por lo que más se busca —el vínculo entre copias es
--    el folio— y ya no lo cubre un índice propio, porque en una PK compuesta la
--    primera columna solo sirve como prefijo. Se le da el suyo.
CREATE INDEX IF NOT EXISTS quotes_folio_idx ON public.quotes (folio);

COMMIT;

-- ---------------------------------------------------------------------------
-- Comprobación posterior: las tres deben salir como se indica.
-- ---------------------------------------------------------------------------
--
--   -- (a) la PK es compuesta
--   SELECT conname, pg_get_constraintdef(oid)
--   FROM   pg_constraint
--   WHERE  conrelid = 'public.quotes'::regclass AND contype = 'p';
--   -- esperado: quotes_pkey  PRIMARY KEY (folio, source_sheet)
--
--   -- (b) no se perdió ni una fila
--   SELECT count(*) FROM public.quotes;   -- esperado: 661
--
--   -- (c) el índice de folio existe
--   SELECT indexname FROM pg_indexes
--   WHERE  tablename = 'quotes' AND indexname = 'quotes_folio_idx';
--
-- ---------------------------------------------------------------------------
-- Reversión (solo si aún no hay cotizaciones repetidas entre hojas)
-- ---------------------------------------------------------------------------
--
--   BEGIN;
--   -- Si esto devuelve filas, NO se puede revertir sin decidir cuál se queda:
--   SELECT folio, count(*) FROM public.quotes GROUP BY folio HAVING count(*) > 1;
--
--   DROP INDEX IF EXISTS public.quotes_folio_idx;
--   ALTER TABLE public.quotes DROP CONSTRAINT quotes_pkey;
--   ALTER TABLE public.quotes ADD CONSTRAINT quotes_pkey PRIMARY KEY (folio);
--   COMMIT;
