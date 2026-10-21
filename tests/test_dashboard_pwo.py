"""La Pre Work Order pide regenerar su dashboard al subir un documento.

`api/services/dashboard_pwo.py` no genera nada: le avisa al repositorio
`Agente_Full` (un `repository_dispatch` de GitHub) que hay un documento nuevo,
y el Action de allá corre los tres agentes. Aquí se prueba ese aviso:

* qué archivos lo disparan y cuáles no (una foto de la obra no reemplaza el
  dashboard);
* que solo viaje una URL del Storage de Holtmont, nunca una cualquiera;
* que el token no se filtre en ningún mensaje;
* y que la petición a GitHub tenga la forma exacta que espera el Action.

La red es la única frontera simulada: `enviar` sustituye a la llamada HTTP, y
`_post_json` se prueba aparte contra un servidor local de verdad.
"""

from __future__ import annotations

import http.server
import json
import re
import threading
from pathlib import Path
from typing import Any, Dict, List

import pytest
import yaml
from fastapi.testclient import TestClient

from api.services import dashboard_pwo

SUPABASE = "https://proyecto-prueba.supabase.co"
ARCHIVO = f"{SUPABASE}/storage/v1/object/public/archivos/2026/10/MEZANINE/Junta%20HLT.xlsx"
TOKEN = "github_pat_de_prueba_123"
ENTORNO = {
    "SUPABASE_URL": SUPABASE,
    "DASHBOARD_PWO_REPO": "Luis-py-stack/Agente_Full",
    "DASHBOARD_PWO_TOKEN": TOKEN,
    "DASHBOARD_PWO_URL": "https://holtmont-pwo.streamlit.app",
}


class GitHubDeMentiras:
    """Anota cada petición y contesta lo que se le diga."""

    def __init__(self, estado: int = 204, cuerpo: str = "") -> None:
        self.estado, self.cuerpo = estado, cuerpo
        self.peticiones: List[Dict[str, Any]] = []

    def __call__(self, url: str, cuerpo: Dict[str, Any], encabezados: Dict[str, str]):
        self.peticiones.append({"url": url, "cuerpo": cuerpo, "encabezados": encabezados})
        return self.estado, self.cuerpo


@pytest.mark.parametrize("nombre", [
    "junta.xlsx", "JUNTA.XLSX", "costos.xls", "datos.csv", "cotizacion.pdf", "minuta.docx",
    f"{SUPABASE}/storage/v1/object/public/a/Reuni%C3%B3n.xlsx?download=1",
])
def test_los_documentos_con_datos_disparan_el_dashboard(nombre):
    assert dashboard_pwo.es_archivo_de_datos(nombre) is True


@pytest.mark.parametrize("nombre", ["fachada.jpg", "recorrido.mp4", "plano.dwg", "", None, "xlsx"])
def test_fotos_videos_y_planos_cad_no_reemplazan_el_dashboard(nombre):
    assert dashboard_pwo.es_archivo_de_datos(nombre) is False


def test_la_liga_corta_se_entrega_cuando_todo_esta_configurado():
    assert dashboard_pwo.link(ENTORNO) == {
        "success": True, "url": "https://holtmont-pwo.streamlit.app", "configurado": True}


def test_sin_token_la_liga_existe_pero_el_dashboard_no_se_puede_regenerar():
    entorno = {**ENTORNO, "DASHBOARD_PWO_TOKEN": ""}

    assert dashboard_pwo.link(entorno) == {
        "success": True, "url": "https://holtmont-pwo.streamlit.app", "configurado": False}


# Repositorio y liga no son secretos (están en agente_full/README.md): si el
# despliegue no los trae, se usan los de Agente_Full. El token sí es secreto y
# es lo único que el despliegue tiene que poner.
REPO_DE_AGENTE_FULL = "Luis-py-stack/Agente_Full"
LIGA_DE_AGENTE_FULL = "https://agentefull-mhytzkjfr38ukzqxnuxbkf.streamlit.app/"
SOLO_EL_TOKEN = {"SUPABASE_URL": SUPABASE, "DASHBOARD_PWO_TOKEN": TOKEN}


def test_sin_repositorio_ni_liga_en_el_despliegue_la_liga_es_la_de_agente_full():
    assert dashboard_pwo.link(SOLO_EL_TOKEN) == {
        "success": True, "url": LIGA_DE_AGENTE_FULL, "configurado": True}


