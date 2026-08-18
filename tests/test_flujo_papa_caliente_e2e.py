"""
El flujo de papa caliente de punta a punta, sobre la base en memoria.

Las pruebas de `test_flujo_asignacion.py` y `test_asignacion_bilateral.py` fijan
cada regla por separado —con `_persist_batch` sustituido por un doble— y esa
separación es la correcta para una regla. Lo que ninguna cubría es el recorrido
completo: seis guardados reales encadenados, cada uno leyendo el estado que
dejó el anterior en la base.

La secuencia vive en `verification/verify_papa_caliente.py`, que también se
corre a mano para inspeccionar la traza. Aquí se ejecuta la misma función y se
comprueban sus resultados, para que el trazador no se pudra en silencio: si una
regla cambia, esta prueba lo dice antes de que alguien abra el script.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verification import verify_papa_caliente as traza  # noqa: E402


@pytest.fixture(scope="module")
def recorrido():
    return traza.recorrer()


def _paso(recorrido, indice: int):
    return recorrido["pasos"][indice]


def test_el_recorrido_no_deja_parcheado_el_modulo_de_guardado():
    """
    `recorrer()` apunta `tracker_store` al motor en memoria; al terminar tiene
    que devolverlo como estaba o contaminaría al resto de la suite.
    """
    from api.services import tracker_store

    antes = (tracker_store._persistencia, tracker_store.read_values)
    traza.recorrer()
    assert (tracker_store._persistencia, tracker_store.read_values) == antes


def test_delegar_una_fase_crea_una_microtarea_por_trabajador(recorrido):
    """Paso 1: la fila se queda en ventas y aparece en la tabla de cada quien."""
    paso = _paso(recorrido, 1)

    assert paso["respuesta"]["success"] is True
    hojas = {m["hoja"] for m in paso["microtareas"]}
    assert hojas == {traza.MIGUEL, traza.ROLANDO}
    assert all("[" in m["concepto"] for m in paso["microtareas"]), (
        "la fase va marcada en el CONCEPTO: es lo que distingue una microtarea")
    assert {m["estatus"] for m in paso["microtareas"]} == {"ASIGNADO"}


def test_las_copias_no_comparten_clave(recorrido):
    """
    Sin `clave_de_copia` las dos filas colapsarían en una: `AV-` es prefijo de
    secuencia global y `compute_dedupe_key` devolvería el folio a secas.
    """
    claves = [m["dedupe_key"] for m in _paso(recorrido, 1)["microtareas"]]
    assert sorted(claves) == [f"{traza.MIGUEL}::{traza.FOLIO}",
                              f"{traza.ROLANDO}::{traza.FOLIO}"]


def test_no_se_delega_una_fase_dejando_otra_abierta(recorrido):
    """Paso 2: el intento se rechaza con el motivo y sin escribir nada."""
    bloqueado = _paso(recorrido, 2)
    previo = _paso(recorrido, 1)

    assert bloqueado["respuesta"]["success"] is False
    assert "CD sigue abierta" in bloqueado["respuesta"]["message"]
    assert bloqueado["proceso_log"] == previo["proceso_log"], (
        "un rechazo no puede dejar media delegación escrita")
    assert bloqueado["maestra"] == previo["maestra"]


def test_el_cierre_de_uno_no_pinta_la_fase_de_verde(recorrido):
    """Paso 3: Miguel termina, Rolando no. La fase sigue en rojo."""
    paso = _paso(recorrido, 3)

    estados = {(e["assignee"], e["status"]) for e in paso["proceso_log"]}
    assert (traza.MIGUEL, "DONE") in estados
    assert (traza.ROLANDO, "IN_PROGRESS") in estados
    assert "🔴 CD" in paso["maestra"]["map_cot"]


def test_la_fase_se_pinta_verde_cuando_terminan_todos(recorrido):
    """Paso 4: con las dos entradas en DONE, y no antes."""
    paso = _paso(recorrido, 4)

    assert all(e["status"] == "DONE" for e in paso["proceso_log"])
    assert "🟢 CD" in paso["maestra"]["map_cot"]


def test_cerrar_una_fase_no_cierra_la_cotizacion(recorrido):
    """
    La regla del dueño: el 100 % de una microtarea pinta la fase, no archiva la
    venta. La maestra llega al final con su avance y su estatus intactos.
    """
    for indice in (3, 4, 5):
        maestra = _paso(recorrido, indice)["maestra"]
        assert maestra["avance"] == 0.0
        assert maestra["estatus"] == "EN PROCESO"
        assert "[" not in maestra["concepto"], (
            "la maestra no hereda el concepto marcado con la fase")


def test_cerrada_la_fase_anterior_ya_se_delega_la_siguiente(recorrido):
    """Paso 5: el mismo intento del paso 2, ahora permitido."""
    paso = _paso(recorrido, 5)

    assert paso["respuesta"]["success"] is True
    assert any(e["step"] == "EP" and e["status"] == "IN_PROGRESS"
               for e in paso["proceso_log"])
    assert "🟢 CD" in paso["maestra"]["map_cot"]
    assert "🔴 EP" in paso["maestra"]["map_cot"]


def test_todas_las_invariantes_del_flujo_se_cumplen(recorrido):
    """
    Las seis propiedades que el trazador comprueba contra el estado final: las
    cinco del recorrido más la del destino, que barre a los nueve vendedores.
    Se afirman con nombre para que un fallo diga cuál se rompió.
    """
    incumplidas = [i["nombre"] for i in recorrido["invariantes"] if not i["cumple"]]
    assert not incumplidas, f"invariantes rotas: {incumplidas}"
    assert len(recorrido["invariantes"]) == 6


def test_ningun_vendedor_recibe_su_fase_en_quotes(recorrido):
    """
    La matriz del trazador, afirmada: los nueve vendedores con tabla `(VENTAS)`
    reciben la microtarea en `tasks`, y la regla anterior los mandaba a `quotes`
    —esa columna se mide, no se supone, para que el antes/después sea real—.
    """
    matriz = recorrido["vendedores"]
    assert len(matriz) == 9
    assert all(f["ahora"]["tabla"] == "tasks" for f in matriz)
    assert all(f["antes"]["tabla"] == "quotes" for f in matriz), (
        "si esto deja de fallar con la regla vieja, el experimento ya no compara nada")
