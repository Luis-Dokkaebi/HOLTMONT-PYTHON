"""
Las columnas de hora se editan con un reloj, igual que las de fecha con un calendario.

Regla del dueño (2026-08-07):

    En el Tracker, en la columna de Hora se usa la hora actual en la que se está
    subiendo la actividad, y en Hr. Est. Fin se debe desplegar un pequeño reloj
    para poner a qué hora se va a terminar, así como en F. Inicio se despliega
    un calendario.

Lo primero ya funcionaba: `addNewRow` pone la hora del reloj del equipo al crear
la fila, y `saveRow` la rellena si quedó vacía. Lo segundo no existía — las dos
columnas de hora caían al `<input>` de texto genérico y había que teclear
`17:30` a mano, con lo que eso invita: `17.30`, `5:30 pm`, `1730`.

El patrón que se replica es el que ya usa la fecha (`index.html:2661`): un
`<input type="date">` **invisible** encima de la celda, con el valor legible
pintado debajo. Al tocar la celda se abre el selector nativo del sistema. Aquí
es lo mismo con `type="time"`, que en el navegador es el relojito.

Por qué el par de conversores. La base guarda `time` y devuelve `"15:54:00"`,
pero `<input type="time">` exige `"HH:MM"` y devuelve `"HH:MM"`. Sin traducir a
la entrada el reloj aparece vacío aunque la celda tenga hora; sin traducir a la
salida se guarda una cadena que `a_hora` sí acepta —maneja los dos formatos—
pero que se vería distinta al resto de la columna.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(RAIZ, "index.html")

# Los encabezados de hora que sirve la API (`TASK_HEADER_MAP`), con las grafías
# que usa la vista y las que llegan con guion bajo desde columnas no curadas.
CABECERAS_DE_HORA = [
    "HORA", "HORA ALTA", "HORA_ALTA",
    "HR. EST. FIN", "HORA ESTIMADA FIN", "HORA_ESTIMADA_FIN",
]

# Columnas que NO deben abrir un reloj, para que la condición no se pase de lista.
NO_SON_HORA = ["FECHA", "FEC. EST. FIN", "CONCEPTO", "RELOJ", "AHORA", "MEJORA"]


def _fuente() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def _node(guion: str):
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


def _declaracion_de_columnas_de_hora() -> str:
    """La lista y la función que la consulta: la segunda no corre sin la primera."""
    m = re.search(r"const COLUMNAS_DE_HORA = \[.*?\];\s*const esColumnaDeHora = .*?;",
                  _fuente(), re.S)
    assert m, "no se encontró `COLUMNAS_DE_HORA` / `esColumnaDeHora` en index.html"
    return m.group(0)


def _condicion_de_hora() -> str:
    """La expresión que decide si una celda se pinta con reloj."""
    m = re.search(r'<div v-else-if="(esColumnaDeHora\(h\))"[^>]*>\s*'
                  r'<div[^>]*>\{\{ formatDisplayTime', _fuente())
    assert m, "no se encontró la celda con reloj en index.html"
    return m.group(1)


def test_la_celda_de_hora_usa_un_input_de_tipo_time() -> None:
    """El relojito es `type="time"`; sin eso no hay selector, hay texto libre."""
    fuente = _fuente()
    assert re.search(r'<input type="time"[^>]*updateTimeFromPicker', fuente), (
        "la celda de hora debe llevar un <input type=\"time\"> conectado al selector"
    )


def test_el_reloj_va_invisible_encima_de_la_celda_como_el_calendario() -> None:
    """
    Mismo patrón que la fecha: valor legible debajo, selector transparente encima.

    Si el input fuera visible, la celda mostraría el widget del navegador en vez
    del valor, y la tabla dejaría de parecerse a la hoja original.
    """
    m = re.search(r'<input type="time"[^>]*>', _fuente())
    assert m, "no se encontró el input de hora"
    assert "opacity:0" in m.group(0), "el selector de hora tiene que ir invisible"
    assert "cursor:pointer" in m.group(0), "la celda tiene que invitar a pulsarla"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("cabecera", CABECERAS_DE_HORA)
def test_todas_las_columnas_de_hora_abren_el_reloj(cabecera: str) -> None:
    guion = f"""
        {_declaracion_de_columnas_de_hora()}
        console.log(JSON.stringify(!!esColumnaDeHora({json.dumps(cabecera)})));
    """
    assert _node(guion) is True, f"{cabecera} debería abrir el reloj"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("cabecera", NO_SON_HORA)
def test_lo_que_no_es_hora_no_abre_el_reloj(cabecera: str) -> None:
    """
    `AHORA` y `MEJORA` contienen «HORA» y no son columnas de hora.

    Por eso la comprobación es por igualdad contra una lista y no un `includes`,
    que es el error que la columna FECHA sí comete y que aquí no se copia.
    """
    guion = f"""
        {_declaracion_de_columnas_de_hora()}
        console.log(JSON.stringify(!!esColumnaDeHora({json.dumps(cabecera)})));
    """
    assert _node(guion) is False, f"{cabecera} no es una columna de hora"


# ---------------------------------------------------------------------------
# Los dos conversores
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("guardado", "en_el_reloj"), [
    ("15:54:00", "15:54"),   # lo que devuelve la base: `time` con segundos
    ("09:15:00", "09:15"),
    ("17:30", "17:30"),      # ya viene corto
    ("", ""),                # celda vacía -> reloj vacío, no medianoche
    (None, ""),
])
def test_la_hora_guardada_se_le_pasa_al_reloj(guardado, en_el_reloj) -> None:
    m = re.search(r"const toTimeValue = .*?\};", _fuente())
    assert m, "no se encontró `toTimeValue` en index.html"
    guion = f"""
        {m.group(0)}
        console.log(JSON.stringify(toTimeValue({json.dumps(guardado)})));
    """
    assert _node(guion) == en_el_reloj


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_lo_que_se_elige_en_el_reloj_se_escribe_en_la_celda() -> None:
    m = re.search(r"const updateTimeFromPicker = \(e, row, h\) => \{.*?\n      \};",
                  _fuente(), re.S)
    assert m, "no se encontró `updateTimeFromPicker` en index.html"
    guion = f"""
        {m.group(0)}
        const row = {{ 'HR. EST. FIN': '' }};
        updateTimeFromPicker({{ target: {{ value: '17:30' }} }}, row, 'HR. EST. FIN');
        const vacia = {{ 'HR. EST. FIN': '17:30' }};
        updateTimeFromPicker({{ target: {{ value: '' }} }}, vacia, 'HR. EST. FIN');
        console.log(JSON.stringify([row['HR. EST. FIN'], vacia['HR. EST. FIN']]));
    """
    elegida, borrada = _node(guion)
    assert elegida == "17:30", "la hora elegida se escribe tal cual"
    assert borrada == "", "vaciar el reloj vacía la celda"


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("guardado", "en_pantalla"), [
    ("15:54:00", "15:54"), ("09:15:00", "09:15"), ("17:30", "17:30"), ("", ""),
])
def test_la_celda_enseña_la_hora_sin_segundos(guardado, en_pantalla) -> None:
    """
    Hoy la columna muestra `15:54:0`, recortado por el ancho. Con el selector se
    pinta el valor legible debajo, y los segundos no aportan nada.
    """
    conversor = re.search(r"const toTimeValue = .*?\};", _fuente())
    pintor = re.search(r"const formatDisplayTime = .*?;", _fuente())
    assert conversor and pintor, "no se encontraron los conversores de hora"
    guion = f"""
        {conversor.group(0)}
        {pintor.group(0)}
        console.log(JSON.stringify(formatDisplayTime({json.dumps(guardado)})));
    """
    assert _node(guion) == en_pantalla


# ---------------------------------------------------------------------------
# Lo que ya funcionaba y no se puede romper
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_una_fila_nueva_sigue_naciendo_con_la_hora_actual() -> None:
    """`addNewRow` pone la hora del equipo en HORA. Es lo que pidió el dueño."""
    m = re.search(r"\} else if \(!isExcludedSheet && hUp === 'HORA'\) \{\n"
                  r"\s*row\[h\] = (.+?);", _fuente())
    assert m, "`addNewRow` ya no rellena HORA con la hora actual"
    guion = f"""
        const now = new Date();
        const hh = String(now.getHours()).padStart(2, '0');
        const mm = String(now.getMinutes()).padStart(2, '0');
        console.log(JSON.stringify({m.group(1)}));
    """
    valor = _node(guion)
    assert re.fullmatch(r"\d{2}:\d{2}", valor), f"se esperaba HH:MM y llegó {valor!r}"


def test_hr_est_fin_no_se_rellena_sola() -> None:
    """
    Solo HORA se autocompleta. La hora estimada de fin la decide la persona.

    Rellenarla con la hora actual sería inventarle un compromiso a quien captura.
    """
    m = re.search(r"if \(hUp === 'HORA' && !row\[h\]\) \{", _fuente())
    assert m, "cambió el autorrelleno de HORA en `saveRow`"
    assert not re.search(r"if \(hUp === 'HR\. EST\. FIN'[^)]*\) \{\s*row\[h\] =", _fuente()), (
        "HR. EST. FIN no debe autocompletarse"
    )


def test_el_backend_acepta_lo_que_manda_el_reloj() -> None:
    """`<input type="time">` emite `HH:MM`; la columna es `time` en Postgres."""
    from datetime import time

    from backend.schemas.task import TaskWrite

    tarea = TaskWrite.desde_hoja({"FOLIO": "JO-1", "HORA": "09:15",
                                  "HR. EST. FIN": "17:30"})
    assert tarea.hora_alta == time(9, 15)
    assert tarea.hora_estimada_fin == time(17, 30)


# ---------------------------------------------------------------------------
# El permiso de campo: el reloj existe pero llegaba `disabled`
# ---------------------------------------------------------------------------
#
# Reporte de ANTONIA_VENTAS (2026-08-20): «en mi tracker no me deja agregar
# Hr. Est. Fin». El reloj estaba puesto, pero el `<input type="time">` lleva
# `:disabled="!isFieldEditable(h, row)"`, y para el rol TONITA esa función
# resuelve por lista blanca de subcadenas en cuanto la fila tiene folio.
#
# La lista traía `FECHA` —que casa con `FECHA_ESTIMADA_FIN`— y `ALTA` —que casa
# de rebote con `HORA_ALTA`—, pero nada que casara con `HORA_ESTIMADA_FIN`, el
# encabezado que rinde la API (`sheets.TASK_HEADER_MAP`). Resultado: la fecha
# estimada de fin se podía cambiar y su hora no, en la misma fila.

# Las grafías con las que la misma columna llega al navegador: la cruda de la
# API, la del rótulo y las de las hojas viejas (`ALIAS_DE_HOJA`).
GRAFIAS_DE_HR_EST_FIN = ["HORA_ESTIMADA_FIN", "HORA ESTIMADA FIN",
                         "HORA ESTIMADA DE FIN", "HR. EST. FIN"]

# Una fila ya dada de alta: con folio, la lista blanca del rol es lo único que
# decide. Antes del folio todo es editable y el defecto no se ve.
FILA_ASIGNADA = {"FOLIO": "AP-0042", "ID": "AP-0042", "ESTATUS": "ASIGNADO"}


def _bloque_de_permisos() -> str:
    m = re.search(r"const isFieldEditable = \(h, row\) => \{.*?\n      \};",
                  _fuente(), re.S)
    assert m, "no se encontró `isFieldEditable` en index.html"
    return "const currentRole = { value: '' };\n" + m.group(0)


def _es_editable(rol: str, encabezado: str, fila: dict) -> bool:
    guion = f"""
        {_bloque_de_permisos()}
        currentRole.value = {json.dumps(rol)};
        console.log(JSON.stringify(
            isFieldEditable({json.dumps(encabezado)}, {json.dumps(fila)})
        ));
    """
    return bool(_node(guion))


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("encabezado", GRAFIAS_DE_HR_EST_FIN)
def test_tonita_pone_la_hora_estimada_de_fin_en_una_actividad_asignada(
        encabezado: str) -> None:
    """El defecto reportado: el reloj salía `disabled` y la celda no respondía."""
    assert _es_editable("TONITA", encabezado, FILA_ASIGNADA), (
        f"{encabezado} quedó de solo lectura en una fila con folio; es justo "
        "cuando se compromete a qué hora se termina la actividad"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_el_encabezado_de_la_hora_es_el_que_rinde_la_api() -> None:
    """
    La prueba de arriba solo vale si `HORA_ESTIMADA_FIN` es de verdad lo que
    llega al navegador. Se comprueba contra el mapa del backend: si mañana la
    API renombra la columna, salta aquí y no en el tracker de Toñita.
    """
    from api.services.sheets import TASK_HEADER_MAP

    assert ("HORA_ESTIMADA_FIN", "hora_estimada_fin") in TASK_HEADER_MAP


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("encabezado", ["CONCEPTO", "FOLIO", "CLASIFICACION"])
def test_abrir_la_hora_no_abre_el_historial(encabezado: str) -> None:
    """
    El contrapeso: un `return true` al principio de la rama TONITA pasaría la
    prueba del defecto y borraría el permiso de campo entero.
    """
    assert not _es_editable("TONITA", encabezado, FILA_ASIGNADA), (
        f"{encabezado} quedó editable en una fila ya dada de alta"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_los_roles_restringidos_no_ganan_la_hora() -> None:
    """El cambio es del tracker de Toñita; los siete restringidos no se tocan."""
    assert not _es_editable("ANGEL_USER", "HORA_ESTIMADA_FIN", FILA_ASIGNADA)


# ---------------------------------------------------------------------------
# El área pulsable
# ---------------------------------------------------------------------------

def test_el_reloj_cubre_la_celda_entera() -> None:
    """
    Segunda mitad del reporte: «agrandar el hitbox para darle click a esa celda».

    El envoltorio se había escrito con `width:100%; height:100%`. Un porcentaje
    de altura dentro de un `<td>` no tiene contra qué resolverse —el hijo no
    aporta altura, porque las dos capas van absolutas— así que el área pulsable
    se quedaba en la altura del contenido, no en la de la fila, que en este
    tracker crece con el `<textarea>` de CONCEPTO.

    La fecha ya lo hace bien (`position:absolute; inset:0`): se ancla al `<td>`,
    que es `position:relative` (`.table-excel td`). Aquí se copia ese anclaje.
    """
    m = re.search(r'<div v-else-if="esColumnaDeHora\(h\)" style="([^"]*)"', _fuente())
    assert m, "no se encontró el envoltorio de la celda de hora"
    estilo = m.group(1).replace(" ", "")
    assert "position:absolute" in estilo and "inset:0" in estilo, (
        "el envoltorio de la hora tiene que anclarse al <td> para que el reloj "
        f"abarque toda la celda; hoy es: {m.group(1)!r}"
    )


def test_el_relojito_se_abre_desde_cualquier_punto_de_la_celda() -> None:
    """
    Por qué el envoltorio a pantalla completa no bastaba.

    Chrome no abre el selector de un `<input type="time">` al pulsar el campo:
    solo lo abre sobre su `::-webkit-calendar-picker-indicator`, el relojito de
    ~15 px pegado al borde derecho. Con el input transparente encima de la
    celda, el resto de la celda se llevaba el clic y no pasaba nada.

    La fecha ya resolvía esto arriba del archivo, estirando ese pseudo-elemento
    hasta cubrir el input entero. La regla se escribió solo para `type="date"`,
    así que la hora se quedó con el hitbox de fábrica. Es el mismo truco, y la
    regla se comparte en vez de duplicarse.
    """
    fuente = _fuente()
    m = re.search(r"([^{}]*)::-webkit-calendar-picker-indicator\s*\{([^}]*)\}", fuente)
    assert m, "no se encontró la regla del indicador del selector"
    selector, cuerpo = m.group(1), m.group(2).replace(" ", "").replace("\n", "")
    assert 'input[type="time"]' in selector, (
        "la regla que estira el indicador tiene que alcanzar también a la hora; "
        f"hoy solo cubre: {selector.strip()!r}"
    )
    for propiedad in ("position:absolute", "width:100%", "height:100%"):
        assert propiedad in cuerpo, (
            f"el indicador de la hora no cubre la celda: falta {propiedad}"
        )
