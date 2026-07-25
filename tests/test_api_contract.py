"""
Contrato de la migración a Python:
  index.html  ->  api_service.js (adaptador)  ->  api/main.py (FastAPI)

Verifica estáticamente (sin levantar el servidor ni requerir credenciales)
que cada función que el frontend invoca por `google.script.run` tenga su
método en el adaptador, y que cada ruta que el adaptador llama exista
realmente en `api/main.py` delegando al motor de reglas.

Ejecución:  python -m pytest tests/test_api_contract.py -v
"""

import ast
import os
import py_compile
import re
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(ROOT, "api", "main.py")
ADAPTER_JS = os.path.join(ROOT, "api_service.js")
INDEX_HTML = os.path.join(ROOT, "index.html")

# Endpoints que la migración debe exponer, con el equivalente en CODIGO.js.
ENDPOINTS_REQUERIDOS = {
    ("POST", "/api/legacy/saveTrackerBatch"): "apiSaveTrackerBatch",
    ("POST", "/api/legacy/updateTask"): "apiUpdateTask",
    ("POST", "/api/legacy/updatePPCV3"): "apiUpdatePPCV3",
    ("GET", "/api/legacy/weeklyPlan"): "apiFetchWeeklyPlanData",
    ("GET", "/api/legacy/salesHistory"): "apiFetchSalesHistory",
    ("GET", "/api/legacy/quoteMetrics"): "apiFetchQuoteAgentMetrics",
    ("POST", "/api/legacy/runQuoteAgent"): "runQuoteMetricsAgent",
    ("GET", "/api/legacy/lastAgentReport"): "apiGetLastAgentReport",
    ("POST", "/api/legacy/writeQuoteMetrics"): "apiWriteQuoteMetricsToSheet",
    ("GET", "/api/legacy/geminiKey"): "apiCheckGeminiKey",
    ("POST", "/api/legacy/geminiKey"): "apiSaveGeminiKey",
    ("POST", "/api/legacy/trackerProductivity"): "runTrackerProductivityAgent",
    ("GET", "/api/legacy/infoBankCompanies"): "apiFetchInfoBankCompanies",
    ("POST", "/api/legacy/logDateChange"): "apiLogDateChange",
    ("POST", "/api/legacy/resyncDirectory"): "apiResyncDirectory",
    ("GET", "/api/legacy/unifiedAgenda"): "apiFetchUnifiedAgenda",
}

# Métodos del adaptador que NO pueden seguir siendo stubs: escriben datos.
METODOS_CRITICOS = [
    "apiSaveTrackerBatch",
    "apiUpdateTask",
    "apiUpdatePPCV3",
    "apiFetchWeeklyPlanData",
    "apiFetchSalesHistory",
]