def test_con_solo_el_token_el_aviso_llega_al_repositorio_de_agente_full():
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.disparar(ARCHIVO, entorno=SOLO_EL_TOKEN, enviar=github)

    assert respuesta["success"] is True
    assert respuesta["url"] == LIGA_DE_AGENTE_FULL
    assert github.peticiones[0]["url"] == f"https://api.github.com/repos/{REPO_DE_AGENTE_FULL}/dispatches"


def test_sin_nada_configurado_solo_se_pide_el_token_y_donde_ponerlo():
    """El error del apartado: las tres variables faltaban en Vercel y se pedían las tres."""
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.procesar(ARCHIVO, "ANTONIO_SALAZAR", entorno={"SUPABASE_URL": SUPABASE},
                                       enviar=github)

    assert respuesta["success"] is False
    assert respuesta["message"] == (
        "Falta configurar DASHBOARD_PWO_TOKEN en el despliegue: agrégalo en Vercel "
        "(Settings → Environment Variables, entorno Production) y vuelve a desplegar.")
    assert respuesta["url"] == LIGA_DE_AGENTE_FULL
    assert github.peticiones == []


def test_subir_un_documento_manda_el_aviso_que_espera_el_action():
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.disparar(ARCHIVO, "1234JH Const 061026", "ANTONIO SALAZAR",
                                       entorno=ENTORNO, enviar=github)

    assert respuesta == {
        "success": True, "url": "https://holtmont-pwo.streamlit.app",
        "message": "El dashboard se está actualizando con Junta HLT.xlsx; tarda unos minutos."}
    (peticion,) = github.peticiones
    assert peticion["url"] == "https://api.github.com/repos/Luis-py-stack/Agente_Full/dispatches"
    assert peticion["cuerpo"] == {
        "event_type": "pwo_dashboard",
        "client_payload": {"file_url": ARCHIVO, "folio": "1234JH Const 061026", "usuario": "ANTONIO SALAZAR"}}
    assert peticion["encabezados"]["Authorization"] == f"Bearer {TOKEN}"
    assert peticion["encabezados"]["Accept"] == "application/vnd.github+json"


def test_la_url_viaja_sin_los_espacios_que_traiga_alrededor():
    github = GitHubDeMentiras()

    dashboard_pwo.disparar(f"  {ARCHIVO}\n", entorno=ENTORNO, enviar=github)

    assert github.peticiones[0]["cuerpo"]["client_payload"]["file_url"] == ARCHIVO


@pytest.mark.parametrize("url", [
    "https://otro-sitio.com/storage/v1/object/public/archivos/a.xlsx",
    f"{SUPABASE}/storage/v1/object/sign/archivos/a.xlsx?token=x",
    f"{SUPABASE}.atacante.com/storage/v1/object/public/archivos/a.xlsx",
    f"{SUPABASE}/storage/v1/object/public/../sign/a.xlsx",
    "",
])
def test_solo_viajan_documentos_del_storage_de_holtmont(url):
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.disparar(url, entorno=ENTORNO, enviar=github)

    assert respuesta["success"] is False
    assert "Storage de Holtmont" in respuesta["message"]
    assert github.peticiones == []


def test_sin_supabase_configurado_no_se_acepta_ninguna_url():
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.disparar(ARCHIVO, entorno={**ENTORNO, "SUPABASE_URL": ""}, enviar=github)

    assert respuesta["success"] is False
    assert github.peticiones == []


def test_una_foto_no_dispara_el_dashboard_aunque_venga_del_storage():
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.disparar(f"{SUPABASE}/storage/v1/object/public/a/fachada.jpg",
                                       entorno=ENTORNO, enviar=github)

    assert respuesta == {"success": False, "url": "https://holtmont-pwo.streamlit.app",
                         "message": "fachada.jpg no es un documento con datos (xlsx, xls, csv, pdf o docx)."}
    assert github.peticiones == []


def test_sin_token_se_dice_que_falta_y_no_se_llama_a_github():
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.disparar(ARCHIVO, entorno={**ENTORNO, "DASHBOARD_PWO_TOKEN": "  "}, enviar=github)

    assert respuesta["success"] is False
    assert "DASHBOARD_PWO_TOKEN" in respuesta["message"]
    assert github.peticiones == []


