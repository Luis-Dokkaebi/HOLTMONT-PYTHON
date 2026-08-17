"""
`bug_tickets`: alta, listado, cambio de estatus y evidencia — sobre
`MemoryEngine`, igual que `tests/test_backend_tasks.py` prueba `tasks`.

La regla que más importa de este módulo, y la que motivó la tabla separada de
`tasks`, es que después del alta solo hay dos mutaciones posibles y ninguna
de las dos toca `descripcion` ni reemplaza `evidencia`. Eso se prueba
directo contra el repositorio (sin mocks en el núcleo) y otra vez contra el
router, para que un cambio futuro en cualquiera de las dos capas lo note.
"""

from __future__ import annotations

import base64
import hashlib
import io
from contextlib import contextmanager
from unittest import mock

import pytest
from pydantic import ValidationError

from api.services import storage
from backend.core.engines.memoria import MemoryEngine
from backend.core.errors import ErrorDeMotor
from backend.repositories.tickets import TicketNoEncontrado, TicketRepository
from backend.schemas.ticket import (
    COLUMNAS_BUG_TICKETS,
    ESTATUS_TERMINALES,
    OBLIGATORIAS_AL_INSERTAR,
    TicketRead,
    TicketUpdate,
    TicketWrite,
)


@pytest.fixture
def repo() -> TicketRepository:
    return TicketRepository(MemoryEngine({"bug_tickets": []}))


# --- Contrato del esquema -------------------------------------------------


def test_el_modelo_de_lectura_cubre_todas_las_columnas():
    faltan = set(COLUMNAS_BUG_TICKETS) - set(TicketRead.model_fields)
    assert not faltan, f"TicketRead no expone: {sorted(faltan)}"


def test_el_alta_no_acepta_columnas_tecnicas():
    """`estatus` y `evidencia` no son campos de TicketWrite: si el cliente los
    manda, la petición falla con 422 en vez de descartarlos en silencio."""
    with pytest.raises(ValidationError):
        TicketWrite(modulo="Tracker", descripcion="X", estatus="RESUELTO")
    with pytest.raises(ValidationError):
        TicketWrite(modulo="Tracker", descripcion="X", evidencia=[{"url": "y"}])


def test_el_patch_no_acepta_descripcion_ni_evidencia():
    """La garantía central: un PATCH no tiene por dónde reescribir lo reportado."""
    with pytest.raises(ValidationError):
        TicketUpdate(estatus="RESUELTO", descripcion="otra cosa")
    with pytest.raises(ValidationError):
        TicketUpdate(estatus="RESUELTO", evidencia=[])


def test_la_severidad_desconocida_se_rechaza():
    with pytest.raises(ValidationError):
        TicketWrite(modulo="Tracker", descripcion="X", severidad="URGENTISIMA")


def test_el_estatus_desconocido_se_rechaza():
    with pytest.raises(ValidationError):
        TicketUpdate(estatus="EN_LIMBO")


def test_severidad_por_defecto_es_media():
    assert TicketWrite(modulo="Tracker", descripcion="X").severidad == "MEDIA"


# --- Alta ------------------------------------------------------------------


def test_crear_asigna_folio_reportado_por_y_estatus_abierto(repo):
    ticket = repo.crear(
        TicketWrite(modulo="Tracker", descripcion="El avance no se guarda"),
        reportado_por="JAIME OLIVO",
    )
    assert ticket.folio == "BUG-0001"
    assert ticket.reportado_por == "JAIME OLIVO"
    assert ticket.estatus == "ABIERTO"
    assert ticket.evidencia == []


def test_los_folios_son_consecutivos(repo):
    primero = repo.crear(TicketWrite(modulo="Tracker", descripcion="A"), reportado_por="X")
    segundo = repo.crear(TicketWrite(modulo="PPC", descripcion="B"), reportado_por="X")
    assert primero.folio == "BUG-0001"
    assert segundo.folio == "BUG-0002"


def test_reportado_por_lo_pone_el_servidor_no_el_cliente(repo):
    """`TicketWrite` ni siquiera tiene el campo: no hay forma de que el
    cliente se haga pasar por otra persona al reportar."""
    assert "reportado_por" not in TicketWrite.model_fields


def test_no_se_puede_crear_un_ticket_sin_usuario_en_sesion(repo):
    from backend.core.errors import BackendError

    with pytest.raises(BackendError):
        repo.crear(TicketWrite(modulo="Tracker", descripcion="X"), reportado_por="")


def test_el_contexto_se_guarda_tal_cual(repo):
    ticket = repo.crear(
        TicketWrite(modulo="Tracker", descripcion="X"),
        reportado_por="JAIME OLIVO",
        contexto={"user_agent": "Chrome", "url": "/tracker"},
    )
    assert ticket.contexto == {"user_agent": "Chrome", "url": "/tracker"}


# --- Listado -----------------------------------------------------------


