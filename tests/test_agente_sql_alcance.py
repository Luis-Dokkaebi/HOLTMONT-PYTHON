"""
El agente, acotado a la hoja de quien pregunta.

Hasta ahora el Agente de Consultas leía `tasks` y `quotes` **enteras** y por eso
solo lo veían dos cuentas. Para que cada ejecutivo pueda preguntar "¿cuántas
cotizaciones tengo pendientes?" hace falta que "tengo" signifique algo, y eso no
se consigue pidiéndoselo al modelo en el prompt: un modelo que olvide poner el
`WHERE` devuelve el trabajo de toda la empresa y la respuesta se lee igual de
bien. El acotado se impone **sobre el SQL ya generado**, antes de ejecutarlo.

La técnica es anteponer un CTE con el nombre de la tabla:

    WITH tasks AS (SELECT * FROM public.tasks WHERE source_sheet = 'X')
    SELECT ... FROM tasks ...

El CTE tapa a la tabla para todas las referencias sin calificar de la consulta,
venga como venga: con alias, con GROUP BY, con subconsultas. No se reescribe el
cuerpo del SQL del modelo, que es lo que se rompe en cuanto llega una consulta
con una forma que no se previó.

**Lo que esto NO es.** No es un control de acceso. La cuenta llega en el cuerpo
de la petición y el backend no tiene sesión —deuda conocida y documentada de
toda la API, ver el comentario sobre `/api/agente/*` en `api/main.py`—, así que
un cliente que llame a la ruta a mano puede decir que es otra persona. Lo que
esto sí es: que la pantalla de cada ejecutivo responda con sus datos y no con
los de toda la empresa, y que eso lo garantice el SQL y no la buena voluntad del
modelo. Cerrarlo del todo es el `Depends` de sesión que le falta a la API entera.
"""

from __future__ import annotations

from typing import Any, Dict, List

from api.services import agente_sql as ag
from api.services import agente_sql_esquemas as esquemas
from api.services import organigrama

TASKS = esquemas.ESQUEMAS["tasks"]
QUOTES = esquemas.ESQUEMAS["quotes"]

HOJA = "EDUARDO MANZANARES"


class LLMFalso:
    """Doble del modelo: devuelve las respuestas de una lista, en orden."""

    def __init__(self, respuestas: List[str]):
        self.respuestas = list(respuestas)

    def invoke(self, _mensajes: Any) -> Any:
        return type("R", (), {"content": self.respuestas.pop(0)})()


class BaseFalsa:
    """Doble de la base: guarda el SQL que de verdad se ejecutó."""

    def __init__(self, filas: List[Dict[str, Any]] = None):
        self.filas = filas if filas is not None else [{"total": 3}]
        self.ejecutados: List[str] = []

    def __call__(self, sql: str) -> List[Dict[str, Any]]:
        self.ejecutados.append(sql)
        return self.filas


# ----------------------------------------------------------------------
# El CTE que acota: función pura
# ----------------------------------------------------------------------


def test_una_consulta_simple_queda_envuelta_en_el_cte_de_la_hoja():
    acotada = ag.acotar_a_la_hoja("SELECT COUNT(*) FROM tasks", "tasks", HOJA)
    assert acotada.startswith("WITH tasks AS (SELECT * FROM public.tasks")
    assert f"source_sheet = '{HOJA}'" in acotada
    assert "SELECT COUNT(*) FROM tasks" in acotada


def test_la_tabla_del_cte_se_lee_calificada_con_el_esquema():
    """
    `FROM public.tasks` y no `FROM tasks`: dentro de un CTE que se llama igual
    que la tabla, el nombre sin calificar es justo el que se presta a
    interpretarse de dos maneras. Calificarlo no deja lugar a dudas.
    """
    acotada = ag.acotar_a_la_hoja("SELECT 1 FROM tasks", "tasks", HOJA)
    assert "FROM public.tasks" in acotada


def test_una_consulta_que_ya_traia_su_propio_with_conserva_los_dos():
    sql = "WITH abiertas AS (SELECT * FROM tasks WHERE avance < 100) SELECT * FROM abiertas"
    acotada = ag.acotar_a_la_hoja(sql, "tasks", HOJA)
    assert acotada.startswith("WITH tasks AS (")
    assert "abiertas AS (SELECT * FROM tasks WHERE avance < 100)" in acotada
    # Un solo WITH en toda la sentencia: dos es un error de sintaxis.
    assert acotada.upper().count("WITH ") == 1