@pytest.mark.parametrize("en_blanco, esperado", [
    ("DASHBOARD_PWO_REPO", f"https://api.github.com/repos/{REPO_DE_AGENTE_FULL}/dispatches"),
    ("DASHBOARD_PWO_URL", LIGA_DE_AGENTE_FULL),
])
def test_repositorio_o_liga_en_blanco_toman_los_de_agente_full(en_blanco, esperado):
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.disparar(ARCHIVO, entorno={**ENTORNO, en_blanco: "  "}, enviar=github)

    assert respuesta["success"] is True
    assert esperado in (respuesta["url"], github.peticiones[0]["url"])


@pytest.mark.parametrize("repo", ["Agente_Full", "dueño/Agente_Full", "a/b/../../orgs/x", "a/b?x=1"])
def test_un_repositorio_mal_escrito_no_arma_una_url_de_github(repo):
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.disparar(ARCHIVO, entorno={**ENTORNO, "DASHBOARD_PWO_REPO": repo}, enviar=github)

    assert respuesta["success"] is False
    assert "DASHBOARD_PWO_REPO" in respuesta["message"]
    assert github.peticiones == []


def test_un_rechazo_de_github_se_reporta_sin_filtrar_el_token():
    github = GitHubDeMentiras(401, json.dumps({"message": f"Bad credentials {TOKEN}"}))

    respuesta = dashboard_pwo.disparar(ARCHIVO, entorno=ENTORNO, enviar=github)

    assert respuesta["success"] is False
    assert "GitHub respondió 401" in respuesta["message"]
    assert TOKEN not in respuesta["message"]
    assert "***" in respuesta["message"]


def test_sin_red_se_reporta_en_vez_de_tronar():
    def sin_red(url, cuerpo, encabezados):
        raise OSError("Name or service not known")

    respuesta = dashboard_pwo.disparar(ARCHIVO, entorno=ENTORNO, enviar=sin_red)

    assert respuesta["success"] is False
    assert "No se pudo avisar a GitHub: Name or service not known" == respuesta["message"]


# --- La llamada HTTP de verdad, contra un servidor local --------------------

class _GitHubLocal(http.server.BaseHTTPRequestHandler):
    recibido: Dict[str, Any] = {}
    estado = 204

    def do_POST(self) -> None:
        largo = int(self.headers["Content-Length"])
        _GitHubLocal.recibido = {"ruta": self.path, "cuerpo": json.loads(self.rfile.read(largo)),
                                 "autorizacion": self.headers["Authorization"],
                                 "tipo": self.headers["Content-Type"]}
        self.send_response(self.estado)
        self.end_headers()
        if self.estado >= 400:
            self.wfile.write(b'{"message": "Not Found"}')

    def do_GET(self) -> None:
        _GitHubLocal.recibido = {"ruta": self.path, "autorizacion": self.headers["Authorization"],
                                 "metodo": self.command}
        self.send_response(self.estado)
        self.end_headers()
        self.wfile.write(b'{"workflow_runs": []}' if self.estado < 400 else b'{"message": "Not Found"}')

    def log_message(self, *args) -> None:
        return


@pytest.fixture
def github_local():
    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _GitHubLocal)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{servidor.server_address[1]}"
    servidor.shutdown()
    _GitHubLocal.estado = 204


def test_post_json_manda_el_cuerpo_y_los_encabezados(github_local):
    estado, texto = dashboard_pwo._post_json(f"{github_local}/repos/o/r/dispatches", {"event_type": "x"},
                                            {"Authorization": "Bearer t"})

    assert (estado, texto) == (204, "")
    assert _GitHubLocal.recibido == {"ruta": "/repos/o/r/dispatches", "cuerpo": {"event_type": "x"},
                                     "autorizacion": "Bearer t", "tipo": "application/json"}


def test_post_json_devuelve_el_error_de_github_sin_lanzar(github_local):
    _GitHubLocal.estado = 404

    assert dashboard_pwo._post_json(f"{github_local}/x", {}, {}) == (404, '{"message": "Not Found"}')