def test_listar_filtra_por_estatus_modulo_y_reportado_por(repo):
    repo.crear(TicketWrite(modulo="Tracker", descripcion="A"), reportado_por="JAIME OLIVO")
    repo.crear(TicketWrite(modulo="PPC", descripcion="B"), reportado_por="TERESA GARZA")
    repo.actualizar_estatus("BUG-0002", TicketUpdate(estatus="EN_REVISION"))

    assert [t.folio for t in repo.listar(modulo="PPC")] == ["BUG-0002"]
    assert [t.folio for t in repo.listar(reportado_por="JAIME OLIVO")] == ["BUG-0001"]
    assert [t.folio for t in repo.listar(estatus="EN_REVISION")] == ["BUG-0002"]
    assert len(repo.listar()) == 2


def test_obtener_un_folio_inexistente_lanza(repo):
    with pytest.raises(TicketNoEncontrado):
        repo.obtener("BUG-9999")


# --- Cambio de estatus ---------------------------------------------------


def test_actualizar_estatus_no_toca_la_descripcion_original(repo):
    repo.crear(TicketWrite(modulo="Tracker", descripcion="El avance no se guarda"), reportado_por="X")
    actualizado = repo.actualizar_estatus(
        "BUG-0001", TicketUpdate(estatus="EN_REVISION")
    )
    assert actualizado.descripcion == "El avance no se guarda"
    assert actualizado.estatus == "EN_REVISION"


@pytest.mark.parametrize("estatus", sorted(ESTATUS_TERMINALES))
def test_los_estatus_terminales_registran_quien_y_cuando_resolvio(repo, estatus):
    repo.crear(TicketWrite(modulo="Tracker", descripcion="X"), reportado_por="X")
    actualizado = repo.actualizar_estatus(
        "BUG-0001", TicketUpdate(estatus=estatus, resuelto_por="SOPORTE")
    )
    assert actualizado.resuelto_por == "SOPORTE"
    assert actualizado.resuelto_en is not None


def test_un_estatus_no_terminal_no_registra_resolucion(repo):
    repo.crear(TicketWrite(modulo="Tracker", descripcion="X"), reportado_por="X")
    actualizado = repo.actualizar_estatus("BUG-0001", TicketUpdate(estatus="EN_REVISION"))
    assert actualizado.resuelto_por is None
    assert actualizado.resuelto_en is None


def test_actualizar_un_folio_inexistente_lanza(repo):
    with pytest.raises(TicketNoEncontrado):
        repo.actualizar_estatus("BUG-9999", TicketUpdate(estatus="RESUELTO"))


# --- Evidencia: la regla central -----------------------------------------


def test_agregar_evidencia_extiende_el_arreglo_sin_perder_lo_anterior(repo):
    repo.crear(TicketWrite(modulo="Tracker", descripcion="X"), reportado_por="X")
    repo.agregar_evidencia("BUG-0001", {"url": "https://.../video1.mp4", "tipo": "video/mp4"})
    actualizado = repo.agregar_evidencia(
        "BUG-0001", {"url": "https://.../captura.png", "tipo": "image/png"}
    )
    assert [e["url"] for e in actualizado.evidencia] == [
        "https://.../video1.mp4",
        "https://.../captura.png",
    ]


def test_no_existe_ninguna_operacion_que_reemplace_la_evidencia(repo):
    """
    No es una prueba de comportamiento por omisión: documenta la superficie
    completa del repositorio para que agregar un `reemplazar_evidencia` en el
    futuro reviente esta prueba y obligue a justificarlo explícitamente.
    """
    metodos_publicos = {n for n in dir(TicketRepository) if not n.startswith("_")}
    assert metodos_publicos == {"obtener", "listar", "crear", "actualizar_estatus", "agregar_evidencia"}


def test_agregar_evidencia_a_un_folio_inexistente_lanza(repo):
    with pytest.raises(TicketNoEncontrado):
        repo.agregar_evidencia("BUG-9999", {"url": "x", "tipo": "video/mp4"})


# --- El motor reproduce el NOT NULL real ----------------------------------


def test_las_obligatorias_al_insertar_son_las_que_no_tienen_default():
    assert OBLIGATORIAS_AL_INSERTAR == {"folio", "reportado_por", "modulo", "descripcion"}


def test_el_motor_rechaza_un_alta_sin_columna_obligatoria():
    engine = MemoryEngine({"bug_tickets": []})
    with pytest.raises(ErrorDeMotor) as exc:
        engine.insertar("bug_tickets", [{"folio": "BUG-0001", "reportado_por": "X"}])  # sin modulo/descripcion
    assert exc.value.codigo == "23502"


# --- Router /api/v2/tickets ------------------------------------------------


@pytest.fixture
def cliente(repo):
    from fastapi.testclient import TestClient

    from api.main import app
    from backend.routers.tickets import obtener_repositorio

    app.dependency_overrides[obtener_repositorio] = lambda: repo
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_el_endpoint_crea_y_devuelve_el_folio(cliente):
    respuesta = cliente.post(
        "/api/v2/tickets",
        json={
            "ticket": {"modulo": "Tracker", "descripcion": "El avance no se guarda"},
            "reportado_por": "JAIME OLIVO",
        },
    )
    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["success"] is True
    assert cuerpo["data"]["folio"] == "BUG-0001"
    assert cuerpo["data"]["estatus"] == "ABIERTO"


