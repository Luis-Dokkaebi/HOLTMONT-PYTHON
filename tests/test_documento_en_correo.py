"""
Los documentos que se suben a la columna `CORREO` del tracker.

Reporte del dueño (2026-08-12):

    «Al cargarse imágenes en columna *correo*, estas al guardarse dejan de ser
    visibles en spreadsheet (se borran). Se intentó cargar nuevamente, mismo
    efecto. Se cargó el documento en ambas columnas, solamente se mantiene la
    columna *Carpeta*.»

La causa no estaba en la subida —el archivo sí llega a Storage y
`/api/legacy/upload` devuelve su URL— sino en el guardado de la fila:

  * `TASK_HEADER_MAP` expone `("CORREO", "correo")`, así que la columna se
    **lee** y se pinta;
  * `ALIAS_DE_HOJA` no tenía entrada para `correo` y `SOLO_LECTURA` la
    incluía, así que `columnas_desde_hoja` la **descartaba en silencio** al
    guardar y el upsert nunca la escribía.

De ahí los tres síntomas exactos del reporte: el enlace desaparece al guardar,
reintentar no cambia nada (se vuelve a descartar), y `CARPETA` —que sí tenía
alias— es la única que sobrevive.

La decisión original de dejarla de solo lectura está documentada en el
comentario de `SOLO_LECTURA`: se midió que sus 2.266 valores son enlaces de
Drive y no direcciones de correo, y se dejó como dato congelado porque «los
archivos quedan fuera del alcance de esta fase». Esa medición sigue siendo
cierta y es justo la razón por la que ahora se acepta: es una columna de
archivos, `index.html` la trata como tal (`isMediaColumn` la lista junto a
`CARPETA`), y el usuario sube documentos ahí a diario.
"""

from __future__ import annotations

import pytest

from api.services import tracker_store
from backend.core.engines.memoria import MemoryEngine
from backend.schemas.task import ALIAS_DE_HOJA, SOLO_LECTURA, TaskWrite
from backend.services.persistencia import PersistenciaTracker

DRIVE_CORREO = "https://drive.google.com/file/d/CORREO-1/view"
DRIVE_CARPETA = "https://drive.google.com/file/d/CARPETA-1/view"

SEMILLA = {
    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "dedupe_key": "JAIME OLIVO::JO-0001",
    "folio": "JO-0001",
    "source_sheet": "JAIME OLIVO",
    "concepto": "REVISAR PLANOS",
    "assignee_raw": "JAIME OLIVO",
    "avance": 0.0,
    "status": "ASIGNADO",
    "correo": "",
    "carpeta": "",
}


@pytest.fixture
def tracker(monkeypatch):
    motor = MemoryEngine({
        "tasks": [dict(SEMILLA)],
        "quotes": [],
        "people": [],
        "plan_semanal": [],
        "task_involucrados": [],
        "system_log": [],
    })
    monkeypatch.setattr(tracker_store, "_persistencia", lambda: PersistenciaTracker(motor))
    monkeypatch.setattr(
        tracker_store, "read_values",
        lambda hoja: [["FOLIO", "CONCEPTO", "RESPONSABLE", "AVANCE", "ESTATUS"]],
    )
    return motor


def _fila(motor: MemoryEngine, folio: str = "JO-0001") -> dict:
    return [f for f in motor.select("tasks") if f["folio"] == folio][0]


# ---------------------------------------------------------------------------
# El contrato: la columna dejó de ser de solo lectura
# ---------------------------------------------------------------------------

def test_correo_se_puede_escribir_desde_el_cliente() -> None:
    """
    Es la prueba que invierte a propósito la decisión anterior.

    Estaba en `SOLO_LECTURA` con la nota «los archivos quedan fuera del alcance
    de esta fase». La fase terminó en cuanto la subida de archivos llegó a la
    vista: dejarla de solo lectura significa borrar lo que el usuario acaba de
    subir, que es peor que cualquiera de los riesgos que se querían evitar.
    """
    assert "correo" not in SOLO_LECTURA
    assert "correo" in TaskWrite.model_fields
    assert "CORREO" in ALIAS_DE_HOJA["correo"]


def test_el_enlace_llega_a_la_columna_al_traducir_la_fila() -> None:
    """`columnas_desde_hoja` descartaba `CORREO` sin avisar."""
    modelo = TaskWrite.desde_hoja({"FOLIO": "JO-0001", "CORREO": DRIVE_CORREO})
    assert modelo.correo == DRIVE_CORREO
    assert "correo" in modelo.columnas()


def test_el_encabezado_en_plural_tambien_resuelve() -> None:
    """`index.html` lista `CORREOS` junto a `CORREO` en `isMediaColumn`."""
    assert TaskWrite.desde_hoja({"FOLIO": "JO-0001", "CORREOS": DRIVE_CORREO}).correo == DRIVE_CORREO


