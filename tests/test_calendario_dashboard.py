"""
El calendario del dashboard: qué ve cada quien y en qué día.

Tres reglas que pidió el dueño el 2026-08-15 y que antes no se cumplían:

1. **Aparece lo que trabajas, no lo que repartes.** Si Toñita le asigna una
   actividad a Sebastián, la fila queda en las dos tablas —la de ella, que la
   repartió, y la de él, que la trabaja— y solo debe salir en el calendario de
   Sebastián. La regla es RESPONSABLE o VENDEDOR.
2. **Los dos orígenes, distinguibles.** Quien tiene tracker y cotizaciones ve
   las dos cosas en su semana, cada fila etiquetada con su `ORIGEN`.
3. **Cada origen se coloca por su fecha.** El tracker por FECHA; las
   cotizaciones por F. INICIO, no por F. VISITA ni F. ENTREGA.

Y el defecto que dejaba el calendario en blanco: la base guarda `date` y la
vista recibía ISO (`2026-08-10`), mientras el calendario comparaba contra
`dd/MM/yy`. Ninguna casilla emparejaba nunca. `FECHA_CALENDARIO` normaliza el
día en ISO y `taskDayKey` (index.html) compara ese único formato.
"""

from __future__ import annotations

import json
import os
import re
import subprocess

import pytest

from api.services import asignacion, tracker_store
from api.services import tracker_rules as rules

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "index.html")


# ----------------------------------------------------------------------
# Andamio: las tres hojas que alimentan el calendario
# ----------------------------------------------------------------------

def _hojas(monkeypatch, contenido):
    """`read_rows` servido desde un diccionario {hoja: [filas activas]}."""
    pedidas = []

    def leer(hoja):
        pedidas.append(hoja)
        return (list(contenido.get(hoja, [])), [], [])

    monkeypatch.setattr(tracker_store, "read_rows", leer)
    return pedidas


def _conceptos(respuesta):
    return {fila.get("CONCEPTO") for fila in respuesta["data"]}


# ----------------------------------------------------------------------
# 1. Solo el responsable
# ----------------------------------------------------------------------

def test_quien_asigna_no_ve_la_actividad_en_su_calendario(monkeypatch):
    """La fila que Toñita repartió es de Sebastián, aunque viva en la hoja de ella."""
    _hojas(monkeypatch, {
        "ANTONIA PINEDA LOPEZ": [
            {"FOLIO": "AP-1", "CONCEPTO": "Levantamiento nave", "FECHA": "2026-08-10",
             "RESPONSABLE": "SEBASTIAN PADILLA"},
            {"FOLIO": "AP-2", "CONCEPTO": "Junta de obra", "FECHA": "2026-08-10",
             "RESPONSABLE": "ANTONIA PINEDA LOPEZ"},
        ],
    })

    datos = tracker_store.fetch_combined_calendar("ANTONIA PINEDA LOPEZ")
    assert _conceptos(datos) == {"Junta de obra"}


def test_el_responsable_si_la_ve_en_su_calendario(monkeypatch):
    """La copia que aterrizó en el tracker de quien la trabaja sí sale."""
    _hojas(monkeypatch, {
        "SEBASTIAN PADILLA": [
            {"FOLIO": "AP-1", "CONCEPTO": "Levantamiento nave", "FECHA": "2026-08-10",
             "RESPONSABLE": "SEBASTIAN PADILLA"},
        ],
    })

    datos = tracker_store.fetch_combined_calendar("SEBASTIAN PADILLA")
    assert _conceptos(datos) == {"Levantamiento nave"}


def test_el_vendedor_ve_su_cotizacion_y_no_la_de_otro(monkeypatch):
    """En ventas la columna que manda es VENDEDOR."""
    _hojas(monkeypatch, {
        "SEBASTIAN PADILLA (VENTAS)": [
            {"FOLIO": "AV-10", "CONCEPTO": "Cotizar oficinas", "F. INICIO": "2026-08-11",
             "VENDEDOR": "SEBASTIAN PADILLA"},
            {"FOLIO": "AV-11", "CONCEPTO": "Cotizar bodega", "F. INICIO": "2026-08-11",
             "VENDEDOR": "TERESA GARZA"},
        ],
    })

    datos = tracker_store.fetch_combined_calendar("SEBASTIAN PADILLA")
    assert _conceptos(datos) == {"Cotizar oficinas"}


def test_una_fila_sin_responsable_es_de_la_hoja_en_la_que_esta(monkeypatch):
    """Capturar algo sin llenar RESPONSABLE no debe hacerlo desaparecer."""
    _hojas(monkeypatch, {
        "ANTONIO SALAZAR": [
            {"FOLIO": "AS-1", "CONCEPTO": "Revisar planos", "FECHA": "2026-08-12",
             "RESPONSABLE": ""},
        ],
    })

    datos = tracker_store.fetch_combined_calendar("ANTONIO SALAZAR")
    assert _conceptos(datos) == {"Revisar planos"}