def test_get_json_pide_con_el_token_y_devuelve_el_cuerpo(github_local):
    _GitHubLocal.estado = 200

    estado, texto = dashboard_pwo._get_json(f"{github_local}/repos/o/r/actions/runs?event=x",
                                           {"Authorization": "Bearer t"})

    assert (estado, json.loads(texto)) == (200, {"workflow_runs": []})
    assert _GitHubLocal.recibido == {"ruta": "/repos/o/r/actions/runs?event=x", "autorizacion": "Bearer t",
                                     "metodo": "GET"}


def test_get_json_devuelve_el_error_de_github_sin_lanzar(github_local):
    _GitHubLocal.estado = 404

    assert dashboard_pwo._get_json(f"{github_local}/x", {}) == (404, '{"message": "Not Found"}')


# --- Apartado Dashboard Streamlit: procesar ---------------------------------

def test_procesar_manda_una_solicitud_en_el_aviso_y_la_devuelve_para_seguirla():
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.procesar(ARCHIVO, "ANTONIO_SALAZAR", entorno=ENTORNO, enviar=github)

    (peticion,) = github.peticiones
    carga = peticion["cuerpo"]["client_payload"]
    assert respuesta["success"] is True
    assert respuesta["url"] == "https://holtmont-pwo.streamlit.app"
    assert respuesta["solicitud"] == carga["solicitud"]
    assert re.fullmatch(r"[0-9a-f]{12}", carga["solicitud"])
    assert carga == {"file_url": ARCHIVO, "folio": "", "usuario": "ANTONIO_SALAZAR",
                     "solicitud": respuesta["solicitud"]}
    assert peticion["cuerpo"]["event_type"] == dashboard_pwo.EVENTO


def test_cada_procesamiento_lleva_su_propia_solicitud():
    github = GitHubDeMentiras()

    primera = dashboard_pwo.procesar(ARCHIVO, entorno=ENTORNO, enviar=github)["solicitud"]
    segunda = dashboard_pwo.procesar(ARCHIVO, entorno=ENTORNO, enviar=github)["solicitud"]

    assert primera != segunda


def test_si_el_aviso_no_sale_no_se_entrega_solicitud_que_seguir():
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.procesar(ARCHIVO, entorno={**ENTORNO, "DASHBOARD_PWO_TOKEN": ""}, enviar=github)

    assert respuesta["success"] is False
    assert "solicitud" not in respuesta
    assert "DASHBOARD_PWO_TOKEN" in respuesta["message"]
    assert github.peticiones == []


def test_procesar_solo_acepta_documentos_del_storage_de_holtmont():
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.procesar("https://otro-sitio.com/a.xlsx", entorno=ENTORNO, enviar=github)

    assert respuesta["success"] is False
    assert github.peticiones == []


# --- Apartado Dashboard Streamlit: seguir la corrida del Action -------------

SOLICITUD = "0123456789ab"


class CorridasDeMentiras:
    """El listado de corridas de GitHub: anota la consulta y contesta lo que se le diga."""

    def __init__(self, corridas: List[Dict[str, Any]] = (), estado: int = 200, texto: str = "") -> None:
        self.estado = estado
        self.texto = texto or json.dumps({"total_count": len(corridas), "workflow_runs": list(corridas)})
        self.consultas: List[Dict[str, Any]] = []

    def __call__(self, url: str, encabezados: Dict[str, str]):
        self.consultas.append({"url": url, "encabezados": encabezados})
        return self.estado, self.texto


def _corrida(status: str, conclusion: Any = None, solicitud: str = SOLICITUD) -> Dict[str, Any]:
    return {"id": 1, "display_title": dashboard_pwo.TITULO_DE_CORRIDA.format(solicitud=solicitud),
            "status": status, "conclusion": conclusion,
            "html_url": "https://github.com/Luis-py-stack/Agente_Full/actions/runs/1"}


def test_se_pregunta_a_github_por_las_corridas_del_aviso_con_el_token():
    github = CorridasDeMentiras()

    dashboard_pwo.estado(SOLICITUD, entorno=ENTORNO, consultar=github)

    (consulta,) = github.consultas
    assert consulta["url"] == ("https://api.github.com/repos/Luis-py-stack/Agente_Full/actions/runs"
                               "?event=repository_dispatch&per_page=50")
    assert consulta["encabezados"]["Authorization"] == f"Bearer {TOKEN}"
    assert consulta["encabezados"]["Accept"] == "application/vnd.github+json"


