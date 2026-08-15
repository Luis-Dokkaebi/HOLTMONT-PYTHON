"""
Agente de métricas de cotizaciones: lectura de columnas y cliente de Gemini.

Dos fallos distintos hacían que el tablero QUOTE_METRICS saliera vacío y que el
análisis de IA nunca se produjera. Están probados por separado porque tienen
causas independientes.

**1. El agente no leía ninguna fecha de la hoja de ventas.**
`compute_quote_metrics` buscaba la fecha en `FECHA` / `FECHA INICIO` /
`FECHA ALTA` / `ALTA`, que son los encabezados del *tracker*. La hoja de ventas
(`ANTONIA_VENTAS`) se rinde con `QUOTE_HEADER_MAP` de `api/services/sheets.py`,
donde las fechas se llaman `F. VISITA`, `F. INICIO` y `F. ENTREGA`. Ninguno de
los cuatro alias existía en esas filas, así que `fecha` era siempre `None` y:

  - con filtro de periodo (el tablero siempre manda mes y año) **toda** fila se
    descartaba → `totalCount` 0 y el mensaje "No hay cotizaciones terminadas
    registradas para <mes>";
  - el bloque de SLA exige `fecha`, así que `slaSummary` quedaba en ceros y
    `alerts` vacío → "Sin alertas críticas" con la hoja llena.

Es el mismo fallo que ya se corrigió en el calendario (`CALENDAR_DATE_ALIASES`,
`tracker_rules.py` §CALENDARIO): una cotización se ubica por su `F. INICIO`.
La decisión del dueño del 2026-08-15 que está anotada ahí es la que se aplica
aquí, y por eso `F. INICIO` gana a `F. VISITA`.

**2. El cliente de Gemini.** Modelo retirado, la key no sobrevivía a la
invocación y los errores de Google se perdían. Ver `test_gemini_*`.
"""

import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import tracker_rules as rules  # noqa: E402
from api.services import tracker_store as store  # noqa: E402
from api.services.sheets import QUOTE_HEADER_MAP  # noqa: E402


# ======================================================================
# 1. LECTURA DE LAS COLUMNAS REALES DE LA HOJA DE VENTAS
# ======================================================================

def _fila_de_ventas(**valores):
    """
    Fila con los encabezados exactos que `sheets.QUOTE_HEADER_MAP` publica.

    Se construye desde el mapa y no a mano: si mañana se renombra una columna
    de ventas, esta prueba deja de fabricar el encabezado viejo y falla, que es
    justo lo que no pasó cuando `FECHA` se convirtió en `F. INICIO`.
    """
    fila = {encabezado: "" for encabezado, _ in QUOTE_HEADER_MAP}
    fila.update(valores)
    return fila


def test_los_alias_de_fecha_cubren_los_encabezados_publicados_de_ventas():
    encabezados = {encabezado for encabezado, _ in QUOTE_HEADER_MAP}
    assert "F. INICIO" in encabezados and "F. ENTREGA" in encabezados
    assert set(rules.QUOTE_DATE_ALIASES) & encabezados
    assert set(rules.QUOTE_CLOSE_DATE_ALIASES) & encabezados


def test_metricas_cuentan_las_cotizaciones_de_la_hoja_real_de_ventas():
    filas = [
        _fila_de_ventas(**{"FOLIO": "AV-1", "CLIENTE": "ACME", "AREA": "INDUSTRIAL",
                           "VENDEDOR": "ANGEL SALINAS", "CLASIFICACION": "A",
                           "F. VISITA": "2026-07-01", "F. INICIO": "2026-07-05",
                           "F. ENTREGA": "2026-07-06", "ESTATUS": "GANADA"}),
        _fila_de_ventas(**{"FOLIO": "AV-2", "CLIENTE": "ACME", "AREA": "INDUSTRIAL",
                           "VENDEDOR": "ANGEL SALINAS", "CLASIFICACION": "AA",
                           "F. VISITA": "2026-07-02", "F. INICIO": "2026-07-05",
                           "F. ENTREGA": "2026-07-25", "ESTATUS": "PERDIDA X PRECIO"}),
        _fila_de_ventas(**{"FOLIO": "AV-3", "CLIENTE": "BETA", "AREA": "COMERCIAL",
                           "VENDEDOR": "TERESA GARZA", "CLASIFICACION": "AAA",
                           "F. VISITA": "2026-06-20", "F. INICIO": "2026-06-30",
                           "F. ENTREGA": "2026-07-10", "ESTATUS": "GANADA"}),
    ]

    m = rules.compute_quote_metrics(filas, month=7, year=2026)

    # AV-3 arranca en junio: queda fuera del periodo aunque se entregue en julio.
    assert m["totalCount"] == 2
    assert m["winLoss"]["ganada"] == 1
    assert m["winLoss"]["perdida"] == 1
    assert m["closeRate"] == 50.0


