"""
Una fase delegada cae SIEMPRE en el tracker de la persona.

Decisión del dueño (2026-08-09): "las delegaciones siempre van al Tracker y no
a cotizaciones, incluso si es vendedor siempre va a su Tracker. Si Antonia
delega en papa caliente a Sebastián, no cae en su tabla ventas sino en su tabla
de Tracker".

Lo que había antes: `resolve_worker_sheet` probaba el tracker y, si esa
partición estaba vacía, **se caía a `<NOMBRE> (VENTAS)`**. Como el ruteo de
`PersistenciaTracker` decide la tabla por el nombre de la hoja
(`is_sales_sheet` -> `quotes`), la microtarea de un vendedor sin filas en su
tracker acababa entre sus cotizaciones. Y si no tenía ninguna de las dos
particiones, la función devolvía `None`: la delegación se perdía en silencio,
con `success: true` para Toñita y la fase abierta para siempre.

Es la misma familia de decisión que `tabla_de_cotizaciones` ya resolvió en el
sentido contrario —una cotización no se filtra al tracker de nadie—, ahora
aplicada al reparto por fases: una microtarea no se filtra a la tabla de ventas
de nadie.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import tracker_rules as rules  # noqa: E402
from api.services import tracker_store  # noqa: E402
from api.services.asignacion import VENDEDORES_CON_TABLA  # noqa: E402
from backend.core.engines.memoria import MemoryEngine  # noqa: E402
from backend.services.persistencia import PersistenciaTracker  # noqa: E402

FOLIO = "AV-3250"

# Las siete personas que ofrece el modal de delegación de `index.html`
# (directorio filtrado por dept/type VENTAS o HIBRIDO, más Miguel Gallardo).
CANDIDATOS_DEL_MODAL = (
    "TERESA GARZA", "ANGEL SALINAS", "EDUARDO MANZANARES", "RAMIRO RODRIGUEZ",
    "SEBASTIAN PADILLA", "MIGUEL GALLARDO", "ADMINISTRADOR",
)


# ----------------------------------------------------------------------
# La regla, sobre la función que resuelve el destino
# ----------------------------------------------------------------------

@pytest.mark.parametrize("vendedor", VENDEDORES_CON_TABLA)
def test_ningun_vendedor_recibe_su_fase_en_la_tabla_de_ventas(vendedor):
    """
    Los nueve vendedores con tabla `(VENTAS)`. El destino es su tracker, y la
    resolución ya no depende de qué partición exista: es el nombre, punto.
    """
    destino = tracker_store.resolve_worker_sheet(vendedor)

    assert destino == vendedor
    assert not rules.is_sales_sheet(destino), (
        f"{vendedor}: una fase delegada nunca cae en una tabla de ventas")


@pytest.mark.parametrize("persona", CANDIDATOS_DEL_MODAL)
def test_todo_candidato_del_modal_resuelve_a_su_tracker(persona):
    """Lo mismo para la lista que de verdad ofrece el modal de delegación."""
    assert tracker_store.resolve_worker_sheet(persona) == persona


def test_el_sufijo_ventas_del_nombre_no_cambia_el_destino():
    """"Sebastian Padilla (VENTAS)" y "sebastian padilla" son la misma persona."""
    assert tracker_store.resolve_worker_sheet("Sebastian Padilla (VENTAS)") == "SEBASTIAN PADILLA"
    assert tracker_store.resolve_worker_sheet("  sebastian padilla  ") == "SEBASTIAN PADILLA"


def test_una_fase_asignada_a_antonia_va_a_su_tracker_personal():
    """
    `ANTONIA_VENTAS` es la tabla de ventas, no la tabla de una persona: el
    trabajo que se le asigna a Antonia va a su tracker. Es la Ley de Antonia,
    ya vigente en `asignacion.hoja_de_persona`.
    """
    assert tracker_store.resolve_worker_sheet("ANTONIA_VENTAS") == rules.ANTONIA_PERSONAL_SHEET


@pytest.mark.parametrize("vacio", ["", "   ", None, "(VENTAS)"])
def test_un_nombre_vacio_no_inventa_un_destino(vacio):
    """Sin nombre no hay hoja: sigue devolviendo None, no una cadena vacía."""
    assert tracker_store.resolve_worker_sheet(vacio) is None


# ----------------------------------------------------------------------
# La regla, de punta a punta contra la base
# ----------------------------------------------------------------------

def _motor_con_vendedores() -> MemoryEngine:
    """
    Base donde cada vendedor tiene SOLO su tabla de ventas poblada.

    Es el peor caso de la regla vieja: el tracker de todos está vacío, así que
    las nueve delegaciones se desviaban a `quotes`.
    """
    return MemoryEngine({
        "quotes": [{
            "folio": FOLIO, "source_sheet": rules.SALES_MASTER_SHEET,
            "cliente": "ACME", "concepto": "COTIZAR NAVE", "avance": 0.0,
            "estatus": "EN PROCESO", "map_cot": "", "proceso_log": "",
        }] + [{
            "folio": f"AV-{100 + i}", "source_sheet": f"{nombre} (VENTAS)",
            "concepto": "OTRA COTIZACION", "avance": 0.0, "estatus": "EN PROCESO",
        } for i, nombre in enumerate(VENDEDORES_CON_TABLA)],
        "tasks": [],
        "people": [],
        "plan_semanal": [],
        "task_involucrados": [],
        "system_log": [],
    })


@pytest.fixture
def base(monkeypatch):
    """`tracker_store` leyendo y escribiendo contra el motor en memoria."""
    from api.services import sheets

    motor = _motor_con_vendedores()
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: PersistenciaTracker(motor))

    def leer(hoja):
        clave = sheets._clave_hoja(hoja)
        cotizaciones = [f for f in motor.select("quotes")
                        if sheets._clave_hoja(f.get("source_sheet")) == clave]
        if cotizaciones:
            return sheets._valores_de_cotizaciones(cotizaciones) or []
        tareas = [f for f in motor.select("tasks")
                  if sheets._clave_hoja(f.get("source_sheet")) == clave]
        if tareas:
            return sheets._valores_de_tareas(tareas) or []
        return []

    monkeypatch.setattr(tracker_store, "read_values", leer)
    return motor


def _delegar(persona: str, paso: str = "CD"):
    return tracker_store.save_tracker_batch(rules.SALES_MASTER_SHEET, [{
        "FOLIO": FOLIO, "CONCEPTO": "COTIZAR NAVE",
        "_assignToWorker": [persona], "_assignStep": paso,
    }], username=rules.SALES_MASTER_SHEET)


@pytest.mark.parametrize("vendedor", VENDEDORES_CON_TABLA)
def test_la_fase_delegada_a_un_vendedor_aterriza_en_tasks(vendedor, base):
    """
    El caso que preguntó el dueño, con los nueve: Antonia delega a Sebastián y la
    microtarea aparece en su tracker, no entre sus cotizaciones.
    """
    respuesta = _delegar(vendedor)
    assert respuesta["success"] is True, respuesta.get("message")

    en_tasks = [f for f in base.select("tasks") if f["folio"] == FOLIO]
    copias_en_quotes = [f for f in base.select("quotes")
                        if f["folio"] == FOLIO
                        and f["source_sheet"] != rules.SALES_MASTER_SHEET]

    assert len(en_tasks) == 1, f"{vendedor}: la fase tiene que caer en su tracker"
    assert rules.normalize_staff_name(en_tasks[0]["source_sheet"]) == vendedor
    assert "[" in en_tasks[0]["concepto"], "sigue siendo una microtarea de fase"
    assert copias_en_quotes == [], (
        f"{vendedor}: ninguna copia puede acabar en una tabla de ventas")


def test_la_cotizacion_maestra_no_se_toca_al_delegar(base):
    """Delegar reparte trabajo; no altera el avance ni el estatus de la venta."""
    _delegar("SEBASTIAN PADILLA")

    maestra = [f for f in base.select("quotes")
               if f["source_sheet"] == rules.SALES_MASTER_SHEET][0]
    assert maestra["avance"] == 0.0
    assert maestra["estatus"] == "EN PROCESO"
    assert "🔴 CD" in maestra["map_cot"]


def test_el_vendedor_cierra_su_fase_desde_el_tracker_y_la_maestra_se_entera(base):
    """
    El reverse sync sigue funcionando con el destino nuevo: el folio `AV-` vuelve
    a la maestra desde la hoja propia del trabajador.
    """
    _delegar("SEBASTIAN PADILLA")
    tracker_store.save_tracker_batch("SEBASTIAN PADILLA", [{
        "FOLIO": FOLIO,
        "CONCEPTO": f"COTIZAR NAVE [{rules.phase_label('CD')}]",
        "AVANCE": "100", "ESTATUS": "HECHO",
    }], username="SEBASTIAN PADILLA")

    maestra = [f for f in base.select("quotes")
               if f["source_sheet"] == rules.SALES_MASTER_SHEET][0]
    assert "🟢 CD" in maestra["map_cot"], "la fase se cierra en el timeline"
    assert maestra["avance"] == 0.0, "pero el 100 % de una fase no cierra la venta"


def test_una_persona_sin_ninguna_particion_ya_no_pierde_su_fase(base):
    """
    El agujero silencioso de la regla vieja: sin tracker y sin tabla de ventas,
    `resolve_worker_sheet` devolvía `None`, la fila no se escribía en ningún
    lado y quien delegaba veía "Guardado exitoso". Ahora la persona estrena su
    tracker.

    Se borran las cotizaciones del vendedor para dejarlo sin ninguna partición,
    que es la situación real de quien todavía no tiene nada capturado.
    """
    base.datos["quotes"] = [f for f in base.datos["quotes"]
                            if f["source_sheet"] == rules.SALES_MASTER_SHEET]

    respuesta = _delegar("ANGEL SALINAS")

    assert respuesta["success"] is True
    filas = [f for f in base.select("tasks") if f["folio"] == FOLIO]
    assert [f["source_sheet"] for f in filas] == ["ANGEL SALINAS"], (
        "una delegación no puede desaparecer sin dejar fila")


def test_dos_vendedores_en_la_misma_fase_reciben_cada_uno_en_su_tracker(base):
    """El reparto múltiple no colapsa: una fila por tracker, con clave propia."""
    tracker_store.save_tracker_batch(rules.SALES_MASTER_SHEET, [{
        "FOLIO": FOLIO, "CONCEPTO": "COTIZAR NAVE",
        "_assignToWorker": ["SEBASTIAN PADILLA", "TERESA GARZA"],
        "_assignStep": "CD",
    }], username=rules.SALES_MASTER_SHEET)

    filas = [f for f in base.select("tasks") if f["folio"] == FOLIO]
    assert {f["source_sheet"] for f in filas} == {"SEBASTIAN PADILLA", "TERESA GARZA"}
    assert len({f["dedupe_key"] for f in filas}) == 2