def test_el_endpoint_rechaza_evidencia_en_el_alta(cliente):
    respuesta = cliente.post(
        "/api/v2/tickets",
        json={
            "ticket": {"modulo": "Tracker", "descripcion": "X", "evidencia": [{"url": "y"}]},
            "reportado_por": "JAIME OLIVO",
        },
    )
    assert respuesta.status_code == 422


def test_el_endpoint_lista_y_filtra(cliente):
    cliente.post("/api/v2/tickets", json={"ticket": {"modulo": "Tracker", "descripcion": "A"}, "reportado_por": "X"})
    cliente.post("/api/v2/tickets", json={"ticket": {"modulo": "PPC", "descripcion": "B"}, "reportado_por": "X"})
    respuesta = cliente.get("/api/v2/tickets", params={"modulo": "PPC"})
    assert [t["folio"] for t in respuesta.json()["data"]] == ["BUG-0002"]


def test_el_endpoint_de_patch_no_acepta_descripcion(cliente):
    cliente.post("/api/v2/tickets", json={"ticket": {"modulo": "Tracker", "descripcion": "X"}, "reportado_por": "X"})
    respuesta = cliente.patch(
        "/api/v2/tickets/BUG-0001",
        json={"estatus": "RESUELTO", "descripcion": "otra cosa"},
    )
    assert respuesta.status_code == 422


def test_el_endpoint_de_patch_devuelve_404_si_no_existe(cliente):
    respuesta = cliente.patch("/api/v2/tickets/BUG-9999", json={"estatus": "RESUELTO"})
    assert respuesta.status_code == 404


def test_el_endpoint_rechaza_reportado_por_en_blanco(cliente):
    """`min_length=1` deja pasar un string de solo espacios; la validación
    real de "hay usuario" vive en el repositorio, no en Pydantic."""
    respuesta = cliente.post(
        "/api/v2/tickets",
        json={"ticket": {"modulo": "Tracker", "descripcion": "X"}, "reportado_por": "   "},
    )
    assert respuesta.status_code == 400


def test_el_endpoint_de_patch_actualiza_con_exito(cliente):
    cliente.post("/api/v2/tickets", json={"ticket": {"modulo": "Tracker", "descripcion": "X"}, "reportado_por": "X"})
    respuesta = cliente.patch("/api/v2/tickets/BUG-0001", json={"estatus": "EN_REVISION"})
    assert respuesta.status_code == 200
    assert respuesta.json()["data"]["estatus"] == "EN_REVISION"


def test_obtener_repositorio_construye_uno_de_verdad_con_memoria(monkeypatch):
    """Sin override: la dependencia real arma un `TicketRepository` sobre el
    motor que diga el entorno. `tests/conftest.py` ya fuerza
    `BACKEND_ENGINE=memoria` para toda la sesión (R7)."""
    from fastapi.testclient import TestClient

    from api.main import app

    respuesta = TestClient(app).get("/api/v2/tickets")
    assert respuesta.status_code == 200
    assert respuesta.json() == {"success": True, "data": [], "count": 0}


def test_obtener_repositorio_devuelve_503_si_no_hay_motor(monkeypatch):
    """La dependencia real (sin override), con el motor apagado a propósito."""
    from fastapi.testclient import TestClient

    from api.main import app
    from backend.core.errors import SinMotorConfigurado
    import backend.routers.tickets as tickets_router

    def _sin_motor():
        raise SinMotorConfigurado("sin motor, a propósito para la prueba")

    monkeypatch.setattr(tickets_router, "construir_engine", _sin_motor)
    respuesta = TestClient(app).get("/api/v2/tickets")
    assert respuesta.status_code == 503


def test_el_endpoint_de_evidencia_agrega_con_exito(cliente, monkeypatch):
    monkeypatch.setattr(
        storage,
        "subir_evidencia_ticket",
        lambda folio, data, tipo, nombre: {
            "success": True, "fileUrl": "https://x/clip.mp4", "mime": "video/mp4", "sha256": "abc123",
        },
    )
    cliente.post("/api/v2/tickets", json={"ticket": {"modulo": "Tracker", "descripcion": "X"}, "reportado_por": "X"})
    respuesta = cliente.post(
        "/api/v2/tickets/BUG-0001/evidencia",
        json={"data": "data:video/mp4;base64,AAAA", "type": "video/mp4", "name": "clip.mp4"},
    )
    assert respuesta.status_code == 200
    assert respuesta.json()["data"]["evidencia"][0]["url"] == "https://x/clip.mp4"


def test_el_endpoint_de_evidencia_404_si_el_ticket_no_existe(cliente, monkeypatch):
    monkeypatch.setattr(
        storage,
        "subir_evidencia_ticket",
        lambda folio, data, tipo, nombre: {
            "success": True, "fileUrl": "https://x/clip.mp4", "mime": "video/mp4", "sha256": "abc123",
        },
    )
    respuesta = cliente.post(
        "/api/v2/tickets/BUG-9999/evidencia",
        json={"data": "data:video/mp4;base64,AAAA", "type": "video/mp4", "name": "clip.mp4"},
    )
    assert respuesta.status_code == 404