def test_mientras_github_no_crea_la_corrida_se_dice_que_no_ha_iniciado():
    otra = _corrida("in_progress", solicitud="ffffffffffff")
    vieja = {**_corrida("completed", "success"), "display_title": "Dashboard PWO"}

    respuesta = dashboard_pwo.estado(SOLICITUD, entorno=ENTORNO, consultar=CorridasDeMentiras([otra, vieja]))

    assert respuesta["success"] is True
    assert respuesta["estado"] == "SIN_INICIAR"
    assert respuesta["run_url"] == ""


@pytest.mark.parametrize("status,esperado", [
    ("queued", "EN_COLA"), ("waiting", "EN_COLA"), ("requested", "EN_COLA"), ("pending", "EN_COLA"),
    ("in_progress", "PROCESANDO"),
])
def test_una_corrida_sin_terminar_se_reporta_en_marcha(status, esperado):
    respuesta = dashboard_pwo.estado(SOLICITUD, entorno=ENTORNO, consultar=CorridasDeMentiras([_corrida(status)]))

    assert respuesta["success"] is True
    assert respuesta["estado"] == esperado
    assert respuesta["run_url"].endswith("/actions/runs/1")


def test_al_terminar_bien_se_entrega_la_liga_corta_y_el_repositorio():
    corridas = CorridasDeMentiras([_corrida("in_progress", solicitud="ffffffffffff"),
                                   _corrida("completed", "success")])

    respuesta = dashboard_pwo.estado(SOLICITUD, entorno=ENTORNO, consultar=corridas)

    assert respuesta == {
        "success": True, "estado": "EXITOSO", "message": "Dashboard generado en GitHub.",
        "url": "https://holtmont-pwo.streamlit.app",
        "repo_url": "https://github.com/Luis-py-stack/Agente_Full",
        "run_url": "https://github.com/Luis-py-stack/Agente_Full/actions/runs/1"}


@pytest.mark.parametrize("conclusion,frase", [
    ("failure", "dashboard anterior"),
    ("cancelled", "Se canceló"),
    ("timed_out", "tiempo máximo"),
    ("action_required", "'action_required'"),
    (None, "''"),
])
def test_una_corrida_que_no_termina_bien_se_reporta_como_error(conclusion, frase):
    corridas = CorridasDeMentiras([_corrida("completed", conclusion)])

    respuesta = dashboard_pwo.estado(SOLICITUD, entorno=ENTORNO, consultar=corridas)

    assert respuesta["success"] is True
    assert respuesta["estado"] == "ERROR"
    assert frase in respuesta["message"]


@pytest.mark.parametrize("solicitud", ["", "  ", "0123456789AB", "0123456789abc", "0123456789a",
                                       "0123456789a\n", "../../orgs/x", "0123456789ag"])
def test_una_solicitud_mal_formada_no_llega_a_github(solicitud):
    github = CorridasDeMentiras()

    respuesta = dashboard_pwo.estado(solicitud, entorno=ENTORNO, consultar=github)

    assert respuesta["success"] is False
    assert "solicitud" in respuesta["message"]
    assert github.consultas == []


def test_la_solicitud_se_acepta_con_espacios_alrededor():
    respuesta = dashboard_pwo.estado(f" {SOLICITUD}\n", entorno=ENTORNO,
                                     consultar=CorridasDeMentiras([_corrida("completed", "success")]))

    assert respuesta["estado"] == "EXITOSO"


def test_sin_token_no_se_pregunta_a_github():
    github = CorridasDeMentiras()

    respuesta = dashboard_pwo.estado(SOLICITUD, entorno={**ENTORNO, "DASHBOARD_PWO_TOKEN": ""}, consultar=github)

    assert respuesta["success"] is False
    assert "DASHBOARD_PWO_TOKEN" in respuesta["message"]
    assert github.consultas == []


def test_con_solo_el_token_se_sigue_la_corrida_en_agente_full():
    github = CorridasDeMentiras([_corrida("completed", "success")])

    respuesta = dashboard_pwo.estado(SOLICITUD, entorno=SOLO_EL_TOKEN, consultar=github)

    assert respuesta["estado"] == "EXITOSO"
    assert respuesta["url"] == LIGA_DE_AGENTE_FULL
    assert respuesta["repo_url"] == f"https://github.com/{REPO_DE_AGENTE_FULL}"
    assert github.consultas[0]["url"].startswith(f"https://api.github.com/repos/{REPO_DE_AGENTE_FULL}/actions/runs")


