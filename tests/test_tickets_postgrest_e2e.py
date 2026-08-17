"""
Reportar un bug de punta a punta **sobre el motor de producción**.

El resto de la suite prueba los tickets contra `MemoryEngine`, que es el doble.
Aquí se levanta un PostgREST falso —un `http.server` que habla el mismo
protocolo: `select` por query string, `Prefer: return=representation` en el
alta— y se apunta `PostgrestEngine` a él. Así se ejerce el camino real
(urllib, cabeceras, paginación, traducción de errores) sin tocar ninguna base.

Existe por lo que pasó el 2026-08-17: el formulario devolvía "vuelve a
intentarlo" a todo el mundo, y con las pruebas en verde sobre `MemoryEngine` no
había forma de distinguir si el alta funcionaba contra PostgREST o no. La
diferencia que importaba estaba justo ahí: `MemoryEngine` no tiene la UNIQUE de
`folio`, así que el choque de folios —la causa real del bloqueo— era invisible
para toda la suite. El doble de aquí sí la impone.

Cubre: que un ticket se manda y se guarda; que la evidencia se agrega sin tocar
lo reportado; el estado exacto de la base el día del bloqueo; dos altas
simultáneas; y qué se ve en pantalla cuando falta la tabla o cuando la clave
del backend no puede escribir (RLS encendida sin políticas, DDL §5).
"""

from __future__ import annotations

import json
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List

import pytest

from backend.core.engines.postgrest import PostgrestEngine
from backend.core.errors import ErrorDeMotor
from backend.repositories.tickets import TicketRepository
from backend.routers.tickets import _fallo_de_motor
from backend.schemas.ticket import TicketWrite

CLAVE_FALSA = "clave-de-prueba-no-es-un-secreto"


class _PostgrestFalso:
    """Las tres operaciones que usa el sistema de tickets, y nada más."""

    def __init__(self) -> None:
        self.tablas: Dict[str, List[Dict[str, Any]]] = {
            "bug_tickets": [],
            "ticket_notificaciones": [],
        }
        # Con la clave `anon` la base deja leer vacío pero rechaza el INSERT:
        # es exactamente lo que hace RLS encendida y sin políticas.
        self.escritura_denegada = False
        self.servidor: ThreadingHTTPServer | None = None

    @property
    def url(self) -> str:
        assert self.servidor is not None
        host, puerto = self.servidor.server_address[:2]
        return f"http://{host}:{puerto}"