def test_el_endpoint_de_evidencia_falla_sin_supabase_configurado(cliente):
    """
    `tests/conftest.py` desconecta SUPABASE_URL/KEY para toda la sesión
    (R7): sin credenciales, el endpoint tiene que fallar de forma visible en
    vez de fingir que subió el archivo — la misma regla que ya protege
    `/api/legacy/upload`.
    """
    cliente.post("/api/v2/tickets", json={"ticket": {"modulo": "Tracker", "descripcion": "X"}, "reportado_por": "X"})
    respuesta = cliente.post(
        "/api/v2/tickets/BUG-0001/evidencia",
        json={"data": "data:video/mp4;base64,AAAA", "type": "video/mp4", "name": "clip.mp4"},
    )
    assert respuesta.status_code == 400
    assert "no está configurado" in respuesta.json()["detail"]


# --- Storage: subir_evidencia_ticket ---------------------------------------


class _AlmacenFalso:
    def __init__(self):
        self.subidas = []

    def from_(self, nombre_bucket):
        self._bucket = nombre_bucket
        return self

    def upload(self, ruta, contenido, opciones):
        assert opciones["upsert"] == "false", "La evidencia nunca debe subir con upsert habilitado"
        self.subidas.append((self._bucket, ruta, contenido, opciones))

    def get_public_url(self, ruta):
        return f"https://supabase.local/storage/v1/object/public/{self._bucket}/{ruta}"


class _ClienteFalso:
    def __init__(self):
        self.storage = _AlmacenFalso()


class _ManagerFalso:
    is_configured = True

    def __init__(self):
        self.client = _ClienteFalso()


def _data_url(contenido: bytes, mime: str = "video/mp4") -> str:
    return f"data:{mime};base64,{base64.b64encode(contenido).decode()}"


def test_subir_evidencia_devuelve_url_y_hash_del_contenido(monkeypatch):
    falso = _ManagerFalso()
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", falso)

    contenido = b"contenido de prueba del video"
    resultado = storage.subir_evidencia_ticket("BUG-0001", _data_url(contenido), "video/mp4", "clip.mp4")

    assert resultado["success"] is True
    assert resultado["sha256"] == hashlib.sha256(contenido).hexdigest()
    assert "ticket-evidencia" in resultado["fileUrl"]
    assert falso.client.storage.subidas[0][3]["upsert"] == "false"


def test_subir_evidencia_rechaza_mime_no_permitido(monkeypatch):
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _ManagerFalso())
    resultado = storage.subir_evidencia_ticket("BUG-0001", _data_url(b"x", "application/zip"), "application/zip", "a.zip")
    assert resultado["success"] is False
    assert "no permitido" in resultado["message"]


def test_subir_evidencia_rechaza_archivos_mas_grandes_que_el_tope(monkeypatch):
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _ManagerFalso())
    monkeypatch.setattr(storage, "MAX_BYTES_EVIDENCIA", 10)
    resultado = storage.subir_evidencia_ticket("BUG-0001", _data_url(b"x" * 100), "video/mp4", "clip.mp4")
    assert resultado["success"] is False
    assert "máximo" in resultado["message"]


def test_subir_evidencia_rechaza_contenido_vacio(monkeypatch):
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _ManagerFalso())
    resultado = storage.subir_evidencia_ticket("BUG-0001", " ", "video/mp4", "clip.mp4")
    assert resultado["success"] is False
    assert "vacío" in resultado["message"]


def test_subir_evidencia_rechaza_un_data_url_corrupto(monkeypatch):
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _ManagerFalso())
    resultado = storage.subir_evidencia_ticket("BUG-0001", "data:video/mp4;base64,***no-es-base64***", "video/mp4", "clip.mp4")
    assert resultado["success"] is False


def test_subir_evidencia_reporta_si_storage_rechaza_la_subida(monkeypatch):
    class _AlmacenQueFalla(_AlmacenFalso):
        def upload(self, ruta, contenido, opciones):
            raise RuntimeError("bucket no existe")

    class _ClienteQueFalla:
        def __init__(self):
            self.storage = _AlmacenQueFalla()

    falso = _ManagerFalso()
    falso.client = _ClienteQueFalla()
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", falso)

    resultado = storage.subir_evidencia_ticket("BUG-0001", _data_url(b"x"), "video/mp4", "clip.mp4")
    assert resultado["success"] is False
    assert "No se pudo subir" in resultado["message"]


def test_ruta_de_evidencia_incluye_el_folio_y_es_unica():
    from datetime import datetime

    a = storage.ruta_de_evidencia("BUG-0001", "clip.mp4", fecha=datetime(2026, 8, 12, 10, 0, 0))
    b = storage.ruta_de_evidencia("BUG-0001", "clip.mp4", fecha=datetime(2026, 8, 12, 10, 0, 1))
    assert "BUG-0001" in a
    assert a != b, "Dos momentos distintos no deben compartir ruta"