def test_el_nombre_del_directorio_cuenta_como_el_de_la_hoja(monkeypatch):
    """
    El selector de involucrados ofrece el `label` ("Erick Sebastian Padilla
    Carrillo"); la hoja se llama "SEBASTIAN PADILLA". Comparar solo contra el
    segundo dejaba fuera justo lo que se asigna desde el selector.
    """
    _hojas(monkeypatch, {
        "SEBASTIAN PADILLA": [
            {"FOLIO": "AS-2", "CONCEPTO": "Visita a planta", "FECHA": "2026-08-13",
             "INVOLUCRADOS": "ERICK SEBASTIAN PADILLA CARRILLO"},
        ],
    })

    datos = tracker_store.fetch_combined_calendar("SEBASTIAN PADILLA")
    assert _conceptos(datos) == {"Visita a planta"}


def test_una_actividad_de_varios_responsables_sale_para_cada_uno(monkeypatch):
    _hojas(monkeypatch, {
        "TERESA GARZA": [
            {"FOLIO": "TG-1", "CONCEPTO": "Precios unitarios", "FECHA": "2026-08-14",
             "RESPONSABLE": "SEBASTIAN PADILLA, TERESA GARZA"},
        ],
    })

    datos = tracker_store.fetch_combined_calendar("TERESA GARZA")
    assert _conceptos(datos) == {"Precios unitarios"}


# ----------------------------------------------------------------------
# 2. Los dos orígenes en la misma semana
# ----------------------------------------------------------------------

def test_quien_tiene_tracker_y_cotizaciones_ve_los_dos_etiquetados(monkeypatch):
    _hojas(monkeypatch, {
        "TERESA GARZA": [
            {"FOLIO": "TG-1", "CONCEPTO": "Actividad", "FECHA": "2026-08-10",
             "RESPONSABLE": "TERESA GARZA"},
        ],
        "TERESA GARZA (VENTAS)": [
            {"FOLIO": "AV-9", "CONCEPTO": "Cotización", "F. INICIO": "2026-08-10",
             "VENDEDOR": "TERESA GARZA"},
        ],
    })

    datos = tracker_store.fetch_combined_calendar("TERESA GARZA")
    origenes = {fila["CONCEPTO"]: fila["ORIGEN"] for fila in datos["data"]}
    assert origenes == {"Actividad": "TRACKER", "Cotización": "COTIZACIONES"}


def test_quien_no_vende_no_tiene_hoja_de_cotizaciones(monkeypatch):
    """Sin tabla `(VENTAS)` no se inventa una: se lee solo el tracker."""
    pedidas = _hojas(monkeypatch, {"ANTONIO SALAZAR": []})
    tracker_store.fetch_combined_calendar("ANTONIO SALAZAR")

    assert "ANTONIO SALAZAR (VENTAS)" not in pedidas
    assert "ANTONIO SALAZAR" in pedidas


def test_tonita_lee_su_tracker_y_la_tabla_maestra_de_ventas(monkeypatch):
    """Sus cotizaciones viven en `ANTONIA_VENTAS`; su trabajo, en su tracker."""
    pedidas = _hojas(monkeypatch, {
        "ANTONIA PINEDA LOPEZ": [
            {"FOLIO": "AP-3", "CONCEPTO": "Presupuesto", "FECHA": "2026-08-10",
             "RESPONSABLE": "ANTONIA PINEDA LOPEZ"},
        ],
        "ANTONIA_VENTAS": [
            {"FOLIO": "AV-1", "CONCEPTO": "Cotizar nave", "F. INICIO": "2026-08-10",
             "VENDEDOR": "ANTONIA_VENTAS"},
            {"FOLIO": "AV-2", "CONCEPTO": "Cotizar patio", "F. INICIO": "2026-08-10",
             "VENDEDOR": "SEBASTIAN PADILLA"},
        ],
    })

    datos = tracker_store.fetch_combined_calendar("ANTONIA_VENTAS")

    assert "ANTONIA PINEDA LOPEZ" in pedidas and "ANTONIA_VENTAS" in pedidas
    # La que repartió a Sebastián es de él, no de ella.
    assert _conceptos(datos) == {"Presupuesto", "Cotizar nave"}