@pytest.fixture
def postgrest_falso(monkeypatch):
    estado = _PostgrestFalso()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silencio en la salida de pytest
            pass

        def _responder(self, codigo: int, cuerpo: Any) -> None:
            crudo = json.dumps(cuerpo).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(crudo)))
            self.end_headers()
            self.wfile.write(crudo)

        def _tabla(self) -> str:
            ruta = urllib.parse.urlparse(self.path).path
            return ruta.rsplit("/", 1)[-1]

        def do_GET(self) -> None:  # noqa: N802 - lo impone http.server
            tabla = self._tabla()
            if tabla not in estado.tablas:
                self._responder(404, {"code": "PGRST205", "message": "Could not find the table"})
                return
            consulta = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            filas = estado.tablas[tabla]
            for columna, valores in consulta.items():
                if columna in {"select", "offset", "limit", "order"}:
                    continue
                esperado = valores[0].removeprefix("eq.")
                filas = [f for f in filas if str(f.get(columna)) == esperado]
            desde = int(consulta.get("offset", ["0"])[0])
            hasta = desde + int(consulta.get("limit", ["1000"])[0])
            self._responder(200, filas[desde:hasta])

        def do_POST(self) -> None:  # noqa: N802
            tabla = self._tabla()
            if tabla not in estado.tablas:
                self._responder(404, {"code": "PGRST205", "message": "Could not find the table"})
                return
            if estado.escritura_denegada:
                self._responder(401, {
                    "code": "42501",
                    "message": "new row violates row-level security policy",
                })
                return
            largo = int(self.headers.get("Content-Length", "0"))
            nuevas = json.loads(self.rfile.read(largo) or b"[]")
            consulta = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            clave = consulta.get("on_conflict", [""])[0]

            if clave:  # upsert: fusiona sobre la fila que ya está
                guardadas = []
                for fila in nuevas:
                    previas = [f for f in estado.tablas[tabla] if f.get(clave) == fila.get(clave)]
                    fusionada = {**(previas[0] if previas else {"id": str(uuid.uuid4())}), **fila}
                    if previas:
                        estado.tablas[tabla][estado.tablas[tabla].index(previas[0])] = fusionada
                    else:
                        estado.tablas[tabla].append(fusionada)
                    guardadas.append(fusionada)
                devuelve = "return=representation" in (self.headers.get("Prefer") or "")
                self._responder(200, guardadas if devuelve else [])
                return

            # INSERT liso. `folio` es UNIQUE en `bug_tickets` (DDL §5): sin esta
            # restricción el doble no reproduce el fallo que tuvo el sistema
            # bloqueado desde el 2026-08-13.
            tomados = {f.get("folio") for f in estado.tablas[tabla]}
            if tabla == "bug_tickets" and any(f.get("folio") in tomados for f in nuevas):
                self._responder(409, {
                    "code": "23505",
                    "message": 'duplicate key value violates unique constraint "bug_tickets_folio_key"',
                })
                return
            guardadas = [{"id": str(uuid.uuid4()), **fila} for fila in nuevas]
            estado.tablas[tabla].extend(guardadas)
            devuelve = "return=representation" in (self.headers.get("Prefer") or "")
            self._responder(201, guardadas if devuelve else [])

    servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    estado.servidor = servidor
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    # urllib honra el proxy del entorno: sin esto la petición a 127.0.0.1 sale
    # por el proxy HTTPS del contenedor y nunca llega al servidor de prueba.
    for nombre in ("no_proxy", "NO_PROXY"):
        monkeypatch.setenv(nombre, "127.0.0.1,localhost")
    try:
        yield estado
    finally:
        servidor.shutdown()
        servidor.server_close()
        hilo.join(timeout=5)


@pytest.fixture
def repo_postgrest(postgrest_falso) -> TicketRepository:
    return TicketRepository(PostgrestEngine(postgrest_falso.url, CLAVE_FALSA))


def test_se_puede_mandar_un_ticket_contra_postgrest(repo_postgrest, postgrest_falso):
    """El caso que reportó el dueño: alta desde el formulario, con evidencia."""
    creado = repo_postgrest.crear(
        TicketWrite(
            modulo="Ventas",
            descripcion="en cotizaciones no me deja agregar una nueva",
            severidad="CRITICA",
        ),
        "LUIS PEREYRA",
        {"url": "https://app/#/ventas"},
    )

    assert creado.folio == "BUG-0001"
    assert creado.estatus == "ABIERTO"
    assert creado.severidad == "CRITICA"
    assert postgrest_falso.tablas["bug_tickets"][0]["descripcion"].startswith("en cotizaciones")

    # El acuse de recibo a quien reportó viaja en la misma alta.
    assert postgrest_falso.tablas["ticket_notificaciones"][0]["destinatario"] == "LUIS PEREYRA"

    # Y el segundo ticket no pisa al primero: el folio avanza.
    segundo = repo_postgrest.crear(TicketWrite(modulo="Tracker", descripcion="otra cosa"), "TERESA")
    assert segundo.folio == "BUG-0002"
    assert len(repo_postgrest.listar()) == 2


def test_la_evidencia_se_agrega_sin_reemplazar_lo_reportado(repo_postgrest):
    repo_postgrest.crear(TicketWrite(modulo="Ventas", descripcion="original"), "LUIS")
    con_evidencia = repo_postgrest.agregar_evidencia(
        "BUG-0001", {"url": "https://x/clip.mp4", "tipo": "video/mp4", "sha256": "a" * 64}
    )

    assert len(con_evidencia.evidencia) == 1
    assert con_evidencia.descripcion == "original", "la evidencia no reescribe el reporte"


