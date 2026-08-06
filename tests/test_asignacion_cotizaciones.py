"""
Una cotización asignada solo puede caer en una tabla `(VENTAS)`.

Regla del dueño (2026-08-06), que **corrige al original**:

    Si no existe la hoja `<Nombre> (VENTAS)`, esa persona ni siquiera debe
    aparecer como destino posible, porque no hay a dónde mandarlo. Una
    cotización no se filtra al tracker de nadie.

El original sí tiene ese escape. `CODIGO.js:2850-2862` intenta primero
`<Nombre> (VENTAS)` y, si esa hoja no existe, **se cae al tracker personal**:

    } else if (findSheetSmart(targetSheet)) {
        finalTarget = targetSheet;      // <- el tracker, no la tabla de ventas
    }

Y esta migración lo empeoraba: `destinos_espejo` resolvía el destino con
`hoja_de_persona`, que purga el sufijo `(VENTAS)` **siempre**, sin mirar quién
asigna. El resultado medido contra la base real el 2026-08-06: Antonia asignó
la cotización `AV-9998` a Teresa Garza y la copia cayó en `tasks`, hoja
`TERESA GARZA` —su tracker de actividades— en vez de en `quotes`, hoja
`TERESA GARZA (VENTAS)`.

La excepción sí estaba implementada, pero en otra función que este camino no
usaba: `resolve_tracker_target(persona, username)` respeta el sufijo cuando
quien asigna es Toñita. `destinos_espejo` ni siquiera recibía el `username`,
así que no podía aplicarla.

Dos decisiones del dueño que esta prueba fija:

  * **Quién tiene tabla `(VENTAS)`.** Tres fuentes discrepaban (el directorio,
    la bandera `seller` de perfiles y las hojas con datos en la base). Se
    resolvió por la unión de las dos que están respaldadas por algo real: el
    directorio (`type` VENTAS/HÍBRIDO, que es lo que en el original crea la
    hoja) y las hojas que tienen cotizaciones migradas. Quedan fuera Alfonso
    Correa y Judith Echavarría, que solo aparecen en la bandera `seller`.
  * **Solo Toñita reparte cotizaciones.** Un vendedor que asigne desde su
    propia tabla no tiene destino: la Ley de Antonia ya le prohíbe escribir en
    una hoja `(VENTAS)` ajena, y el tracker dejó de ser una salida.
"""

from __future__ import annotations

import pytest

from api.services import tracker_store
from api.services.asignacion import (
    VENDEDORES_CON_TABLA,
    destinos_espejo,
    tabla_de_cotizaciones,
)
from backend.core.engines.memoria import MemoryEngine
from backend.services.persistencia import PersistenciaTracker

ANTONIA = "ANTONIA_VENTAS"

# Los ocho que el dueño autorizó como destino de una cotización.
CON_TABLA = [
    "EDUARDO MANZANARES", "RAMIRO RODRIGUEZ", "SEBASTIAN PADILLA", "TERESA GARZA",
    "ANGEL SALINAS", "EDUARDO TERAN", "EDGAR LOPEZ", "JUAN JOSE SANCHEZ",
]

# Personas reales del directorio que **no** tienen tabla de cotizaciones.
SIN_TABLA = [
    "ALFONSO CORREA", "JUDITH ECHAVARRIA", "GERALDINE MARTINEZ HERNANDEZ",
    "JAIME OLIVO", "VANESSA DE LARA", "ROLANDO MORENO",
]


# ---------------------------------------------------------------------------
# Quién tiene tabla de cotizaciones
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("nombre", CON_TABLA)
def test_los_ocho_autorizados_tienen_tabla_de_cotizaciones(nombre: str) -> None:
    assert tabla_de_cotizaciones(nombre) == f"{nombre} (VENTAS)"


@pytest.mark.parametrize("nombre", SIN_TABLA)
def test_quien_no_vende_no_tiene_tabla_de_cotizaciones(nombre: str) -> None:
    """Sin tabla no hay destino: la cadena vacía es "no hay a dónde mandarlo"."""
    assert tabla_de_cotizaciones(nombre) == ""


def test_el_sufijo_ya_escrito_no_se_duplica() -> None:
    """El frontend manda el nombre con sufijo; no puede salir `X (VENTAS) (VENTAS)`."""
    assert tabla_de_cotizaciones("TERESA GARZA (VENTAS)") == "TERESA GARZA (VENTAS)"


def test_el_nombre_se_reconoce_sin_importar_como_venga_escrito() -> None:
    """`source_sheet` guarda capitalización mixta y el frontend pide en mayúsculas."""
    for variante in ("Sebastian Padilla", "  sebastian padilla  ", "SEBASTIAN PADILLA"):
        assert tabla_de_cotizaciones(variante) == "SEBASTIAN PADILLA (VENTAS)"


def test_antonia_no_es_destino_de_una_cotizacion() -> None:
    """
    `ANTONIA_VENTAS` es la tabla de ventas, no la de una persona.

    Es la decisión 3 del módulo: el trabajo que se le asigna a Antonia va a su
    tracker personal, y una cotización no se le "asigna" a la tabla maestra.
    """
    assert tabla_de_cotizaciones("ANTONIA_VENTAS") == ""


def test_la_lista_de_vendedores_es_explicita_y_no_deducida() -> None:
    """
    Se declara, no se infiere.

    Tres fuentes discrepaban y ninguna era correcta por sí sola. Dejarla como
    una lista visible obliga a que dar de alta a un vendedor sea una decisión
    consciente y auditable, en vez del efecto colateral de una bandera.
    """
    assert sorted(VENDEDORES_CON_TABLA) == sorted(CON_TABLA)