# --- Fallos del motor: lo que vio el dueño el 2026-08-13 -----------------
#
# Reportar un bug con la tabla `bug_tickets` sin crear devolvía a la pantalla
# el texto crudo de PostgREST:
#
#   "PostgREST GET bug_tickets?select=folio&offset=0&limit=1000 respondió 404"
#
# Tres defectos en una sola pantalla: el listado no manejaba ningún fallo del
# motor (500 sin controlar), el alta lo mapeaba a 400 —como si el cliente
# hubiera mandado algo mal, cuando la tabla no existe— y el mensaje interno
# viajaba tal cual al usuario. Quien reporta un bug no puede hacer nada con
# una cadena de consulta de PostgREST.


def _motor_que_falla(mensaje="PostgREST GET bug_tickets?select=folio&offset=0&limit=1000 respondió 404",
                     codigo="PGRST205"):
    """Motor cuyo `select` revienta como lo hace PostgREST sin la tabla."""
    engine = MemoryEngine({"bug_tickets": []})

    def _revienta(*args, **kwargs):
        raise ErrorDeMotor(mensaje, codigo=codigo, detalle="{}")

    engine.select = _revienta
    return engine


@pytest.fixture
def cliente_motor_roto():
    from fastapi.testclient import TestClient

    from api.main import app
    from backend.routers.tickets import obtener_repositorio

    repo = TicketRepository(_motor_que_falla())
    app.dependency_overrides[obtener_repositorio] = lambda: repo
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


CRUDO = ["PostgREST", "select=folio", "offset=", "limit=1000"]


def test_el_alta_con_la_tabla_sin_crear_avisa_que_falta_el_ddl(cliente_motor_roto):
    respuesta = cliente_motor_roto.post(
        "/api/v2/tickets",
        json={"ticket": {"modulo": "Tracker", "descripcion": "X"}, "reportado_por": "X"},
    )
    assert respuesta.status_code == 503, "la tabla ausente no es culpa de quien reporta"
    detalle = respuesta.json()["detail"]
    assert "bug_tickets" in detalle and "DDL" in detalle, f"mensaje poco accionable: {detalle}"


@pytest.mark.parametrize("metodo,ruta,cuerpo", [
    ("get", "/api/v2/tickets", None),
    ("post", "/api/v2/tickets", {"ticket": {"modulo": "T", "descripcion": "X"}, "reportado_por": "X"}),
    ("patch", "/api/v2/tickets/BUG-0001", {"estatus": "RESUELTO"}),
])
def test_ningun_endpoint_devuelve_500_ni_filtra_el_error_del_motor(
    cliente_motor_roto, metodo, ruta, cuerpo
):
    respuesta = getattr(cliente_motor_roto, metodo)(ruta, **({"json": cuerpo} if cuerpo else {}))
    assert respuesta.status_code != 500, "el fallo del motor quedó sin manejar"
    assert respuesta.status_code in (502, 503)
    detalle = respuesta.json()["detail"]
    for fragmento in CRUDO:
        assert fragmento not in detalle, f"se filtró {fragmento!r} al usuario: {detalle}"


def test_un_fallo_de_motor_que_no_es_tabla_faltante_es_502(cliente_motor_roto):
    """Un corte de red no debe decir "falta el DDL": son causas distintas."""
    from fastapi.testclient import TestClient

    from api.main import app
    from backend.routers.tickets import obtener_repositorio

    repo = TicketRepository(_motor_que_falla("Fallo de red hacia PostgREST: timeout", codigo=""))
    app.dependency_overrides[obtener_repositorio] = lambda: repo
    try:
        respuesta = TestClient(app).get("/api/v2/tickets")
    finally:
        app.dependency_overrides.clear()
    assert respuesta.status_code == 502
    assert "DDL" not in respuesta.json()["detail"]


def test_el_endpoint_de_evidencia_tambien_traduce_el_fallo_del_motor(monkeypatch):
    """La subida a Storage sale bien, pero guardar la referencia falla."""
    from fastapi.testclient import TestClient

    from api.main import app
    from backend.routers.tickets import obtener_repositorio

    monkeypatch.setattr(
        storage, "subir_evidencia_ticket",
        lambda folio, data, tipo, nombre: {
            "success": True, "fileUrl": "https://x/clip.mp4", "mime": "video/mp4", "sha256": "abc",
        },
    )
    repo = TicketRepository(_motor_que_falla())
    app.dependency_overrides[obtener_repositorio] = lambda: repo
    try:
        respuesta = TestClient(app).post(
            "/api/v2/tickets/BUG-0001/evidencia",
            json={"data": "data:video/mp4;base64,AAAA", "type": "video/mp4", "name": "clip.mp4"},
        )
    finally:
        app.dependency_overrides.clear()
    assert respuesta.status_code == 503
    assert "PostgREST" not in respuesta.json()["detail"]


def test_un_error_de_negocio_no_se_confunde_con_un_fallo_de_motor():
    """
    `_es_tabla_faltante` solo mira los `ErrorDeMotor`. Un `BackendError` de
    otra clase —"sin usuario en sesión"— tiene que seguir siendo un 400 con
    su mensaje propio, no un 502 genérico.
    """
    from backend.routers.tickets import _es_tabla_faltante
    from backend.core.errors import BackendError

    assert _es_tabla_faltante(BackendError("sin usuario en sesión")) is False