def test_con_el_repositorio_mal_escrito_no_se_arma_la_liga_del_repositorio():
    github = CorridasDeMentiras()

    respuesta = dashboard_pwo.estado(SOLICITUD, entorno={**ENTORNO, "DASHBOARD_PWO_REPO": "a/b/../c"},
                                     consultar=github)

    assert respuesta["success"] is False
    assert respuesta["repo_url"] == ""
    assert "DASHBOARD_PWO_REPO" in respuesta["message"]
    assert github.consultas == []


@pytest.mark.parametrize("codigo", [403, 404])
def test_un_token_sin_permiso_de_actions_se_explica_sin_filtrarlo(codigo):
    github = CorridasDeMentiras(estado=codigo, texto=json.dumps({"message": f"Resource not accessible {TOKEN}"}))

    respuesta = dashboard_pwo.estado(SOLICITUD, entorno=ENTORNO, consultar=github)

    assert respuesta["success"] is False
    assert f"GitHub respondió {codigo}" in respuesta["message"]
    assert "Actions: Read" in respuesta["message"]
    assert TOKEN not in respuesta["message"]


def test_otro_rechazo_de_github_se_reporta_sin_la_pista_de_permisos():
    github = CorridasDeMentiras(estado=500, texto="Server Error")

    respuesta = dashboard_pwo.estado(SOLICITUD, entorno=ENTORNO, consultar=github)

    assert respuesta["message"] == "GitHub respondió 500: Server Error"


def test_sin_red_el_seguimiento_se_reporta_sin_filtrar_el_token():
    def sin_red(url, encabezados):
        raise OSError(f"timed out con {TOKEN}")

    respuesta = dashboard_pwo.estado(SOLICITUD, entorno=ENTORNO, consultar=sin_red)

    assert respuesta["success"] is False
    assert respuesta["message"] == "No se pudo consultar a GitHub: timed out con ***"


@pytest.mark.parametrize("texto", ["no es json", "[1, 2]", '{"workflow_runs": null}', '{"workflow_runs": [1]}'])
def test_una_respuesta_rara_de_github_cuenta_como_corrida_no_encontrada(texto):
    respuesta = dashboard_pwo.estado(SOLICITUD, entorno=ENTORNO, consultar=CorridasDeMentiras(texto=texto))

    assert respuesta["success"] is True
    assert respuesta["estado"] == "SIN_INICIAR"


# --- Los endpoints ----------------------------------------------------------

@pytest.fixture
def cliente(monkeypatch):
    for clave, valor in ENTORNO.items():
        monkeypatch.setenv(clave, valor)
    from api.main import app

    return TestClient(app)


def test_el_endpoint_dispara_con_la_configuracion_del_despliegue(cliente, monkeypatch):
    github = GitHubDeMentiras()
    monkeypatch.setattr(dashboard_pwo, "_post_json", github)

    respuesta = cliente.post("/api/pwo/dashboard", json={"fileUrl": ARCHIVO, "folio": "1234", "usuario": "ADMIN"})

    assert respuesta.status_code == 200
    assert respuesta.json()["success"] is True
    assert github.peticiones[0]["cuerpo"]["client_payload"] == {"file_url": ARCHIVO, "folio": "1234", "usuario": "ADMIN"}


def test_el_endpoint_acepta_la_peticion_sin_folio(cliente, monkeypatch):
    github = GitHubDeMentiras()
    monkeypatch.setattr(dashboard_pwo, "_post_json", github)

    respuesta = cliente.post("/api/pwo/dashboard", json={"fileUrl": ARCHIVO})

    assert respuesta.json()["success"] is True
    assert github.peticiones[0]["cuerpo"]["client_payload"]["folio"] == ""


def test_el_endpoint_de_la_liga_corta(cliente):
    assert cliente.get("/api/pwo/dashboard").json() == {
        "success": True, "url": "https://holtmont-pwo.streamlit.app", "configurado": True}


