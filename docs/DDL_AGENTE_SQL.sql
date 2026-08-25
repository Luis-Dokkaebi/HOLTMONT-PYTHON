-- =====================================================================
-- Agente de Consultas — canal de lectura sobre PostgREST
-- =====================================================================
--
-- QUÉ HACE
-- Crea una función que ejecuta un SELECT y devuelve el resultado como JSON.
-- `api/services/agente_sql.py` la llama por RPC (`POST /rest/v1/rpc/...`), que
-- es la única forma de ejecutar SQL a través de PostgREST.
--
-- CÓMO SE INSTALA
-- Supabase → SQL Editor → pegar este archivo entero → Run. Una sola vez.
-- No hace falta ninguna variable de entorno nueva: el agente usa las
-- `SUPABASE_URL` y `SUPABASE_KEY` que la aplicación ya tiene configuradas.
--
-- POR QUÉ EXISTE, PUDIENDO CONECTAR DIRECTO A POSTGRES
-- Porque el despliegue usa PostgREST, no una conexión TCP a Postgres. La
-- alternativa —`AGENTE_SQL_DATABASE_URL`— sigue existiendo y tiene prioridad si
-- está definida; esto es el camino que funciona con lo que ya hay puesto.
--
-- =====================================================================
-- POR QUÉ ESTO NO ES UNA PUERTA TRASERA
-- =====================================================================
--
-- Sí: la función recibe SQL y lo ejecuta. La garantía de que aun así no puede
-- escribir es UNA, y conviene decir cuál NO es.
--
-- ❌ NO es `STABLE`. Se midió contra PostgreSQL 16.13 y es falso que baste:
--
--      select agente_sql_consulta('select un_escritor_volatil() as x');
--
--    ...pasa el filtro de texto (empieza por SELECT), atraviesa la función
--    `STABLE` y **escribe**. PostgreSQL prohíbe las sentencias de escritura que
--    ejecuta directamente una función no volátil, pero NO las que hace una
--    función volátil llamada desde ella. La restricción no se hereda.
--
--    `STABLE` se conserva abajo porque cierra el caso directo y no cuesta nada,
--    pero como única defensa era una garantía imaginaria.
--
-- ✅ LA GARANTÍA ES EL ROL. La función es `SECURITY DEFINER` y su dueño es
--    `agente_sql_lector`, un rol al que solo se le concede SELECT sobre las dos
--    tablas que el agente puede leer. Todo lo que ocurre dentro —incluida
--    cualquier función anidada— corre con ESE rol. Un INSERT no falla por una
--    comprobación de texto: falla porque el rol no tiene el permiso.
--
--    `SECURITY DEFINER` suele ser una mala señal porque normalmente ELEVA
--    privilegios. Aquí hace lo contrario: el dueño tiene MENOS permisos que
--    quien llama. Es una reducción, y por eso es segura.
--
--    De regalo, la lista blanca de tablas queda impuesta por la base: el rol no
--    tiene SELECT sobre `profiles` ni sobre nada más, así que
--    `select * from profiles` falla aunque el guardarraíl de texto se rodee.
--
-- Las otras dos capas siguen en pie, en este orden:
--   1. `agente_sql.validar_sql` en Python (SELECT/WITH, una sentencia, sin
--      verbos de escritura, solo la tabla del esquema pedido).
--   2. La comprobación de texto de esta función, redundante a propósito.
--   3. El rol. Esta es la que sostiene el edificio.
--
-- Quién puede llamarla: solo `service_role`, es decir, el backend. Esa clave ya
-- permite leer y escribir cualquier tabla por REST, así que esta función le
-- concede estrictamente menos de lo que ya tenía.
--
-- =====================================================================