# --- Verificación de integridad ------------------------------------------
#
# La evidencia NO es inmutable frente a la clave de servicio. Medido contra el
# proyecto real el 2026-08-13, con `service_role` sobre un objeto ya subido:
#
#   POST al mismo path        -> 409 Duplicate            (bloqueado)
#   PUT con x-upsert: true    -> 200, archivo sobrescrito (NO bloqueado)
#   DELETE                    -> 200 Successfully deleted (NO bloqueado)
#
# `service_role` tiene BYPASSRLS, así que las políticas no lo alcanzan, y
# Storage no ofrece object-lock. No pudiendo impedirlo, lo que queda es
# detectarlo: eso es `verificar_evidencia`, y estas pruebas son las que
# sostienen esa promesa.


class _AlmacenConContenido(_AlmacenFalso):
    def __init__(self, contenido=None, falla=False):
        super().__init__()
        self._contenido = contenido
        self._falla = falla

    def download(self, ruta):
        if self._falla:
            raise RuntimeError("Object not found")
        return self._contenido


def _manager_con(contenido=None, falla=False):
    falso = _ManagerFalso()
    almacen = _AlmacenConContenido(contenido, falla)

    class _C:
        storage = almacen

    falso.client = _C()
    return falso


URL_EVIDENCIA = (
    "https://x.supabase.co/storage/v1/object/public/ticket-evidencia/2026/AGOSTO/BUG-0001/v.png"
)


def test_evidencia_intacta_cuando_el_hash_coincide(monkeypatch):
    contenido = b"contenido original del video"
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _manager_con(contenido))
    r = storage.verificar_evidencia(URL_EVIDENCIA, hashlib.sha256(contenido).hexdigest())
    assert r["estado"] == "intacta"


def test_evidencia_alterada_se_detecta(monkeypatch):
    """El caso que de verdad importa: alguien sobrescribió el archivo."""
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _manager_con(b"ALTERADO"))
    r = storage.verificar_evidencia(URL_EVIDENCIA, hashlib.sha256(b"original").hexdigest())
    assert r["estado"] == "alterada"
    assert r["sha256_actual"] != r["sha256_esperado"]


def test_evidencia_borrada_se_detecta(monkeypatch):
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _manager_con(falla=True))
    r = storage.verificar_evidencia(URL_EVIDENCIA, "a" * 64)
    assert r["estado"] == "desaparecida"


def test_sin_hash_guardado_no_se_finge_una_verificacion(monkeypatch):
    """Devolver "intacta" sin nada contra qué comparar sería mentir."""
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _manager_con(b"x"))
    assert storage.verificar_evidencia(URL_EVIDENCIA, None)["estado"] == "sin_hash"


def test_una_url_de_otro_bucket_no_se_da_por_buena(monkeypatch):
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _manager_con(b"x"))
    otra = "https://x.supabase.co/storage/v1/object/public/archivos/2026/AGOSTO/cot.pdf"
    assert storage.verificar_evidencia(otra, "a" * 64)["estado"] == "indeterminado"


def test_el_endpoint_de_verificacion_reporta_integridad(cliente, monkeypatch):
    contenido = b"video original"
    sha = hashlib.sha256(contenido).hexdigest()
    monkeypatch.setattr(
        storage, "subir_evidencia_ticket",
        lambda folio, data, tipo, nombre: {
            "success": True, "fileUrl": URL_EVIDENCIA, "mime": "video/mp4", "sha256": sha,
        },
    )
    cliente.post("/api/v2/tickets", json={"ticket": {"modulo": "T", "descripcion": "X"}, "reportado_por": "X"})
    cliente.post("/api/v2/tickets/BUG-0001/evidencia",
                 json={"data": "data:video/mp4;base64,AAAA", "type": "video/mp4", "name": "v.mp4"})

    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _manager_con(contenido))
    ok = cliente.get("/api/v2/tickets/BUG-0001/evidencia/verificacion").json()
    assert ok["integra"] is True

    # Ahora alguien sobrescribe el archivo en Storage.
    monkeypatch.setattr("api.services.supabase_manager.sb_manager", _manager_con(b"ALTERADO"))
    malo = cliente.get("/api/v2/tickets/BUG-0001/evidencia/verificacion").json()
    assert malo["integra"] is False
    assert malo["evidencia"][0]["estado"] == "alterada"


def test_verificar_un_ticket_inexistente_es_404(cliente):
    assert cliente.get("/api/v2/tickets/BUG-9999/evidencia/verificacion").status_code == 404


def test_un_ticket_sin_evidencia_es_integro_por_vacuidad(cliente):
    cliente.post("/api/v2/tickets", json={"ticket": {"modulo": "T", "descripcion": "X"}, "reportado_por": "X"})
    r = cliente.get("/api/v2/tickets/BUG-0001/evidencia/verificacion").json()
    assert r["integra"] is True and r["evidencia"] == []


def test_la_verificacion_traduce_el_fallo_del_motor(cliente_motor_roto):
    r = cliente_motor_roto.get("/api/v2/tickets/BUG-0001/evidencia/verificacion")
    assert r.status_code in (502, 503)
    assert "PostgREST" not in r.json()["detail"]