def test_sin_permiso_de_escritura_el_mensaje_dice_que_clave_falta(repo_postgrest, postgrest_falso):
    """
    Con la clave `anon` sobre una tabla con RLS: el listado sale vacío —así que
    nada avisa— y el alta la rechaza la base. Es el fallo que dejó el formulario
    inservible para todo el equipo, y el mensaje tiene que nombrar la causa.
    """
    postgrest_falso.escritura_denegada = True

    assert repo_postgrest.listar() == [], "la lectura no delata el problema: por eso pasó inadvertido"

    with pytest.raises(ErrorDeMotor) as exc:
        repo_postgrest.crear(TicketWrite(modulo="Ventas", descripcion="X"), "LUIS")

    assert exc.value.estado == 401
    assert exc.value.codigo == "42501"

    respuesta = _fallo_de_motor(exc.value)
    assert respuesta.status_code == 503
    assert "service_role" in respuesta.detail and "SUPABASE_KEY" in respuesta.detail
    assert "42501" in respuesta.detail
    assert CLAVE_FALSA not in respuesta.detail, "la credencial no viaja a pantalla"


def test_con_la_tabla_sin_crear_el_mensaje_manda_al_ddl(postgrest_falso):
    """PostgREST responde 404/PGRST205 y eso no es culpa de quien reporta."""
    postgrest_falso.tablas.pop("bug_tickets")
    repo = TicketRepository(PostgrestEngine(postgrest_falso.url, CLAVE_FALSA))

    with pytest.raises(ErrorDeMotor) as exc:
        repo.crear(TicketWrite(modulo="Ventas", descripcion="X"), "LUIS")

    respuesta = _fallo_de_motor(exc.value)
    assert respuesta.status_code == 503
    assert "bug_tickets" in respuesta.detail and "DDL" in respuesta.detail
    assert "select=" not in respuesta.detail, "la consulta cruda no viaja a pantalla"


def test_con_la_base_como_estaba_el_2026_08_17_el_alta_vuelve_a_funcionar(
    repo_postgrest, postgrest_falso
):
    """
    Reproducción exacta del bloqueo, sobre PostgREST y con la UNIQUE puesta.

    Estado medido en la base real ese día: una sola fila, y su folio `BUG-0002`
    (de `BUG-0001` no quedaba rastro). Contando filas, cada alta pedía
    `BUG-0002` → `23505` → "vuelve a intentarlo" para todo el equipo, siempre.
    """
    postgrest_falso.tablas["bug_tickets"].append({
        "id": "ya-existente", "folio": "BUG-0002", "reportado_por": "CARLOS_MENDEZ",
        "modulo": "Tracker", "descripcion": "lo de antes", "severidad": "MEDIA",
        "estatus": "CERRADO", "evidencia": [],
    })

    creado = repo_postgrest.crear(
        TicketWrite(modulo="Ventas", descripcion="no me deja agregar una cotización"), "LUIS"
    )

    assert creado.folio == "BUG-0003"
    assert len(postgrest_falso.tablas["bug_tickets"]) == 2, "el ticket quedó guardado"


def test_dos_altas_simultaneas_no_pierden_ninguna(repo_postgrest, postgrest_falso):
    """
    El folio no tiene candado: la segunda alta calcula el mismo número, la
    UNIQUE la rebota con 409 y el repositorio recalcula. Ninguna se pierde.
    """
    folios = []
    original = repo_postgrest._siguiente_folio
    llamadas = {"n": 0}

    def _siempre_el_mismo_la_primera_vez():
        # Imita la carrera: las dos altas leen la tabla antes de que la otra
        # haya escrito, así que las dos calculan BUG-0001.
        llamadas["n"] += 1
        return "BUG-0001" if llamadas["n"] <= 2 else original()

    repo_postgrest._siguiente_folio = _siempre_el_mismo_la_primera_vez
    for quien in ("LUIS", "TERESA"):
        folios.append(repo_postgrest.crear(TicketWrite(modulo="Ventas", descripcion="X"), quien).folio)

    assert folios == ["BUG-0001", "BUG-0002"]
    assert len(postgrest_falso.tablas["bug_tickets"]) == 2