def test_los_eventos_personales_siguen_saliendo_marcados(monkeypatch):
    _hojas(monkeypatch, {
        "ANTONIO SALAZAR": [],
        "AGENDA_PERSONAL": [
            {"ID": "P-1", "TITULO": "Gimnasio", "FECHA": "2026-08-15",
             "USUARIO": "ANTONIO SALAZAR"},
            {"ID": "P-2", "TITULO": "Dentista", "FECHA": "2026-08-15",
             "USUARIO": "TERESA GARZA"},
        ],
    })

    fila = tracker_store.fetch_combined_calendar("ANTONIO SALAZAR")["data"]
    assert len(fila) == 1
    assert fila[0]["CONCEPTO"] == "Gimnasio"
    assert fila[0]["CLIENTE"] == "PERSONAL"
    assert fila[0]["ORIGEN"] == "PERSONAL"
    assert fila[0]["FECHA_CALENDARIO"] == "2026-08-15"


def test_un_folio_compartido_entre_origenes_no_se_come_una_fila(monkeypatch):
    """La clave de deduplicación lleva el origen: son dos filas del calendario."""
    _hojas(monkeypatch, {
        "TERESA GARZA": [
            {"FOLIO": "AV-9", "CONCEPTO": "Seguimiento", "FECHA": "2026-08-10",
             "RESPONSABLE": "TERESA GARZA"},
        ],
        "TERESA GARZA (VENTAS)": [
            {"FOLIO": "AV-9", "CONCEPTO": "Cotización", "F. INICIO": "2026-08-10",
             "VENDEDOR": "TERESA GARZA"},
        ],
    })

    datos = tracker_store.fetch_combined_calendar("TERESA GARZA")
    assert len(datos["data"]) == 2


def test_sin_hoja_no_se_adivina_nada(monkeypatch):
    _hojas(monkeypatch, {})
    assert tracker_store.fetch_combined_calendar("")["success"] is False


def test_sin_persona_no_hay_tablas_que_leer():
    assert tracker_store.hojas_del_calendario("") == {"tracker": "", "cotizaciones": ""}


def test_una_fila_sin_folio_se_identifica_por_concepto_y_fecha(monkeypatch):
    """Es la misma cadena de identidad que usa el Gatekeeper al guardar."""
    _hojas(monkeypatch, {
        "ANTONIO SALAZAR": [
            {"CONCEPTO": "Sin folio", "FECHA": "2026-08-10", "RESPONSABLE": "ANTONIO SALAZAR"},
            {"CONCEPTO": "Sin folio", "FECHA": "2026-08-10", "RESPONSABLE": "ANTONIO SALAZAR"},
            {"CONCEPTO": "", "FECHA": "2026-08-10", "RESPONSABLE": "ANTONIO SALAZAR"},
        ],
    })

    datos = tracker_store.fetch_combined_calendar("ANTONIO SALAZAR")["data"]
    # Las dos primeras son la misma fila; la tercera no tiene con qué
    # identificarse y se descarta, como hacía el original.
    assert len(datos) == 1
    assert datos[0]["CONCEPTO"] == "Sin folio"


# ----------------------------------------------------------------------
# 3. Cada origen, por su fecha
# ----------------------------------------------------------------------

def test_el_tracker_se_coloca_por_fecha(monkeypatch):
    _hojas(monkeypatch, {
        "ANTONIO SALAZAR": [
            {"FOLIO": "AS-3", "CONCEPTO": "X", "FECHA": "2026-08-10",
             "FECHA_RESPUESTA": "2026-08-20", "RESPONSABLE": "ANTONIO SALAZAR"},
        ],
    })

    fila = tracker_store.fetch_combined_calendar("ANTONIO SALAZAR")["data"][0]
    assert fila["FECHA_CALENDARIO"] == "2026-08-10"


def test_la_cotizacion_se_coloca_por_f_inicio_y_no_por_la_visita(monkeypatch):
    _hojas(monkeypatch, {
        "TERESA GARZA (VENTAS)": [
            {"FOLIO": "AV-9", "CONCEPTO": "Cotizar", "F. VISITA": "2026-08-03",
             "F. INICIO": "2026-08-10", "F. ENTREGA": "2026-08-25",
             "VENDEDOR": "TERESA GARZA"},
        ],
        "TERESA GARZA": [],
    })

    fila = tracker_store.fetch_combined_calendar("TERESA GARZA")["data"][0]
    assert fila["FECHA_CALENDARIO"] == "2026-08-10"


@pytest.mark.parametrize("valor, esperado", [
    ("2026-08-10", "2026-08-10"),
    ("10/08/26", "2026-08-10"),
    ("10/08/2026", "2026-08-10"),
    ("", ""),
    ("SIN FECHA", ""),
])
def test_la_fecha_del_calendario_sale_siempre_en_iso(valor, esperado):
    fila = {"FECHA": valor}
    assert rules.calendar_date(fila, rules.CALENDAR_ORIGIN_TRACKER) == esperado


def test_un_origen_desconocido_no_coloca_la_fila_en_ningun_dia():
    assert rules.calendar_date({"FECHA": "2026-08-10"}, "OTRO") == ""


# ----------------------------------------------------------------------
# La regla pura, aislada
# ----------------------------------------------------------------------

