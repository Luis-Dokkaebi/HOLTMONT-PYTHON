"""
El agente de consultas en lenguaje natural (`api/services/agente_sql.py`).

Lo que se prueba aquí **no** es que el modelo escriba buen SQL —eso no se puede
probar—, sino las tres cosas de las que depende que el módulo sea seguro y
honesto:

1. **Que nunca se ejecute lo que no debe.** Los guardarraíles son funciones
   puras y se ejercen una por una, incluidos los casos que un regex ingenuo
   falla: un `;` dentro de un literal, un `--` dentro de un `ILIKE`, un CTE
   cuyo alias parece una tabla prohibida.
2. **Que el grafo elija bien la rama.** Que reintente cuando la base falla, que
   pare a los tres intentos y que sin LLM diga que falta la clave en vez de
   inventar una respuesta.
3. **Que ningún correo salga a una dirección que no esté en la lista blanca.**

Todos los dobles van en las **fronteras** —el LLM y la ejecución del SQL— y
ninguno en el núcleo. El motor en memoria no interpreta SQL a propósito
(`backend/core/engines/memoria.py`): un intérprete de juguete convertiría estas
pruebas en una medición de ese intérprete.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import agente_sql as ag  # noqa: E402
from api.services import agente_sql_correo as correos  # noqa: E402
from api.services import agente_sql_esquemas as esquemas  # noqa: E402

TASKS = esquemas.ESQUEMAS["tasks"]
QUOTES = esquemas.ESQUEMAS["quotes"]
SOLO_TASKS = frozenset({"tasks"})


class LLMFalso:
    """
    Doble del modelo: devuelve las respuestas de una lista, en orden.

    Guarda los prompts recibidos para poder comprobar que el error de la base
    llega de verdad al reintento; sin eso, "reintenta" y "reintenta con el error
    a la vista" son indistinguibles y solo la segunda sirve de algo.
    """

    def __init__(self, respuestas: List[str]):
        self.respuestas = list(respuestas)
        self.prompts: List[str] = []

    def invoke(self, mensajes: Any) -> Any:
        if isinstance(mensajes, list):
            self.prompts.append("\n".join(str(getattr(m, "content", m)) for m in mensajes))
        else:
            self.prompts.append(str(mensajes))

        contenido = self.respuestas.pop(0) if self.respuestas else ""

        class _Respuesta:
            content = contenido

        return _Respuesta()


# ======================================================================
# 1. El escáner léxico
# ======================================================================


def test_el_escaner_no_destroza_un_literal_con_dos_guiones():
    """
    `re.sub(r"--[^\\n]*", ...)` se comería medio `WHERE` y dejaría SQL roto.

    Es el bug que motivó cambiar las dos expresiones regulares por un escáner:
    'pre--fabricado' es un concepto plausible en una constructora.
    """
    sql = "SELECT * FROM tasks WHERE concepto ILIKE '%pre--fabricado%'"
    assert ag.sin_comentarios(sql) == sql


def test_el_escaner_si_quita_un_comentario_de_verdad():
    ejecutable = ag.sin_comentarios("SELECT 1 -- esto sobra\nFROM tasks")
    assert "esto sobra" not in ejecutable
    assert "FROM tasks" in ejecutable


def test_el_escaner_quita_comentarios_de_bloque():
    assert "oculto" not in ag.sin_comentarios("SELECT /* oculto */ 1 FROM tasks")


def test_el_texto_analizable_vacia_los_literales():
    """El contenido del literal desaparece; el resto de la consulta no."""
    analizable = ag.para_analisis("SELECT * FROM tasks WHERE status ILIKE '%DROP%'")
    assert "DROP" not in analizable
    assert "FROM tasks" in analizable


def test_el_escaner_respeta_la_comilla_escapada():
    sql = "SELECT * FROM tasks WHERE concepto = 'O''Brien'"
    assert ag.sin_comentarios(sql) == sql
    # Y el literal entero se vació: nada de su contenido llega al análisis.
    assert "Brien" not in ag.para_analisis(sql)


# ======================================================================
# 2. Los guardarraíles
# ======================================================================


def test_una_consulta_normal_pasa():
    assert ag.validar_sql("SELECT departamento, COUNT(*) FROM tasks GROUP BY 1",
                          SOLO_TASKS) == ""


def test_un_cte_pasa_y_su_alias_no_cuenta_como_tabla():
    """
    Sin descontar los alias de `WITH`, la lista blanca rechazaría toda consulta
    agregada — que es justo la forma que el modelo elige para "cuántas por
    departamento".
    """
    sql = ("WITH resumen AS (SELECT departamento, COUNT(*) AS n FROM tasks "
           "GROUP BY 1) SELECT * FROM resumen ORDER BY n DESC")
    assert ag.validar_sql(sql, SOLO_TASKS) == ""


@pytest.mark.parametrize("sql", [
    "DELETE FROM tasks",
    "UPDATE tasks SET avance = 0",
    "INSERT INTO tasks (folio) VALUES ('x')",
    "DROP TABLE tasks",
    "TRUNCATE tasks",
    "ALTER TABLE tasks ADD COLUMN x text",
])
def test_las_sentencias_que_escriben_se_bloquean(sql):
    assert "BLOQUEO" in ag.validar_sql(sql, SOLO_TASKS)


def test_una_segunda_sentencia_se_bloquea():
    motivo = ag.validar_sql("SELECT * FROM tasks; DROP TABLE tasks", SOLO_TASKS)
    assert "más de una sentencia" in motivo


def test_el_punto_y_coma_final_no_se_confunde_con_una_segunda_sentencia():
    assert ag.validar_sql("SELECT * FROM tasks;", SOLO_TASKS) == ""


def test_un_punto_y_coma_dentro_de_un_literal_no_bloquea():
    """
    Sin vaciar los literales, `'a;b'` parece una segunda sentencia y la
    consulta se rechaza sin motivo. Falso positivo, pero rompe el módulo igual.
    """
    assert ag.validar_sql(
        "SELECT * FROM tasks WHERE comentarios ILIKE '%a;b%'", SOLO_TASKS) == ""


def test_una_palabra_prohibida_dentro_de_un_literal_no_bloquea():
    """`DO` está en la lista de verbos y aparece dentro de cualquier `'%DO%'`."""
    assert ag.validar_sql(
        "SELECT * FROM tasks WHERE status ILIKE '%TERMINADO%'", SOLO_TASKS) == ""


def test_un_verbo_escondido_tras_un_comentario_de_linea_no_se_cuela():
    """
    `SELECT 1 -- \\n; DROP TABLE tasks` es el ataque clásico contra un validador
    que mira la cadena cruda. Aquí el comentario se quita ANTES de revisar, así
    que el `DROP` queda a la vista y se bloquea.
    """
    assert "BLOQUEO" in ag.validar_sql(
        "SELECT 1 FROM tasks -- inocente\n; DROP TABLE tasks", SOLO_TASKS)


def test_no_se_puede_leer_una_tabla_ajena():
    """
    El guardarraíl del notebook dejaba pasar esto: comprobaba que fuera un
    SELECT, no QUÉ se leía.
    """
    motivo = ag.validar_sql("SELECT * FROM auth.users", SOLO_TASKS)
    assert "solo se pueden leer las tablas" in motivo


def test_no_se_puede_leer_quotes_desde_el_esquema_de_tasks():
    """Cada consulta se acota a SU tabla, no al conjunto de las permitidas."""
    assert "BLOQUEO" in ag.validar_sql("SELECT * FROM quotes", SOLO_TASKS)
    assert ag.validar_sql("SELECT * FROM quotes", frozenset({"quotes"})) == ""


def test_no_se_pueden_leer_los_catalogos_del_servidor():
    assert "catálogos" in ag.validar_sql(
        "SELECT * FROM pg_shadow", SOLO_TASKS)


def test_un_join_a_una_tabla_prohibida_se_bloquea():
    sql = "SELECT * FROM tasks JOIN profiles ON tasks.assignee_id = profiles.id"
    assert "BLOQUEO" in ag.validar_sql(sql, SOLO_TASKS)


def test_una_consulta_sin_from_se_bloquea():
    """
    `SELECT 1` no lee nada, pero tampoco responde nada. Se rechaza para que la
    lista blanca no tenga un hueco por el que pasen las funciones del servidor.
    """
    assert "BLOQUEO" in ag.validar_sql("SELECT 1", SOLO_TASKS)


def test_una_consulta_vacia_se_bloquea():
    assert "BLOQUEO" in ag.validar_sql("   ", SOLO_TASKS)


# ======================================================================
# 3. El techo de filas
# ======================================================================


def test_acotar_envuelve_y_pone_el_limite():
    acotada = ag.acotar("SELECT * FROM tasks", techo=40)
    assert acotada.startswith("SELECT * FROM (")
    assert acotada.rstrip().endswith("LIMIT 40")


def test_acotar_conserva_los_literales_del_filtro():
    """
    Acotar el texto *analizable* ejecutaría la consulta con los `ILIKE`
    vaciados: devolvería la tabla entera en vez de las filas filtradas, y nadie
    lo notaría porque la respuesta seguiría teniendo la forma correcta.
    """
    acotada = ag.acotar("SELECT * FROM tasks WHERE departamento ILIKE '%HVAC%'")
    assert "%HVAC%" in acotada


def test_acotar_quita_el_punto_y_coma_final():
    """Un `;` dentro del paréntesis es un error de sintaxis en Postgres."""
    assert ";" not in ag.acotar("SELECT * FROM tasks;")


def test_acotar_no_rompe_una_consulta_que_ya_traia_su_limit():
    acotada = ag.acotar("SELECT * FROM tasks ORDER BY folio LIMIT 5")
    assert "LIMIT 5" in acotada and acotada.rstrip().endswith("LIMIT 40")


# ======================================================================
# 4. La extracción del SQL de la respuesta del modelo
# ======================================================================


def test_se_extrae_el_sql_del_bloque_markdown():
    assert ag.extraer_sql("```sql\nSELECT 1 FROM tasks\n```") == "SELECT 1 FROM tasks"


def test_sin_bloque_markdown_se_toma_el_texto_pelado():
    assert ag.extraer_sql("  SELECT 1 FROM tasks  ") == "SELECT 1 FROM tasks"


# ======================================================================
# 5. El grafo
# ======================================================================


def test_una_consulta_correcta_responde_con_el_sql_a_la_vista():
    """
    El SQL viaja en la respuesta a propósito: sin él, una cifra inventada por el
    modelo es indistinguible de una contada por la base.
    """
    llm = LLMFalso(["```sql\nSELECT departamento FROM tasks\n```", "Hay 3 tareas."])
    filas = [{"departamento": "HVAC"}]

    resultado = ag.ejecutar("¿cuántas tareas?", TASKS, llm=llm,
                            ejecutar_sql=lambda sql: filas)

    assert resultado["success"] is True
    assert resultado["respuesta"] == "Hay 3 tareas."
    assert resultado["sql"] == "SELECT departamento FROM tasks"
    assert resultado["filas"] == filas
    assert resultado["intentos"] == 1


def test_el_sql_que_llega_a_la_base_viene_acotado():
    """El límite viaja DENTRO del SQL, no se aplica después en memoria."""
    ejecutados: List[str] = []
    llm = LLMFalso(["```sql\nSELECT * FROM tasks\n```", "ok"])

    ag.ejecutar("todo", TASKS, llm=llm,
                ejecutar_sql=lambda sql: ejecutados.append(sql) or [])

    assert ejecutados[0].rstrip().endswith(f"LIMIT {ag.TECHO_FILAS}")


def test_un_error_de_la_base_reintenta_con_el_error_a_la_vista():
    """
    El bucle de auto-corrección solo sirve si el modelo VE qué falló. Se
    comprueba que el texto del error aparece en el prompt del segundo intento.
    """
    llm = LLMFalso([
        "```sql\nSELECT columna_que_no_existe FROM tasks\n```",
        "```sql\nSELECT folio FROM tasks\n```",
        "Listo.",
    ])
    intentos = {"n": 0}

    def ejecutar_sql(sql: str) -> List[Dict[str, Any]]:
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise RuntimeError('column "columna_que_no_existe" does not exist')
        return [{"folio": "AV-1"}]

    resultado = ag.ejecutar("dame folios", TASKS, llm=llm, ejecutar_sql=ejecutar_sql)

    assert resultado["success"] is True
    assert resultado["intentos"] == 2
    assert "columna_que_no_existe" in llm.prompts[1]


def test_el_bucle_se_detiene_a_los_tres_intentos():
    """
    Sin tope, un modelo que repite el mismo fallo gasta llamadas para siempre.
    Al tercero se rinde y explica, no se cuelga.
    """
    llm = LLMFalso(["```sql\nSELECT malo FROM tasks\n```"] * 3 + ["No se pudo."])

    def siempre_falla(sql: str):
        raise RuntimeError("boom")

    resultado = ag.ejecutar("x", TASKS, llm=llm, ejecutar_sql=siempre_falla)

    assert resultado["success"] is False
    assert resultado["intentos"] == ag.MAX_INTENTOS
    assert resultado["respuesta"] == "No se pudo."


def test_un_sql_bloqueado_nunca_llega_a_la_base():
    """
    La comprobación más importante del archivo: que el guardarraíl corte ANTES
    de ejecutar, no que solo marque el resultado como fallido.
    """
    llamadas: List[str] = []
    llm = LLMFalso(["```sql\nDROP TABLE tasks\n```"] * 3 + ["No se pudo."])

    resultado = ag.ejecutar("borra todo", TASKS, llm=llm,
                            ejecutar_sql=lambda sql: llamadas.append(sql) or [])

    assert llamadas == []
    assert resultado["success"] is False


def test_sin_llm_no_se_inventa_una_respuesta():
    """
    Una respuesta fabricada sin modelo es indistinguible de una real para quien
    la lee, y de aquí salen decisiones sobre tareas y cotizaciones reales.
    """
    resultado = ag.ejecutar("¿cuántas?", TASKS, llm=None, ejecutar_sql=lambda s: [])
    assert resultado["success"] is False
    assert "GROQ_API_KEY" in resultado["message"]


def test_sin_ejecutor_se_dice_que_falta_la_base():
    llm = LLMFalso(["```sql\nSELECT folio FROM tasks\n```"] * 3 + ["Sin base."])
    resultado = ag.ejecutar("x", TASKS, llm=llm, ejecutar_sql=None)
    assert resultado["success"] is False


def test_una_pregunta_vacia_no_gasta_una_llamada_al_modelo():
    llm = LLMFalso(["no debería usarse"])
    assert ag.ejecutar("   ", TASKS, llm=llm)["success"] is False
    assert llm.prompts == []


def test_si_el_modelo_falla_al_redactar_no_se_lanza():
    """Un fallo de red al final no puede tumbar una consulta que ya se ejecutó."""
    class LLMQueFallaAlFinal(LLMFalso):
        def invoke(self, mensajes):
            if len(self.prompts) >= 1:
                self.prompts.append("fallo")
                raise RuntimeError("sin red")
            return super().invoke(mensajes)

    llm = LLMQueFallaAlFinal(["```sql\nSELECT folio FROM tasks\n```"])
    resultado = ag.ejecutar("x", TASKS, llm=llm, ejecutar_sql=lambda s: [{"folio": "1"}])
    assert "error técnico" in resultado["respuesta"]


def test_las_filas_se_formatean_con_el_nombre_de_la_columna():
    """
    El notebook mandaba tuplas anónimas: `('HVAC', 12)` obliga al modelo a
    adivinar qué es cada valor, y con dos columnas del mismo tipo adivina mal.
    """
    texto = ag.formatear_filas([{"departamento": "HVAC", "n": 12}])
    assert "departamento=" in texto and "n=" in texto


def test_sin_filas_se_dice_que_no_hubo_resultados():
    assert ag.formatear_filas([]) == "(sin resultados)"


# ======================================================================
# 6. Los esquemas
# ======================================================================


def test_el_prompt_lista_las_columnas_reales_de_la_tabla():
    """
    El bloque de columnas se genera desde `backend/schemas`, así que si mañana
    cambia el esquema y no el prompt, esta prueba lo dice.
    """
    from backend.schemas.task import TIPOS_REALES

    prompt = TASKS.prompt_sistema()
    for columna in TIPOS_REALES:
        assert columna in prompt


def test_el_prompt_declara_los_tipos_reales_y_no_los_del_notebook():
    """
    El notebook le decía al modelo que las fechas eran TEXT y que las comparara
    como cadenas. En `tasks` son `date`. Seguir esa instrucción con el esquema
    real produce SQL que falla o, peor, que filtra mal en silencio.
    """
    prompt = TASKS.prompt_sistema()
    assert "fecha_alta (date)" in prompt
    assert "avance (numeric)" in prompt
    assert "hora_alta (time without time zone)" in prompt


def test_el_prompt_de_quotes_avisa_de_la_clave_compuesta():
    """
    La clave de `quotes` es (folio, source_sheet): la misma cotización vive en
    dos filas y un `COUNT(*)` ingenuo la cuenta dos veces.
    """
    assert "COUNT(DISTINCT folio)" in QUOTES.prompt_sistema()


def test_cada_esquema_solo_se_deja_leer_a_si_mismo():
    assert esquemas.TABLAS_PERMITIDAS == frozenset({"tasks", "quotes"})


def test_un_esquema_inexistente_devuelve_none_y_no_lanza():
    assert esquemas.esquema("tasks_rows_sql") is None
    assert esquemas.esquema("") is None
    assert esquemas.esquema("TASKS").clave == "tasks"


# ======================================================================
# 7. Los motores: quién puede ejecutar SQL crudo y quién no
# ======================================================================


def test_el_motor_en_memoria_no_ejecuta_sql_y_lo_dice():
    """
    No es una carencia: un intérprete de SQL de juguete haría que las pruebas
    del agente midieran ese intérprete y no Postgres (Directiva Cero, §2).
    """
    from backend.core.engines.memoria import MemoryEngine
    from backend.core.errors import ErrorDeMotor

    with pytest.raises(ErrorDeMotor, match="no ejecuta SQL"):
        MemoryEngine().consulta_cruda("SELECT 1")


def test_el_motor_postgrest_ejecuta_por_rpc():
    """
    CAMBIO DE CONTRATO (justificado en el PR): antes esto lanzaba "PostgREST no
    puede ejecutar SQL directo". Era cierto para SQL arbitrario, pero PostgREST
    sí puede **llamar funciones**, y `docs/DDL_AGENTE_SQL.sql` crea una que
    ejecuta el SELECT. Se conserva la prueba con la aserción invertida en vez de
    borrarla, para que quede escrito qué cambió y por qué.
    """
    from backend.core.engines import postgrest as pg

    motor = pg.PostgrestEngine("https://ejemplo.supabase.co", "clave-de-prueba")
    llamadas = []
    motor._pedir = lambda metodo, ruta, cuerpo=None, prefer="": (
        llamadas.append((metodo, ruta, cuerpo)) or [{"n": 7}])

    assert motor.consulta_cruda("SELECT count(*) AS n FROM tasks") == [{"n": 7}]
    assert llamadas == [("POST", f"rpc/{pg.FUNCION_AGENTE}",
                         {"consulta": "SELECT count(*) AS n FROM tasks"})]


def test_si_falta_la_funcion_rpc_se_dice_que_ejecutar():
    """
    El error tiene que nombrar el archivo. "PGRST202: function not found" es
    verdad y no le sirve a nadie para arreglarlo.
    """
    from backend.core.engines import postgrest as pg
    from backend.core.errors import ErrorDeMotor

    motor = pg.PostgrestEngine("https://ejemplo.supabase.co", "clave")

    def _no_existe(metodo, ruta, cuerpo=None, prefer=""):
        raise ErrorDeMotor("PostgREST POST falló", codigo="PGRST202", estado=404)

    motor._pedir = _no_existe

    with pytest.raises(pg.ErrorDeConfiguracion, match="DDL_AGENTE_SQL.sql"):
        motor.consulta_cruda("SELECT 1")


def test_si_la_clave_no_tiene_permiso_se_dice_cual_usar():
    """
    El DDL concede la función solo a `service_role`. Con la clave publicable el
    404/403 es indistinguible de "la función no existe" si no se traduce.
    """
    from backend.core.engines import postgrest as pg
    from backend.core.errors import ErrorDeMotor

    motor = pg.PostgrestEngine("https://ejemplo.supabase.co", "clave")

    def _sin_permiso(metodo, ruta, cuerpo=None, prefer=""):
        raise ErrorDeMotor("PostgREST POST falló", codigo="42501", estado=403)

    motor._pedir = _sin_permiso

    with pytest.raises(pg.ErrorDeConfiguracion, match="clave de servicio"):
        motor.consulta_cruda("SELECT 1")


def test_un_error_de_sql_por_rpc_no_se_disfraza_de_configuracion():
    """
    Un `relation "tasks" does not exist` SÍ lo puede arreglar el modelo
    reescribiendo. Traducirlo a error de configuración cortaría el bucle de
    auto-corrección justo cuando sirve.

    CORRECCIÓN MEDIDA: esta prueba fingía `estado=400` para un `42P01`, y ese
    404/400 no es un detalle. PostgREST **no** devuelve 400 para
    `undefined_table`: devuelve **404** (`pgErrorStatus` en `PostgREST/Error.hs`
    mapea `42P01` y `42883` a `status404`). Con el 400 inventado la prueba
    pasaba y el bug seguía vivo en producción; ver
    `test_una_tabla_que_no_existe_no_se_reporta_como_funcion_rpc_ausente`.
    """
    from backend.core.engines import postgrest as pg
    from backend.core.errors import ErrorDeMotor

    motor = pg.PostgrestEngine("https://ejemplo.supabase.co", "clave")

    def _sql_malo(metodo, ruta, cuerpo=None, prefer=""):
        raise ErrorDeMotor('relation "tsaks" does not exist',
                           codigo="42P01", estado=404)

    motor._pedir = _sql_malo

    with pytest.raises(ErrorDeMotor) as capturado:
        motor.consulta_cruda("SELECT * FROM tsaks")
    assert not isinstance(capturado.value, pg.ErrorDeConfiguracion)


def test_una_tabla_que_no_existe_no_se_reporta_como_funcion_rpc_ausente():
    """
    El fallo que se midió en producción, reproducido.

    La función RPC estaba instalada y respondía en el SQL Editor, pero la
    interfaz insistía con «La función agente_sql_consulta no existe en la base.
    Ejecuta docs/DDL_AGENTE_SQL.sql». El motivo: la consulta de dentro nombraba
    una tabla que no existe, PostgREST devuelve **404** para `42P01`, y la
    traducción miraba solo el estado. Un mensaje que manda ejecutar un archivo
    ya ejecutado deja al usuario sin salida.

    El error tiene que llegar con el nombre de la relación, que es lo único que
    permite arreglarlo (y lo que el bucle de auto-corrección le enseña al
    modelo en el siguiente intento).
    """
    from backend.core.engines import postgrest as pg
    from backend.core.errors import ErrorDeMotor

    motor = pg.PostgrestEngine("https://ejemplo.supabase.co", "clave")
    cuerpo = ('{"code":"42P01","details":null,"hint":null,'
              '"message":"relation \\"tasks\\" does not exist"}')

    def _tabla_ausente(metodo, ruta, cuerpo_=None, prefer=""):
        raise ErrorDeMotor(f"PostgREST POST {ruta} respondió 404",
                           codigo="42P01", detalle=cuerpo, estado=404)

    motor._pedir = _tabla_ausente

    with pytest.raises(ErrorDeMotor) as capturado:
        motor.consulta_cruda("SELECT count(*) AS n FROM tasks")
    assert not isinstance(capturado.value, pg.ErrorDeConfiguracion)
    assert "DDL_AGENTE_SQL.sql" not in str(capturado.value)
    assert "42P01" in capturado.value.codigo


def test_una_funcion_que_invento_el_modelo_tampoco_se_disfraza():
    """
    `42883` también vuelve con 404, y casi siempre es del SQL de dentro.

    Si el modelo escribe `select fecha_bonita(fecha_alta) from tasks`, eso lo
    arregla reescribiendo la consulta. Cortar el bucle ahí y mandar ejecutar un
    DDL es mandar al usuario a arreglar lo que no está roto.
    """
    from backend.core.engines import postgrest as pg
    from backend.core.errors import ErrorDeMotor

    motor = pg.PostgrestEngine("https://ejemplo.supabase.co", "clave")

    def _funcion_inventada(metodo, ruta, cuerpo=None, prefer=""):
        raise ErrorDeMotor(f"PostgREST POST {ruta} respondió 404",
                           codigo="42883",
                           detalle='{"code":"42883","message":"function '
                                   'fecha_bonita(date) does not exist"}',
                           estado=404)

    motor._pedir = _funcion_inventada

    with pytest.raises(ErrorDeMotor) as capturado:
        motor.consulta_cruda("SELECT fecha_bonita(fecha_alta) FROM tasks")
    assert not isinstance(capturado.value, pg.ErrorDeConfiguracion)


def test_un_42883_que_nombra_la_funcion_del_agente_si_es_configuracion():
    """
    La otra cara: si la que no existe es **nuestra** función RPC, el consejo de
    ejecutar el DDL es exactamente el correcto.

    Pasa cuando la caché de esquema de PostgREST está al día pero la función se
    borró después, o cuando nunca se ejecutó el archivo. Se distingue por el
    nombre en el cuerpo del error, no por el estado, que es el mismo 404.
    """
    from backend.core.engines import postgrest as pg
    from backend.core.errors import ErrorDeMotor

    motor = pg.PostgrestEngine("https://ejemplo.supabase.co", "clave")

    def _sin_funcion(metodo, ruta, cuerpo=None, prefer=""):
        raise ErrorDeMotor(f"PostgREST POST {ruta} respondió 404",
                           codigo="42883",
                           detalle='{"code":"42883","message":"function '
                                   'public.agente_sql_consulta(text) does not '
                                   'exist"}',
                           estado=404)

    motor._pedir = _sin_funcion

    with pytest.raises(pg.ErrorDeConfiguracion, match="DDL_AGENTE_SQL.sql"):
        motor.consulta_cruda("SELECT 1")


def test_un_404_sin_cuerpo_sigue_siendo_la_ruta_rpc_que_falta():
    """
    Un 404 sin `code` es PostgREST diciendo que la ruta no está: ahí sí falta
    ejecutar el archivo. Es el caso que la traducción original acertaba, y no
    puede perderse al arreglar los otros.
    """
    from backend.core.engines import postgrest as pg
    from backend.core.errors import ErrorDeMotor

    motor = pg.PostgrestEngine("https://ejemplo.supabase.co", "clave")

    def _ruta_ausente(metodo, ruta, cuerpo=None, prefer=""):
        raise ErrorDeMotor(f"PostgREST POST {ruta} respondió 404", estado=404)

    motor._pedir = _ruta_ausente

    with pytest.raises(pg.ErrorDeConfiguracion, match="DDL_AGENTE_SQL.sql"):
        motor.consulta_cruda("SELECT 1")


def test_sin_motor_configurado_el_ejecutor_es_none_y_no_lanza(monkeypatch):
    """El módulo se degrada; no tumba la aplicación."""
    for variable in ("DATABASE_URL", "SUPABASE_URL", "SUPABASE_KEY", "BACKEND_ENGINE"):
        monkeypatch.delenv(variable, raising=False)
    assert ag.ejecutor_disponible() is None


def test_sin_clave_de_groq_no_hay_llm(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert ag.llm_disponible() is None


# ======================================================================
# 8. El flujo de correos
# ======================================================================


def test_las_areas_salen_del_json_del_modelo():
    llm = LLMFalso(['["RH", "FINANZAS"]'])
    assert correos.detectar_areas("RH y FINANZAS van tarde", llm) == ["RH", "FINANZAS"]


def test_sin_llm_no_se_detectan_areas_y_no_se_lanza():
    assert correos.detectar_areas("lo que sea", None) == []


def test_una_respuesta_del_modelo_que_no_es_json_no_rompe_nada():
    assert correos.detectar_areas("x", LLMFalso(["lo siento, no puedo"])) == []


def test_siempre_hay_un_borrador_por_area_pedida():
    """
    Si el modelo se salta un área, esa área simplemente no recibiría correo y
    nadie lo notaría: en pantalla una lista incompleta se ve igual que una
    completa. El respaldo cierra ese hueco.
    """
    llm = LLMFalso(['[{"area": "RH", "asunto": "A", "cuerpo": "B"}]'])
    borradores = correos.generar_borradores("p", "r", ["RH", "FINANZAS"], llm)

    assert set(borradores) == {"RH", "FINANZAS"}
    assert borradores["RH"]["cuerpo"] == "B"
    assert "FINANZAS" in borradores["FINANZAS"]["cuerpo"]


def test_el_respaldo_copia_la_respuesta_literal_sin_parafrasearla():
    borradores = correos.generar_borradores("p", "18 tareas abiertas", ["RH"], None)
    assert "18 tareas abiertas" in borradores["RH"]["cuerpo"]


def test_el_nombre_del_area_se_empareja_sin_tildes_ni_mayusculas():
    llm = LLMFalso(['[{"area": "construccion", "asunto": "A", "cuerpo": "B"}]'])
    borradores = correos.generar_borradores("p", "r", ["CONSTRUCCIÓN"], llm)
    assert borradores["CONSTRUCCIÓN"]["cuerpo"] == "B"


def test_un_cambio_solo_toca_el_area_indicada():
    llm = LLMFalso(['{"asunto": "Nuevo", "cuerpo": "Cuerpo nuevo"}'])
    nuevo = correos.aplicar_cambio("RH", {"asunto": "A", "cuerpo": "B"},
                                   "hazlo formal", "datos", llm)
    assert nuevo == {"asunto": "Nuevo", "cuerpo": "Cuerpo nuevo"}


def test_si_el_cambio_falla_se_devuelve_none_y_el_borrador_queda_intacto():
    """
    Sustituir un borrador aprobado por uno a medias es peor que no cambiarlo:
    el usuario ya lo leyó y no lo va a releer.
    """
    assert correos.aplicar_cambio("RH", {"asunto": "A", "cuerpo": "B"},
                                  "cambia", "datos", LLMFalso(["no soy JSON"])) is None
    assert correos.aplicar_cambio("RH", {"asunto": "A", "cuerpo": "B"},
                                  "", "datos", LLMFalso(["{}"])) is None


def test_un_json_incompleto_tampoco_reemplaza_el_borrador():
    llm = LLMFalso(['{"asunto": "Solo asunto"}'])
    assert correos.aplicar_cambio("RH", {"asunto": "A", "cuerpo": "B"},
                                  "x", "d", llm) is None


# --- La lista blanca ---------------------------------------------------


def test_las_cuentas_del_directorio_estan_permitidas():
    assert "jaimeolivo@empresa.com" in correos.destinatarios_permitidos()


def test_una_direccion_de_fuera_no_esta_permitida(monkeypatch):
    monkeypatch.delenv(correos.ENV_DESTINATARIOS, raising=False)
    permitidas, rechazadas = correos.separar_permitidos(["atacante@gmail.com"])
    assert permitidas == []
    assert rechazadas == ["atacante@gmail.com"]


def test_la_variable_de_entorno_amplia_la_lista_blanca(monkeypatch):
    monkeypatch.setenv(correos.ENV_DESTINATARIOS, "externo@proveedor.mx")
    permitidas, rechazadas = correos.separar_permitidos(["externo@proveedor.mx"])
    assert permitidas == ["externo@proveedor.mx"] and rechazadas == []


def test_enviar_a_una_direccion_no_autorizada_no_manda_nada(monkeypatch):
    """
    La prueba que justifica todo el módulo: sin lista blanca, quien tenga el
    agente puede sacar `tasks` y `quotes` a cualquier buzón, firmado con la
    cuenta de la empresa.
    """
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.delenv(correos.ENV_DESTINATARIOS, raising=False)
    enviados: List[Any] = []
    monkeypatch.setattr("api.services.correo.enviar",
                        lambda **kw: enviados.append(kw) or {"success": True})

    resultado = correos.enviar({"RH": {"asunto": "A", "cuerpo": "B"}},
                               {"RH": "atacante@gmail.com"})

    assert resultado["success"] is False
    assert enviados == []
    assert "atacante@gmail.com" in resultado["rechazados"]


def test_una_copia_no_autorizada_tambien_frena_el_envio(monkeypatch):
    """La fuga por CC es igual de fuga que por Para."""
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.delenv(correos.ENV_DESTINATARIOS, raising=False)
    enviados: List[Any] = []
    monkeypatch.setattr("api.services.correo.enviar",
                        lambda **kw: enviados.append(kw) or {"success": True})

    resultado = correos.enviar({"RH": {"asunto": "A", "cuerpo": "B"}},
                               {"RH": "jaimeolivo@empresa.com"},
                               copia=["fuera@gmail.com"])

    assert resultado["success"] is False and enviados == []


def test_un_envio_autorizado_si_llega_al_canal_de_correo(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    enviados: List[Dict[str, Any]] = []
    monkeypatch.setattr("api.services.correo.enviar",
                        lambda **kw: enviados.append(kw) or {"success": True})

    resultado = correos.enviar({"RH": {"asunto": "Reporte", "cuerpo": "Cuerpo"}},
                               {"RH": "jaimeolivo@empresa.com"}, notas="Nota final")

    assert resultado["success"] is True
    assert enviados[0]["destinatarios"] == ["jaimeolivo@empresa.com"]
    assert "Nota final" in enviados[0]["html"]


def test_el_cuerpo_del_correo_va_escapado(monkeypatch):
    """
    El texto lo redacta un modelo a partir de celdas que captura cualquier
    usuario del Tracker. Un `<script>` en `comentarios` no puede llegar como
    marcado al cliente de correo de nadie.
    """
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    enviados: List[Dict[str, Any]] = []
    monkeypatch.setattr("api.services.correo.enviar",
                        lambda **kw: enviados.append(kw) or {"success": True})

    correos.enviar({"RH": {"asunto": "A", "cuerpo": "<script>alert(1)</script>"}},
                   {"RH": "jaimeolivo@empresa.com"})

    assert "<script>" not in enviados[0]["html"]
    assert "&lt;script&gt;" in enviados[0]["html"]


def test_sin_smtp_no_se_reporta_un_envio_que_no_ocurrio(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    resultado = correos.enviar({"RH": {"asunto": "A", "cuerpo": "B"}},
                               {"RH": "jaimeolivo@empresa.com"})
    assert resultado["success"] is False
    assert "SMTP_HOST" in resultado["message"]


def test_un_area_sin_destinatario_se_reporta_y_no_frena_a_las_demas(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.ejemplo.com")
    monkeypatch.setattr("api.services.correo.enviar", lambda **kw: {"success": True})

    resultado = correos.enviar(
        {"RH": {"asunto": "A", "cuerpo": "B"}, "HVAC": {"asunto": "C", "cuerpo": "D"}},
        {"RH": "jaimeolivo@empresa.com"})

    por_area = {e["area"]: e for e in resultado["enviados"]}
    assert por_area["RH"]["success"] is True
    assert por_area["HVAC"]["success"] is False
    assert resultado["success"] is False


@pytest.mark.parametrize("entrada,esperado", [
    ("a@b.com, c@d.com", ["a@b.com", "c@d.com"]),
    ("  a@b.com  ", ["a@b.com"]),
    ("no-es-un-correo", []),
    ("a@b.com, a@b.com", ["a@b.com"]),
    (None, []),
    ([], []),
])
def test_la_limpieza_de_listas_de_correo(entrada, esperado):
    assert correos.limpiar_lista(entrada) == esperado


# ======================================================================
# 9. Los caminos de fallo que quedaban sin ejercer
# ======================================================================


def test_un_identificador_citado_sobrevive_al_escaner():
    """
    `"tasks"` entre comillas dobles es un identificador, no un literal: su
    contenido tiene que llegar entero al análisis, o la lista blanca no vería
    de qué tabla se lee y bloquearía una consulta válida.
    """
    sql = 'SELECT folio FROM "tasks"'
    assert ag.sin_comentarios(sql) == sql
    assert ag.validar_sql(sql, SOLO_TASKS) == ""


def test_un_literal_sin_cerrar_termina_y_se_traga_lo_que_venga_detras():
    """
    El modelo puede devolver SQL truncado. Dos cosas tienen que cumplirse:

    1. El escáner **termina** en vez de recorrer el texto en un bucle infinito.
    2. Todo lo que viene tras la comilla sin cerrar queda DENTRO del literal, así
       que un `DROP` escondido ahí no es una sentencia, es texto.

    La consulta pasa la validación —no hay nada peligroso que ver— y es Postgres
    quien la rechaza por comilla sin terminar. El error vuelve al agente, que
    reintenta. Eso es correcto: el validador no es un analizador sintáctico y no
    debe fingir que lo es.
    """
    sql = "SELECT * FROM tasks WHERE x = 'sin cerrar; DROP TABLE tasks"
    assert ag.validar_sql(sql, SOLO_TASKS) == ""
    assert "DROP" not in ag.para_analisis(sql)


def test_un_comentario_de_bloque_sin_cerrar_tampoco_cuelga():
    """Mismo caso con `/*`: lo que sigue es comentario, no sentencia."""
    sql = "SELECT * FROM tasks /* sin cerrar; DROP TABLE tasks"
    assert ag.validar_sql(sql, SOLO_TASKS) == ""
    assert "DROP" not in ag.para_analisis(sql)


def test_si_el_modelo_falla_al_generar_el_sql_se_explica_y_no_se_lanza():
    """
    Un corte de red en el primer nodo no puede propagarse como excepción: la
    petición HTTP devolvería 500 y el usuario vería una pantalla rota en vez
    del motivo.
    """
    class LLMCaido:
        def __init__(self):
            self.llamadas = 0

        def invoke(self, mensajes):
            self.llamadas += 1
            if self.llamadas <= ag.MAX_INTENTOS:
                raise RuntimeError("sin red")

            class _R:
                content = "No se pudo consultar."

            return _R()

    resultado = ag.ejecutar("x", TASKS, llm=LLMCaido(), ejecutar_sql=lambda s: [])

    assert resultado["success"] is False
    assert resultado["respuesta"] == "No se pudo consultar."


def test_si_el_grafo_revienta_entero_se_devuelve_el_motivo(monkeypatch):
    """
    La última red: si construir o invocar el grafo falla por algo que no
    previmos —un cambio de API de LangGraph, por ejemplo—, el endpoint responde
    `success: false` con el motivo, no un 500 sin explicación.

    Se rompe `construir_grafo` y no el LLM: un fallo del modelo ya lo capturan
    los nodos, así que por ahí nunca se llegaría a este `except`.
    """
    def _explota(*args, **kwargs):
        raise RuntimeError("LangGraph cambió de API")

    monkeypatch.setattr(ag, "construir_grafo", _explota)

    resultado = ag.ejecutar("x", TASKS, llm=LLMFalso(["lo que sea"]),
                            ejecutar_sql=lambda s: [])
    assert resultado["success"] is False
    assert "no pudo completar" in resultado["message"]


def test_se_avisa_cuando_las_filas_se_recortaron():
    """
    Un recorte silencioso es peor que ninguno: el modelo redactaría "hay 40
    tareas" sobre un resultado que en realidad tenía más.
    """
    filas = [{"folio": str(i)} for i in range(ag.TECHO_FILAS + 5)]
    texto = ag.formatear_filas(filas)
    assert "recortadas" in texto
    assert texto.count("\n") == ag.TECHO_FILAS


def test_con_motor_en_memoria_no_hay_ejecutor(monkeypatch):
    """
    `BACKEND_ENGINE=memoria` expone `consulta_cruda`, pero declara
    `soporta_sql_crudo = False`. Devolver un ejecutor que se sabe roto es lo que
    hacía que el bucle de auto-corrección gastara tres llamadas al modelo.
    """
    monkeypatch.delenv(ag.ENV_DSN_AGENTE, raising=False)
    monkeypatch.setenv("BACKEND_ENGINE", "memoria")
    assert ag.ejecutor_disponible() is None


def test_con_una_clave_falsa_de_groq_el_llm_no_tumba_el_modulo(monkeypatch):
    """
    Construir el cliente puede fallar (clave con formato raro, paquete ausente).
    Devuelve `None` y el módulo se degrada; no revienta el import ni la ruta.
    """
    from api import paperclip_agents

    monkeypatch.setenv("GROQ_API_KEY", "clave-invalida")

    def _explota(**kwargs):
        raise RuntimeError("credencial rechazada")

    monkeypatch.setattr(paperclip_agents, "ChatGroq", _explota)
    assert ag.llm_disponible() is None


def test_sin_el_paquete_de_groq_tampoco_hay_llm(monkeypatch):
    from api import paperclip_agents

    monkeypatch.setenv("GROQ_API_KEY", "cualquiera")
    monkeypatch.setattr(paperclip_agents, "ChatGroq", None)
    assert ag.llm_disponible() is None


def test_si_el_modelo_falla_al_detectar_areas_se_devuelve_lista_vacia():
    """Un fallo de red aquí no puede impedir que se redacten los correos a mano."""
    class LLMCaido:
        def invoke(self, mensajes):
            raise RuntimeError("sin red")

    assert correos.detectar_areas("RH va tarde", LLMCaido()) == []


def test_un_json_malformado_del_modelo_no_rompe_la_deteccion_de_areas():
    llm = LLMFalso(['["RH", "FINANZAS"'])   # array sin cerrar
    assert correos.detectar_areas("x", llm) == []


def test_generar_borradores_sin_areas_no_llama_al_modelo():
    llm = LLMFalso(["no debería usarse"])
    assert correos.generar_borradores("p", "r", [], llm) == {}
    assert llm.prompts == []


def test_un_elemento_que_no_es_objeto_se_ignora_al_armar_borradores():
    """El modelo a veces devuelve un array de cadenas. No puede tumbar el paso."""
    llm = LLMFalso(['["RH", {"area": "RH", "asunto": "A", "cuerpo": "B"}]'])
    borradores = correos.generar_borradores("p", "r", ["RH"], llm)
    assert borradores["RH"]["cuerpo"] == "B"


def test_aplicar_cambio_sobre_algo_que_no_es_un_borrador_devuelve_none():
    assert correos.aplicar_cambio("RH", None, "cambia", "d", LLMFalso(["{}"])) is None


# ======================================================================
# 10. De qué conexión sale el SQL  (regresión del fallo en producción)
# ======================================================================
# El despliegue real usa PostgREST, no SQLAlchemy. `ejecutor_disponible`
# comprobaba con `getattr` que existiera `consulta_cruda` y `PostgrestEngine`
# la tiene —lanzando—, así que devolvía un ejecutor roto: el usuario vio
# "El motor PostgREST no puede ejecutar SQL directo" DESPUÉS de que el bucle
# de auto-corrección gastara tres llamadas al modelo.
#
# Dos arreglos, y una prueba por cada uno:
#   1. `soporta_sql_crudo` se pregunta antes de llamar.
#   2. `AGENTE_SQL_DATABASE_URL` da al agente su propia conexión de solo
#      lectura, sin cambiarle el motor a toda la aplicación.

# DSN con el dialecto real. `create_engine` no abre ninguna conexión al
# construirse, así que esto ejerce el cableado sin tocar ninguna base — y con
# el mismo dialecto que producción: SQLite rechaza `pool_size`, así que un
# `sqlite://` habría "probado" un camino que en Postgres no existe.
DSN_DE_PRUEBA = "postgresql+psycopg://lector:clave@base.invalido:6543/postgres"


@pytest.fixture(autouse=True)
def _sin_motores_cacheados():
    """El caché de motores es de módulo; sin limpiarlo, una prueba filtra a la otra."""
    ag._MOTORES.clear()
    yield
    ag._MOTORES.clear()


def _entorno_de_produccion(monkeypatch) -> None:
    """PostgREST y nada más: el despliegue tal como está hoy."""
    monkeypatch.delenv(ag.ENV_DSN_AGENTE, raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("BACKEND_ENGINE", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://ejemplo.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "clave-de-prueba")


def test_con_postgrest_hay_ejecutor_por_rpc(monkeypatch):
    """
    CAMBIO DE CONTRATO: antes esto era `None` y el módulo quedaba inservible en
    el despliegue real, que usa PostgREST. Ahora hay ejecutor —el RPC—; que la
    función esté instalada o no lo dice `consulta_cruda` con un error que nombra
    el archivo, y ese error NO es reintentable.
    """
    _entorno_de_produccion(monkeypatch)
    assert ag.ejecutor_disponible() is not None


def test_sin_base_no_se_llama_al_modelo_ni_una_vez(monkeypatch):
    """
    El coste real del fallo: tres llamadas al LLM para un error de
    configuración que se conocía antes de la primera.
    """
    for variable in ("AGENTE_SQL_DATABASE_URL", "DATABASE_URL", "SUPABASE_URL",
                     "SUPABASE_KEY", "BACKEND_ENGINE"):
        monkeypatch.delenv(variable, raising=False)
    from fastapi.testclient import TestClient

    from api.main import app

    llamadas = []
    monkeypatch.setattr(ag, "llm_disponible",
                        lambda: llamadas.append(1) or LLMFalso(["no debería usarse"]))

    respuesta = TestClient(app).post(
        "/api/agente/consulta", json={"pregunta": "cuántas tareas hay"}).json()

    assert respuesta["success"] is False
    assert "DDL_AGENTE_SQL.sql" in respuesta["message"]
    assert llamadas == []


def test_el_dsn_propio_del_agente_da_un_ejecutor(monkeypatch):
    _entorno_de_produccion(monkeypatch)
    monkeypatch.setenv(ag.ENV_DSN_AGENTE, DSN_DE_PRUEBA)
    assert ag.ejecutor_disponible() is not None


def test_el_dsn_propio_gana_sobre_el_motor_de_la_aplicacion(monkeypatch):
    """
    El agente lee por SU conexión aunque la aplicación tenga una utilizable.

    No es un capricho: el DSN de la aplicación tiene permiso de escritura y el
    del agente apunta a `agentesql_readonly`. Que el agente prefiera el suyo es
    lo que hace verdadera la frase "un rol sin permiso de escritura no se puede
    rodear" del docstring del módulo.
    """
    monkeypatch.delenv("BACKEND_ENGINE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:clave@host:5432/postgres")
    monkeypatch.setenv(ag.ENV_DSN_AGENTE, DSN_DE_PRUEBA)

    ejecutor = ag.ejecutor_disponible()
    assert ejecutor is not None
    # El ejecutor es el del motor dedicado, no el de la aplicación.
    assert ejecutor.__self__ is ag._MOTORES[DSN_DE_PRUEBA]


def test_el_motor_dedicado_se_reutiliza_entre_peticiones(monkeypatch):
    """
    Un `create_engine` por petición deja un pool colgando en cada llamada; en un
    proceso largo eso agota las conexiones de la base.
    """
    _entorno_de_produccion(monkeypatch)
    monkeypatch.setenv(ag.ENV_DSN_AGENTE, DSN_DE_PRUEBA)

    ag.ejecutor_disponible()
    ag.ejecutor_disponible()
    assert list(ag._MOTORES) == [DSN_DE_PRUEBA]


def test_un_dsn_ilegible_cae_al_motor_de_la_aplicacion(monkeypatch):
    """
    Un DSN mal escrito no puede dejar el módulo muerto si hay otro camino: se
    avisa por log y se sigue por el RPC de PostgREST.
    """
    _entorno_de_produccion(monkeypatch)
    monkeypatch.setenv(ag.ENV_DSN_AGENTE, "esto-no-es-un-dsn")
    assert ag.ejecutor_disponible() is not None


# --- El esquema del DSN ------------------------------------------------
#
# El DSN que Supabase entrega en su panel ("Connection string" del pooler)
# empieza por `postgresql://`, sin driver. SQLAlchemy resuelve ese esquema al
# dialecto por defecto, `psycopg2`, que este proyecto NO instala:
# `requirements.txt` declara `psycopg[binary]>=3.1`, la versión 3.
#
# El resultado era el peor de los posibles: `ModuleNotFoundError: No module
# named 'psycopg2'` dentro de `_motor_dedicado`, que lo captura, lo imprime en
# un log que nadie mira y devuelve `None`. El agente caía al motor de la
# aplicación y contestaba "no tengo por dónde consultar la base" — es decir,
# el mensaje de "falta configurar la variable" con la variable ya configurada.
#
# Pedirle al usuario que escriba `postgresql+psycopg://` es pedirle que
# recuerde un detalle del driver para pegar una cadena que el proveedor le da
# hecha. El esquema se normaliza aquí.


def test_el_dsn_del_panel_de_supabase_da_un_ejecutor(monkeypatch):
    """
    La cadena tal como la copia un humano del panel de Supabase, sin `+psycopg`.

    Antes de este arreglo devolvía el ejecutor de PostgREST (o `None`): el DSN
    se descartaba en silencio por un `ModuleNotFoundError` de psycopg2.
    """
    _entorno_de_produccion(monkeypatch)
    dsn = "postgresql://lector:clave@base.invalido:6543/postgres"
    monkeypatch.setenv(ag.ENV_DSN_AGENTE, dsn)

    ejecutor = ag.ejecutor_disponible()
    assert ejecutor is not None
    assert ejecutor.__self__ is ag._MOTORES[dsn]


def test_el_dsn_sin_driver_gana_sobre_el_motor_de_la_aplicacion(monkeypatch):
    """
    La garantía de solo lectura no puede depender de cómo se escribió el
    esquema: si el DSN del agente se descarta, el agente lee por el motor de la
    aplicación, que sí tiene permiso de escritura.
    """
    monkeypatch.delenv("BACKEND_ENGINE", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://app:clave@host:5432/postgres")
    dsn = "postgresql://agentesql_readonly:clave@base.invalido:6543/postgres"
    monkeypatch.setenv(ag.ENV_DSN_AGENTE, dsn)

    ejecutor = ag.ejecutor_disponible()
    assert ejecutor.__self__ is ag._MOTORES[dsn]


@pytest.mark.parametrize("dsn,esperado", [
    # Lo que da el panel de Supabase.
    ("postgresql://u:c@h:6543/postgres", "postgresql+psycopg"),
    # El alias histórico de Heroku, que SQLAlchemy 2.x ya no resuelve.
    ("postgres://u:c@h:6543/postgres", "postgresql+psycopg"),
    # Un driver escrito a propósito se respeta: quien lo pone sabe lo que hace.
    ("postgresql+psycopg://u:c@h:6543/postgres", "postgresql+psycopg"),
    ("postgresql+psycopg2://u:c@h:6543/postgres", "postgresql+psycopg2"),
    # Otro motor no se toca.
    ("sqlite://", "sqlite"),
])
def test_el_esquema_del_dsn_se_normaliza_al_driver_instalado(dsn, esperado):
    """
    Se comprueba el `drivername` que queda en el motor, no el texto de entrada:
    lo que decide qué paquete importa SQLAlchemy es la URL ya resuelta.
    """
    from backend.core.engines.sqlalchemy_engine import normalizar_dsn

    from sqlalchemy.engine.url import make_url

    assert make_url(normalizar_dsn(dsn)).drivername == esperado


def test_normalizar_un_dsn_ilegible_no_lanza():
    """
    `normalizar_dsn` no valida: quien valida es `create_engine`, que ya tiene
    un `except` alrededor en `_motor_dedicado`. Una cadena que no es un DSN
    sale igual que entró y falla donde ya se sabía fallar.
    """
    from backend.core.engines.sqlalchemy_engine import normalizar_dsn

    assert normalizar_dsn("esto-no-es-un-dsn") == "esto-no-es-un-dsn"
    assert normalizar_dsn("") == ""


def test_el_dsn_normalizado_llega_a_create_engine(monkeypatch):
    """
    La prueba de que la normalización viaja hasta SQLAlchemy y no se queda en
    una variable local: se espía `create_engine` en su frontera.
    """
    import sqlalchemy

    from backend.core.engines.sqlalchemy_engine import SqlAlchemyEngine

    vistos = []
    original = sqlalchemy.create_engine

    def espia(url, **kwargs):
        vistos.append(url)
        return original(url, **kwargs)

    monkeypatch.setattr(sqlalchemy, "create_engine", espia)
    SqlAlchemyEngine("postgresql://u:c@h:6543/postgres")

    assert vistos == ["postgresql+psycopg://u:c@h:6543/postgres"]


def test_sin_ningun_motor_configurado_no_hay_ejecutor(monkeypatch):
    """El caso en que de verdad no hay por dónde: ni DSN propio ni motor."""
    for variable in (ag.ENV_DSN_AGENTE, "DATABASE_URL", "SUPABASE_URL",
                     "SUPABASE_KEY", "BACKEND_ENGINE"):
        monkeypatch.delenv(variable, raising=False)
    assert ag.ejecutor_disponible() is None


@pytest.mark.parametrize("modulo,clase,esperado", [
    ("backend.core.engines.sqlalchemy_engine", "SqlAlchemyEngine", True),
    # PostgREST puede, pero solo a través de la función RPC del DDL.
    ("backend.core.engines.postgrest", "PostgrestEngine", True),
    ("backend.core.engines.memoria", "MemoryEngine", False),
])
def test_cada_motor_declara_si_puede_ejecutar_sql_crudo(modulo, clase, esperado):
    """
    La capacidad se declara en la clase, no se descubre llamando y viendo qué
    pasa. Un motor nuevo tiene que decidirlo a propósito.
    """
    import importlib

    assert getattr(importlib.import_module(modulo), clase).soporta_sql_crudo is esperado


# ======================================================================
# 11. Un fallo de configuración no cuesta tres llamadas al modelo
# ======================================================================


def _error_de_configuracion():
    from backend.core.engines.postgrest import ErrorDeConfiguracion

    return ErrorDeConfiguracion("Falta ejecutar docs/DDL_AGENTE_SQL.sql")


def test_un_error_de_configuracion_no_se_reintenta():
    """
    La diferencia que justifica todo el mecanismo: reescribir el SQL no instala
    una función que falta. Reintentar solo gasta llamadas para acabar diciendo
    lo mismo que ya se sabía en la primera.
    """
    llm = LLMFalso(["```sql\nSELECT folio FROM tasks\n```", "Falta configurar algo."])

    def _falta_la_funcion(sql):
        raise _error_de_configuracion()

    resultado = ag.ejecutar("x", TASKS, llm=llm, ejecutar_sql=_falta_la_funcion)

    assert resultado["success"] is False
    assert resultado["intentos"] == 1          # una, no tres
    assert "DDL_AGENTE_SQL.sql" in resultado["message"]


def test_un_error_de_sql_si_se_reintenta():
    """
    La otra mitad: un error que el modelo SÍ puede arreglar sigue reintentando.
    Sin esta prueba, cortar el bucle de más se vería igual de bien.
    """
    llm = LLMFalso([
        "```sql\nSELECT columna_mala FROM tasks\n```",
        "```sql\nSELECT folio FROM tasks\n```",
        "Listo.",
    ])
    intentos = {"n": 0}

    def _falla_una_vez(sql):
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise RuntimeError('column "columna_mala" does not exist')
        return [{"folio": "AV-1"}]

    resultado = ag.ejecutar("x", TASKS, llm=llm, ejecutar_sql=_falla_una_vez)
    assert resultado["success"] is True and resultado["intentos"] == 2


def test_el_router_corta_el_bucle_con_la_marca():
    """La regla, aislada del grafo."""
    assert ag.ruta_tras_ejecutar(
        {"error": "x", "intentos": 1, "reintentable": False}) == "responder"
    assert ag.ruta_tras_ejecutar(
        {"error": "x", "intentos": 1, "reintentable": True}) == "generar"
    assert ag.ruta_tras_ejecutar(
        {"error": "", "intentos": 1}) == "responder"


def test_un_fallo_de_red_tampoco_se_reintenta():
    from backend.core.errors import ErrorDeMotor

    assert ag._es_reintentable(ErrorDeMotor("Fallo de red hacia PostgREST: x")) is False
    assert ag._es_reintentable(RuntimeError("syntax error at or near")) is True


# ======================================================================
# 12. El diagnóstico
# ======================================================================
# Existe porque el módulo tiene tres dependencias de despliegue y, cuando falla
# una, el usuario solo ve "no pude consultar". Averiguar cuál costaba una ronda
# de mensajes con quien escribió el código. Eso ya pasó tres veces.


def test_el_diagnostico_dice_que_falta_la_clave_del_modelo(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    _entorno_de_produccion(monkeypatch)

    informe = ag.diagnostico()
    assert informe["modelo"]["ok"] is False
    assert "GROQ_API_KEY" in informe["modelo"]["detalle"]
    assert informe["listo"] is False


def test_el_diagnostico_dice_que_falta_el_ddl(monkeypatch):
    """
    Con el motor en pie pero la función sin instalar, el informe tiene que
    nombrar el archivo — que es la única parte accionable.
    """
    _entorno_de_produccion(monkeypatch)
    monkeypatch.setattr(ag, "ejecutor_disponible",
                        lambda: (_ for _ in ()).throw(AssertionError("no usar")))

    def _falta(sql):
        raise _error_de_configuracion()

    monkeypatch.setattr(ag, "ejecutor_disponible", lambda: _falta)

    informe = ag.diagnostico()
    assert informe["base"]["ok"] is True
    assert informe["consulta"]["ok"] is False
    assert "DDL_AGENTE_SQL.sql" in informe["consulta"]["detalle"]
    assert informe["listo"] is False


def test_el_diagnostico_dice_listo_cuando_todo_responde(monkeypatch):
    _entorno_de_produccion(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "clave")
    monkeypatch.setattr(ag, "llm_disponible", lambda: LLMFalso(["ok"]))
    monkeypatch.setattr(ag, "ejecutor_disponible", lambda: (lambda sql: [{"ok": 1}]))

    informe = ag.diagnostico()
    assert informe["listo"] is True
    assert informe["consulta"]["ok"] is True


def test_el_diagnostico_no_llama_al_modelo(monkeypatch):
    """
    Un diagnóstico que gasta una llamada al modelo no se puede pulsar dos veces
    seguidas sin pensárselo, y entonces no se pulsa.
    """
    _entorno_de_produccion(monkeypatch)
    invocaciones = []

    class LLMQueCuenta(LLMFalso):
        def invoke(self, mensajes):
            invocaciones.append(1)
            return super().invoke(mensajes)

    monkeypatch.setenv("GROQ_API_KEY", "clave")
    monkeypatch.setattr(ag, "llm_disponible", lambda: LLMQueCuenta(["x"]))
    monkeypatch.setattr(ag, "ejecutor_disponible", lambda: (lambda sql: []))

    ag.diagnostico()
    assert invocaciones == []


def test_el_diagnostico_comprueba_la_base_de_verdad(monkeypatch):
    """
    Se ejecuta un `SELECT 1`, no se mira si la variable está definida: una
    variable puesta con un valor equivocado se ve igual que una puesta bien.

    AMPLIADA: antes exigía `len(ejecutados) == 1`. Ese uno era justo el
    agujero — `SELECT 1` no nombra ninguna tabla, así que pasaba en una base
    donde no existía ni una de las del agente y el informe decía "listo"
    mientras cada pregunta fallaba. Ahora se comprueba también cada tabla; la
    intención de la prueba (medir, no leer variables) es la misma y por eso se
    conserva en vez de reemplazarse.
    """
    _entorno_de_produccion(monkeypatch)
    ejecutados = []
    monkeypatch.setattr(ag, "ejecutor_disponible",
                        lambda: (lambda sql: ejecutados.append(sql) or []))

    ag.diagnostico()
    assert "SELECT 1" in ejecutados[0]
    for esq in esquemas.ESQUEMAS.values():
        assert any(f"FROM {esq.tabla} " in sql for sql in ejecutados[1:]), (
            f"el diagnóstico no comprobó la tabla {esq.tabla}")


def test_el_diagnostico_nombra_la_tabla_que_no_se_puede_leer(monkeypatch):
    """
    El fallo que trajo este cambio, visto desde el diagnóstico.

    Con las tablas del despliegue llamándose `tasks_rows_sql`, el agente pedía
    `tasks` y todo lo que llegaba a pantalla era «La función
    agente_sql_consulta no existe en la base». El diagnóstico tiene que decir
    la otra mitad: qué tabla es, y las dos salidas posibles.
    """
    _entorno_de_produccion(monkeypatch)
    monkeypatch.setenv("GROQ_API_KEY", "clave")
    monkeypatch.setattr(ag, "llm_disponible", lambda: LLMFalso(["ok"]))

    def _sin_tabla(sql):
        if "FROM tasks " in sql:
            raise RuntimeError('relation "tasks" does not exist')
        return [{"ok": 1}]

    monkeypatch.setattr(ag, "ejecutor_disponible", lambda: _sin_tabla)

    informe = ag.diagnostico()
    assert informe["consulta"]["ok"] is True       # el canal RPC sí responde
    assert informe["tablas"]["ok"] is False
    assert informe["listo"] is False
    detalle = informe["tablas"]["por_esquema"]["tasks"]["detalle"]
    assert "tasks" in detalle
    assert "AGENTE_SQL_TABLA_TASKS" in detalle
    assert "DDL_AGENTE_SQL.sql" in detalle


def test_el_diagnostico_no_comprueba_tablas_si_el_canal_no_responde(monkeypatch):
    """
    Sin canal, cada sonda de tabla es otra llamada condenada a fallar con el
    mismo error. Se dice una vez y se para.
    """
    _entorno_de_produccion(monkeypatch)

    def _falta(sql):
        raise _error_de_configuracion()

    monkeypatch.setattr(ag, "ejecutor_disponible", lambda: _falta)

    informe = ag.diagnostico()
    assert informe["tablas"]["ok"] is False
    assert informe["tablas"]["por_esquema"] == {}


def test_el_diagnostico_sin_motor_no_lanza(monkeypatch):
    for variable in (ag.ENV_DSN_AGENTE, "DATABASE_URL", "SUPABASE_URL",
                     "SUPABASE_KEY", "BACKEND_ENGINE"):
        monkeypatch.delenv(variable, raising=False)

    informe = ag.diagnostico()
    assert informe["base"]["ok"] is False
    assert informe["listo"] is False


def test_la_ruta_de_diagnostico_responde(monkeypatch):
    from fastapi.testclient import TestClient

    from api.main import app

    _entorno_de_produccion(monkeypatch)
    cuerpo = TestClient(app).get("/api/agente/diagnostico").json()
    assert set(cuerpo) >= {"listo", "modelo", "base", "consulta"}


# ----------------------------------------------------------------------
# El nombre real de las tablas (AGENTE_SQL_TABLA_*)
# ----------------------------------------------------------------------
# Por qué existe esta configuración y no un nombre fijo: hay despliegues donde
# `tasks`/`quotes` todavía no están y lo cargado son los volcados del notebook
# (`tasks_rows_sql`, `quotes_rows_sql`). Con el nombre fijo, el agente pedía una
# tabla inexistente y el 404 resultante se leía como «falta la función RPC».


def test_sin_variable_el_agente_sigue_consultando_las_tablas_de_la_app(monkeypatch):
    """
    El valor por defecto no se mueve.

    Es la decisión documentada del módulo —la aplicación escribe en `tasks`, y
    una copia suelta contesta con datos viejos sin avisar—, así que encender la
    salida de emergencia no puede cambiársela a quien no la pidió.
    """
    for variable in esquemas.ENV_TABLA.values():
        monkeypatch.delenv(variable, raising=False)

    construidos = esquemas._construir_esquemas()
    assert construidos["tasks"].tabla == "tasks"
    assert construidos["quotes"].tabla == "quotes"


def test_la_variable_cambia_la_tabla_del_prompt_y_de_la_lista_blanca(monkeypatch):
    """
    Las tres cosas se mueven juntas o no sirve de nada.

    El nombre viaja al prompt (para que el modelo escriba el FROM correcto) y a
    la lista blanca de `validar_sql` (para que no lo rechace). Cambiar solo una
    deja al agente generando SQL que él mismo bloquea.
    """
    monkeypatch.setenv("AGENTE_SQL_TABLA_TASKS", "tasks_rows_sql")

    tareas = esquemas._construir_esquemas()["tasks"]
    assert tareas.tabla == "tasks_rows_sql"
    assert "tasks_rows_sql" in tareas.prompt_sistema()

    permitidas = frozenset({tareas.tabla})
    assert ag.validar_sql("SELECT count(*) FROM tasks_rows_sql", permitidas) == ""
    # Y la de antes deja de estar permitida: la lista blanca es UNA tabla.
    assert "BLOQUEO" in ag.validar_sql("SELECT count(*) FROM tasks", permitidas)


def test_un_nombre_de_tabla_con_sql_dentro_se_ignora(monkeypatch, capsys):
    """
    El valor de la variable acaba dentro de un `FROM` y dentro de la lista
    blanca. Si no fuera un identificador limpio, la lista blanca dejaría de ser
    una lista blanca.

    Se ignora y se avisa, en vez de usarlo o de tumbar el módulo: es la única
    de las tres salidas que no empeora nada.
    """
    monkeypatch.setenv("AGENTE_SQL_TABLA_TASKS", "tasks; drop table quotes")

    assert esquemas._construir_esquemas()["tasks"].tabla == "tasks"
    assert "no es un nombre de tabla válido" in capsys.readouterr().out


def test_un_nombre_de_tabla_vacio_no_borra_el_valor_por_defecto(monkeypatch):
    """Una variable definida pero vacía es una variable sin definir."""
    monkeypatch.setenv("AGENTE_SQL_TABLA_QUOTES", "   ")
    assert esquemas._construir_esquemas()["quotes"].tabla == "quotes"