def test_el_periodo_se_filtra_por_f_inicio_y_no_por_f_visita():
    """La visita puede caer en otro mes; el trabajo se cuenta donde empieza."""
    fila = _fila_de_ventas(**{"FOLIO": "AV-9", "CLASIFICACION": "A",
                              "F. VISITA": "2026-06-28", "F. INICIO": "2026-07-02",
                              "F. ENTREGA": "2026-07-03", "ESTATUS": "GANADA"})

    assert rules.compute_quote_metrics([fila], month=7, year=2026)["totalCount"] == 1
    assert rules.compute_quote_metrics([fila], month=6, year=2026)["totalCount"] == 0


def test_el_sla_se_mide_contra_f_entrega_no_contra_el_dia_de_hoy():
    """
    Sin `F. ENTREGA` el cálculo usaba `now`, así que toda cotización cerrada de
    un mes pasado aparecía fuera de SLA por el simple paso del tiempo.
    """
    filas = [
        _fila_de_ventas(**{"FOLIO": "AV-1", "CLASIFICACION": "A",
                           "F. INICIO": "2026-07-05", "F. ENTREGA": "2026-07-06",
                           "ESTATUS": "GANADA"}),
        _fila_de_ventas(**{"FOLIO": "AV-2", "CLASIFICACION": "AA",
                           "F. INICIO": "2026-07-05", "F. ENTREGA": "2026-07-25",
                           "ESTATUS": "PERDIDA X PRECIO"}),
    ]

    m = rules.compute_quote_metrics(filas, month=7, year=2026)

    assert m["slaSummary"]["A"]["count"] == 1
    assert m["slaSummary"]["A"]["ok"] == 1          # 1 día contra SLA de 3
    assert m["slaSummary"]["A"]["avgDays"] == 1
    assert m["slaSummary"]["AA"]["fail"] == 1       # 20 días contra SLA de 14
    assert [a["folio"] for a in m["alerts"]] == ["AV-2"]


def test_el_desglose_por_area_y_cliente_sale_de_las_columnas_de_ventas():
    filas = [
        _fila_de_ventas(**{"FOLIO": "AV-1", "CLIENTE": "ACME", "AREA": "INDUSTRIAL",
                           "VENDEDOR": "ANGEL SALINAS", "CLASIFICACION": "AAA",
                           "F. INICIO": "2026-07-05", "F. ENTREGA": "2026-08-20",
                           "ESTATUS": "GANADA"}),
    ]

    m = rules.compute_quote_metrics(filas, month=7, year=2026)

    assert [d["nombre"] for d in m["byDepartmentArr"]] == ["INDUSTRIAL"]
    assert [v["nombre"] for v in m["byCotizadorArr"]] == ["ANGEL SALINAS"]
    # 46 días contra SLA de 30: el cliente entra al panel de AAA fuera de SLA.
    cliente = m["aaaByClientArr"][0]
    assert (cliente["cliente"], cliente["total"], cliente["fueraSla"]) == ("ACME", 1, 1)


def test_las_filas_con_encabezados_del_tracker_se_siguen_leyendo():
    """Compatibilidad: la hoja original de Apps Script traía `FECHA`."""
    filas = [{"FOLIO": "AV-1", "FECHA": "05/07/26", "ESTATUS": "GANADA",
              "CLASIFICACION": "A", "FECHA_TERMINO": "06/07/26"}]

    m = rules.compute_quote_metrics(filas, month=7, year=2026)

    assert m["totalCount"] == 1
    assert m["slaSummary"]["A"]["ok"] == 1


