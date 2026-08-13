"""
Avisos a quien reportó un bug, sobre `MemoryEngine`.

Dos reglas gobiernan este módulo y las dos se prueban aquí:

1. **Notificar nunca tumba el ticket.** Si el aviso falla, el reporte ya se
   guardó y el reporte es lo que importa. Es la misma decisión que ya toma
   `tracker_store._enviar_webhook` con Make.com.
2. **Nadie ve ni marca los avisos de otro.** El filtro por destinatario se
   aplica siempre, también cuando la petición trae ids.
"""

from __future__ import annotations

import pytest

from backend.core.engines.memoria import MemoryEngine
from backend.core.errors import ErrorDeMotor
from backend.repositories.notificaciones import NotificacionRepository
from backend.repositories.tickets import TicketRepository
from backend.schemas.notificacion import (
    COLUMNAS_NOTIFICACIONES,
    MENSAJES,
    NotificacionRead,
    mensaje_de,
)
from backend.schemas.ticket import TicketUpdate, TicketWrite


@pytest.fixture
def motor() -> MemoryEngine:
    return MemoryEngine({"bug_tickets": [], "ticket_notificaciones": []})


@pytest.fixture
def tickets(motor) -> TicketRepository:
    return TicketRepository(motor)


@pytest.fixture
def avisos(motor) -> NotificacionRepository:
    return NotificacionRepository(motor)


# --- Contrato de los mensajes -------------------------------------------


def test_el_modelo_cubre_todas_las_columnas():
    faltan = set(COLUMNAS_NOTIFICACIONES) - set(NotificacionRead.model_fields)
    assert not faltan, f"NotificacionRead no expone: {sorted(faltan)}"


def test_hay_un_mensaje_por_cada_estatus_del_ticket():
    """Si se agrega un estatus y se olvida su texto, esta prueba lo dice."""
    from backend.schemas.ticket import ESTATUS_VALIDOS

    faltan = set(ESTATUS_VALIDOS) - set(MENSAJES)
    assert not faltan, f"Estatus sin mensaje de aviso: {sorted(faltan)}"


def test_el_mensaje_de_en_revision_es_el_que_pidio_el_dueno():
    assert mensaje_de("EN_REVISION") == (
        "Estamos trabajando en tu problema, te avisaremos cuando quede resuelto."
    )


def test_un_estatus_sin_mensaje_no_inventa_uno():
    """`None` es respuesta válida: significa "esto no amerita avisar"."""
    assert mensaje_de("ESTATUS_QUE_NO_EXISTE") is None
    assert mensaje_de(None) is None
    assert mensaje_de("") is None


# --- El aviso se genera solo -------------------------------------------


def test_reportar_un_bug_deja_acuse_de_recibo(tickets, avisos):
    tickets.crear(TicketWrite(modulo="Tracker", descripcion="X"), reportado_por="TERESA GARZA")
    bandeja = avisos.listar("TERESA GARZA")
    assert len(bandeja) == 1
    assert bandeja[0].estatus == "ABIERTO"
    assert bandeja[0].folio == "BUG-0001"
    assert bandeja[0].leida is False


def test_pasar_a_revision_avisa_a_quien_reporto(tickets, avisos):
    """El caso que pidió el dueño, tal cual."""
    tickets.crear(TicketWrite(modulo="PPC", descripcion="X"), reportado_por="TERESA GARZA")
    tickets.actualizar_estatus("BUG-0001", TicketUpdate(estatus="EN_REVISION", resuelto_por="SOPORTE"))

    bandeja = avisos.listar("TERESA GARZA")
    assert [a.estatus for a in bandeja] == ["EN_REVISION", "ABIERTO"], "el más reciente va primero"
    assert "te avisaremos cuando quede resuelto" in bandeja[0].mensaje


def test_cada_cambio_deja_su_propio_aviso(tickets, avisos):
    """Un aviso es un evento, no un estado: tres cambios, tres avisos."""
    tickets.crear(TicketWrite(modulo="PPC", descripcion="X"), reportado_por="TERESA GARZA")
    tickets.actualizar_estatus("BUG-0001", TicketUpdate(estatus="EN_REVISION"))
    tickets.actualizar_estatus("BUG-0001", TicketUpdate(estatus="RESUELTO", resuelto_por="SOPORTE"))
    assert [a.estatus for a in avisos.listar("TERESA GARZA")] == [
        "RESUELTO", "EN_REVISION", "ABIERTO",
    ]