-- =====================================================================
-- LO ÚNICO QUE SE AJUSTA: CÓMO SE LLAMAN TUS TABLAS
-- =====================================================================
--
-- El agente lee DOS tablas: las actividades y las cotizaciones. En este
-- repositorio se llaman `tasks` y `quotes`, que son las que escribe la
-- aplicación. Si en tu base se llaman de otra forma —por ejemplo los volcados
-- del notebook, `tasks_rows_sql` y `quotes_rows_sql`—, cambia el `array` de la
-- línea marcada más abajo. Es el único sitio.
--
-- ⚠️ **Y cambia también la aplicación, o esto no sirve de nada.** El nombre de
-- la tabla vive en dos sitios que TIENEN que coincidir:
--
--   1. aquí, que es quien concede el `SELECT`;
--   2. `AGENTE_SQL_TABLA_TASKS` / `AGENTE_SQL_TABLA_QUOTES` en el entorno del
--      despliegue (Vercel), que es lo que el agente escribe en el `FROM`.
--
-- Sin (2), el agente sigue pidiendo `tasks`, PostgreSQL responde `42P01`
-- ("relation does not exist") y PostgREST lo devuelve como **404**. Ese 404 es
-- exactamente el mismo que devuelve cuando la función RPC no existe, y por eso
-- la pantalla decía «La función agente_sql_consulta no existe en la base.
-- Ejecuta docs/DDL_AGENTE_SQL.sql» con el archivo ya ejecutado y funcionando.
-- Si no sabes qué tablas tienes, la consulta que lo dice está al final.
--
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. El rol de solo lectura
-- ---------------------------------------------------------------------
-- `nologin`: no es una cuenta, es un contenedor de permisos para que la
-- función corra dentro de él.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'agente_sql_lector') then
    create role agente_sql_lector nologin;
  end if;
end
$$;

-- ---------------------------------------------------------------------
-- 2. Lo que hace falta para poder TRANSFERIRLE la función (paso 5)
-- ---------------------------------------------------------------------
-- En Supabase `postgres` **no es superusuario**. Para `ALTER FUNCTION ... OWNER
-- TO agente_sql_lector` PostgreSQL exige dos cosas de quien ejecuta esto:
--
--   * ser miembro del rol destino  -> `grant agente_sql_lector to postgres`
--   * que el destino tenga CREATE en el esquema -> `grant create on schema`
--
-- Sin ellas el archivo aborta en el paso 5 con "must be member of role
-- agente_sql_lector", y como el SQL Editor ejecuta todo en una transacción, no
-- queda instalado NADA. El `CREATE` se devuelve en el paso 6, en cuanto deja de
-- hacer falta: un rol de solo lectura que puede crear objetos no es de solo
-- lectura.
grant agente_sql_lector to postgres;
grant usage, create on schema public to agente_sql_lector;

-- ---------------------------------------------------------------------
-- 3. SELECT, y solo SELECT, sobre las tablas del agente
-- ---------------------------------------------------------------------
-- Ampliar el alcance del agente cuesta una línea explícita en el `array`. Que
-- cueste eso es la mitad del control.
--
-- Una tabla que no existe **avisa y no aborta**, a propósito: si el `array` y
-- tu base no coinciden, lo que quieres es enterarte de cuál falta, no que se
-- caiga el archivo entero y te quedes sin función ni pista. El informe del
-- final lo repite en una tabla que se lee de un vistazo.
do $$
declare
  -- <<<<<<<<<< AJUSTA AQUÍ SI TUS TABLAS SE LLAMAN DISTINTO >>>>>>>>>>
  tablas_del_agente text[] := array['tasks', 'quotes'];
  -- <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
  tabla text;
begin
  foreach tabla in array tablas_del_agente loop
    if to_regclass(format('public.%I', tabla)) is null then
      raise warning 'La tabla public.% NO existe: el agente no podrá leerla. '
                    'Revisa el nombre en el array de arriba.', tabla;
    else
      execute format('grant select on public.%I to agente_sql_lector', tabla);
    end if;
  end loop;
end
$$;