# ---------------------------------------------------------------------------
# A dónde va la copia
# ---------------------------------------------------------------------------

def test_antonia_asigna_una_cotizacion_a_la_tabla_de_ventas_del_vendedor() -> None:
    """El fallo medido en producción: caía en `TERESA GARZA`, no en su tabla."""
    destinos = destinos_espejo(ANTONIA, {"VENDEDOR": "TERESA GARZA (VENTAS)"},
                               username=ANTONIA)
    assert destinos == ["TERESA GARZA (VENTAS)"]


def test_antonia_asigna_a_alguien_sin_tabla_y_no_hay_destino() -> None:
    """
    Lo que el dueño pidió expresamente: no se filtra al tracker de nadie.

    Es el caso que el original resuelve mal (`CODIGO.js:2856`, el `else if` que
    se cae al tracker).
    """
    assert destinos_espejo(ANTONIA, {"VENDEDOR": "ALFONSO CORREA"},
                           username=ANTONIA) == []


def test_un_vendedor_no_reparte_cotizaciones() -> None:
    """Solo Toñita reparte: ni a la tabla del otro, ni a su tracker."""
    assert destinos_espejo("SEBASTIAN PADILLA (VENTAS)",
                           {"VENDEDOR": "TERESA GARZA"},
                           username="SEBASTIAN_PADILLA") == []


def test_asignar_a_varios_vendedores_reparte_a_las_tablas_que_existen() -> None:
    """De tres nombres, solo los dos con tabla reciben; el tercero no se cuela."""
    destinos = destinos_espejo(
        ANTONIA, {"VENDEDOR": "TERESA GARZA, ALFONSO CORREA, RAMIRO RODRIGUEZ"},
        username=ANTONIA)
    assert destinos == ["TERESA GARZA (VENTAS)", "RAMIRO RODRIGUEZ (VENTAS)"]


def test_la_asignacion_en_el_tracker_no_cambia() -> None:
    """
    La regla nueva es solo para cotizaciones.

    Comprobado contra la base real el 2026-08-06: `JO-9998` quedó en la hoja de
    Jaime y en la de Geraldine. Eso sigue igual y esta prueba lo protege.
    """
    assert destinos_espejo("JAIME OLIVO",
                           {"INVOLUCRADOS": "GERALDINE MARTINEZ HERNANDEZ"},
                           username="JAIME_OLIVO") == ["GERALDINE MARTINEZ HERNANDEZ"]


def test_un_vendedor_sigue_pudiendo_asignar_desde_su_tracker() -> None:
    """
    Ser vendedor no le quita su tracker.

    Sebastián asignando una **actividad** desde su tracker personal reparte
    como cualquiera; lo que no puede es repartir cotizaciones.
    """
    assert destinos_espejo("SEBASTIAN PADILLA",
                           {"INVOLUCRADOS": "JAIME OLIVO"},
                           username="SEBASTIAN_PADILLA") == ["JAIME OLIVO"]


# ---------------------------------------------------------------------------
# De punta a punta: la copia aterriza en `quotes`, no en `tasks`
# ---------------------------------------------------------------------------

@pytest.fixture
def motor():
    return MemoryEngine({
        "tasks": [], "quotes": [], "people": [], "plan_semanal": [],
        "task_involucrados": [], "system_log": [],
    })


@pytest.fixture
def tracker(monkeypatch, motor):
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: PersistenciaTracker(motor))
    monkeypatch.setattr(
        tracker_store, "read_values",
        lambda hoja: [["FOLIO", "CLIENTE", "CONCEPTO", "VENDEDOR", "AVANCE", "ESTATUS"]],
    )
    return motor


def test_la_cotizacion_asignada_aterriza_en_quotes_y_no_en_el_tracker(tracker):
    respuesta = tracker_store.save_tracker_batch(
        ANTONIA,
        [{"FOLIO": "AV-7001", "CLIENTE": "ACME", "CONCEPTO": "COTIZAR NAVE",
          "VENDEDOR": "TERESA GARZA (VENTAS)", "AVANCE": "0", "ESTATUS": "ASIGNADO"}],
        username=ANTONIA,
    )
    assert respuesta["success"] is True, respuesta.get("message")

    hojas = sorted(f["source_sheet"] for f in tracker.select("quotes")
                   if f["folio"] == "AV-7001")
    assert hojas == ["ANTONIA_VENTAS", "TERESA GARZA (VENTAS)"], (
        "la copia debe quedar en la tabla de cotizaciones de la vendedora"
    )
    assert [f for f in tracker.select("tasks") if f["folio"] == "AV-7001"] == [], (
        "una cotización nunca puede aparecer en el tracker de actividades"
    )


def test_asignar_a_quien_no_tiene_tabla_deja_la_cotizacion_solo_en_ventas(tracker):
    respuesta = tracker_store.save_tracker_batch(
        ANTONIA,
        [{"FOLIO": "AV-7002", "CLIENTE": "ACME", "CONCEPTO": "COTIZAR OFICINA",
          "VENDEDOR": "ALFONSO CORREA", "AVANCE": "0", "ESTATUS": "ASIGNADO"}],
        username=ANTONIA,
    )
    assert respuesta["success"] is True, respuesta.get("message")

    hojas = [f["source_sheet"] for f in tracker.select("quotes") if f["folio"] == "AV-7002"]
    assert hojas == ["ANTONIA_VENTAS"]
    assert [f for f in tracker.select("tasks") if f["folio"] == "AV-7002"] == [], (
        "sin tabla (VENTAS) no hay destino: no se filtra al tracker"
    )