def test_quien_mueve_su_propio_ticket_no_se_avisa_a_si_mismo(tickets, avisos):
    """Soporte resolviendo un bug que él mismo reportó: ya sabe lo que hizo."""
    tickets.crear(TicketWrite(modulo="PPC", descripcion="X"), reportado_por="LUIS_CARLOS")
    tickets.actualizar_estatus("BUG-0001", TicketUpdate(estatus="RESUELTO", resuelto_por="LUIS_CARLOS"))
    # Solo queda el acuse de recibo del alta.
    assert [a.estatus for a in avisos.listar("LUIS_CARLOS")] == ["ABIERTO"]


def test_el_aviso_va_a_quien_reporto_no_a_quien_resuelve(tickets, avisos):
    tickets.crear(TicketWrite(modulo="PPC", descripcion="X"), reportado_por="TERESA GARZA")
    tickets.actualizar_estatus("BUG-0001", TicketUpdate(estatus="RESUELTO", resuelto_por="ANTONIO_SALAZAR"))
    assert len(avisos.listar("TERESA GARZA")) == 2
    assert avisos.listar("ANTONIO_SALAZAR") == []


# --- Notificar nunca tumba el ticket ------------------------------------


def test_si_el_aviso_falla_el_ticket_se_guarda_igual(motor, tickets):
    """
    La regla más importante del módulo. Perder un aviso es molesto; perder
    el reporte de un bug es el defecto que este sistema existe para evitar.
    """
    original = motor.insertar

    def falla_solo_en_avisos(tabla, filas):
        if tabla == "ticket_notificaciones":
            raise ErrorDeMotor("la tabla de avisos no existe", codigo="PGRST205")
        return original(tabla, filas)

    motor.insertar = falla_solo_en_avisos
    creado = tickets.crear(TicketWrite(modulo="PPC", descripcion="X"), reportado_por="TERESA GARZA")

    assert creado.folio == "BUG-0001", "el ticket tenía que guardarse igual"
    assert motor.datos["ticket_notificaciones"] == []


def test_si_el_aviso_falla_el_cambio_de_estatus_se_guarda_igual(motor, tickets):
    tickets.crear(TicketWrite(modulo="PPC", descripcion="X"), reportado_por="TERESA GARZA")
    original = motor.insertar

    def falla_solo_en_avisos(tabla, filas):
        if tabla == "ticket_notificaciones":
            raise ErrorDeMotor("caída de red")
        return original(tabla, filas)

    motor.insertar = falla_solo_en_avisos
    actualizado = tickets.actualizar_estatus("BUG-0001", TicketUpdate(estatus="EN_REVISION"))
    assert actualizado.estatus == "EN_REVISION"


def test_un_ticket_sin_reportante_no_intenta_avisar(avisos):
    assert avisos.crear_para_ticket("BUG-1", "", "EN_REVISION") is None
    assert avisos.crear_para_ticket("BUG-1", None, "EN_REVISION") is None


# --- Bandeja: leer y marcar --------------------------------------------


def test_contar_no_leidas_es_el_numero_del_globito(tickets, avisos):
    tickets.crear(TicketWrite(modulo="PPC", descripcion="X"), reportado_por="TERESA GARZA")
    tickets.actualizar_estatus("BUG-0001", TicketUpdate(estatus="EN_REVISION"))
    assert avisos.contar_no_leidas("TERESA GARZA") == 2


def test_marcar_todas_como_leidas(tickets, avisos):
    tickets.crear(TicketWrite(modulo="PPC", descripcion="X"), reportado_por="TERESA GARZA")
    tickets.actualizar_estatus("BUG-0001", TicketUpdate(estatus="EN_REVISION"))

    assert avisos.marcar_leidas("TERESA GARZA") == 2
    assert avisos.contar_no_leidas("TERESA GARZA") == 0
    assert len(avisos.listar("TERESA GARZA")) == 2, "marcarlas no las borra"


def test_marcar_una_sola_por_id(tickets, avisos):
    tickets.crear(TicketWrite(modulo="PPC", descripcion="X"), reportado_por="TERESA GARZA")
    tickets.actualizar_estatus("BUG-0001", TicketUpdate(estatus="EN_REVISION"))
    bandeja = avisos.listar("TERESA GARZA")

    assert avisos.marcar_leidas("TERESA GARZA", ids=[bandeja[0].id]) == 1
    assert avisos.contar_no_leidas("TERESA GARZA") == 1


def test_marcar_dos_veces_no_cuenta_dos_veces(tickets, avisos):
    tickets.crear(TicketWrite(modulo="PPC", descripcion="X"), reportado_por="TERESA GARZA")
    assert avisos.marcar_leidas("TERESA GARZA") == 1
    assert avisos.marcar_leidas("TERESA GARZA") == 0


def test_nadie_ve_la_bandeja_de_otro(tickets, avisos):
    tickets.crear(TicketWrite(modulo="PPC", descripcion="A"), reportado_por="TERESA GARZA")
    tickets.crear(TicketWrite(modulo="PPC", descripcion="B"), reportado_por="MIGUEL GALLARDO")
    assert [a.folio for a in avisos.listar("TERESA GARZA")] == ["BUG-0001"]
    assert [a.folio for a in avisos.listar("MIGUEL GALLARDO")] == ["BUG-0002"]


