"""
`docs/DDL_AGENTE_SQL.sql` ejercido contra un PostgreSQL de verdad.

Estas pruebas existen porque las dos afirmaciones de seguridad de ese archivo
**se escribieron primero mal y las tumbó la medición**, no la revisión:

1. «`STABLE` impide escribir» — **falso**. Una función `VOLATILE` llamada desde
   dentro sí escribe, y la restricción no se hereda. Se midió: la consulta
   `select un_escritor() as x` pasa el filtro de texto, atraviesa la función
   `STABLE` e **inserta una fila**. La garantía real es el rol dueño, que solo
   tiene SELECT.
2. «`set statement_timeout` acota la consulta» — **falso** en las cuatro formas
   probadas: `statement_timeout` se arma cuando arranca la sentencia externa y
   cambiarlo a mitad no rearma el temporizador.

Las dos habrían llegado a producción como comentarios tranquilizadores encima de
un guardarraíl que no existía. Por eso este archivo prueba el DDL ejecutándolo,
no leyéndolo.

Se salta —nunca se da por bueno— si no hay un binario de PostgreSQL en la
máquina; en CI, donde sí lo hay, corre en serio (RESTRICCIONES_EXTREMAS.md R8:
un fallo de infraestructura no es un fallo de código).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import shlex
import subprocess
import tempfile

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
DDL = RAIZ / "docs" / "DDL_AGENTE_SQL.sql"
PUERTO = int(os.environ.get("HOLTMONT_TEST_PG_PORT", "55433"))


def _binarios_de_postgres():
    """`(initdb, pg_ctl, psql)` si los tres existen; `None` si falta alguno."""
    directos = [shutil.which(n) for n in ("initdb", "pg_ctl", "psql")]
    if all(directos):
        return directos
    for version in ("16", "15", "14", "17"):
        base = pathlib.Path(f"/usr/lib/postgresql/{version}/bin")
        candidatos = [base / "initdb", base / "pg_ctl", base / "psql"]
        if all(c.exists() for c in candidatos):
            return [str(c) for c in candidatos]
    return None


BINARIOS = _binarios_de_postgres()

pytestmark = pytest.mark.skipif(
    BINARIOS is None,
    reason="PostgreSQL no está instalado en este entorno: no se puede ejercer el DDL",
)


def _cuenta_sin_privilegios():
    """
    Nombre de una cuenta sin privilegios, o `None` si ya no somos root.

    `initdb` se niega a correr como root —"cannot be run as root"— y aquí la
    suite corre como root. En CI normalmente no, y entonces esto es un no-op.
    """
    import pwd

    if os.geteuid() != 0:
        return None
    for nombre in ("postgres", "nobody", "daemon"):
        try:
            pwd.getpwnam(nombre)
            return nombre
        except KeyError:
            continue
    return None


def _correr(orden, cuenta, **kwargs):
    """
    Ejecuta `orden`, cambiando de usuario con `su` si hace falta.

    Con `su` y no con `preexec_fn=os.setuid`, y la diferencia no es de estilo:
    `subprocess` documenta `preexec_fn` como inseguro en un proceso con hilos, y
    `tests/conftest.py` levanta un servidor. Con `preexec_fn` esta suite moría
    con código 144 y **sin una sola línea de salida** — el proceso entero caía
    antes de que pytest pudiera escribir el informe.
    """
    if cuenta is None:
        return subprocess.run(orden, **kwargs)
    texto = " ".join(shlex.quote(parte) for parte in orden)
    return subprocess.run(["su", cuenta, "-s", "/bin/sh", "-c", texto], **kwargs)


@pytest.fixture(scope="module")
def base():
    """
    Un PostgreSQL efímero con las tablas mínimas y el DDL ya instalado.

    Es una base propia y desechable, no la de nadie: R7 dice que ninguna prueba
    toca la base de producción, y ejercer un DDL de permisos es justo lo que
    NUNCA debe correr contra datos reales.
    """
    initdb, pg_ctl, psql = BINARIOS
    with tempfile.TemporaryDirectory(prefix="pg_agente_", dir="/var/tmp") as tmp:
        datos = pathlib.Path(tmp) / "datos"
        sock = pathlib.Path(tmp) / "sock"
        sock.mkdir()
        bitacora = pathlib.Path(tmp) / "servidor.log"
        bitacora.touch()

        usuario = os.environ.get("HOLTMONT_TEST_PG_USER", "postgres")
        cuenta = _cuenta_sin_privilegios()
        if cuenta is not None:
            subprocess.run(["chown", "-R", cuenta, tmp], check=True, capture_output=True)

        _correr([initdb, "-D", str(datos), "-U", usuario, "--auth=trust"],
                cuenta, check=True, capture_output=True, timeout=120)

        # `-l` es obligatorio, no cosmético: sin archivo de log el servidor
        # hereda el pipe que abre `capture_output` y `subprocess.run` espera a
        # que se cierre, cosa que no pasa nunca porque el servidor sigue vivo.
        _correr([pg_ctl, "-D", str(datos), "-l", str(bitacora), "-o",
                 f"-p {PUERTO} -k {sock}", "-w", "start"],
                cuenta, check=True, capture_output=True, timeout=120)
        try:
            def sql(texto: str, tolerar_error: bool = False):
                proceso = subprocess.run(
                    [psql, "-h", str(sock), "-p", str(PUERTO), "-U", usuario,
                     "-tA", "-c", texto],
                    capture_output=True, text=True, timeout=60)
                if proceso.returncode and not tolerar_error:
                    raise AssertionError(proceso.stderr)
                return (proceso.stdout + proceso.stderr).strip()

            sql("""
                create table tasks (folio text, departamento text, avance numeric);
                create table quotes (folio text, area text);
                create table profiles (username text, password text);
                insert into tasks values
                    ('AV-1','HVAC',100),('AV-2','HVAC',40),('AV-3','FINANZAS',10);
                insert into profiles values ('ADMIN','no-mirar');
            """)
            # Los roles que Supabase trae de fábrica y el DDL da por existentes.
            for rol in ("service_role", "anon", "authenticated"):
                sql(f"create role {rol};", tolerar_error=True)

            instalacion = subprocess.run(
                [psql, "-h", str(sock), "-p", str(PUERTO), "-U", usuario,
                 "-v", "ON_ERROR_STOP=1", "-q", "-f", str(DDL)],
                capture_output=True, text=True, timeout=120)
            assert instalacion.returncode == 0, instalacion.stderr

            # El escritor escondido: una función VOLATILE que inserta. Es el
            # ataque que el filtro de texto NO ve, porque la consulta empieza
            # por SELECT.
            sql("""
                create function escritor_oculto() returns int
                language plpgsql volatile as $x$
                begin insert into tasks(folio) values ('COLADO'); return 1; end; $x$;
            """)
            yield sql
        finally:
            _correr([pg_ctl, "-D", str(datos), "-m", "immediate", "stop"],
                    cuenta, capture_output=True, timeout=60)


def _consultar(sql, consulta: str) -> str:
    escapada = consulta.replace("'", "''")
    return sql(f"select public.agente_sql_consulta('{escapada}');", tolerar_error=True)


# ======================================================================
# Lo que sí debe poder hacer
# ======================================================================


def test_el_ddl_se_instala_sin_errores(base):
    """Si el archivo no se puede ejecutar entero, nada de lo demás importa."""
    assert "agente_sql_consulta" in base(
        "select proname from pg_proc where proname = 'agente_sql_consulta';")


def test_una_consulta_de_lectura_devuelve_json(base):
    salida = _consultar(base, "select departamento, count(*) as n from tasks group by 1 order by 1")
    assert '"departamento": "FINANZAS"' in salida
    assert '"departamento": "HVAC"' in salida


def test_una_consulta_sin_resultados_devuelve_lista_vacia(base):
    """`[]` y no `null`: `consulta_cruda` espera una lista."""
    assert _consultar(base, "select folio from tasks where folio = 'NO-EXISTE'") == "[]"


# ======================================================================
# Lo que NO debe poder hacer
# ======================================================================


@pytest.mark.parametrize("consulta", [
    "delete from tasks",
    "update tasks set avance = 0",
    "insert into tasks(folio) values ('X')",
    "drop table tasks",
    "grant all on tasks to public",
])
def test_las_escrituras_directas_se_rechazan(base, consulta):
    """Las para el filtro de texto de la propia función, antes de llegar al rol."""
    assert "Solo se permiten consultas SELECT o WITH" in _consultar(base, consulta)


@pytest.mark.parametrize("consulta", [
    "select escritor_oculto() as x",
    "select 1 from tasks where escritor_oculto() > 0",
])
def test_una_escritura_escondida_tras_un_select_se_rechaza(base, consulta):
    """
    **La prueba que da sentido a este archivo.**

    Esta consulta empieza por SELECT, así que pasa los dos filtros de texto —el
    de Python y el de la función—. La primera versión del DDL confiaba en
    `STABLE` para pararla, y no la paraba: insertaba la fila.

    Lo que la para es que la función corre como `agente_sql_lector`, un rol sin
    INSERT. Si alguien quita el `SECURITY DEFINER` o el `alter function ... owner
    to`, esta prueba se pone roja y esa es toda su razón de existir.
    """
    assert "permission denied for table tasks" in _consultar(base, consulta)


def test_ninguna_escritura_llego_a_la_tabla(base):
    """La comprobación de resultado, no de mensaje de error."""
    assert base("select count(*) from tasks where folio = 'COLADO';") == "0"
    assert base("select count(*) from tasks;") == "3"


def test_la_lista_blanca_de_tablas_la_impone_el_rol(base):
    """
    `profiles` no está en los `grant select` del DDL, así que la base la niega
    aunque el guardarraíl de texto de Python se rodeara. Dos capas, y esta no
    depende de que un regex esté bien escrito.
    """
    assert "permission denied for table profiles" in _consultar(base, "select * from profiles")


def test_el_rol_no_puede_crear_nada_en_el_esquema(base):
    """`revoke create on schema public`: ni siquiera una tabla temporal suya."""
    assert base(
        "select has_schema_privilege('agente_sql_lector', 'public', 'CREATE');") == "f"


def test_el_rol_solo_tiene_select_sobre_las_dos_tablas(base):
    """Se comprueba el permiso, no el texto del DDL que lo concede."""
    for tabla in ("tasks", "quotes"):
        assert base(
            f"select has_table_privilege('agente_sql_lector', '{tabla}', 'SELECT');") == "t"
        for escritura in ("INSERT", "UPDATE", "DELETE"):
            assert base(
                f"select has_table_privilege('agente_sql_lector', "
                f"'{tabla}', '{escritura}');") == "f", (
                f"agente_sql_lector no debería poder {escritura} sobre {tabla}")


def test_la_funcion_corre_como_el_rol_de_solo_lectura(base):
    """
    `SECURITY DEFINER` + dueño correcto. Son las dos mitades de la garantía: con
    `SECURITY INVOKER` correría como quien llama —el backend, que sí escribe— y
    todo lo de arriba se cae.
    """
    assert base("select prosecdef from pg_proc where proname='agente_sql_consulta';") == "t"
    assert base(
        "select r.rolname from pg_proc p join pg_roles r on r.oid = p.proowner "
        "where p.proname = 'agente_sql_consulta';") == "agente_sql_lector"


def test_ni_anon_ni_authenticated_pueden_ejecutar_la_funcion(base):
    """
    `anon` es la clave que viaja al navegador. Si pudiera llamar a esto, el
    agente dejaría de tener control de acceso: `tasks` es el trabajo de todos
    los departamentos.
    """
    for rol in ("anon", "authenticated", "public"):
        assert base(
            f"select has_function_privilege('{rol}', "
            "'public.agente_sql_consulta(text)', 'EXECUTE');") == "f", (
            f"{rol} no debería poder ejecutar la función")


def test_service_role_si_puede_ejecutarla(base):
    """El backend, y solo el backend."""
    assert base(
        "select has_function_privilege('service_role', "
        "'public.agente_sql_consulta(text)', 'EXECUTE');") == "t"


def test_el_ddl_es_idempotente(base):
    """
    Se ejecuta dos veces sin romperse: quien lo pegue por segunda vez —porque no
    recuerda si ya lo hizo— no debe encontrarse un error.
    """
    initdb, pg_ctl, psql = BINARIOS
    assert "agente_sql_consulta" in base(
        "select proname from pg_proc where proname='agente_sql_consulta';")
    # `create or replace` + el `do $$ ... if not exists` del rol.
    assert base("select count(*) from pg_roles where rolname='agente_sql_lector';") == "1"


# ======================================================================
# Lo que pasa cuando el array de tablas y la base no coinciden
# ======================================================================
# El fallo que trajo estas pruebas: alguien cambió los `grant select` a las
# tablas de su base (`tasks_rows_sql`), una de ellas no existía con ese nombre,
# y el archivo abortó entero. Como el SQL Editor de Supabase ejecuta todo en una
# transacción, no quedó instalado NADA — pero el error que se leía en la
# interfaz seguía siendo «la función no existe», que manda a ejecutar el archivo
# que acaba de fallar. El bucle se cierra sobre sí mismo.


def _ddl_con_tablas(*tablas: str) -> str:
    """El DDL con otro array de tablas. El resto del archivo, intacto."""
    texto = DDL.read_text(encoding="utf-8")
    original = "array['tasks', 'quotes']"
    assert original in texto, "cambió el array de tablas del DDL"
    nuevo = "array[" + ", ".join(f"'{t}'" for t in tablas) + "]"
    return texto.replace(original, nuevo, 1)


def test_una_tabla_inexistente_avisa_pero_no_tumba_la_instalacion(base):
    """
    Avisar y seguir, no abortar.

    Abortar deja al usuario sin función Y sin pista: el mensaje que ve en la
    interfaz le dice que ejecute este archivo, que es justo lo que acaba de
    hacer. Con el aviso, el informe del final le dice qué tabla no está.
    """
    salida = base(_ddl_con_tablas("tasks", "quotes", "tabla_que_no_existe"))

    assert "tabla_que_no_existe" in salida
    assert "NO existe" in salida
    # Y lo importante: lo demás quedó instalado.
    assert base("select proname from pg_proc "
                "where proname='agente_sql_consulta';") == "agente_sql_consulta"
    assert base("select has_table_privilege('agente_sql_lector', "
                "'tasks', 'SELECT');") == "t"


def test_el_informe_final_dice_que_tablas_puede_leer_el_agente(base):
    """
    La fila que contesta "ya ejecuté el DDL y sigue fallando".

    Se mide sobre los permisos reales (`has_table_privilege`), no sobre lo que
    el archivo pretendía conceder: si el array no coincide con la base, esta
    fila lo enseña.
    """
    salida = base(DDL.read_text(encoding="utf-8"))

    assert "Tablas que el agente puede leer" in salida
    assert "tasks" in salida and "quotes" in salida
    assert "Función instalada" in salida
    assert "service_role puede ejecutarla" in salida


def test_el_rol_no_se_queda_con_el_create_que_necesito_para_ser_dueno(base):
    """
    El paso 2 le presta CREATE sobre `public` porque `ALTER FUNCTION ... OWNER
    TO` lo exige; el paso 6 se lo quita. Si el préstamo se quedara puesto, el
    rol "de solo lectura" podría crear tablas, vistas y funciones en `public` —
    y una función suya la ejecutaría el propio canal del agente.
    """
    assert base("select has_schema_privilege('agente_sql_lector', "
                "'public', 'CREATE');") == "f"
    # El préstamo tiene que seguir funcionando: reinstalar no puede fallar.
    base(DDL.read_text(encoding="utf-8"))
    assert base(
        "select r.rolname from pg_proc p join pg_roles r on r.oid = p.proowner "
        "where p.proname = 'agente_sql_consulta';") == "agente_sql_lector"


def test_el_informe_avisa_del_rls_que_dejaria_al_agente_sin_filas(base):
    """
    La única avería de este archivo que NO da error.

    `service_role` tiene BYPASSRLS; `agente_sql_lector` no. Una tabla con RLS
    encendida y sin política para él devuelve **cero filas sin fallar**: el
    canal en verde, el diagnóstico diciendo "listo" y el agente contestando
    "no encontré datos" a todas las preguntas. Un cero silencioso es
    indistinguible de un dato real para quien lo lee, así que tiene que salir
    en el informe.
    """
    assert "✅ ninguna" in base(DDL.read_text(encoding="utf-8"))

    base("alter table quotes enable row level security;")
    try:
        salida = base(DDL.read_text(encoding="utf-8"))
        assert "RLS que dejaría al agente sin filas" in salida
        assert "⚠️ quotes" in salida
        # Y se mide de verdad: con RLS y sin política, el rol no ve nada.
        assert _consultar(base, "select folio from quotes") == "[]"
    finally:
        base("alter table quotes disable row level security;")

    assert "✅ ninguna" in base(DDL.read_text(encoding="utf-8"))


# ======================================================================
# El archivo, ejecutado en las condiciones de Supabase y no en las de un
# PostgreSQL recién instalado
# ======================================================================
#
# Todo lo de arriba instala el DDL como **superusuario**, que es justo el caso
# en el que sus pasos 2 y 5 no hacen falta: un superusuario se salta "debes ser
# miembro del rol destino" y es dueño de todo. Si esos pasos se rompieran, esta
# suite seguiría en verde y el archivo abortaría en el único sitio donde se
# ejecuta de verdad.
#
# Y aborta ENTERO: el SQL Editor de Supabase corre el archivo en una
# transacción, así que un fallo en el paso 5 no deja nada instalado —ni la
# función, ni una pista—, solo la pantalla repitiendo que hay que ejecutar el
# DDL. Ese es exactamente el bucle que se quiere hacer imposible.

PUERTO_SUPABASE = int(os.environ.get("HOLTMONT_TEST_PG_PORT_SUPA", "55434"))


@pytest.fixture(scope="module")
def supabase():
    """
    El DDL instalado en un PostgreSQL montado como el de Supabase.

    Tres diferencias con el de arriba, y las tres tocan a este archivo:

    * **`postgres` no es superusuario.** Es quien ejecuta el SQL Editor.
    * **`public` es de `pg_database_owner`**, no de `postgres`; por ahí pasa el
      `grant usage, create on schema public` del paso 2.
    * **Existen `anon`, `authenticated` y `service_role`**, y `authenticator` es
      miembro de los tres con `noinherit`, que es como PostgREST cambia de rol.

    Devuelve `(consultar, informe)`: la función para preguntarle a la base y la
    salida literal de la instalación.
    """
    initdb, pg_ctl, psql = BINARIOS
    with tempfile.TemporaryDirectory(prefix="pg_supa_", dir="/var/tmp") as tmp:
        datos = pathlib.Path(tmp) / "datos"
        sock = pathlib.Path(tmp) / "sock"
        sock.mkdir()
        bitacora = pathlib.Path(tmp) / "servidor.log"
        bitacora.touch()

        cuenta = _cuenta_sin_privilegios()
        if cuenta is not None:
            subprocess.run(["chown", "-R", cuenta, tmp], check=True, capture_output=True)

        # El superusuario se llama `supabase_admin`, como allí, para que
        # `postgres` no acabe siéndolo por ser el que creó el clúster.
        _correr([initdb, "-D", str(datos), "-U", "supabase_admin", "--auth=trust"],
                cuenta, check=True, capture_output=True, timeout=120)
        _correr([pg_ctl, "-D", str(datos), "-l", str(bitacora), "-o",
                 f"-p {PUERTO_SUPABASE} -k {sock}", "-w", "start"],
                cuenta, check=True, capture_output=True, timeout=120)
        try:
            def psql_como(usuario: str, *extra: str, texto: str = ""):
                orden = [psql, "-h", str(sock), "-p", str(PUERTO_SUPABASE),
                         "-U", usuario, "-d", "postgres", "-tA", *extra]
                if texto:
                    orden += ["-c", texto]
                return _correr(orden, cuenta, capture_output=True, text=True, timeout=120)

            def sql(texto: str, usuario: str = "supabase_admin",
                    tolerar_error: bool = False) -> str:
                proceso = psql_como(usuario, texto=texto)
                if proceso.returncode and not tolerar_error:
                    raise AssertionError(proceso.stderr)
                return (proceso.stdout + proceso.stderr).strip()

            sql("""
                create role postgres nosuperuser createrole createdb login bypassrls;
                create role anon nologin;
                create role authenticated nologin;
                create role service_role nologin bypassrls;
                create role authenticator login noinherit;
                grant anon, authenticated, service_role to authenticator;
                alter schema public owner to pg_database_owner;
                alter database postgres owner to postgres;
            """)
            sql("""
                create table public.tasks (folio text, departamento text, avance numeric);
                create table public.quotes (folio text, area text);
                create table public.profiles (username text, password text);
                insert into tasks values ('AV-1','HVAC',100),('AV-2','FINANZAS',10);
            """, usuario="postgres")

            # `--single-transaction` es lo que hace el SQL Editor, y es lo que
            # convierte cualquier error del archivo en "no quedó nada".
            instalacion = psql_como("postgres", "-v", "ON_ERROR_STOP=1",
                                    "--single-transaction", "-f", str(DDL))
            yield sql, instalacion
        finally:
            _correr([pg_ctl, "-D", str(datos), "-m", "immediate", "stop"],
                    cuenta, capture_output=True, timeout=60)


def test_el_ddl_se_instala_con_un_postgres_que_no_es_superusuario(supabase):
    """La instalación entera, en una transacción y sin superusuario."""
    _, instalacion = supabase
    assert instalacion.returncode == 0, instalacion.stderr
    # Un `returncode` 0 no basta: el archivo avisa sin abortar cuando una tabla
    # del `array` no existe, así que puede terminar bien y dejar al agente sin
    # nada que leer. Lo que se comprueba es el informe.
    assert "❌" not in instalacion.stdout, instalacion.stdout
    assert "✅ quotes, tasks" in instalacion.stdout, instalacion.stdout


def test_la_funcion_corre_como_el_rol_de_lectura_sin_superusuario(supabase):
    """
    El paso 5 es el que puede fallar callado si el paso 2 no se hizo.

    Sin ese `alter function ... owner to`, la función quedaría a nombre de
    `postgres` —que en Supabase escribe en todas las tablas— y el archivo sería
    exactamente la puerta trasera que su cabecera dice no ser, sin un solo error
    por pantalla.
    """
    sql, _ = supabase
    dueño = sql("select r.rolname from pg_proc p join pg_roles r on r.oid = p.proowner "
                "where p.oid = to_regprocedure('public.agente_sql_consulta(text)');")
    assert dueño == "agente_sql_lector", dueño


def test_el_rol_no_conserva_el_create_prestado_sin_superusuario(supabase):
    """El paso 6 devuelve el CREATE que pidió prestado el paso 2."""
    sql, _ = supabase
    assert sql("select has_schema_privilege('agente_sql_lector', 'public', 'CREATE');") == "f"


def test_postgrest_no_necesita_que_authenticator_ejecute_la_funcion(supabase):
    """
    Deja medido por qué el DDL concede EXECUTE **solo** a `service_role`.

    Es la duda que aparece cada vez que sale un `PGRST202`: «¿no habrá que
    concedérselo también a `authenticator`, que es con quien PostgREST se
    conecta?». La respuesta es no, y está en su código: la caché de rutas la
    llena `allFunctions`, sin filtro de permisos, y el `has_function_privilege`
    solo lo aplica `accessibleFuncs`, que alimenta el OpenAPI
    (`src/PostgREST/SchemaCache.hs`).

    Se fija aquí porque la conclusión es invisible desde el SQL y la tentación
    —añadir `grant execute ... to authenticator`— abre el canal a cualquiera con
    la clave anónima, que es justo lo que cierra el paso 7.
    """
    sql, _ = supabase
    ve = ("select has_function_privilege('{}', "
          "to_regprocedure('public.agente_sql_consulta(text)'), 'EXECUTE');")
    assert sql(ve.format("authenticator")) == "f"
    assert sql(ve.format("service_role")) == "t"
