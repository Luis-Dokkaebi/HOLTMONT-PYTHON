"""
Estatus final de una cotización: al 100 % el vendedor dice en qué terminó.

Regla del dueño (2026-08-10):

    Cuando algún vendedor termine una cotización al 100 %, debe seleccionar uno
    de estos estatus: PERDIDA POR TIEMPO, PERDIDA POR PRECIO, CANCELADA POR
    PLANTA, ENVIADA o GANADA. Se abre un selector para saber en qué terminó esa
    cotización, y con eso se hacen mejor los KPI.

Por qué hacía falta. Hoy una cotización puede llegar al 100 % con el estatus en
`PENDIENTE`, vacío o con un comentario, y los KPI solo pueden decir que se
cerró: `compute_quote_metrics` clasifica en ganada/perdida/en proceso y ahí se
acaba la información. El motivo de la pérdida —tiempo, precio o cancelación de
la planta— es justo lo accionable y no se estaba capturando.

Dos de los cinco estatus ni siquiera se reconocían antes de este cambio:

* `PERDIDA POR PRECIO` caía en `normalize_status(...) is None`, o sea "esto no
  es un estatus", porque la única familia con sufijo libre reconocida era la de
  TIEMPO. Se guardaba como texto suelto.
* `CANCELADA POR PLANTA` se colapsaba contra `CANCELADA` a secas, que es lo que
  pasa cuando cancela el cliente. Los dos motivos quedaban en el mismo cubo.

Las dos puntas de la regla se prueban aquí: el motor en Python
(`api/services/tracker_rules.py`) y su gemelo en el frontend (`index.html`), que
es quien abre el selector. Que las dos listas de estatus coincidan es una
prueba, no una convención.

Ejecución:  python -m pytest tests/test_estatus_final_cotizacion.py -v
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

from api.services.tracker_rules import (
    FINAL_QUOTE_STATUSES,
    classify_quote_status,
    compute_quote_metrics,
    is_final_quote_status,
    is_terminal_status,
    needs_final_quote_status,
    normalize_status,
)

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "index.html")


def _fuente() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def _node(guion: str):
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


# ----------------------------------------------------------------------
# Los cinco estatus
# ----------------------------------------------------------------------

def test_son_exactamente_los_cinco_que_pidio_el_dueno() -> None:
    assert FINAL_QUOTE_STATUSES == (
        "PERDIDA POR TIEMPO",
        "PERDIDA POR PRECIO",
        "CANCELADA POR PLANTA",
        "ENVIADA",
        "GANADA",
    )


@pytest.mark.parametrize(("crudo", "esperado"), [
    # Las grafías que ya viven en la hoja, columna por columna.
    ("Perdida x Tiempo", "PERDIDA POR TIEMPO"),
    ("perdida por tiempo", "PERDIDA POR TIEMPO"),
    ("PERDIDO X TIEMPO", "PERDIDA POR TIEMPO"),
    ("Perdida x Precio", "PERDIDA POR PRECIO"),
    ("PERDIDA POR PRECIO", "PERDIDA POR PRECIO"),
    ("perdido x precio", "PERDIDA POR PRECIO"),
    ("Cancelada x Planta", "CANCELADA POR PLANTA"),
    ("CANCELADO POR PLANTA", "CANCELADA POR PLANTA"),
    ("Enviada", "ENVIADA"),
    ("ENVIADO", "ENVIADA"),
    ("Ganada", "GANADA"),
    ("GANADO", "GANADA"),
])
def test_las_grafias_de_la_hoja_llegan_al_canonico(crudo: str, esperado: str) -> None:
    assert normalize_status(crudo) == esperado


def test_perdida_por_precio_ya_no_se_pierde() -> None:
    """
    Antes devolvía `None` —"esto no es un estatus"— y el motivo se perdía.

    Es el defecto concreto que motivó el cambio: la única familia con sufijo
    libre reconocida era TIEMPO, así que `PERDIDA X PRECIO` no casaba con nada.
    """
    assert normalize_status("PERDIDA X PRECIO") == "PERDIDA POR PRECIO"
    assert normalize_status("PERDIDA X PRECIO DEL CLIENTE") == "PERDIDA POR PRECIO"


def test_cancelada_por_planta_no_se_confunde_con_cancelada_por_cliente() -> None:
    """Dos motivos distintos que antes caían en el mismo cubo `CANCELADA`."""
    assert normalize_status("Cancelada x Planta") == "CANCELADA POR PLANTA"
    assert normalize_status("Cancelada x Cliente") == "CANCELADA"
    assert normalize_status("CANCELADO") == "CANCELADA"


@pytest.mark.parametrize("valor", [
    "PERDIDA POR TIEMPO", "PERDIDA POR PRECIO", "CANCELADA POR PLANTA",
    "ENVIADA", "GANADA",
    "Perdida x Tiempo", "Perdida x Precio", "Cancelada x Planta",
    "ENVIADO", "GANADO",
])
def test_los_cinco_y_sus_grafias_cuentan_como_estatus_final(valor: str) -> None:
    assert is_final_quote_status(valor) is True


@pytest.mark.parametrize("valor", [
    "", None, "PENDIENTE", "EN PROCESO", "ASIGNADO", "EN REVISION",
    "CANCELADA",            # cancelada a secas: no dice quién canceló
    "SUSPENDIDA", "HECHO",  # terminal, pero no es un cierre de cotización
    "RAM", "100.0", "es referente al primer correo enviado",
])
def test_lo_que_no_cierra_una_cotizacion(valor) -> None:
    assert is_final_quote_status(valor) is False


# ----------------------------------------------------------------------
# La regla: 100 % sin estatus final -> hay que abrir el selector
# ----------------------------------------------------------------------

@pytest.mark.parametrize(("avance", "estatus", "hace_falta"), [
    (100, "", True),                    # el caso que pidió el dueño
    ("100%", "PENDIENTE", True),
    (1, "EN REVISION", True),           # el 1 nativo de la hoja es 100 %
    ("100", "Cancelada", True),         # cancelada a secas no dice el motivo
    (100, "GANADA", False),
    (100, "Perdida x Precio", False),
    ("100%", "CANCELADA POR PLANTA", False),
    (50, "", False),                    # no ha terminado
    ("1", "", False),                   # el string "1" es 1 %, no 100 %
    ("", "", False),
    (None, None, False),
])
def test_cuando_hace_falta_elegir_el_estatus_final(avance, estatus, hace_falta) -> None:
    assert needs_final_quote_status(avance, estatus) is hace_falta


# ----------------------------------------------------------------------
# Lo que no se puede romper: clasificación y auto-archivado
# ----------------------------------------------------------------------

@pytest.mark.parametrize(("estatus", "cubo"), [
    ("GANADA", "GANADA"),
    ("PERDIDA POR TIEMPO", "PERDIDA"),
    ("PERDIDA POR PRECIO", "PERDIDA"),
    ("CANCELADA POR PLANTA", "PERDIDA"),
    # ENVIADA es "ya salió al cliente", no un cierre: el resultado aún no se
    # conoce y meterla en ganadas inflaría la tasa de cierre.
    ("ENVIADA", "EN_PROCESO"),
])
def test_los_kpi_siguen_clasificando_igual(estatus: str, cubo: str) -> None:
    assert classify_quote_status(estatus) == cubo


@pytest.mark.parametrize("valor", [
    "Perdida x Tiempo", "Perdida x Precio", "Cancelada x Planta",
    "PERDIDA X PRECIO", "CANCELADO POR PLANTA", "ENVIADA", "GANADO",
])
def test_normalizar_no_cambia_si_la_fila_es_terminal(valor: str) -> None:
    """
    El invariante que hace segura la migración de `scripts/normalizar_estatus.py`:
    si el valor crudo contaba como terminal, su canónico tiene que contar igual.
    """
    canonico = normalize_status(valor)
    assert is_terminal_status(valor) == is_terminal_status(canonico or "")


@pytest.mark.parametrize("canonico", FINAL_QUOTE_STATUSES)
def test_los_cinco_son_punto_fijo(canonico: str) -> None:
    assert normalize_status(canonico) == canonico


# ----------------------------------------------------------------------
# El pago: los KPI ya pueden desglosar el motivo
# ----------------------------------------------------------------------

def test_las_metricas_desglosan_el_motivo_de_cierre() -> None:
    filas = [
        {"FOLIO": "AV-1", "FECHA": "05/07/26", "ESTATUS": "GANADA"},
        {"FOLIO": "AV-2", "FECHA": "05/07/26", "ESTATUS": "Perdida x Precio"},
        {"FOLIO": "AV-3", "FECHA": "05/07/26", "ESTATUS": "PERDIDA X PRECIO"},
        {"FOLIO": "AV-4", "FECHA": "05/07/26", "ESTATUS": "Cancelada x Planta"},
        {"FOLIO": "AV-5", "FECHA": "05/07/26", "ESTATUS": "Perdida x Tiempo"},
        {"FOLIO": "AV-6", "FECHA": "05/07/26", "ESTATUS": "ENVIADA"},
        {"FOLIO": "AV-7", "FECHA": "05/07/26", "ESTATUS": "EN PROCESO"},
    ]
    m = compute_quote_metrics(filas, month=7, year=2026)
    motivos = {fila["estatus"]: fila["total"] for fila in m["porMotivoArr"]}

    assert motivos == {
        "PERDIDA POR TIEMPO": 1,
        "PERDIDA POR PRECIO": 2,
        "CANCELADA POR PLANTA": 1,
        "ENVIADA": 1,
        "GANADA": 1,
    }
    # `EN PROCESO` no cerró, así que no cuenta como cierre sin motivo.
    assert m["cerradasSinMotivo"] == 0


def test_una_cerrada_sin_motivo_se_ve_en_las_metricas() -> None:
    """
    Las filas históricas cerradas con `CANCELADA` a secas o `HECHO` siguen
    contando en ganadas/perdidas, pero se reportan aparte: son las que el
    selector nuevo evita que se sigan capturando.
    """
    filas = [
        {"FOLIO": "AV-1", "FECHA": "05/07/26", "ESTATUS": "CANCELADA"},
        {"FOLIO": "AV-2", "FECHA": "05/07/26", "ESTATUS": "GANADA"},
    ]
    m = compute_quote_metrics(filas, month=7, year=2026)

    assert m["cerradasSinMotivo"] == 1
    assert m["winLoss"]["perdida"] == 1          # sigue contando como perdida
    assert m["closeRate"] == 50.0


def test_las_metricas_viejas_no_cambian() -> None:
    """El desglose se suma; no mueve ningún número que ya se estuviera leyendo."""
    filas = [
        {"FOLIO": "AV-1", "CLIENTE": "ACME", "VENDEDOR": "ANGEL SALINAS",
         "FECHA": "05/07/26", "ESTATUS": "GANADA", "CLASIFICACION": "A",
         "FECHA_TERMINO": "06/07/26"},
        {"FOLIO": "AV-2", "CLIENTE": "ACME", "VENDEDOR": "ANGEL SALINAS",
         "FECHA": "05/07/26", "ESTATUS": "PERDIDA X PRECIO", "CLASIFICACION": "AA",
         "FECHA_TERMINO": "25/07/26"},
    ]
    m = compute_quote_metrics(filas, month=7, year=2026)

    assert m["totalCount"] == 2
    assert m["winLoss"] == {"ganada": 1, "perdida": 1, "enProceso": 0, "total": 2}
    assert m["closeRate"] == 50.0
    assert m["slaSummary"]["AA"]["fail"] == 1


# ======================================================================
# El gemelo en el frontend (index.html): el selector
# ======================================================================

def _declaracion_js() -> str:
    """
    Las cinco piezas del frontend, en orden: sin la lista no corre el resto.

    Se extraen del `index.html` real —no se copian aquí— para que la prueba
    falle si alguien cambia la lógica del navegador.
    """
    fuente = _fuente()
    piezas = []
    for patron in (
        r"const ESTATUS_FINAL_COTIZACION = \[.*?\];",
        r"const esAvanceCompleto = .*?\n      \};",
        r"const esEstatusFinalCotizacion = .*?\n      \};",
        r"const esTablaDeCotizaciones = .*?;",
        r"const claveDeColumna = .*?;",
        r"const claveDeAvance = .*?;",
        r"const necesitaEstatusFinal = .*?\n      \};",
    ):
        m = re.search(patron, fuente, re.DOTALL)
        assert m, f"no se encontró {patron!r} en index.html"
        piezas.append(m.group(0))
    return "\n".join(piezas)


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_la_lista_del_navegador_es_la_misma_que_la_del_motor() -> None:
    """
    Si las dos listas divergen, el vendedor elige un estatus que los KPI no
    saben clasificar. Por eso la paridad es una prueba y no una convención.
    """
    guion = f"""
        {_declaracion_js()}
        console.log(JSON.stringify(ESTATUS_FINAL_COTIZACION.map(o => o.label)));
    """
    assert _node(guion) == list(FINAL_QUOTE_STATUSES)


VALORES_DE_AVANCE = [1, 100, "100", "100%", "1", "1.0", 0.5, "", "50%", "abc"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("valor", VALORES_DE_AVANCE)
def test_el_navegador_lee_el_avance_igual_que_el_motor(valor) -> None:
    """
    Misma trampa de siempre (AGENTS.md §4): el número `1` es 100 %, el string
    `"1"` es 1 %. Si el navegador la leyera distinto, el selector se abriría en
    la fila equivocada.
    """
    guion = f"""
        {_declaracion_js()}
        console.log(JSON.stringify(esAvanceCompleto({json.dumps(valor)})));
    """
    from api.services.tracker_rules import is_progress_complete

    assert _node(guion) is is_progress_complete(valor)


VALORES_DE_ESTATUS = [
    "PERDIDA POR TIEMPO", "PERDIDA POR PRECIO", "CANCELADA POR PLANTA",
    "ENVIADA", "GANADA", "Perdida x Tiempo", "Perdida x Precio",
    "Cancelada x Planta", "ENVIADO", "GANADO", "CANCELADA", "PENDIENTE",
    "EN PROCESO", "", "HECHO", "RAM",
]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("valor", VALORES_DE_ESTATUS)
def test_el_navegador_reconoce_los_mismos_cierres_que_el_motor(valor: str) -> None:
    guion = f"""
        {_declaracion_js()}
        console.log(JSON.stringify(esEstatusFinalCotizacion({json.dumps(valor)})));
    """
    assert _node(guion) is is_final_quote_status(valor)


CABECERAS_VENTAS = ["FOLIO", "CLIENTE", "CONCEPTO", "AVANCE", "ESTATUS",
                    "COTIZACION", "F2", "LAYOUT"]
CABECERAS_TRACKER = ["ID", "CONCEPTO", "FECHA", "AVANCE", "ESTATUS", "ARCHIVO"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("fila", "cabeceras", "hace_falta"), [
    ({"AVANCE": "100", "ESTATUS": ""}, CABECERAS_VENTAS, True),
    ({"AVANCE": 1, "ESTATUS": "PENDIENTE"}, CABECERAS_VENTAS, True),
    ({"AVANCE": "100%", "ESTATUS": "GANADA"}, CABECERAS_VENTAS, False),
    ({"AVANCE": "100", "ESTATUS": "Perdida x Tiempo"}, CABECERAS_VENTAS, False),
    ({"AVANCE": "80", "ESTATUS": ""}, CABECERAS_VENTAS, False),
    # Una actividad del tracker general no es una cotización: no se le pregunta.
    ({"AVANCE": "100", "ESTATUS": ""}, CABECERAS_TRACKER, False),
])
def test_solo_se_pregunta_en_una_cotizacion_terminada(fila, cabeceras, hace_falta) -> None:
    guion = f"""
        {_declaracion_js()}
        console.log(JSON.stringify(!!necesitaEstatusFinal({json.dumps(fila)}, {json.dumps(cabeceras)})));
    """
    assert _node(guion) is hace_falta


def test_la_celda_de_avance_abre_el_selector_al_editarse() -> None:
    """Sin el enganche en la celda, el vendedor solo vería el selector al guardar."""
    m = re.search(r'<div v-else-if="String\(h\)\.toUpperCase\(\)\.includes\(\'AVANCE\'\)".*?</div>',
                  _fuente(), re.DOTALL)
    assert m, "no se encontró la celda de AVANCE en index.html"
    assert "onAvanceEditado(row)" in m.group(0), (
        "la celda de AVANCE debe llamar a `onAvanceEditado` al cambiar"
    )


def test_guardar_no_deja_pasar_una_cotizacion_al_100_sin_estatus_final() -> None:
    """
    La celda pregunta, pero el guardado es la puerta: se puede llegar al 100 %
    pegando un valor, con el guardado masivo o desde otra vista.
    """
    fuente = _fuente()
    for funcion in ("const saveRow = async (row, event) => {",
                    "const saveAllTrackerRows = async () => {"):
        assert funcion in fuente, f"`{funcion}` cambió de firma en index.html"

    m = re.search(r"const saveRow = async \(row, event\) => \{.*?\n      \};", fuente, re.DOTALL)
    assert m and "await pedirEstatusFinal(row, staffTracker.value.headers)" in m.group(0), (
        "`saveRow` debe pedir el estatus final antes de guardar"
    )
    m = re.search(r"const saveAllTrackerRows = async \(\) => \{.*?\n      \};", fuente, re.DOTALL)
    assert m and "await pedirEstatusFinal(row, staffTracker.value.headers)" in m.group(0), (
        "`saveAllTrackerRows` debe pedir el estatus final antes de guardar"
    )


def _declaracion_del_selector() -> str:
    """`pedirEstatusFinal` y su candado, sobre las piezas que ya se extraen."""
    fuente = _fuente()
    piezas = [_declaracion_js()]
    for patron in (r"const selectorEstatusAbierto = new WeakMap\(\);",
                   r"const pedirEstatusFinal = async \(row, headers\) => \{.*?\n      \};"):
        m = re.search(patron, fuente, re.DOTALL)
        assert m, f"no se encontró {patron!r} en index.html"
        piezas.append(m.group(0))
    return "\n".join(piezas)


# Swal y el DOM de mentira: el selector se prueba de verdad, sin navegador.
BANCO_DE_PRUEBAS_SWAL = """
    let veces = 0, cerrar = null, elementos = {};
    const Swal = {
        fire: (cfg) => {
            veces++;
            elementos = {};
            for (let i = 0; i < 9; i++) {
                const el = { _click: null };
                el.addEventListener = (ev, fn) => { el._click = fn; };
                elementos['fin-opt-' + i] = el;
            }
            if (cfg.didOpen) cfg.didOpen();
            return { then: (cb) => { cerrar = cb; } };
        },
        close: () => { if (cerrar) cerrar(); }
    };
    const document = { getElementById: (id) => elementos[id] || null };