def test_nadie_marca_como_leido_el_aviso_de_otro(tickets, avisos):
    """
    El filtro por destinatario se aplica también cuando vienen ids: mandar el
    id de otra persona no debe marcárselo.
    """
    tickets.crear(TicketWrite(modulo="PPC", descripcion="A"), reportado_por="TERESA GARZA")
    ajeno = avisos.listar("TERESA GARZA")[0]

    assert avisos.marcar_leidas("MIGUEL GALLARDO", ids=[ajeno.id]) == 0
    assert avisos.contar_no_leidas("TERESA GARZA") == 1, "le marcaron el aviso a otra persona"


def test_sin_destinatario_no_se_lista_ni_se_marca_nada(avisos):
    assert avisos.listar("") == []
    assert avisos.marcar_leidas("") == 0


# --- Endpoints ----------------------------------------------------------


@pytest.fixture
def cliente(tickets):
    from fastapi.testclient import TestClient

    from api.main import app
    from backend.routers.tickets import obtener_repositorio

    app.dependency_overrides[obtener_repositorio] = lambda: tickets
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_el_endpoint_devuelve_la_bandeja_y_el_contador(cliente):
    cliente.post("/api/v2/tickets",
                 json={"ticket": {"modulo": "PPC", "descripcion": "X"}, "reportado_por": "TERESA GARZA"})
    cuerpo = cliente.get("/api/v2/notificaciones", params={"usuario": "TERESA GARZA"}).json()
    assert cuerpo["no_leidas"] == 1
    assert cuerpo["data"][0]["estatus"] == "ABIERTO"


def test_el_endpoint_filtra_solo_no_leidas(cliente):
    cliente.post("/api/v2/tickets",
                 json={"ticket": {"modulo": "PPC", "descripcion": "X"}, "reportado_por": "TERESA GARZA"})
    cliente.post("/api/v2/notificaciones/marcar-leidas", json={"destinatario": "TERESA GARZA"})
    cliente.patch("/api/v2/tickets/BUG-0001", json={"estatus": "EN_REVISION"})

    todas = cliente.get("/api/v2/notificaciones", params={"usuario": "TERESA GARZA"}).json()
    nuevas = cliente.get("/api/v2/notificaciones",
                         params={"usuario": "TERESA GARZA", "solo_no_leidas": True}).json()
    assert len(todas["data"]) == 2
    assert [a["estatus"] for a in nuevas["data"]] == ["EN_REVISION"]


def test_el_endpoint_de_marcar_devuelve_el_contador_nuevo(cliente):
    cliente.post("/api/v2/tickets",
                 json={"ticket": {"modulo": "PPC", "descripcion": "X"}, "reportado_por": "TERESA GARZA"})
    r = cliente.post("/api/v2/notificaciones/marcar-leidas",
                     json={"destinatario": "TERESA GARZA"}).json()
    assert r["marcadas"] == 1 and r["no_leidas"] == 0


def test_el_endpoint_exige_saber_de_quien_es_la_bandeja(cliente):
    assert cliente.get("/api/v2/notificaciones").status_code == 422
    assert cliente.post("/api/v2/notificaciones/marcar-leidas", json={}).status_code == 422


def test_el_endpoint_de_marcar_no_acepta_campos_extra(cliente):
    """`extra="forbid"`: nadie cuela un campo que el servidor no espera."""
    r = cliente.post("/api/v2/notificaciones/marcar-leidas",
                     json={"destinatario": "TERESA GARZA", "leida": False})
    assert r.status_code == 422


def test_los_endpoints_de_avisos_traducen_el_fallo_del_motor():
    from fastapi.testclient import TestClient

    from api.main import app
    from backend.routers.tickets import obtener_repositorio

    motor = MemoryEngine({"bug_tickets": [], "ticket_notificaciones": []})

    def revienta(*args, **kwargs):
        raise ErrorDeMotor("PostgREST GET ticket_notificaciones?select=* respondió 404",
                           codigo="PGRST205")

    motor.select = revienta
    app.dependency_overrides[obtener_repositorio] = lambda: TicketRepository(motor)
    try:
        cli = TestClient(app)
        listado = cli.get("/api/v2/notificaciones", params={"usuario": "X"})
        marcar = cli.post("/api/v2/notificaciones/marcar-leidas", json={"destinatario": "X"})
    finally:
        app.dependency_overrides.clear()

    for respuesta in (listado, marcar):
        assert respuesta.status_code in (502, 503)
        assert "PostgREST" not in respuesta.json()["detail"]