# ----------------------------------------------------------------------
# Contrato con las tres tablas del tablero
# ----------------------------------------------------------------------
# `index.html` lee `c.name`, `c.dept`, `c.ganadas`, `c.clasA`, `c.slaOk`… y las
# reglas solo publicaban `nombre`, `ganada` y `perdida`. Resultado: las tablas
# DESEMPEÑO POR COTIZADOR y POR DEPARTAMENTO salían con las celdas en blanco y
# un `NAN%` en la columna de cierre, y el panel de clientes AAA no listaba un
# solo proyecto. Se ve en cuanto se abre la vista, y aun así llevaba así desde
# la migración: ninguna prueba miraba las claves que consume la plantilla.

def test_la_tabla_por_cotizador_trae_las_claves_que_lee_la_vista():
    filas = [
        {"FOLIO": "AV-1", "VENDEDOR": "ANGEL SALINAS", "AREA": "INDUSTRIAL",
         "CLASIFICACION": "A", "F. INICIO": "2026-07-05", "F. ENTREGA": "2026-07-06",
         "ESTATUS": "GANADA"},
        {"FOLIO": "AV-2", "VENDEDOR": "ANGEL SALINAS", "AREA": "INDUSTRIAL",
         "CLASIFICACION": "AA", "F. INICIO": "2026-07-05", "F. ENTREGA": "2026-07-25",
         "ESTATUS": "PERDIDA X PRECIO"},
        {"FOLIO": "AV-3", "VENDEDOR": "ANGEL SALINAS", "AREA": "COMERCIAL",
         "CLASIFICACION": "AAA", "F. INICIO": "2026-07-06", "F. ENTREGA": "2026-07-20",
         "ESTATUS": "EN PROCESO"},
    ]

    fila = rules.compute_quote_metrics(filas, month=7, year=2026)["byCotizadorArr"][0]

    assert fila["name"] == "ANGEL SALINAS"
    assert fila["dept"] == "INDUSTRIAL"      # el área con más cotizaciones suyas
    assert (fila["total"], fila["ganadas"], fila["perdidas"]) == (3, 1, 1)
    assert (fila["clasA"], fila["clasAA"], fila["clasAAA"]) == (1, 1, 1)
    assert (fila["slaOk"], fila["slaFail"]) == (2, 1)   # AV-2 se pasó de 14 días
    # Las claves originales siguen ahí: `write_quote_metrics_to_sheet` las usa.
    assert fila["nombre"] == "ANGEL SALINAS" and fila["ganada"] == 1 and fila["perdida"] == 1


def test_la_tabla_por_departamento_trae_las_claves_que_lee_la_vista():
    filas = [
        {"FOLIO": "AV-1", "AREA": "INDUSTRIAL", "F. INICIO": "2026-07-05", "ESTATUS": "GANADA"},
        {"FOLIO": "AV-2", "AREA": "INDUSTRIAL", "F. INICIO": "2026-07-05",
         "ESTATUS": "PERDIDA X PRECIO"},
    ]

    fila = rules.compute_quote_metrics(filas, month=7, year=2026)["byDepartmentArr"][0]

    assert fila["dept"] == "INDUSTRIAL"
    assert (fila["total"], fila["ganadas"], fila["perdidas"]) == (2, 1, 1)
    assert fila["nombre"] == "INDUSTRIAL" and fila["ganada"] == 1


def test_el_panel_de_clientes_aaa_lista_sus_proyectos():
    filas = [
        {"FOLIO": "AV-1", "CLIENTE": "ACME", "CONCEPTO": "NAVE INDUSTRIAL",
         "CLASIFICACION": "AAA", "F. INICIO": "2026-07-01", "F. ENTREGA": "2026-07-20",
         "ESTATUS": "GANADA"},
        {"FOLIO": "AV-2", "CLIENTE": "ACME", "CONCEPTO": "AMPLIACION",
         "CLASIFICACION": "AAA", "F. INICIO": "2026-07-01", "F. ENTREGA": "2026-09-01",
         "ESTATUS": "PERDIDA X PRECIO"},
    ]

    cliente = rules.compute_quote_metrics(filas, month=7, year=2026)["aaaByClientArr"][0]

    assert cliente["cliente"] == "ACME"
    assert cliente["count"] == 2 and cliente["total"] == 2
    assert (cliente["ganadas"], cliente["perdidas"]) == (1, 1)
    assert cliente["fueraSla"] == 1          # AV-2: 62 días contra SLA de 30
    assert [p["folio"] for p in cliente["projects"]] == ["AV-1", "AV-2"]
    assert cliente["projects"][0] == {"folio": "AV-1", "concepto": "NAVE INDUSTRIAL",
                                      "isGanada": True, "isPerdida": False,
                                      "durationDays": 19}
    assert cliente["projects"][1]["isPerdida"] is True