"""

CABECERAS_JSON = json.dumps(CABECERAS_VENTAS)


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_lo_que_elige_el_vendedor_se_escribe_en_la_fila() -> None:
    guion = f"""
        {BANCO_DE_PRUEBAS_SWAL}
        {_declaracion_del_selector()}
        const row = {{ AVANCE: '100', ESTATUS: '' }};
        const p = pedirEstatusFinal(row, {CABECERAS_JSON});
        elementos['fin-opt-1']._click();       // PERDIDA POR PRECIO
        p.then(ok => console.log(JSON.stringify([ok, row.ESTATUS, veces])));
    """
    puede_guardar, estatus, veces = _node(guion)
    assert puede_guardar is True
    assert estatus == "PERDIDA POR PRECIO"
    assert veces == 1


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_cancelar_el_selector_no_deja_guardar_ni_inventa_estatus() -> None:
    """
    Cerrar el diálogo no puede valer como respuesta: la cotización se queda sin
    guardar antes que quedar cerrada con un motivo que nadie eligió.
    """
    guion = f"""
        {BANCO_DE_PRUEBAS_SWAL}
        {_declaracion_del_selector()}
        const row = {{ AVANCE: '100', ESTATUS: 'PENDIENTE' }};
        const p = pedirEstatusFinal(row, {CABECERAS_JSON});
        Swal.close();
        p.then(ok => console.log(JSON.stringify([ok, row.ESTATUS])));
    """
    assert _node(guion) == [False, "PENDIENTE"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_no_se_abren_dos_selectores_para_la_misma_fila() -> None:
    """
    Al pulsar «guardar» el navegador dispara antes el `change` de la celda de
    AVANCE: las dos rutas piden el estatus por el mismo dato. Sin el candado el
    vendedor vería dos diálogos encadenados.
    """
    guion = f"""
        {BANCO_DE_PRUEBAS_SWAL}
        {_declaracion_del_selector()}
        const row = {{ AVANCE: '100', ESTATUS: '' }};
        const desdeLaCelda = pedirEstatusFinal(row, {CABECERAS_JSON});
        const desdeElGuardado = pedirEstatusFinal(row, {CABECERAS_JSON});
        elementos['fin-opt-4']._click();       // GANADA
        Promise.all([desdeLaCelda, desdeElGuardado])
            .then(r => console.log(JSON.stringify([veces, r[0], r[1], row.ESTATUS])));
    """
    veces, celda, guardado, estatus = _node(guion)
    assert veces == 1, "se abrió el selector dos veces para la misma fila"
    assert celda is True and guardado is True
    assert estatus == "GANADA"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_una_cotizacion_que_ya_dijo_como_termino_no_vuelve_a_preguntar() -> None:
    guion = f"""
        {BANCO_DE_PRUEBAS_SWAL}
        {_declaracion_del_selector()}
        const row = {{ AVANCE: '100', ESTATUS: 'Perdida x Tiempo' }};
        pedirEstatusFinal(row, {CABECERAS_JSON})
            .then(ok => console.log(JSON.stringify([ok, veces, row.ESTATUS])));
    """
    assert _node(guion) == [True, 0, "Perdida x Tiempo"]


def test_el_panel_de_kpi_ensena_el_motivo_de_cierre() -> None:
    """El pago de la regla: el desglose que ahora existe se tiene que ver."""
    fuente = _fuente()
    assert 'v-for="motivo in (quoteMetrics.data.porMotivoArr || [])"' in fuente, (
        "el panel de cotizaciones debe listar `porMotivoArr`"
    )
    assert "quoteMetrics.data.cerradasSinMotivo" in fuente, (
        "el panel debe avisar de las cotizaciones que cerraron sin motivo"
    )
    assert re.search(r"\bcolorDeEstatusFinal,", fuente), (
        "`colorDeEstatusFinal` no está en el objeto que devuelve `setup()`"
    )


def test_el_selector_esta_conectado_a_la_vista() -> None:
    """Vue solo ve lo que `setup()` devuelve: sin esto la celda lanza ReferenceError."""
    fuente = _fuente()
    m = re.search(r"const pedirEstatusFinal = async \(row, headers\) => \{.*?\n      \};",
                  fuente, re.DOTALL)
    assert m, "no se encontró `pedirEstatusFinal` en index.html"
    assert "Swal.fire(" in m.group(0), "el selector se dibuja con Swal, como el de estatus"
    assert re.search(r"\bonAvanceEditado,", fuente), (
        "`onAvanceEditado` no está en el objeto que devuelve `setup()`"
    )
