"""
Las Pantallas de McDonald's: la tabla de un ejecutivo en una televisión colgada.

Solo muestra. No captura, no edita, no borra. Esa decisión la tomó Antonio y
cambia todo lo demás: sin escritura no hay concurrencia, no hay permisos por
fila y no hace falta sesión — una televisión no puede teclear una contraseña.

Lo que se prueba aquí es el preparado de los datos (`api/services/pantalla.py`),
que es donde viven las cuatro decisiones que una pantalla de pared impone y una
de escritorio no:

1. **Las columnas de la hoja, no las veintiuna.** La pantalla se parece a la
   hoja de Google que la oficina ya conoce (decisión del dueño, 2026-10-29):
   mismas columnas visibles y el mismo semáforo. `MONTO` **no** es una de
   ellas: la pantalla la ve todo el piso, incluidas visitas.
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
    # Las columnas son las de la hoja del Tracker, en su orden. La fecha sale
    # como en la hoja (dd/mm/aa) y el avance con su signo de porcentaje.
    assert listo["paginas"] == [[{
        "FOLIO": "AV-1192", "AREA": "HVAC", "FECHA": "", "CLASIFICACION": "",
        "CONCEPTO": "Mantenimiento de chillers", "INVOLUCRADOS": "", "AVANCE": "40%",
        "FECHA_ESTIMADA_FIN": "20/09/26", "DIAS": "", "PRIORIDAD": "ALTA",
        "ESTATUS": "ASIGNADO", "_semaforo": {},
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


# ----------------------------------------------------------------------
# Las columnas reales de la hoja
# ----------------------------------------------------------------------


def test_prioridades_y_status_de_la_hoja_real_llenan_prioridad_y_estatus():
    """
    El Tracker guarda `PRIORIDADES`, `STATUS` y `AVANCE %`, no `PRIORIDAD`,
    `ESTATUS` y `AVANCE`. La pantalla buscaba solo el nombre exacto y las dos
    columnas salían vacías en la televisión de todo el mundo, sin ningún error.
    Los alias ya existen en `tracker_rules.COLUMN_ALIASES` y se reutilizan.
    """
    fila = {"FOLIO": "RC-0131", "PRIORIDADES": "URGENTE", "STATUS": "EN PROCESO",
            "AVANCE %": "35"}
    recortada = pantalla.solo_columnas([fila], pantalla.COLUMNAS_TRACKER)[0]
    assert recortada["PRIORIDAD"] == "URGENTE"
    assert recortada["ESTATUS"] == "EN PROCESO"
    assert recortada["AVANCE"] == "35"


def test_la_columna_alta_del_tracker_se_muestra_como_area():
    """En el Tracker el área se llama `ALTA` (ver `COLUMN_ALIASES["AREA"]`)."""
    recortada = pantalla.solo_columnas([{"ALTA": "DISEÑO"}], pantalla.COLUMNAS_TRACKER)[0]
    assert recortada["AREA"] == "DISEÑO"


def test_ventas_muestra_las_columnas_de_la_hoja_de_cotizaciones():
    """Las mismas que la hoja de Google que la oficina ya lee, en su orden."""
    assert pantalla.COLUMNAS_VENTAS[:10] == (
        "FOLIO", "AREA", "CLIENTE", "CONCEPTO", "CLASIFICACION", "VENDEDOR",
        "F. VISITA", "F. INICIO", "F. ENTREGA", "DIAS")


# ----------------------------------------------------------------------
# El semáforo: el mismo de la hoja
# ----------------------------------------------------------------------


def _unica(fila, hoja="EDUARDO MANZANARES"):
    """La única fila que la televisión pintaría con esa hoja."""
    return pantalla.preparar([fila], hoja, AHORA)["paginas"][0][0]


def test_una_actividad_a_con_cinco_dias_pinta_su_fecha_y_sus_dias_de_rojo():
    fila = _unica({"FOLIO": "A1", "CLASIFICACION": "A", "FECHA": "2026-09-07",
                   "AVANCE": "10"})
    assert fila["DIAS"] == 5
    assert fila["_semaforo"] == {"FECHA": "rojo", "DIAS": "rojo"}


def test_dentro_del_aviso_se_pinta_de_amarillo():
    fila = _unica({"CLASIFICACION": "AA", "FECHA": "2026-08-30", "AVANCE": "10"})
    assert fila["_semaforo"]["DIAS"] == "amarillo"


def test_a_tiempo_se_pinta_de_verde():
    fila = _unica({"CLASIFICACION": "AAA", "FECHA": "2026-09-09", "AVANCE": "10"})
    assert fila["_semaforo"]["DIAS"] == "verde"


def test_los_dias_se_cuentan_hasta_hoy_y_no_se_copian_de_lo_guardado():
    """
    `RELOJ`/`DIAS` en la base es una foto del día en que alguien guardó la
    fila: se queda viejo. La hoja de Google los calcula con `TODAY()`, y la
    pantalla tiene que dar el mismo número que la hoja.
    """
    fila = _unica({"CLASIFICACION": "AA", "FECHA": "2026-09-02", "RELOJ": "3",
                   "AVANCE": "10"})
    assert fila["DIAS"] == 10


def test_una_fecha_escrita_como_en_la_hoja_tambien_cuenta():
    fila = _unica({"CLASIFICACION": "AA", "FECHA": "02/09/2026", "AVANCE": "10"})
    assert fila["DIAS"] == 10


def test_sin_clasificacion_hay_dias_pero_no_se_inventa_un_color():
    fila = _unica({"FECHA": "2026-08-01", "AVANCE": "10"})
    assert fila["DIAS"] == 42
    assert fila["_semaforo"] == {}


def test_sin_fecha_de_inicio_no_hay_dias_ni_color():
    fila = _unica({"CLASIFICACION": "A", "AVANCE": "10"})
    assert fila["DIAS"] == ""
    assert fila["_semaforo"] == {}


def test_lo_terminado_no_se_pinta_de_rojo():
    fila = _unica({"CLASIFICACION": "A", "FECHA": "2026-08-01", "AVANCE": "100"})
    assert fila["_semaforo"] == {}


def test_en_ventas_cada_fecha_lleva_su_color_y_los_dias_cuentan_desde_f_inicio():
    """
    Como en la hoja: F. VISITA y F. INICIO se pintan cada una por su propia
    fecha, y DÍAS cuenta desde F. INICIO (el día en que se trabaja la
    cotización, la misma fecha que usa el calendario).
    """
    fila = _unica({"CLASIFICACION": "AA", "F. VISITA": "2026-08-31",
                   "F. INICIO": "2026-08-20", "AVANCE": "0"},
                  hoja="SEBASTIAN PADILLA (VENTAS)")
    assert fila["DIAS"] == 23
    assert fila["_semaforo"] == {"F. VISITA": "amarillo", "F. INICIO": "rojo",
                                 "DIAS": "rojo"}


def test_el_semaforo_es_el_del_tracker_y_no_una_copia(monkeypatch):
    """Si mañana cambia un límite en `tracker_rules`, la pared cambia con él."""
    from api.services import tracker_rules

    monkeypatch.setitem(tracker_rules.SLA_LIMITS, "A", 30)
    fila = _unica({"CLASIFICACION": "A", "FECHA": "2026-09-07", "AVANCE": "10"})
    assert fila["_semaforo"]["DIAS"] == "verde"


def test_se_cuentan_vencidas_por_vencer_a_tiempo_y_sin_semaforo():
    filas = [
        {"CLASIFICACION": "A", "FECHA": "2026-09-01", "AVANCE": "10"},
        {"CLASIFICACION": "A", "FECHA": "2026-09-02", "AVANCE": "10"},
        {"CLASIFICACION": "AA", "FECHA": "2026-08-30", "AVANCE": "10"},
        {"CLASIFICACION": "AAA", "FECHA": "2026-09-10", "AVANCE": "10"},
        {"FECHA": "2026-09-10", "AVANCE": "10"},
        {"CLASIFICACION": "A", "FECHA": "2026-08-01", "AVANCE": "100"},
    ]
    listo = pantalla.preparar(filas, "EDUARDO MANZANARES", AHORA)
    assert listo["semaforo"] == {"rojo": 2, "amarillo": 1, "verde": 1, "sin": 1}


# ----------------------------------------------------------------------
# Cómo se lee cada celda
# ----------------------------------------------------------------------


def test_las_fechas_salen_como_en_la_hoja():
    fila = _unica({"FECHA_ESTIMADA_FIN": "2026-09-20", "AVANCE": "10"})
    assert fila["FECHA_ESTIMADA_FIN"] == "20/09/26"


def test_una_fecha_que_no_se_entiende_se_deja_tal_cual():
    fila = _unica({"FECHA_ESTIMADA_FIN": "pronto", "AVANCE": "10"})
    assert fila["FECHA_ESTIMADA_FIN"] == "pronto"


def test_el_avance_sale_con_su_porcentaje():
    assert _unica({"AVANCE %": "35"})["AVANCE"] == "35%"
    assert _unica({"AVANCE": ""})["AVANCE"] == ""


# ----------------------------------------------------------------------
# El orden: lo más reciente arriba, como en la hoja
# ----------------------------------------------------------------------


def test_lo_mas_reciente_va_arriba_como_en_la_hoja():
    filas = [{"FOLIO": f, "FECHA": d, "AVANCE": "10"} for f, d in
             (("vieja", "2026-09-01"), ("nueva", "2026-09-10"), ("media", "2026-09-05"))]
    listo = pantalla.preparar(filas, "EDUARDO MANZANARES", AHORA)
    assert [f["FOLIO"] for f in listo["paginas"][0]] == ["nueva", "media", "vieja"]


def test_lo_que_no_tiene_fecha_va_despues_de_lo_fechado():
    filas = [{"FOLIO": "sin", "AVANCE": "10"},
             {"FOLIO": "con", "FECHA": "2026-09-01", "AVANCE": "10"}]
    listo = pantalla.preparar(filas, "EDUARDO MANZANARES", AHORA)
    assert [f["FOLIO"] for f in listo["paginas"][0]] == ["con", "sin"]


def test_lo_terminado_va_al_final_aunque_sea_lo_mas_reciente():
    filas = [{"FOLIO": "hecha", "FECHA": "2026-09-11", "AVANCE": "100"},
             {"FOLIO": "pendiente", "FECHA": "2026-09-01", "AVANCE": "10"}]
    listo = pantalla.preparar(filas, "EDUARDO MANZANARES", AHORA)
    assert [f["FOLIO"] for f in listo["paginas"][0]] == ["pendiente", "hecha"]


# ----------------------------------------------------------------------
# Lo que la televisión pone alrededor de la tabla
# ----------------------------------------------------------------------


def test_la_pantalla_trae_la_foto_y_el_puesto_de_la_persona():
    from api.services import organigrama

    listo = pantalla.preparar([], "SEBASTIAN PADILLA (VENTAS)", AHORA)
    ficha = organigrama.FICHAS["SEBASTIAN PADILLA"]
    assert listo["persona"] == {"puesto": ficha["puesto"], "foto": ficha["foto"]}


def test_una_hoja_sin_ficha_no_inventa_persona():
    assert pantalla.preparar([], "ANTONIA_VENTAS", AHORA)["persona"] == {}


def test_la_pantalla_dice_si_son_cotizaciones_o_actividades():
    assert pantalla.preparar([], "SEBASTIAN PADILLA (VENTAS)", AHORA)["tipo"] == "ventas"
    assert pantalla.preparar([], "SEBASTIAN PADILLA", AHORA)["tipo"] == "tracker"


def test_la_leyenda_usa_los_limites_del_semaforo():
    from api.services import tracker_rules

    assert pantalla.preparar([], "SEBASTIAN PADILLA", AHORA)["limites"] == tracker_rules.SLA_LIMITS


def test_la_ruta_cuenta_los_dias_con_la_hora_de_la_oficina(monkeypatch):
    """
    Vercel corre en UTC. De 18:00 a medianoche en Monterrey ya es el día
    siguiente en UTC, y la pared sumaría un día de más a todo comparada con la
    hoja de Google, que cuenta con la hora de la oficina.
    """
    from datetime import timedelta

    from fastapi.testclient import TestClient

    import api.main as main
    from api.main import app

    visto = {}

    def preparar(filas, hoja, ahora):
        visto["ahora"] = ahora
        return {"success": True}

    monkeypatch.setattr(main, "get_data", lambda sheet: {"success": True, "data": []})
    monkeypatch.setattr(main.pantalla, "preparar", preparar)
    TestClient(app).get("/api/pantalla", params={"hoja": "EDUARDO MANZANARES"})
    assert visto["ahora"].utcoffset() == timedelta(hours=-6)


def test_las_etiquetas_cortas_son_solo_de_las_columnas_que_se_muestran():
    """`CLASIFICACION` no cabe en su columna; `F. FIN` no existe en ventas."""
    assert pantalla.preparar([], "SEBASTIAN PADILLA (VENTAS)", AHORA)["etiquetas"] == {
        "CLASIFICACION": "CLASIF.", "DIAS": "DÍAS"}