def test_el_endpoint_procesar_avisa_con_solicitud(cliente, monkeypatch):
    github = GitHubDeMentiras()
    monkeypatch.setattr(dashboard_pwo, "_post_json", github)

    respuesta = cliente.post("/api/dashboard/procesar", json={"fileUrl": ARCHIVO, "usuario": "ANTONIO_SALAZAR"})

    cuerpo = respuesta.json()
    assert respuesta.status_code == 200
    assert cuerpo["success"] is True
    assert github.peticiones[0]["cuerpo"]["client_payload"] == {
        "file_url": ARCHIVO, "folio": "", "usuario": "ANTONIO_SALAZAR", "solicitud": cuerpo["solicitud"]}


def test_el_endpoint_procesar_acepta_la_peticion_sin_usuario(cliente, monkeypatch):
    github = GitHubDeMentiras()
    monkeypatch.setattr(dashboard_pwo, "_post_json", github)

    cliente.post("/api/dashboard/procesar", json={"fileUrl": ARCHIVO})

    assert github.peticiones[0]["cuerpo"]["client_payload"]["usuario"] == ""


def test_el_endpoint_de_estado_sigue_la_corrida(cliente, monkeypatch):
    monkeypatch.setattr(dashboard_pwo, "_get_json", CorridasDeMentiras([_corrida("completed", "success")]))

    cuerpo = cliente.get("/api/dashboard/estado", params={"solicitud": SOLICITUD}).json()

    assert cuerpo["estado"] == "EXITOSO"
    assert cuerpo["url"] == "https://holtmont-pwo.streamlit.app"


def test_el_endpoint_de_estado_exige_la_solicitud(cliente):
    assert cliente.get("/api/dashboard/estado").status_code == 422


# --- El contrato con el Action de Agente_Full -------------------------------

def _workflow() -> Dict[str, Any]:
    ruta = Path(__file__).resolve().parent.parent / "agente_full" / "workflow_dashboard_pwo.yml"
    with open(ruta, encoding="utf-8") as archivo:
        return yaml.safe_load(archivo)


def test_el_action_escucha_el_mismo_evento_que_manda_holtmont():
    # PyYAML lee la clave `on:` como el booleano True.
    assert _workflow()[True]["repository_dispatch"]["types"] == [dashboard_pwo.EVENTO]


def test_la_corrida_del_action_lleva_la_solicitud_en_el_nombre_que_busca_el_seguimiento():
    """Sin esto `estado` nunca encuentra la corrida y la pantalla se queda en "Cargando..."."""
    esperado = dashboard_pwo.TITULO_DE_CORRIDA.format(solicitud="${{ github.event.client_payload.solicitud }}")

    assert _workflow()["run-name"] == esperado


def test_el_action_lee_las_claves_que_manda_holtmont():
    pasos = _workflow()["jobs"]["generar"]["steps"]
    generar = next(p for p in pasos if p.get("name") == "Generar y validar el dashboard")

    assert "client_payload.file_url" in generar["env"]["FILE_URL"]
    assert "client_payload.folio" in generar["env"]["FOLIO"]


def test_ningun_paso_del_action_mete_datos_del_usuario_directo_al_shell():
    for paso in _workflow()["jobs"]["generar"]["steps"]:
        assert "${{" not in paso.get("run", ""), paso.get("name")


def test_el_codigo_generado_corre_sin_token_de_github_ni_credenciales_en_git():
    trabajo = _workflow()["jobs"]["generar"]
    checkout = trabajo["steps"][0]
    generar = next(p for p in trabajo["steps"] if p.get("name") == "Generar y validar el dashboard")

    assert checkout["with"]["persist-credentials"] is False
    assert not any("GITHUB_TOKEN" in str(valor) or "GH_TOKEN" in clave for clave, valor in generar["env"].items())
    assert _workflow()["concurrency"]["cancel-in-progress"] is False


def test_el_codigo_generado_corre_como_un_usuario_sin_sudo_que_el_action_crea_antes():
    pasos = _workflow()["jobs"]["generar"]["steps"]
    nombres = [p.get("name") for p in pasos]
    generar = pasos[nombres.index("Generar y validar el dashboard")]
    crear = pasos[nombres.index("Crear el usuario aislado")]

    assert nombres.index("Crear el usuario aislado") < nombres.index("Generar y validar el dashboard")
    assert generar["env"]["USUARIO_AISLADO"] in crear["run"].split()
    assert generar["env"]["TMPDIR"] == "/tmp"