def leer(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def rutas_de_main():
    """(método, ruta) -> nombre de la función que la atiende."""
    arbol = ast.parse(leer(MAIN_PY))
    rutas = {}
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in nodo.decorator_list:
            if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                continue
            metodo = dec.func.attr.upper()
            if metodo not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
                continue
            if not dec.args or not isinstance(dec.args[0], ast.Constant):
                continue
            rutas[(metodo, dec.args[0].value)] = nodo
    return rutas


@pytest.fixture(scope="module")
def rutas():
    return rutas_de_main()


def test_main_py_compila():
    with tempfile.TemporaryDirectory() as tmp:
        py_compile.compile(MAIN_PY, cfile=os.path.join(tmp, "main.pyc"), doraise=True)


@pytest.mark.parametrize("clave,equivalente", sorted(ENDPOINTS_REQUERIDOS.items()))
def test_endpoint_existe_en_main(rutas, clave, equivalente):
    assert clave in rutas, f"Falta {clave[0]} {clave[1]} en api/main.py (equivalente de {equivalente})"


def test_endpoints_delegan_al_motor_de_reglas(rutas):
    """Los endpoints legacy no reimplementan la lógica: usan tracker_store/tracker_rules."""
    sin_delegar = []
    for (metodo, ruta), funcion in rutas.items():
        if not ruta.startswith("/api/legacy/"):
            continue
        cuerpo = ast.dump(funcion)
        if "tracker_store" not in cuerpo and "tracker_rules" not in cuerpo and "get_directory_from_db" not in cuerpo:
            sin_delegar.append(f"{metodo} {ruta}")
    assert not sin_delegar, f"Endpoints que no delegan al motor de reglas: {sin_delegar}"


def test_endpoints_declarados_antes_del_static_mount():
    """StaticFiles montado en '/' debe ir al final o capturaría las rutas de API."""
    contenido = leer(MAIN_PY)
    mount = contenido.index('app.mount("/", StaticFiles')
    ultimo_endpoint = contenido.rindex('@app.post("/api/legacy/')
    assert ultimo_endpoint < mount, "Hay endpoints declarados después del mount de StaticFiles"


def metodos_del_adaptador():
    js = leer(ADAPTER_JS)
    cuerpo = js[js.index("class GoogleScriptRunAdapter"):]
    return {m.group(1): m.group(0) for m in re.finditer(r"^    ([A-Za-z0-9_]+)\(", cuerpo, re.MULTILINE)}


def cuerpo_de_metodo(nombre):
    js = leer(ADAPTER_JS)
    patron = re.compile(rf"^    {re.escape(nombre)}\([^)]*\)\s*\{{(.*?)^    \}}", re.MULTILINE | re.DOTALL)
    m = patron.search(js)
    return m.group(1) if m else ""


@pytest.mark.parametrize("metodo", METODOS_CRITICOS)
def test_metodos_criticos_no_son_stubs(metodo):
    cuerpo = cuerpo_de_metodo(metodo)
    assert cuerpo, f"{metodo} no está definido en el adaptador"
    assert "not implemented" not in cuerpo and "stub" not in cuerpo.lower(), f"{metodo} sigue siendo un stub"
    assert "_post(" in cuerpo or "_call(" in cuerpo or "fetch(" in cuerpo, f"{metodo} no llama al backend"


def test_frontend_no_llama_metodos_inexistentes_en_el_adaptador():
    """Todo `google.script.run.apiX()` de index.html debe existir en el adaptador."""
    html = leer(INDEX_HTML)
    llamadas = {m.group(1) for m in re.finditer(r"\.\s*((?:api|run)[A-Za-z0-9_]*)\s*\(", html)}
    definidos = set(metodos_del_adaptador())
    faltantes = sorted(llamadas - definidos)
    assert not faltantes, f"El adaptador no implementa: {faltantes}"


def test_rutas_usadas_por_el_adaptador_existen_en_main(rutas):
    """Cada endpoint que llama el adaptador debe existir realmente en FastAPI."""
    js = leer(ADAPTER_JS)
    rutas_declaradas = {ruta for _, ruta in rutas}
    referencias = set()

    for m in re.finditer(r"_post\(\s*[`'\"]([^`'\"?]+)", js):
        referencias.add(("POST", m.group(1)))
    for m in re.finditer(r"_call\(\s*[`'\"]([^`'\"?]+)", js):
        referencias.add(("GET", m.group(1)))
    for m in re.finditer(r"fetch\(`\$\{API_BASE_URL\}([^`?]+)", js):
        ruta = m.group(1)
        if "${" in ruta:      # el helper genérico _call recibe la ruta por parámetro
            continue
        referencias.add(("ANY", ruta))

    faltantes = sorted(
        f"{metodo} {ruta}" for metodo, ruta in referencias
        if ruta not in rutas_declaradas
    )
    assert not faltantes, f"El adaptador llama rutas inexistentes en main.py: {faltantes}"


def test_todos_los_metodos_del_agente_de_metricas_estan_mapeados():
    definidos = set(metodos_del_adaptador())
    requeridos = {
        "apiFetchQuoteAgentMetrics", "runQuoteMetricsAgent", "apiGetLastAgentReport",
        "apiWriteQuoteMetricsToSheet", "apiCheckGeminiKey", "apiSaveGeminiKey",
        "runTrackerProductivityAgent", "apiResyncDirectory", "apiLogDateChange",
        "apiFetchInfoBankCompanies", "runPaperclipAgents",
    }
    assert requeridos.issubset(definidos), f"Faltan en el adaptador: {sorted(requeridos - definidos)}"