def test_sin_supabase_la_verificacion_no_finge_un_veredicto():
    """`tests/conftest.py` desconecta las credenciales (R7): sin Storage no se
    puede afirmar ni que está intacta ni que la alteraron."""
    assert storage.verificar_evidencia(URL_EVIDENCIA, "a" * 64)["estado"] == "indeterminado"


# --- Por qué falla, no solo que falló ------------------------------------
#
# El 2026-08-17 el formulario devolvía a todo el mundo el mismo texto:
#
#   "No se pudo consultar el sistema de tickets. Vuelve a intentarlo; si
#    sigue fallando, avisa al equipo."
#
# Es el mensaje de "la base no responde, reintenta". Pero tres de las causas
# posibles NO se arreglan reintentando —falta la tabla, falta una columna, la
# clave del backend no puede escribir— y con ese texto ni quien reporta ni el
# equipo tenían con qué distinguirlas. Cada una tiene ahora su mensaje y su
# código; el 502 genérico queda solo para lo que sí es transitorio.


@contextmanager
def _cliente_con_motor(motor):
    from fastapi.testclient import TestClient

    from api.main import app
    from backend.routers.tickets import obtener_repositorio

    app.dependency_overrides[obtener_repositorio] = lambda: TicketRepository(motor)
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _motor_que_rechaza(mensaje, codigo="", estado=0, detalle="{}"):
    """Motor cuyo `select` y `insertar` fallan como lo hace PostgREST."""
    engine = MemoryEngine({"bug_tickets": [], "ticket_notificaciones": []})

    def _revienta(*args, **kwargs):
        raise ErrorDeMotor(mensaje, codigo=codigo, detalle=detalle, estado=estado)

    engine.select = _revienta
    engine.insertar = _revienta
    engine.upsert = _revienta
    return engine


ALTA = {"ticket": {"modulo": "Ventas", "descripcion": "no me deja agregar"}, "reportado_por": "LUIS"}


def test_la_clave_sin_permiso_no_dice_reintenta_sino_que_clave_hace_falta():
    """
    El caso que deja el formulario roto para todo el equipo: `bug_tickets`
    lleva RLS encendida y sin políticas (DDL §5), así que con la clave `anon`
    el listado sale vacío pero el alta la rechaza la base. Reintentar no lo
    arregla nunca; hay que cambiar `SUPABASE_KEY` por la `service_role`.
    """
    motor = _motor_que_rechaza(
        "PostgREST POST bug_tickets respondió 401",
        codigo="42501",
        estado=401,
        detalle='{"code":"42501","message":"new row violates row-level security policy"}',
    )
    with _cliente_con_motor(motor) as cliente:
        respuesta = cliente.post("/api/v2/tickets", json=ALTA)

    assert respuesta.status_code == 503, "no es culpa de quien reporta ni es transitorio"
    detalle = respuesta.json()["detail"]
    assert "SUPABASE_KEY" in detalle and "service_role" in detalle, detalle
    assert "Reintentar no lo arregla" in detalle, detalle
    assert "42501" in detalle, "el equipo necesita el código para actuar"
    for fragmento in CRUDO:
        assert fragmento not in detalle, f"se filtró {fragmento!r}: {detalle}"


def test_un_403_sin_codigo_tambien_se_lee_como_permiso():
    """PostgREST no siempre manda `code`; el estado HTTP basta para clasificar."""
    motor = _motor_que_rechaza("PostgREST POST bug_tickets respondió 403", estado=403)
    with _cliente_con_motor(motor) as cliente:
        respuesta = cliente.post("/api/v2/tickets", json=ALTA)

    assert respuesta.status_code == 503
    assert "service_role" in respuesta.json()["detail"]


def test_una_columna_que_falta_pide_reaplicar_el_ddl_no_reintentar():
    """Esquema viejo aplicado: la tabla está, `contexto` no. Antes era un 502."""
    motor = _motor_que_rechaza(
        "PostgREST POST bug_tickets respondió 400",
        codigo="PGRST204",
        estado=400,
        detalle='{"code":"PGRST204","message":"Could not find the \'contexto\' column"}',
    )
    with _cliente_con_motor(motor) as cliente:
        respuesta = cliente.post("/api/v2/tickets", json=ALTA)

    assert respuesta.status_code == 503
    detalle = respuesta.json()["detail"]
    assert "columnas" in detalle and "DDL" in detalle, detalle
    assert "PGRST204" in detalle


def test_un_corte_de_red_sigue_siendo_502_y_sin_codigo_inventado():
    motor = _motor_que_rechaza("Fallo de red hacia PostgREST: timeout")
    with _cliente_con_motor(motor) as cliente:
        respuesta = cliente.post("/api/v2/tickets", json=ALTA)

    assert respuesta.status_code == 502
    detalle = respuesta.json()["detail"]
    assert "Vuelve a intentarlo" in detalle
    assert "código" not in detalle, "sin código de la base, no se inventa uno"