def test_es_responsable_compara_por_nombre_normalizado():
    fila = {"RESPONSABLE": "sebastian  padilla"}
    assert asignacion.es_responsable(fila, ["SEBASTIAN PADILLA"]) is True
    assert asignacion.es_responsable(fila, ["TERESA GARZA"]) is False


def test_es_responsable_sin_persona_no_deja_pasar_nada():
    """Sin nombre con quien comparar, la respuesta segura es que no es suya."""
    assert asignacion.es_responsable({"RESPONSABLE": "X"}, []) is False


def test_los_nombres_de_tonita_incluyen_su_tracker_personal():
    nombres = asignacion.nombres_de_persona("ANTONIA_VENTAS")
    assert "ANTONIA VENTAS" in nombres
    assert "ANTONIA PINEDA LOPEZ" in nombres
    # Su tracker personal no puede salir dos veces aunque el organigrama ya lo
    # liste entre sus nombres: la lista alimenta una comparación, no un conteo.
    assert nombres.count("ANTONIA PINEDA LOPEZ") == 1


def test_un_nombre_vacio_no_tiene_nombres_con_los_que_comparar():
    assert asignacion.nombres_de_persona("   ") == []


# ----------------------------------------------------------------------
# La vista: emparejar el día y distinguir el origen
# ----------------------------------------------------------------------

def _fuente_index() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def _bloque(patron: str, nombre: str) -> str:
    m = re.search(patron, _fuente_index(), re.S)
    assert m, f"no se encontró {nombre} en index.html"
    return m.group(0)


def _node(guion: str):
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


def _entorno_calendario() -> str:
    """Las funciones reales de la vista, listas para evaluar con Node."""
    return "\n".join([
        _bloque(r"const taskDayKey = \(task\) => \{.*?\n      \};", "taskDayKey"),
        _bloque(r"const getTaskOrigin = \(task\) => \{.*?\n      \};", "getTaskOrigin"),
        _bloque(r"const ORIGIN_COLORS = .*?\n", "ORIGIN_COLORS"),
        _bloque(r"const getOriginColor = \(task\) => .*?\n", "getOriginColor"),
    ])


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="node no está instalado")
def test_la_vista_empareja_el_dia_venga_la_fecha_como_venga():
    guion = _entorno_calendario() + """
    const casos = [
      taskDayKey({ ORIGEN: 'TRACKER', FECHA_CALENDARIO: '2026-08-10' }),
      taskDayKey({ ORIGEN: 'TRACKER', FECHA: '10/08/26' }),
      taskDayKey({ ORIGEN: 'COTIZACIONES', 'F. INICIO': '2026-08-11' }),
      taskDayKey({ ORIGEN: 'COTIZACIONES', FECHA: '2026-08-30' }),
      taskDayKey({}),
    ];
    console.log(JSON.stringify(casos));
    """
    assert _node(guion) == ["2026-08-10", "2026-08-10", "2026-08-11", "", ""]


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="node no está instalado")
def test_la_vista_etiqueta_cada_origen_con_su_color():
    guion = _entorno_calendario() + """
    console.log(JSON.stringify({
      cotizacion: getTaskOrigin({ ORIGEN: 'COTIZACIONES' }),
      tracker: getTaskOrigin({ ORIGEN: 'TRACKER' }),
      personalViejo: getTaskOrigin({ CLIENTE: 'PERSONAL' }),
      ninguno: getTaskOrigin({}),
      colorDistinto: getOriginColor({ ORIGEN: 'COTIZACIONES' }) !== getOriginColor({ ORIGEN: 'TRACKER' })
    }));
    """
    assert _node(guion) == {
        "cotizacion": "COTIZACIÓN",
        "tracker": "TRACKER",
        "personalViejo": "PERSONAL",
        "ninguno": "",
        "colorDistinto": True,
    }


def test_el_calendario_pide_el_tracker_y_no_la_hoja_de_ventas():
    """
    `calendarTarget` decide de quién es el calendario. Mandar la hoja `(VENTAS)`
    —lo que hacía antes— dejaba al vendedor sin sus actividades del tracker,
    porque el backend une los dos orígenes a partir del nombre de la persona.
    """
    fuente = _bloque(r"const calendarTarget = \(\) => \{.*?\n      \};", "calendarTarget")
    assert fuente.index("if (trackerMod) return trackerMod.target") \
        < fuente.index("if (salesMod) return salesMod.target"), \
        "el módulo de tracker debe resolverse antes que el de ventas"


def test_las_casillas_del_calendario_se_piden_por_dia_iso():
    """La plantilla compara contra `day.iso`: es el formato que manda el backend."""
    fuente = _fuente_index()
    assert "getTasksForDay(day.iso)" in fuente
    assert "getTasksForDay(day.dateStr)" not in fuente