def test_un_with_recursive_sigue_siendo_recursive():
    """
    `WITH tasks AS (...), RECURSIVE ...` no es SQL válido: la palabra va pegada
    al WITH. Un CTE no recursivo dentro de una lista RECURSIVE sí es legal.
    """
    sql = "WITH RECURSIVE arbol AS (SELECT 1) SELECT * FROM arbol"
    acotada = ag.acotar_a_la_hoja(sql, "tasks", HOJA)
    assert acotada.startswith("WITH RECURSIVE tasks AS (")
    assert "arbol AS (SELECT 1)" in acotada


def test_una_hoja_con_apostrofe_no_rompe_el_literal():
    """
    Los nombres salen del organigrama, no del usuario, pero un literal que se
    arma pegando texto es un literal que se arma pegando texto.
    """
    acotada = ag.acotar_a_la_hoja("SELECT 1 FROM tasks", "tasks", "O'BRIEN")
    assert "'O''BRIEN'" in acotada


def test_el_punto_y_coma_final_no_parte_la_sentencia():
    acotada = ag.acotar_a_la_hoja("SELECT 1 FROM tasks;", "tasks", HOJA)
    assert ";" not in acotada.rstrip(";")


def test_cotizaciones_se_acota_por_su_propia_tabla():
    acotada = ag.acotar_a_la_hoja("SELECT * FROM quotes", "quotes", "EDUARDO MANZANARES (VENTAS)")
    assert acotada.startswith("WITH quotes AS (SELECT * FROM public.quotes")
    assert "EDUARDO MANZANARES (VENTAS)" in acotada


# ----------------------------------------------------------------------
# El nodo: lo que de verdad llega a la base
# ----------------------------------------------------------------------


def test_sin_hoja_el_sql_llega_a_la_base_tal_cual():
    """Quien no está acotado —ADMIN— sigue leyendo la tabla entera."""
    base = BaseFalsa()
    ag.nodo_ejecutar_sql({"sql": "SELECT COUNT(*) FROM tasks"}, base, TASKS)
    assert "WITH tasks AS" not in base.ejecutados[0]


def test_con_hoja_la_base_recibe_la_consulta_acotada():
    base = BaseFalsa()
    ag.nodo_ejecutar_sql({"sql": "SELECT COUNT(*) FROM tasks"}, base, TASKS, hoja=HOJA)
    assert "WITH tasks AS" in base.ejecutados[0]
    assert f"source_sheet = '{HOJA}'" in base.ejecutados[0]


def test_el_techo_de_filas_sigue_puesto_sobre_la_consulta_acotada():
    base = BaseFalsa()
    ag.nodo_ejecutar_sql({"sql": "SELECT * FROM tasks"}, base, TASKS, hoja=HOJA)
    ejecutado = base.ejecutados[0]
    assert "resultado_acotado" in ejecutado
    assert f"LIMIT {ag.TECHO_FILAS}" in ejecutado


def test_un_group_by_del_modelo_tambien_queda_acotado():
    """
    La forma que el modelo elige para las preguntas agregadas. Si el acotado
    fuera un `WHERE` pegado al final, aquí se rompería o contaría de más.
    """
    base = BaseFalsa()
    sql = "SELECT departamento, COUNT(*) FROM tasks GROUP BY departamento ORDER BY 2 DESC"
    ag.nodo_ejecutar_sql({"sql": sql}, base, TASKS, hoja=HOJA)
    assert "WITH tasks AS" in base.ejecutados[0]
    assert "GROUP BY departamento" in base.ejecutados[0]


def test_un_alias_de_tabla_sigue_funcionando():
    """
    `FROM tasks t` con un `WHERE` reescrito a mano habría dado un SQL inválido.
    Con el CTE el alias no estorba, porque el cuerpo no se toca.
    """
    base = BaseFalsa()
    ag.nodo_ejecutar_sql({"sql": "SELECT t.folio FROM tasks t"}, base, TASKS, hoja=HOJA)
    assert "FROM tasks t" in base.ejecutados[0]