def test_el_fallo_de_los_avisos_nombra_su_propia_tabla():
    """
    `ticket_notificaciones` es de la §6 del DDL, tabla aparte. El mensaje decía
    siempre `bug_tickets`, así que mandaba a crear una tabla que ya existía.
    """
    motor = _motor_que_rechaza(
        "PostgREST GET ticket_notificaciones?select=* respondió 404", codigo="PGRST205", estado=404
    )
    with _cliente_con_motor(motor) as cliente:
        respuesta = cliente.get("/api/v2/notificaciones", params={"usuario": "LUIS"})

    assert respuesta.status_code == 503
    assert "ticket_notificaciones" in respuesta.json()["detail"]


# --- El diagnóstico que antes solo estaba en los registros ----------------


def test_el_diagnostico_dice_que_el_sistema_opera(cliente):
    r = cliente.get("/api/v2/tickets/diagnostico")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["operativo"] is True
    assert {t["tabla"] for t in cuerpo["tablas"]} == {"bug_tickets", "ticket_notificaciones"}
    assert all(t["ok"] for t in cuerpo["tablas"])


def test_el_diagnostico_nombra_la_causa_de_cada_tabla():
    motor = _motor_que_rechaza(
        "PostgREST GET bug_tickets?select=folio respondió 401", codigo="42501", estado=401
    )
    with _cliente_con_motor(motor) as cliente:
        cuerpo = cliente.get("/api/v2/tickets/diagnostico").json()

    assert cuerpo["operativo"] is False
    for tabla in cuerpo["tablas"]:
        assert tabla["ok"] is False
        assert tabla["causa"] == "permiso_denegado"
        assert tabla["codigo"] == "42501"
        assert "service_role" in tabla["que_hacer"]


def test_el_diagnostico_no_filtra_la_consulta_ni_la_credencial(cliente):
    crudo = cliente.get("/api/v2/tickets/diagnostico").text
    assert "SUPABASE_KEY=" not in crudo
    assert "apikey" not in crudo.lower()


# --- Un alta que no confirma la fila no puede salir como 500 -------------


def test_un_alta_sin_fila_de_vuelta_es_un_fallo_de_motor_no_un_500():
    """
    `insertar` pide `Prefer: return=representation`. Si la respuesta llega
    vacía, `guardadas[0]` reventaba con `IndexError` → 500 sin causa.
    """
    motor = MemoryEngine({"bug_tickets": [], "ticket_notificaciones": []})
    motor.insertar = lambda *a, **k: []
    repo = TicketRepository(motor)

    with pytest.raises(ErrorDeMotor):
        repo.crear(TicketWrite(modulo="Ventas", descripcion="X"), "LUIS")

    with _cliente_con_motor(motor) as cliente:
        respuesta = cliente.post("/api/v2/tickets", json=ALTA)
    assert respuesta.status_code == 502, "es un fallo del motor, no un 500 sin manejar"


def test_el_motor_postgrest_guarda_el_estado_http():
    """
    La clasificación se apoya en `estado`, no en buscar texto en el mensaje:
    PostgREST no siempre manda `code` en el cuerpo.
    """
    import urllib.error

    from backend.core.engines.postgrest import PostgrestEngine

    motor = PostgrestEngine("https://proyecto.supabase.co", "clave-de-prueba")

    def _cae(*args, **kwargs):
        raise urllib.error.HTTPError(
            "https://proyecto.supabase.co/rest/v1/bug_tickets", 401, "Unauthorized", {},
            io.BytesIO(b'{"code":"42501","message":"permission denied"}'),
        )

    with mock.patch("urllib.request.urlopen", _cae):
        with pytest.raises(ErrorDeMotor) as exc:
            motor.select("bug_tickets")

    assert exc.value.estado == 401
    assert exc.value.codigo == "42501"


def test_las_mutaciones_sin_fila_de_vuelta_tampoco_revientan():
    """Mismo cuidado que en el alta, en las otras dos escrituras posibles."""
    motor = MemoryEngine({"bug_tickets": [], "ticket_notificaciones": []})
    repo = TicketRepository(motor)
    repo.crear(TicketWrite(modulo="Ventas", descripcion="X"), "LUIS")
    motor.upsert = lambda *a, **k: []

    with pytest.raises(ErrorDeMotor):
        repo.actualizar_estatus("BUG-0001", TicketUpdate(estatus="RESUELTO", resuelto_por="SOPORTE"))
    with pytest.raises(ErrorDeMotor):
        repo.agregar_evidencia("BUG-0001", {"url": "https://x/v.mp4", "tipo": "video/mp4"})


def test_un_error_de_negocio_no_se_clasifica_como_permiso_ni_lleva_codigo():
    """
    "Sin usuario en sesión" es un `BackendError` que no viene del motor: ni es
    un problema de permisos ni tiene código de la base que ofrecer al equipo.
    """
    from backend.core.errors import BackendError
    from backend.routers.tickets import _causa, _es_permiso_denegado, _pista

    error = BackendError("No se puede reportar un ticket sin usuario en sesión.")
    assert _es_permiso_denegado(error) is False
    assert _pista(error) == ""
    assert _causa(error) == "motor_caido"