def test_una_cotizacion_sin_area_cae_en_general_y_no_en_blanco():
    filas = [{"FOLIO": "AV-1", "VENDEDOR": "ANGEL SALINAS", "F. INICIO": "2026-07-05",
              "ESTATUS": "GANADA"}]

    m = rules.compute_quote_metrics(filas, month=7, year=2026)

    assert m["byDepartmentArr"][0]["dept"] == "GENERAL"
    assert m["byCotizadorArr"][0]["dept"] == "GENERAL"


def test_camino_completo_de_la_base_a_los_kpis_sin_mocks_en_el_nucleo():
    """
    Filas de `quotes` → serialización real de la hoja → `rows_to_dicts` → KPIs.

    Las pruebas anteriores del agente inventaban filas con la clave `FECHA`, que
    ningún componente de la cadena produce; por eso el bug sobrevivió a 706
    pruebas en verde. Aquí no se escribe ni un encabezado a mano: la matriz la
    arma `sheets._valores_de_cotizaciones`, la misma que sirve el endpoint.
    """
    from api.services.sheets import _valores_de_cotizaciones

    filas_de_la_base = [
        # `completada` marca la cotización como archivada → "TAREAS REALIZADAS".
        {"folio": "AV-1", "cliente": "ACME", "area": "INDUSTRIAL", "clasificacion": "A",
         "vendedor_raw": "ANGEL SALINAS", "f_visita": "2026-06-28", "f_inicio": "2026-07-05",
         "f_entrega": "2026-07-06", "estatus": "GANADA", "completada": True},
        {"folio": "AV-2", "cliente": "BETA", "area": "COMERCIAL", "clasificacion": "AA",
         "vendedor_raw": "TERESA GARZA", "f_visita": "2026-07-01", "f_inicio": "2026-07-05",
         "f_entrega": "2026-07-25", "estatus": "PERDIDA X PRECIO", "completada": True},
        {"folio": "AV-3", "cliente": "GAMMA", "area": "INDUSTRIAL", "clasificacion": "A",
         "vendedor_raw": "ANGEL SALINAS", "f_visita": "2026-07-02", "f_inicio": "2026-07-10",
         "f_entrega": "", "estatus": "EN PROCESO", "completada": False},
    ]

    activas, historial, _ = rules.rows_to_dicts(_valores_de_cotizaciones(filas_de_la_base))
    m = rules.compute_quote_metrics(list(activas) + list(historial), month=7, year=2026)

    assert m["totalCount"] == 3
    assert m["winLoss"] == {"ganada": 1, "perdida": 1, "enProceso": 1, "total": 3}
    assert m["closeRate"] == 50.0
    assert m["slaSummary"]["A"]["ok"] == 1        # AV-1: 1 día contra SLA de 3
    assert m["slaSummary"]["AA"]["fail"] == 1     # AV-2: 20 días contra SLA de 14

    # AV-3 sigue abierta y sin F. ENTREGA: se mide contra hoy, así que en cuanto
    # pasa su SLA entra en alertas. Es deliberado (`referencia = cierre || hoy`
    # en `CODIGO.js`) y es el caso que más importa: una cotización vencida que
    # todavía nadie cerró. Por eso se afirma su presencia en vez de excluirla.
    assert sorted(a["folio"] for a in m["alerts"]) == ["AV-2", "AV-3"]
    assert sorted(v["nombre"] for v in m["byCotizadorArr"]) == ["ANGEL SALINAS", "TERESA GARZA"]


# ======================================================================
# 2. CLIENTE DE GEMINI
# ======================================================================

class _RespuestaFalsa:
    """Sustituto de lo que devuelve `urllib.request.urlopen`."""

    def __init__(self, payload):
        self._cuerpo = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def _respuesta_de_texto(texto):
    return {"candidates": [{"content": {"parts": [{"text": texto}]}}]}


