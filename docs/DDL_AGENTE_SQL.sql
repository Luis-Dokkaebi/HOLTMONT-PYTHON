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

-- El rol de solo lectura. `nologin`: no es una cuenta, es un contenedor de
-- permisos para que la función corra dentro de él.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'agente_sql_lector') then
    create role agente_sql_lector nologin;
  end if;
end
$$;

grant usage on schema public to agente_sql_lector;

-- SOLO estas dos tablas, y solo SELECT. Si mañana el agente debe leer una
-- tabla más, se añade aquí a propósito: que ampliar su alcance exija una línea
-- explícita es la mitad del control.
grant select on public.tasks  to agente_sql_lector;
grant select on public.quotes to agente_sql_lector;

-- Que no pueda crear nada en el esquema, ni siquiera una tabla temporal suya.
revoke create on schema public from agente_sql_lector;

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
-- alguien lo añada creyendo que faltaba.
--
-- Se probaron las tres formas contra PostgreSQL 16.13 y NINGUNA funciona:
--
--   STABLE   + atributo `set statement_timeout`  -> pg_sleep(15) termina
--   VOLATILE + atributo `set statement_timeout`  -> pg_sleep(15) termina
--   VOLATILE + `set local` dentro del cuerpo     -> pg_sleep(15) termina
--   ALTER ROLE agente_sql_lector SET ...         -> pg_sleep(15) termina
--
-- El motivo es el mismo en los cuatro: `statement_timeout` se arma cuando
-- ARRANCA la sentencia externa, y cambiarlo a mitad no rearma el temporizador.
-- La función ya está dentro de esa sentencia cuando podría tocarlo.
--
-- Dónde sí se puede poner, si se quiere:
--
--   alter role service_role set statement_timeout = '8s';
--
-- ...pero eso afecta a TODAS las peticiones del backend, no solo a las del
-- agente, así que es una decisión del dueño y no un valor por defecto que se
-- cuela en un archivo de instalación.
--
-- Qué acota mientras tanto: `agente_sql.acotar()` envuelve toda consulta en un
-- LIMIT antes de mandarla. Y el camino alternativo —`AGENTE_SQL_DATABASE_URL`,
-- con SQLAlchemy— sí impone el tiempo máximo, porque ahí el `SET LOCAL` va en
-- una sentencia aparte antes del SELECT y el temporizador se arma a tiempo
-- (medido: `canceling statement due to statement timeout`).
as $$
declare
  resultado jsonb;
begin
  -- Comprobación de solo lectura, redundante con `STABLE` a propósito:
  -- si algún día alguien cambia la volatilidad de la función por descuido, esto
  -- sigue en pie. Una defensa que depende de una sola línea no es una defensa.
  if consulta !~* '^\s*(select|with)\s' then
    raise exception 'Solo se permiten consultas SELECT o WITH';
  end if;

  execute format('select coalesce(jsonb_agg(t), ''[]''::jsonb) from (%s) t', consulta)
    into resultado;

  return resultado;
end;
$$;

-- El dueño es lo que hace que `security definer` reduzca privilegios en vez de
-- elevarlos. Sin esta línea la función correría como quien la creó —normalmente
-- `postgres`— y sería exactamente la puerta trasera que dice no ser.
alter function public.agente_sql_consulta(text) owner to agente_sql_lector;

comment on function public.agente_sql_consulta(text) is
  'Canal de solo lectura del Agente de Consultas (api/services/agente_sql.py). '
  'Corre como el rol agente_sql_lector, que solo tiene SELECT sobre tasks y '
  'quotes. Ver docs/DDL_AGENTE_SQL.sql.';

-- Solo el backend. `anon` es la clave que viaja al navegador y `authenticated`
-- es cualquiera con sesión: ni uno ni otro debe poder ejecutar SQL, aunque sea
-- de lectura, porque la tabla `tasks` es el trabajo de todos los departamentos.
revoke all on function public.agente_sql_consulta(text) from public;
revoke all on function public.agente_sql_consulta(text) from anon;
revoke all on function public.agente_sql_consulta(text) from authenticated;
grant execute on function public.agente_sql_consulta(text) to service_role;

-- PostgREST cachea el esquema; sin esto la función tarda en aparecer en la API.
notify pgrst, 'reload schema';

-- =====================================================================
-- COMPROBACIÓN
-- =====================================================================
-- Después de ejecutar lo de arriba, esto debe devolver el conteo de tareas:
--
--   select public.agente_sql_consulta('select count(*) as n from tasks');
--
-- Y esto debe FALLAR con "is not allowed in a non-volatile function", que es la
-- prueba de que la garantía de solo lectura está viva:
--
--   select public.agente_sql_consulta('delete from tasks');
--
-- Y esta es LA comprobación que importa, la que el filtro de texto no cubre:
-- una escritura escondida detrás de un SELECT legítimo. Debe fallar con
-- "permission denied for table tasks", que es el rol haciendo su trabajo:
--
--   create function colado() returns int language plpgsql volatile as
--     $x$ begin insert into tasks(folio) values ('X'); return 1; end; $x$;
--   select public.agente_sql_consulta('select colado() as x');
--
-- Y esta debe fallar con "permission denied for table profiles": la lista blanca
-- de tablas la impone el rol, no solo el guardarraíl de texto de Python.
--
--   select public.agente_sql_consulta('select * from profiles');
--
-- Desde la aplicación: GET /api/agente/diagnostico lo comprueba entero y dice
-- qué falta, sin gastar una llamada al modelo.
-- =====================================================================