-- ---------------------------------------------------------------------
-- 4. La función
-- ---------------------------------------------------------------------
create or replace function public.agente_sql_consulta(consulta text)
returns jsonb
language plpgsql
stable                      -- cierra el caso directo; NO es la garantía (ver arriba)
security definer            -- corre como `agente_sql_lector`: ESTA es la garantía
-- `search_path` fijo: sin esto, quien llama puede anteponer un esquema suyo y
-- cambiar a qué tabla se refiere un nombre dentro de la función. Con
-- `SECURITY DEFINER` eso deja de ser una molestia y pasa a ser un agujero.
set search_path = public, pg_temp
-- NO hay techo de tiempo aquí, y conviene que se lea por qué en vez de que
-- alguien lo añada creyendo que faltaba. Se probaron las cuatro formas contra
-- PostgreSQL 16.13 y ninguna funciona: `statement_timeout` se arma cuando
-- ARRANCA la sentencia externa, y cambiarlo a mitad no rearma el temporizador.
-- Lo que sí acota: `agente_sql.acotar()` envuelve toda consulta en un LIMIT.
as $$
declare
  resultado jsonb;
begin
  -- Comprobación de solo lectura, redundante con `STABLE` a propósito: si
  -- alguien cambia la volatilidad por descuido, esto sigue en pie.
  if consulta !~* '^\s*(select|with)\s' then
    raise exception 'Solo se permiten consultas SELECT o WITH';
  end if;

  execute format('select coalesce(jsonb_agg(t), ''[]''::jsonb) from (%s) t', consulta)
    into resultado;

  return resultado;
end;
$$;

-- ---------------------------------------------------------------------
-- 5. El dueño: lo que hace que `security definer` REDUZCA privilegios
-- ---------------------------------------------------------------------
-- Sin esta línea la función correría como quien la creó —normalmente
-- `postgres`— y sería exactamente la puerta trasera que dice no ser.
alter function public.agente_sql_consulta(text) owner to agente_sql_lector;

comment on function public.agente_sql_consulta(text) is
  'Canal de solo lectura del Agente de Consultas (api/services/agente_sql.py). '
  'Corre como el rol agente_sql_lector, que solo tiene SELECT sobre las tablas '
  'del agente. Ver docs/DDL_AGENTE_SQL.sql.';

-- ---------------------------------------------------------------------
-- 6. Se devuelve el CREATE prestado en el paso 2
-- ---------------------------------------------------------------------
-- Ya no hace falta —la función ya es suya— y dejarlo puesto convertiría al rol
-- de solo lectura en un rol que puede crear tablas, funciones y vistas en
-- `public`. Va aquí y no antes porque antes del paso 5 sí hacía falta.
revoke create on schema public from agente_sql_lector;

-- ---------------------------------------------------------------------
-- 7. Quién puede llamarla: solo el backend
-- ---------------------------------------------------------------------
-- `anon` es la clave que viaja al navegador y `authenticated` es cualquiera con
-- sesión: ni uno ni otro debe poder ejecutar SQL, aunque sea de lectura.
revoke all on function public.agente_sql_consulta(text) from public;
revoke all on function public.agente_sql_consulta(text) from anon;
revoke all on function public.agente_sql_consulta(text) from authenticated;
grant execute on function public.agente_sql_consulta(text) to service_role;

-- ---------------------------------------------------------------------
-- 8. PostgREST cachea el esquema; sin esto la función tarda en aparecer
-- ---------------------------------------------------------------------
notify pgrst, 'reload schema';

-- =====================================================================
-- INFORME: qué quedó instalado (se lee en el panel de resultados)
-- =====================================================================
-- Cuatro filas. Si las cuatro salen con ✅, el canal está completo.
-- La última es la que importa cuando "ya ejecuté el DDL y sigue fallando":
-- dice qué tablas puede leer el agente REALMENTE, medido sobre los permisos y
-- no sobre lo que este archivo pretendía conceder.
select 'Función instalada' as comprobacion,
       case when to_regprocedure('public.agente_sql_consulta(text)') is null
            then '❌ NO — mira los errores de arriba'
            else '✅ sí' end as resultado
union all
select 'Corre como agente_sql_lector',
       coalesce((select case when r.rolname = 'agente_sql_lector'
                             then '✅ sí' else '❌ corre como ' || r.rolname end
                 from pg_proc p join pg_roles r on r.oid = p.proowner
                 where p.oid = to_regprocedure('public.agente_sql_consulta(text)')),
                '❌ la función no existe')