@pytest.fixture(autouse=True)
def _entorno_sin_key(monkeypatch):
    """Ninguna prueba hereda la key del entorno de quien la corre."""
    monkeypatch.delenv(store.GEMINI_KEY_ENV, raising=False)
    monkeypatch.delenv(store.GEMINI_MODEL_ENV, raising=False)
    yield


def test_el_modelo_por_defecto_ya_no_es_el_retirado_gemini_15():
    """
    `gemini-1.5-flash` responde 404 en `v1beta` para las API keys emitidas
    después de su retiro: el agente fallaba con una key perfectamente válida.
    """
    assert "1.5" not in store.GEMINI_MODELS[0]
    assert store.GEMINI_MODELS[0].startswith("gemini-")


def test_el_modelo_se_puede_fijar_por_entorno(monkeypatch):
    monkeypatch.setenv(store.GEMINI_MODEL_ENV, "gemini-3-pro")
    assert store.modelos_gemini()[0] == "gemini-3-pro"


def test_sin_key_no_se_llama_a_la_red_y_el_mensaje_lo_dice(monkeypatch):
    def _prohibido(*_a, **_k):  # pragma: no cover - no debe ejecutarse
        raise AssertionError("no debe haber petición sin key")

    monkeypatch.setattr(store.urllib.request, "urlopen", _prohibido)

    resultado = store.call_gemini("hola")

    assert resultado["success"] is False
    assert "GEMINI_API_KEY" in resultado["text"]


def test_la_key_del_argumento_gana_a_la_del_entorno(monkeypatch):
    monkeypatch.setenv(store.GEMINI_KEY_ENV, "AIza-del-entorno")
    urls = []

    def _falsa(request, timeout=None):
        urls.append(request.full_url)
        return _RespuestaFalsa(_respuesta_de_texto("análisis"))

    monkeypatch.setattr(store.urllib.request, "urlopen", _falsa)

    resultado = store.call_gemini("hola", api_key="AIza-de-la-peticion")

    assert resultado == {"success": True, "text": "análisis"}
    assert "AIza-de-la-peticion" in urls[0]
    assert "AIza-del-entorno" not in urls[0]


def test_un_404_de_modelo_cae_al_siguiente_modelo_de_la_lista(monkeypatch):
    """
    Google retira modelos sin avisar. Que el agente muera con la lista entera
    por probar es lo que convirtió un cambio de catálogo en una caída total.
    """
    intentos = []

    def _falsa(request, timeout=None):
        intentos.append(request.full_url)
        if len(intentos) == 1:
            raise urllib.error.HTTPError(
                request.full_url, 404, "Not Found", {},
                _cuerpo_de_error("models/x is not found for API version v1beta"))
        return _RespuestaFalsa(_respuesta_de_texto("análisis con el segundo"))

    monkeypatch.setattr(store.urllib.request, "urlopen", _falsa)

    resultado = store.call_gemini("hola", api_key="AIza-valida")

    assert resultado["success"] is True
    assert len(intentos) == 2
    assert store.GEMINI_MODELS[0] in intentos[0]
    assert store.GEMINI_MODELS[1] in intentos[1]


def test_una_key_invalida_devuelve_el_motivo_real_de_google(monkeypatch):
    """
    Antes el mensaje era "HTTP Error 400: Bad Request" y no había forma de
    saber si sobraba un espacio en la key o si el modelo no existía.
    """
    def _falsa(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {},
            _cuerpo_de_error("API key not valid. Please pass a valid API key."))

    monkeypatch.setattr(store.urllib.request, "urlopen", _falsa)

    resultado = store.call_gemini("hola", api_key="AIza-rota")

    assert resultado["success"] is False
    assert "API key not valid" in resultado["text"]


def test_un_400_de_key_no_reintenta_con_los_demas_modelos(monkeypatch):
    """Cambiar de modelo no arregla una key mala: se corta al primer intento."""
    intentos = []

    def _falsa(request, timeout=None):
        intentos.append(request.full_url)
        raise urllib.error.HTTPError(
            request.full_url, 400, "Bad Request", {},
            _cuerpo_de_error("API key not valid. Please pass a valid API key."))

    monkeypatch.setattr(store.urllib.request, "urlopen", _falsa)

    store.call_gemini("hola", api_key="AIza-rota")

    assert len(intentos) == 1