def test_una_consulta_que_se_llama_igual_que_la_tabla_se_rechaza():
    """
    Si el modelo define `WITH tasks AS (...)`, su CTE taparía al del acotado y
    la consulta leería la tabla entera.

    Ya lo rechaza `validar_sql`, y por un camino que no es evidente:
    `tablas_referenciadas` resta los nombres de CTE, así que una consulta cuyo
    único `FROM` apunta a un CTE llamado como la tabla se queda sin ninguna
    tabla declarada. Se escribió una guarda aparte para este caso y resultó ser
    código inalcanzable; se quitó, y esta prueba es lo que sostiene esa
    decisión: **si alguien cambia esa resta, esto se pone en rojo** y el acotado
    vuelve a ser esquivable.

    Por eso el mensaje se comprueba y no solo el bloqueo: con un `assert
    "BLOQUEO" in error` a secas, esta prueba pasaba por la razón equivocada y
    la guarda muerta parecía viva.
    """
    base = BaseFalsa()
    sql = "WITH tasks AS (SELECT * FROM tasks) SELECT COUNT(*) FROM tasks"
    salida = ag.nodo_ejecutar_sql({"sql": sql}, base, TASKS, hoja=HOJA)
    assert base.ejecutados == []
    assert salida["error"] == "BLOQUEO DE SEGURIDAD: la consulta no declara de qué tabla lee."


def test_una_tabla_calificada_a_mano_ya_estaba_bloqueada():
    """
    `FROM public.tasks` esquivaría el CTE. La lista blanca de tablas ya lo
    rechazaba antes de esta función; esta prueba fija esa garantía, porque de
    ella depende que el acotado no se pueda rodear.
    """
    base = BaseFalsa()
    salida = ag.nodo_ejecutar_sql(
        {"sql": "SELECT COUNT(*) FROM public.tasks"}, base, TASKS, hoja=HOJA)
    assert base.ejecutados == []
    assert "BLOQUEO DE SEGURIDAD" in salida["error"]


# ----------------------------------------------------------------------
# `ejecutar`: lo que ve quien pregunta
# ----------------------------------------------------------------------


def test_la_respuesta_dice_con_que_hoja_se_contesto():
    """
    Sin esto, "tienes 3 pendientes" y "hay 3 en toda la empresa" se leen igual.
    """
    base = BaseFalsa()
    salida = ag.ejecutar("cuántas tengo", TASKS,
                         llm=LLMFalso(["SELECT COUNT(*) FROM tasks", "Tienes 3."]),
                         ejecutar_sql=base, hoja=HOJA)
    assert salida["success"] is True
    assert salida["alcance"] == HOJA


def test_se_devuelve_el_sql_que_de_verdad_se_ejecuto():
    """
    El panel enseña el SQL para que se pueda comprobar de dónde salió el número.
    Enseñar el del modelo y ejecutar otro convierte esa garantía en un adorno.
    """
    base = BaseFalsa()
    salida = ag.ejecutar("cuántas tengo", TASKS,
                         llm=LLMFalso(["SELECT COUNT(*) FROM tasks", "Tienes 3."]),
                         ejecutar_sql=base, hoja=HOJA)
    assert "WITH tasks AS" in salida["sql_ejecutado"]
    assert salida["sql"] == "SELECT COUNT(*) FROM tasks"


def test_sin_acotar_no_se_inventa_un_alcance():
    base = BaseFalsa()
    salida = ag.ejecutar("cuántas hay", TASKS,
                         llm=LLMFalso(["SELECT COUNT(*) FROM tasks", "Hay 3."]),
                         ejecutar_sql=base)
    assert salida["alcance"] == ""


# ----------------------------------------------------------------------
# Qué hoja le toca a cada quien
# ----------------------------------------------------------------------


def test_la_hoja_de_cotizaciones_de_un_vendedor_lleva_el_sufijo():
    assert organigrama.hoja_de_cotizaciones("EDUARDO_MANZANARES") == "EDUARDO MANZANARES (VENTAS)"


def test_antonia_tiene_la_tabla_maestra_y_no_una_con_sufijo():
    """
    `ANTONIA_VENTAS` es el core de ventas, no el tracker de una persona
    (AGENTS.md §3). Darle "ANTONIA PINEDA LOPEZ (VENTAS)" la dejaría
    preguntando contra una partición vacía.
    """
    assert organigrama.hoja_de_cotizaciones("ANTONIA_VENTAS") == "ANTONIA_VENTAS"


def test_quien_no_vende_no_tiene_hoja_de_cotizaciones():
    """
    Cadena vacía, no el nombre de su tracker: devolverlo acotaría `quotes` por
    una hoja que no existe ahí y respondería siempre cero, que se lee como "no
    tengo cotizaciones" en vez de como "esta pregunta no es para ti".
    """
    assert organigrama.hoja_de_cotizaciones("JUANY_RODRIGUEZ") == ""


def test_una_cuenta_desconocida_no_tiene_hojas():
    assert organigrama.hoja_de_cotizaciones("NO_EXISTE") == ""


# ----------------------------------------------------------------------
# Quién ve el módulo ahora
# ----------------------------------------------------------------------