def test_varios_archivos_conservan_el_salto_de_linea() -> None:
    """
    `handleCellFile` concatena los enlaces con `\\n` en la misma celda.

    Si el modelo recortara o normalizara el texto, el segundo documento que
    subiera el usuario se comería al primero.
    """
    dos = DRIVE_CORREO + "\n" + "https://drive.google.com/file/d/CORREO-2/view"
    assert TaskWrite.desde_hoja({"FOLIO": "JO-0001", "CORREO": dos}).correo == dos


# ---------------------------------------------------------------------------
# El síntoma, por el camino que usa la vista
# ---------------------------------------------------------------------------

def test_el_documento_subido_a_correo_sobrevive_al_guardado(tracker) -> None:
    """El reporte, tal cual: se sube a `CORREO` y se guarda la fila."""
    respuesta = tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"FOLIO": "JO-0001", "CONCEPTO": "REVISAR PLANOS",
          "RESPONSABLE": "JAIME OLIVO", "ESTATUS": "ASIGNADO",
          "CORREO": DRIVE_CORREO}],
        username="JAIME_OLIVO",
    )

    assert respuesta["success"] is True, respuesta.get("message")
    assert _fila(tracker)["correo"] == DRIVE_CORREO


def test_cargar_en_las_dos_columnas_conserva_las_dos(tracker) -> None:
    """
    «Se cargó el documento en ambas columnas, solamente se mantiene la columna
    *Carpeta*».
    """
    respuesta = tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"FOLIO": "JO-0001", "CONCEPTO": "REVISAR PLANOS",
          "RESPONSABLE": "JAIME OLIVO", "ESTATUS": "ASIGNADO",
          "CORREO": DRIVE_CORREO, "CARPETA": DRIVE_CARPETA}],
        username="JAIME_OLIVO",
    )

    assert respuesta["success"] is True, respuesta.get("message")
    fila = _fila(tracker)
    assert fila["correo"] == DRIVE_CORREO
    assert fila["carpeta"] == DRIVE_CARPETA


def test_reintentar_la_carga_no_vuelve_a_borrarla(tracker) -> None:
    """«Cargar nuevamente, mismo efecto»: el segundo guardado también persiste."""
    for enlace in (DRIVE_CORREO, DRIVE_CORREO + "\nhttps://drive.google.com/file/d/CORREO-2/view"):
        tracker_store.save_tracker_batch(
            "JAIME OLIVO",
            [{"FOLIO": "JO-0001", "CONCEPTO": "REVISAR PLANOS",
              "RESPONSABLE": "JAIME OLIVO", "ESTATUS": "ASIGNADO",
              "CORREO": enlace}],
            username="JAIME_OLIVO",
        )
        assert _fila(tracker)["correo"] == enlace


def test_el_enlace_guardado_se_vuelve_a_ver_en_la_hoja(tracker) -> None:
    """
    Lo que ve el usuario: la matriz que arma la vista trae el enlace bajo
    `CORREO`. Guardar bien pero no devolverlo sería el mismo síntoma.
    """
    from api.services.sheets import TASK_HEADER_MAP, _valores_de_tareas

    tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"FOLIO": "JO-0001", "CONCEPTO": "REVISAR PLANOS",
          "RESPONSABLE": "JAIME OLIVO", "ESTATUS": "ASIGNADO",
          "CORREO": DRIVE_CORREO}],
        username="JAIME_OLIVO",
    )

    valores = _valores_de_tareas(tracker.select("tasks"))
    encabezados = [h for h, _ in TASK_HEADER_MAP]
    columna = valores[0].index("CORREO")
    assert valores[0][:len(encabezados)] == encabezados
    fila = [f for f in valores[1:] if f and f[0] == "JO-0001"][0]
    assert fila[columna] == DRIVE_CORREO


def test_guardar_sin_tocar_correo_no_borra_el_documento(tracker) -> None:
    """
    Una edición cualquiera (cambiar el avance) no puede llevarse por delante el
    archivo: la columna ausente conserva lo que había, que es el contrato del
    upsert con merge de `preparar_fila`.
    """
    tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"FOLIO": "JO-0001", "CONCEPTO": "REVISAR PLANOS",
          "RESPONSABLE": "JAIME OLIVO", "ESTATUS": "ASIGNADO",
          "CORREO": DRIVE_CORREO}],
        username="JAIME_OLIVO",
    )
    tracker_store.save_tracker_batch(
        "JAIME OLIVO",
        [{"FOLIO": "JO-0001", "CONCEPTO": "REVISAR PLANOS",
          "RESPONSABLE": "JAIME OLIVO", "ESTATUS": "ASIGNADO", "AVANCE": "50"}],
        username="JAIME_OLIVO",
    )

    fila = _fila(tracker)
    assert fila["correo"] == DRIVE_CORREO
    assert fila["avance"] == 50.0