union all
select 'service_role puede ejecutarla',
       case when to_regprocedure('public.agente_sql_consulta(text)') is null then '❌ n/a'
            when has_function_privilege('service_role',
                   to_regprocedure('public.agente_sql_consulta(text)'), 'EXECUTE')
            then '✅ sí' else '❌ NO' end
union all
select 'Tablas que el agente puede leer',
       coalesce((select '✅ ' || string_agg(distinct c.relname, ', ' order by c.relname)
                 from pg_class c join pg_namespace n on n.oid = c.relnamespace
                 where n.nspname = 'public'
                   and c.relkind in ('r', 'v', 'm', 'p', 'f')
                   and has_table_privilege('agente_sql_lector', c.oid, 'SELECT')),
                '❌ ninguna — el array del paso 3 no coincide con tus tablas')
union all
select 'RLS que dejaría al agente sin filas',
       coalesce((select '⚠️ ' || string_agg(c.relname, ', ' order by c.relname)
                 from pg_class c join pg_namespace n on n.oid = c.relnamespace
                 where n.nspname = 'public' and c.relrowsecurity
                   and has_table_privilege('agente_sql_lector', c.oid, 'SELECT')),
                '✅ ninguna');

-- =====================================================================
-- LA FILA DEL RLS: POR QUÉ ESTÁ AHÍ
-- =====================================================================
-- Es la única avería de este archivo que **no da error**. `service_role` tiene
-- BYPASSRLS y `agente_sql_lector` no, así que una tabla con RLS encendida y sin
-- política para él devuelve **cero filas, sin fallar**. El agente contestaría
-- "no encontré datos" a todas las preguntas, con el canal en verde y el
-- diagnóstico diciendo que todo está bien.
--
-- Si esa fila sale con ⚠️, la salida es una política de solo lectura por tabla.
-- Va comentada a propósito: tocar el RLS de una tabla de negocio se decide, no
-- se hereda de un archivo de instalación. `DROP ... IF EXISTS` + `CREATE`
-- porque PostgreSQL no admite `CREATE POLICY IF NOT EXISTS`.
--
--   drop policy if exists agente_sql_lector_lee on public.tasks;
--   create policy agente_sql_lector_lee on public.tasks
--     for select to agente_sql_lector using (true);
--
--   drop policy if exists agente_sql_lector_lee on public.quotes;
--   create policy agente_sql_lector_lee on public.quotes
--     for select to agente_sql_lector using (true);
--
-- `using (true)` no amplía nada: el rol ya tiene SELECT sobre esas dos tablas y
-- solo se llega a él por la función RPC, que únicamente `service_role` ejecuta.
-- =====================================================================

-- =====================================================================
-- SI EL INFORME SALE BIEN Y LA INTERFAZ SIGUE FALLANDO
-- =====================================================================
-- Primero: `GET /api/agente/diagnostico` lo comprueba entero desde la
-- aplicación —función, permiso y CADA tabla— sin gastar una llamada al modelo,
-- y dice cuál de las tres falta. Es más rápido que cualquier cosa de aquí.
--
-- Para ver qué tablas hay, por si el nombre no era el que creías:
--
--   select table_name from information_schema.tables
--    where table_schema = 'public' order by 1;
--
-- Las tres comprobaciones de la garantía de solo lectura, que deben FALLAR:
--
--   -- 1) escritura directa: "Solo se permiten consultas SELECT o WITH"
--   select public.agente_sql_consulta('delete from tasks');
--
--   -- 2) escritura escondida tras un SELECT — la que el filtro de texto NO ve.
--   --    Debe fallar con "permission denied for table tasks": es el rol, no el
--   --    regex, y es la razón de ser de este archivo.
--   create function colado() returns int language plpgsql volatile as
--     $x$ begin insert into tasks(folio) values ('X'); return 1; end; $x$;
--   select public.agente_sql_consulta('select colado() as x');
--
--   -- 3) tabla fuera de la lista: "permission denied for table profiles"
--   select public.agente_sql_consulta('select * from profiles');
-- =====================================================================
