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


@pytest.mark.parametrize("faltante", ["DASHBOARD_PWO_REPO", "DASHBOARD_PWO_TOKEN", "DASHBOARD_PWO_URL"])
def test_sin_configuracion_se_dice_que_falta_y_no_se_llama_a_github(faltante):
    github = GitHubDeMentiras()

    respuesta = dashboard_pwo.disparar(ARCHIVO, entorno={**ENTORNO, faltante: "  "}, enviar=github)

    assert respuesta["success"] is False
    assert faltante in respuesta["message"]
    assert github.peticiones == []


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


# --- El contrato con el Action de Agente_Full -------------------------------

def _workflow() -> Dict[str, Any]:
    ruta = Path(__file__).resolve().parent.parent / "agente_full" / "workflow_dashboard_pwo.yml"
    with open(ruta, encoding="utf-8") as archivo:
        return yaml.safe_load(archivo)


def test_el_action_escucha_el_mismo_evento_que_manda_holtmont():
    # PyYAML lee la clave `on:` como el booleano True.
    assert _workflow()[True]["repository_dispatch"]["types"] == [dashboard_pwo.EVENTO]


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