def test_el_agente_ahora_lo_ve_quien_tiene_tracker_propio():
    from api.main import _ve_agente_sql

    assert _ve_agente_sql("STAFF_USER", "EDUARDO_MANZANARES") is True


def test_el_admin_lo_sigue_viendo():
    from api.main import _ve_agente_sql

    assert _ve_agente_sql("ADMIN", "LUIS_CARLOS") is True


def test_una_cuenta_de_control_sin_tracker_propio_no_lo_ve():
    """
    `PREWORK_ORDER` no es una persona con hoja: no hay "sus" datos que acotar,
    así que verlo sería verlo todo.
    """
    from api.main import _ve_agente_sql

    assert _ve_agente_sql("WORKORDER_USER", "PREWORK_ORDER") is False


def test_el_admin_no_queda_acotado():
    from api.main import _alcance_del_agente

    assert _alcance_del_agente("ADMIN", "LUIS_CARLOS", "tasks") == ""


def test_la_bandera_explicita_sigue_sin_acotar():
    """ANTONIO_SALAZAR la lleva desde 2026-08-22 y su trabajo es ver el total."""
    from api.main import _alcance_del_agente

    assert _alcance_del_agente("STAFF_USER", "ANTONIO_SALAZAR", "tasks") == ""


def test_un_ejecutivo_queda_acotado_a_su_hoja():
    from api.main import _alcance_del_agente

    assert _alcance_del_agente("STAFF_USER", "EDUARDO_MANZANARES", "tasks") == "EDUARDO MANZANARES"


def test_un_ejecutivo_preguntando_por_cotizaciones_va_a_su_tabla_de_ventas():
    from api.main import _alcance_del_agente

    assert (_alcance_del_agente("STAFF_USER", "EDUARDO_MANZANARES", "quotes")
            == "EDUARDO MANZANARES (VENTAS)")


# ----------------------------------------------------------------------
# La ruta
# ----------------------------------------------------------------------


def test_la_ruta_acota_por_la_cuenta_que_recibe(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    base = BaseFalsa()
    monkeypatch.setattr(ag, "ejecutor_disponible", lambda: base)
    monkeypatch.setattr(ag, "llm_disponible",
                        lambda: LLMFalso(["SELECT COUNT(*) FROM tasks", "Tienes 3."]))

    cuerpo = TestClient(app).post("/api/agente/consulta", json={
        "pregunta": "¿cuántas tengo pendientes?",
        "esquema": "tasks",
        "cuenta": "EDUARDO_MANZANARES",
        "role": "STAFF_USER",
    }).json()

    assert cuerpo["success"] is True
    assert cuerpo["alcance"] == "EDUARDO MANZANARES"
    assert "source_sheet = 'EDUARDO MANZANARES'" in base.ejecutados[0]


def test_la_ruta_sin_cuenta_se_comporta_como_antes(monkeypatch):
    """
    El contrato viejo sigue en pie: sin `cuenta` no se acota. Es lo que hoy
    usan ADMIN y ANTONIO_SALAZAR, y romperlo dejaría el módulo sin sus dos
    únicos usuarios actuales.
    """
    from fastapi.testclient import TestClient

    from api.main import app

    base = BaseFalsa()
    monkeypatch.setattr(ag, "ejecutor_disponible", lambda: base)
    monkeypatch.setattr(ag, "llm_disponible",
                        lambda: LLMFalso(["SELECT COUNT(*) FROM tasks", "Hay 3."]))

    cuerpo = TestClient(app).post("/api/agente/consulta",
                                  json={"pregunta": "¿cuántas hay?"}).json()

    assert cuerpo["alcance"] == ""
    assert "WITH tasks AS" not in base.ejecutados[0]


def test_un_vendedor_sin_tabla_de_cotizaciones_recibe_un_aviso_y_no_la_tabla_entera(monkeypatch):
    """
    **Falla cerrado.** Si no se le encuentra hoja a quien pregunta, la salida
    segura es no responder, no responder con el trabajo de toda la empresa.
    """
    from fastapi.testclient import TestClient

    from api.main import app

    llamadas = []
    monkeypatch.setattr(ag, "ejecutor_disponible", lambda: BaseFalsa())
    monkeypatch.setattr(ag, "llm_disponible", lambda: llamadas.append(1))

    cuerpo = TestClient(app).post("/api/agente/consulta", json={
        "pregunta": "¿cuántas cotizaciones tengo?",
        "esquema": "quotes",
        "cuenta": "JUANY_RODRIGUEZ",
        "role": "STAFF_USER",
    }).json()

    assert cuerpo["success"] is False
    assert "cotizaciones" in cuerpo["message"].lower()
    assert llamadas == []