def test_una_respuesta_sin_texto_se_reporta_como_no_analizable(monkeypatch):
    monkeypatch.setattr(
        store.urllib.request, "urlopen",
        lambda request, timeout=None: _RespuestaFalsa(
            {"promptFeedback": {"blockReason": "SAFETY"}}))

    resultado = store.call_gemini("hola", api_key="AIza-valida")

    assert resultado["success"] is False
    assert "no devolvió contenido analizable" in resultado["text"]
    assert "SAFETY" in resultado["text"]


def test_un_corte_por_longitud_se_reporta_con_su_finish_reason(monkeypatch):
    monkeypatch.setattr(
        store.urllib.request, "urlopen",
        lambda request, timeout=None: _RespuestaFalsa(
            {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]}))

    resultado = store.call_gemini("hola", api_key="AIza-valida")

    assert resultado["success"] is False
    assert "MAX_TOKENS" in resultado["text"]


def test_una_respuesta_sin_candidatos_ni_motivo_tambien_se_explica(monkeypatch):
    monkeypatch.setattr(
        store.urllib.request, "urlopen",
        lambda request, timeout=None: _RespuestaFalsa({"candidates": [{"finishReason": "STOP"}]}))

    resultado = store.call_gemini("hola", api_key="AIza-valida")

    assert resultado["success"] is False
    assert "sin candidatos" in resultado["text"]


def test_un_error_http_sin_cuerpo_json_cae_al_codigo_y_la_razon(monkeypatch):
    """Un 502 del balanceador devuelve HTML: el mensaje no puede quedar vacío."""
    def _falsa(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 502, "Bad Gateway", {}, None)

    monkeypatch.setattr(store.urllib.request, "urlopen", _falsa)

    resultado = store.call_gemini("hola", api_key="AIza-valida")

    assert resultado["success"] is False
    assert "502" in resultado["text"] and "Bad Gateway" in resultado["text"]


def test_si_todos_los_modelos_dan_404_se_dice_con_el_ultimo_motivo(monkeypatch):
    def _falsa(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url, 404, "Not Found", {},
            _cuerpo_de_error("models/x is not found for API version v1beta"))

    monkeypatch.setattr(store.urllib.request, "urlopen", _falsa)

    resultado = store.call_gemini("hola", api_key="AIza-valida")

    assert resultado["success"] is False
    assert "ningún modelo disponible" in resultado["text"]
    assert "is not found" in resultado["text"]


def test_la_red_caida_no_lanza_y_lo_reporta(monkeypatch):
    def _falsa(request, timeout=None):
        raise urllib.error.URLError("temporary failure in name resolution")

    monkeypatch.setattr(store.urllib.request, "urlopen", _falsa)

    resultado = store.call_gemini("hola", api_key="AIza-valida")

    assert resultado["success"] is False
    assert "Error al consultar Gemini" in resultado["text"]


def test_se_saltan_los_candidatos_sin_texto_y_se_toma_el_que_lo_trae(monkeypatch):
    monkeypatch.setattr(
        store.urllib.request, "urlopen",
        lambda request, timeout=None: _RespuestaFalsa(
            {"candidates": [{"content": {"parts": [{"thought": True}]}},
                            {"content": {"parts": [{"text": "el análisis"}]}}]}))

    assert store.call_gemini("hola", api_key="AIza-valida")["text"] == "el análisis"


def test_verificar_la_key_manda_un_prompt_minimo(monkeypatch):
    """Verificar no puede costar lo que un reporte completo."""
    prompts = []
    monkeypatch.setattr(store, "call_gemini",
                        lambda prompt, api_key=None: prompts.append(prompt) or
                        {"success": True, "text": "OK"})

    store.verificar_gemini_key("AIza-valida")

    assert len(prompts) == 1 and len(prompts[0]) < 60


def test_el_texto_se_arma_con_todas_las_partes_de_la_respuesta(monkeypatch):
    monkeypatch.setattr(
        store.urllib.request, "urlopen",
        lambda request, timeout=None: _RespuestaFalsa(
            {"candidates": [{"content": {"parts": [{"text": "primera."},
                                                   {"text": "segunda."}]}}]}))

    assert store.call_gemini("hola", api_key="AIza-valida")["text"] == "primera.\nsegunda."


