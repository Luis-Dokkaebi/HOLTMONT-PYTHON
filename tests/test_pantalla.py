"""
Las Pantallas de McDonald's: la tabla de un ejecutivo en una televisión colgada.

Solo muestra. No captura, no edita, no borra. Esa decisión la tomó Antonio y
cambia todo lo demás: sin escritura no hay concurrencia, no hay permisos por
fila y no hace falta sesión — una televisión no puede teclear una contraseña.

Lo que se prueba aquí es el preparado de los datos (`api/services/pantalla.py`),
que es donde viven las cuatro decisiones que una pantalla de pared impone y una
de escritorio no:

1. **Caben seis columnas, no veintiuna.** A cuatro metros, una tabla de 21
   columnas no se lee. Se eligen seis y `MONTO` **no** es una de ellas: la
   pantalla la ve todo el piso, incluidas visitas.
2. **Lo que falta va primero.** Una pantalla que abre con las tareas al 100 %
   gasta su única página en lo que ya está hecho.
3. **Las filas que no caben existen igual.** Se paginan para que la televisión
   las rote; recortarlas sin decirlo esconde trabajo.
4. **Una pantalla congelada se ve igual que una viva.** Por eso sale
   `generado_en`: es lo único que permite a la televisión saber —y decir— que
   lleva dos minutos sin datos frescos. Es el fallo peligroso de este módulo,
   porque nadie lo nota: la tabla se ve perfectamente normal.

El reloj se inyecta (R8): una prueba que llama a `datetime.now()` mide el
momento en que se corrió, no el comportamiento.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from api.services import pantalla

AHORA = datetime(2026, 9, 12, 17, 30, 0, tzinfo=timezone.utc)

FILA_TRACKER = {
    "FOLIO": "AV-1192", "RESPONSABLE": "EDUARDO MANZANARES", "AREA": "HVAC",
    "CONCEPTO": "Mantenimiento de chillers", "AVANCE": "40",
    "FECHA_ESTIMADA_FIN": "2026-09-20", "PRIORIDAD": "ALTA", "ESTATUS": "ASIGNADO",
    "COMENTARIOS": "hablar con el cliente", "RELOJ": "00:00:00", "_rowIndex": 4,
}

FILA_VENTAS = {
    "FOLIO": "1013.0", "AREA": "VENTAS", "CLIENTE": "PANASONIC MTY",
    "CONCEPTO": "Ampliación de nave", "AVANCE": "70", "F. ENTREGA": "2026-10-01",
    "ESTATUS": "EN PROCESO", "MONTO": "1250000", "COMENTARIOS": "pendiente layout",
}


# ----------------------------------------------------------------------
# Qué columnas se muestran
# ----------------------------------------------------------------------


def test_la_hoja_de_un_tracker_usa_las_columnas_del_tracker():
    assert pantalla.columnas_de("EDUARDO MANZANARES") == pantalla.COLUMNAS_TRACKER


def test_la_hoja_de_ventas_de_una_persona_usa_las_columnas_de_ventas():
    assert pantalla.columnas_de("EDUARDO MANZANARES (VENTAS)") == pantalla.COLUMNAS_VENTAS


def test_la_hoja_maestra_de_ventas_tambien_es_de_ventas():
    """
    `ANTONIA_VENTAS` no lleva "(VENTAS)" entre paréntesis y aun así lo es. La
    regla ya existe en `tracker_rules.is_sales_sheet` y no se reescribe aquí:
    dos copias de la misma regla se desincronizan y nadie se entera.
    """
    assert pantalla.columnas_de("ANTONIA_VENTAS") == pantalla.COLUMNAS_VENTAS


def test_el_monto_no_sale_por_defecto():
    """
    Va colgada en una pared que ve todo el piso y quien entre de visita. Que el
    importe de cada cotización sea legible desde el pasillo es una decisión de
    negocio, no un valor por defecto.
    """
    assert "MONTO" not in pantalla.columnas_de("EDUARDO MANZANARES (VENTAS)")


def test_el_monto_se_puede_encender_por_entorno(monkeypatch):
    monkeypatch.setenv(pantalla.ENV_MONTO, "1")
    assert "MONTO" in pantalla.columnas_de("EDUARDO MANZANARES (VENTAS)")


def test_encender_el_monto_no_lo_mete_en_un_tracker(monkeypatch):
    """El tracker no tiene columna de importe: añadirla pintaría una vacía."""
    monkeypatch.setenv(pantalla.ENV_MONTO, "1")
    assert "MONTO" not in pantalla.columnas_de("EDUARDO MANZANARES")


# ----------------------------------------------------------------------
# Leer el valor de una fila
# ----------------------------------------------------------------------


def test_solo_salen_las_columnas_elegidas():
    recortada = pantalla.solo_columnas([FILA_VENTAS], pantalla.COLUMNAS_VENTAS)[0]
    assert set(recortada) == set(pantalla.COLUMNAS_VENTAS)
    assert "MONTO" not in recortada
    assert "COMENTARIOS" not in recortada


def test_el_encabezado_se_reconoce_aunque_cambie_el_punto_o_el_acento():
    """
    En estas hojas conviven `F. ENTREGA`, `F.ENTREGA` y `FECHA_ESTIMADA_FIN` con
    y sin acento; `backend/schemas/hoja.clave_encabezado` ya resuelve eso y es
    el que se usa. Comparar cadenas crudas deja la columna vacía en pantalla sin
    ningún error: se ve como una cotización sin fecha de entrega.
    """
    fila = dict(FILA_VENTAS)
    fila["F.ENTREGA"] = fila.pop("F. ENTREGA")
    recortada = pantalla.solo_columnas([fila], pantalla.COLUMNAS_VENTAS)[0]
    assert recortada["F. ENTREGA"] == "2026-10-01"


def test_una_columna_que_la_fila_no_trae_sale_vacia_y_no_revienta():
    recortada = pantalla.solo_columnas([{"FOLIO": "AV-1"}], pantalla.COLUMNAS_TRACKER)[0]
    assert recortada["FOLIO"] == "AV-1"
    assert recortada["CONCEPTO"] == ""


# ----------------------------------------------------------------------
# El orden: lo que falta, primero
# ----------------------------------------------------------------------


def test_lo_pendiente_va_antes_que_lo_terminado():
    filas = [
        {"FOLIO": "hecha", "AVANCE": "100"},
        {"FOLIO": "pendiente", "AVANCE": "40"},
    ]
    assert [f["FOLIO"] for f in pantalla.pendientes_primero(filas)] == ["pendiente", "hecha"]


def test_el_uno_nativo_de_la_hoja_cuenta_como_cien_por_ciento():
    """
    Una celda con formato de porcentaje llega como `1`, no como `100`
    (AGENTS.md §4). Tratarlo como 1 % pondría en primera página, cada mañana,
    todo lo que ya se terminó. La regla vive en `tracker_rules` y se reutiliza.
    """
    filas = [{"FOLIO": "hecha", "AVANCE": 1}, {"FOLIO": "pendiente", "AVANCE": "40"}]
    assert [f["FOLIO"] for f in pantalla.pendientes_primero(filas)] == ["pendiente", "hecha"]


def test_el_orden_dentro_de_cada_grupo_no_se_toca():
    """
    Orden estable: dos pantallas seguidas con los mismos datos muestran lo mismo
    en el mismo sitio. Una tabla que se baraja sola es ilegible de lejos.
    """
    filas = [{"FOLIO": f"P{i}", "AVANCE": "10"} for i in range(5)]
    assert [f["FOLIO"] for f in pantalla.pendientes_primero(filas)] == [
        "P0", "P1", "P2", "P3", "P4"]


# ----------------------------------------------------------------------
# Las páginas que la televisión va a rotar
# ----------------------------------------------------------------------


def test_las_filas_se_reparten_en_paginas_del_tamano_pedido():
    paginas = pantalla.paginar([{"n": i} for i in range(25)], 10)
    assert [len(p) for p in paginas] == [10, 10, 5]


def test_sin_filas_hay_una_pagina_vacia_y_no_cero():
    """
    Cero páginas deja a la televisión sin nada que pintar y el bucle de rotación
    dividiendo entre cero. Una página vacía se pinta como "sin pendientes".
    """
    assert pantalla.paginar([], 10) == [[]]


def test_un_tamano_de_pagina_absurdo_no_cuelga_la_pantalla():
    assert pantalla.paginar([{"n": 1}], 0) == [[{"n": 1}]]


# ----------------------------------------------------------------------
# `preparar`: lo que consume la televisión
# ----------------------------------------------------------------------


def test_la_respuesta_trae_columnas_paginas_y_el_momento_en_que_se_genero():
    listo = pantalla.preparar([FILA_TRACKER], "EDUARDO MANZANARES", AHORA)
    assert listo["success"] is True
    assert listo["hoja"] == "EDUARDO MANZANARES"
    assert listo["columnas"] == list(pantalla.COLUMNAS_TRACKER)
    assert listo["paginas"] == [[{
        "FOLIO": "AV-1192", "CONCEPTO": "Mantenimiento de chillers", "AVANCE": "40",
        "FECHA_ESTIMADA_FIN": "2026-09-20", "PRIORIDAD": "ALTA", "ESTATUS": "ASIGNADO",
    }]]
    assert listo["generado_en"] == AHORA.isoformat()


def test_se_cuenta_cuanto_hay_y_cuanto_falta():
    filas = [dict(FILA_TRACKER, AVANCE="100"), dict(FILA_TRACKER, AVANCE="10")]
    listo = pantalla.preparar(filas, "EDUARDO MANZANARES", AHORA)
    assert listo["total"] == 2
    assert listo["pendientes"] == 1


def test_una_hoja_enorme_se_recorta_y_lo_dice():
    """
    Recortar está bien; recortar en silencio no. `total` sigue siendo el número
    real para que la pantalla pueda decir "mostrando 200 de 340".
    """
    filas = [dict(FILA_TRACKER, FOLIO=f"F{i}", AVANCE="10")
             for i in range(pantalla.TOPE_FILAS + 40)]
    listo = pantalla.preparar(filas, "EDUARDO MANZANARES", AHORA)
    assert listo["total"] == pantalla.TOPE_FILAS + 40
    assert sum(len(p) for p in listo["paginas"]) == pantalla.TOPE_FILAS
    assert listo["recortado"] is True


def test_una_hoja_normal_no_se_marca_como_recortada():
    assert pantalla.preparar([FILA_TRACKER], "EDUARDO MANZANARES", AHORA)["recortado"] is False


def test_una_hoja_vacia_responde_con_exito_y_una_pagina_vacia():
    """
    Una persona sin pendientes no es un error. Un `success: false` pondría un
    aviso rojo en la pared de quien va al día.
    """
    listo = pantalla.preparar([], "EDUARDO MANZANARES", AHORA)
    assert listo["success"] is True
    assert listo["paginas"] == [[]]
    assert listo["total"] == 0


def test_dos_llamadas_con_los_mismos_datos_dan_lo_mismo():
    """R8: sin esto, la pantalla podría barajar filas entre refrescos."""
    filas = [dict(FILA_TRACKER, FOLIO=f"F{i}") for i in range(20)]
    assert (pantalla.preparar(filas, "EDUARDO MANZANARES", AHORA)
            == pantalla.preparar(filas, "EDUARDO MANZANARES", AHORA))


# ----------------------------------------------------------------------
# La ruta HTTP
# ----------------------------------------------------------------------


def test_la_ruta_devuelve_la_pantalla_de_esa_hoja(monkeypatch):
    from fastapi.testclient import TestClient

    import api.main as main
    from api.main import app

    monkeypatch.setattr(main, "get_data", lambda sheet: {"success": True, "data": [FILA_TRACKER]})
    cuerpo = TestClient(app).get("/api/pantalla", params={"hoja": "EDUARDO MANZANARES"}).json()

    assert cuerpo["success"] is True
    assert cuerpo["columnas"] == list(pantalla.COLUMNAS_TRACKER)
    assert cuerpo["paginas"][0][0]["FOLIO"] == "AV-1192"


def test_la_ruta_no_publica_una_tabla_sensible():
    """
    La pantalla no pide sesión, así que su única puerta es qué tabla acepta.
    `profiles` guarda las credenciales de las 41 cuentas: sin esto, la URL de
    una televisión sería una lectura de la tabla de usuarios.
    """
    from fastapi.testclient import TestClient

    from api.main import app

    for tabla in ("profiles", "PROFILES", "Users"):
        respuesta = TestClient(app).get("/api/pantalla", params={"hoja": tabla})
        assert respuesta.status_code == 403, f"{tabla} no debería publicarse"


def test_la_ruta_exige_decir_que_hoja():
    from fastapi.testclient import TestClient

    from api.main import app

    assert TestClient(app).get("/api/pantalla").status_code == 422