def _cuerpo_de_error(mensaje):
    """Cuerpo de error tal como lo rinde `generativelanguage.googleapis.com`."""
    import io

    return io.BytesIO(json.dumps(
        {"error": {"code": 400, "message": mensaje, "status": "INVALID_ARGUMENT"}}
    ).encode("utf-8"))


# ======================================================================
# 3. LA KEY VIAJA EN LA PETICIÓN (Vercel es sin estado)
# ======================================================================

def test_guardar_la_key_rechaza_un_formato_que_google_no_emite():
    resultado = store.save_gemini_key("mi-key")

    assert resultado["success"] is False
    assert "AIza" in resultado["message"]
    assert os.environ.get(store.GEMINI_KEY_ENV, "") == ""


def test_guardar_la_key_avisa_de_que_no_persiste_entre_invocaciones(monkeypatch):
    monkeypatch.setattr(store, "verificar_gemini_key", lambda key: {"success": True, "text": "ok"})

    resultado = store.save_gemini_key("AIza" + "b" * 31)

    assert resultado["success"] is True
    assert "no persiste" in resultado["message"].lower()


def test_guardar_la_key_la_verifica_contra_google(monkeypatch):
    """Guardar sin verificar es lo que dejaba descubrir el error tres pasos después."""
    monkeypatch.setattr(
        store, "verificar_gemini_key",
        lambda key: {"success": False, "text": "API key not valid. Please pass a valid API key."})

    resultado = store.save_gemini_key("AIza" + "c" * 31)

    assert resultado["success"] is False
    assert "API key not valid" in resultado["message"]
    assert os.environ.get(store.GEMINI_KEY_ENV, "") == ""


def test_el_agente_usa_la_key_que_llega_en_la_peticion(monkeypatch):
    """
    En Vercel cada petición puede caer en una instancia distinta, así que la key
    guardada en `os.environ` por `POST /geminiKey` no existe para el `POST
    /runQuoteAgent` siguiente. Por eso el tablero decía "Sin GEMINI_API_KEY
    configurada" justo después de guardarla.
    """
    recibidas = []

    monkeypatch.setattr(store, "fetch_quote_metrics",
                        lambda month, year: {"metrics": rules.compute_quote_metrics([], month, year)})
    monkeypatch.setattr(store, "send_to_outlook", lambda payload: {"success": True})
    monkeypatch.setattr(store, "call_gemini",
                        lambda prompt, api_key=None: recibidas.append(api_key) or
                        {"success": True, "text": "análisis"})

    respuesta = store.run_quote_metrics_agent(7, 2026, api_key="AIza-de-la-peticion")

    assert recibidas == ["AIza-de-la-peticion"]
    assert respuesta["lastRun"]["geminiOk"] is True
    assert respuesta["lastRun"]["geminiSummary"] == "análisis"


def test_el_endpoint_de_runquoteagent_reenvia_la_key_del_cuerpo(monkeypatch):
    """La cadena completa: cuerpo HTTP → `run_quote_metrics_agent` → Gemini."""
    from fastapi.testclient import TestClient

    from api.main import app

    recibidas = []
    monkeypatch.setattr(
        store, "run_quote_metrics_agent",
        lambda month, year, api_key=None: recibidas.append((month, year, api_key)) or
        {"success": True, "lastRun": {}})

    respuesta = TestClient(app).post(
        "/api/legacy/runQuoteAgent",
        json={"month": 7, "year": 2026, "geminiKey": "AIza-de-la-peticion"})

    assert respuesta.status_code == 200
    assert recibidas == [(7, 2026, "AIza-de-la-peticion")]


def test_el_endpoint_funciona_sin_key_en_el_cuerpo(monkeypatch):
    """Con `GEMINI_API_KEY` en el despliegue, el navegador no manda nada."""
    from fastapi.testclient import TestClient

    from api.main import app

    recibidas = []
    monkeypatch.setattr(
        store, "run_quote_metrics_agent",
        lambda month, year, api_key=None: recibidas.append(api_key) or
        {"success": True, "lastRun": {}})

    respuesta = TestClient(app).post("/api/legacy/runQuoteAgent", json={"month": 7, "year": 2026})

    assert respuesta.status_code == 200
    assert recibidas == [None]
