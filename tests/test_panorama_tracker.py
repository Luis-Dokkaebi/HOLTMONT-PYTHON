"""
El panorama del tracker: cuatro indicadores derivados de las reglas existentes.

Rediseño pedido por el cliente (2026-08-07): que la tabla no se vea plana y que
arriba se muestre el panorama de actividades. Es un cambio **visual**: las
columnas, el semáforo y las funciones de guardado no se tocan.

La decisión que importa está en de dónde salen los números:

  * **Retrasada** es, literalmente, la fila que el semáforo pinta de rojo. El
    dueño lo definió como "una actividad A que lleva +3 días está atrasada", y
    eso ya es `getTrafficStyle`: A > 3, AA > 15, AAA > 30. Se reusa la función
    en vez de recalcular los umbrales, para que no existan dos verdades: si un
    umbral cambia, el panel cambia con él.
  * **Terminada** es lo que ya está en TAREAS REALIZADAS (`history`), que lo
    decide el backend con `_esta_archivada`.
  * **Urgente** sale de la columna PRIORIDAD.
  * **Total** es activas + terminadas.

La dona muestra solo tres grupos —terminadas, retrasadas y en tiempo— porque son
los únicos que no se solapan y suman el total. Urgentes se queda fuera a
propósito: una urgente puede estar además retrasada, y la suma dejaría de
cuadrar sin que nadie lo note.
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


def _fuente() -> str:
    with open(INDEX, encoding="utf-8") as fh:
        return fh.read()


def _bloque(patron: str, nombre: str) -> str:
    m = re.search(patron, _fuente(), re.S)
    assert m, f"no se encontró {nombre} en index.html"
    return m.group(0)


def _node(guion: str):
    salida = subprocess.run(["node", "-e", guion], capture_output=True,
                            text=True, timeout=30, check=False)
    assert salida.returncode == 0, f"node falló: {salida.stderr}"
    return json.loads(salida.stdout)


def _entorno() -> str:
    """Las funciones reales de la vista, listas para evaluar con Node."""
    return "\n".join([
        _bloque(r"const getTrafficStyle = \(row\) => \{.*?\n      \};", "getTrafficStyle"),
        _bloque(r"const CLASIFICACIONES = .*?;", "CLASIFICACIONES"),
        _bloque(r"const valorDeColumna = .*?\n      \};", "valorDeColumna"),
        _bloque(r"const clasificacionDe = .*?;", "clasificacionDe"),
        _bloque(r"const esUrgente = .*?;", "esUrgente"),
        _bloque(r"const esRetrasada = .*?;", "esRetrasada"),
        _bloque(r"const desglosar = \(filas\) => \{.*?\n      \};", "desglosar"),
    ])


# ---------------------------------------------------------------------------
# Retrasada = la que el semáforo pinta de rojo
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("clasi", "dias", "retrasada"), [
    # El ejemplo literal del dueño: una A con más de 3 días.
    ("A", 3, False), ("A", 4, True), ("A", 40, True),
    ("AA", 15, False), ("AA", 16, True),
    ("AAA", 30, False), ("AAA", 31, True),
    # Sin clasificación no hay plazo contra el que llegar tarde.
    ("", 999, False), ("B", 999, False),
])
def test_retrasada_es_exactamente_el_rojo_del_semaforo(clasi, dias, retrasada) -> None:
    guion = f"""
        {_entorno()}
        console.log(JSON.stringify(esRetrasada(
            {{ CLASIFICACION: {json.dumps(clasi)}, RELOJ: {dias} }})));
    """
    assert _node(guion) is retrasada


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_el_panel_no_define_umbrales_propios() -> None:
    """
    `esRetrasada` tiene que consultar `getTrafficStyle`, no repetir los números.

    Si alguien copiara los umbrales aquí, cambiar el semáforo dejaría el panel
    contando mal y en silencio.
    """
    m = re.search(r"const esRetrasada = .*?;", _fuente())
    assert m and "getTrafficStyle" in m.group(0), (
        "esRetrasada debe derivarse del semáforo, no de umbrales copiados"
    )


# ---------------------------------------------------------------------------
# Urgente y clasificación
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize(("columna", "valor", "urgente"), [
    ("PRIORIDAD", "URGENTE", True), ("PRIORIDADES", "URGENTE", True),
    ("PRIORIDADES", "urgente", True), ("PRIORIDADES", " URGENTE ", True),
    ("PRIORIDADES", "ALTA", False), ("PRIORIDADES", "", False),
])
def test_urgente_sale_de_la_columna_de_prioridad(columna, valor, urgente) -> None:
    guion = f"""
        {_entorno()}
        console.log(JSON.stringify(esUrgente({{ {json.dumps(columna)}: {json.dumps(valor)} }})));
    """
    assert _node(guion) is urgente


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
@pytest.mark.parametrize("columna", ["CLASIFICACION", "CLASI", "CLAS"])
def test_la_clasificacion_se_lee_con_sus_tres_nombres(columna: str) -> None:
    """El tracker la rotula `Clasi` y la vista de ventas `Clas`."""
    guion = f"""
        {_entorno()}
        console.log(JSON.stringify(clasificacionDe({{ {json.dumps(columna)}: 'AA' }})));
    """
    assert _node(guion) == "AA"


# ---------------------------------------------------------------------------
# El desglose
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_el_desglose_cuenta_por_clasificacion() -> None:
    guion = f"""
        {_entorno()}
        console.log(JSON.stringify(desglosar([
            {{CLASI:'A'}}, {{CLASI:'A'}}, {{CLASI:'AA'}}, {{CLASI:'AAA'}}, {{CLASI:''}}
        ])));
    """
    assert _node(guion) == {"total": 5, "A": 2, "AA": 1, "AAA": 1}


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_las_filas_sin_clasificar_cuentan_en_el_total_pero_no_en_el_desglose() -> None:
    """
    El desglose puede no sumar el total, y es correcto que así sea.

    En los datos reales hay filas sin clasificación. Repartirlas a la fuerza en
    A/AA/AAA sería inventar; esconderlas del total sería mentir sobre cuántas
    actividades hay.
    """
    guion = f"""
        {_entorno()}
        const d = desglosar([{{CLASI:'A'}}, {{CLASI:''}}, {{}}]);
        console.log(JSON.stringify([d.total, d.A + d.AA + d.AAA]));
    """
    assert _node(guion) == [3, 1]


# ---------------------------------------------------------------------------
# La dona: los arcos tienen que caber en el círculo que se dibuja
# ---------------------------------------------------------------------------

def _radio_del_svg() -> int:
    """
    El `r` con el que se pinta el aro, leído del propio SVG.

    Los dos `<circle>` —el riel de fondo y los arcos— tienen que compartir
    radio; si alguien cambiara solo uno, aquí saldrían dos valores y el `pop`
    fallaría antes de que la dona se viera torcida.
    """
    svg = _bloque(r'<svg viewBox="0 0 104 104" class="dona".*?</svg>', "SVG de la dona")
    radios = {int(r) for r in re.findall(r'\br="(\d+)"', svg)}
    assert len(radios) == 1, f"los círculos de la dona no comparten radio: {radios}"
    return radios.pop()


def _radio_del_computo() -> int:
    """El radio con el que `arcosDeLaDona` calcula la circunferencia."""
    bloque = _bloque(r"const arcosDeLaDona = computed\(\(\) => \{.*?\n      \}\);",
                     "arcosDeLaDona")
    m = re.search(r"\bR\s*=\s*(\d+)", bloque)
    assert m, "no se encontró el radio en arcosDeLaDona"
    return int(m.group(1))


def test_el_radio_del_computo_es_el_del_circulo() -> None:
    """
    Un radio en el cálculo y otro en el dibujo hacen que la dona mienta.

    Con `R = 54` en el cómputo y `r = 42` en el SVG, la circunferencia que se
    reparte (339.29) es un 28 % mayor que la que existe (263.89). Con los datos
    reales del tracker —338 actividades: 309 A, 16 AA, 11 AAA— el arco de A
    mide 310.18 y por sí solo da la vuelta entera al aro: se ve un único color
    y las tres clasificaciones dejan de distinguirse.
    """
    assert _radio_del_computo() == _radio_del_svg()


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_los_tres_arcos_caben_y_llenan_la_dona() -> None:
    """
    Los arcos suman la circunferencia exacta, ni uno la desborda.

    Se usan las cifras reales de la captura del cliente para que el caso sea el
    que falló, no uno inventado.
    """
    bloque = _bloque(r"const arcosDeLaDona = computed\(\(\) => \{.*?\n      \}\);",
                     "arcosDeLaDona")
    guion = f"""
        const computed = (fn) => ({{ get value() {{ return fn(); }} }});
        const trackerKpis = {{ value: {{ anillo: [
            {{ etiqueta: 'A',   n: 309, color: 'a' }},
            {{ etiqueta: 'AA',  n: 16,  color: 'aa' }},
            {{ etiqueta: 'AAA', n: 11,  color: 'aaa' }},
        ] }} }};
        {bloque}
        const C = 2 * Math.PI * {_radio_del_svg()};
        const arcos = arcosDeLaDona.value;
        const largos = arcos.map(a => Number(a.dash.split(' ')[0]));
        console.log(JSON.stringify({{
            n: arcos.length,
            cabe: largos.every(l => l <= C + 1e-6),
            suma: Math.round(largos.reduce((a, b) => a + b, 0) * 1000) / 1000,
            circunferencia: Math.round(C * 1000) / 1000,
        }}));
    """
    r = _node(guion)
    assert r["n"] == 3, "las tres clasificaciones tienen que dar un arco cada una"
    assert r["cabe"], "un arco mide más que el aro y tapa a los demás"
    assert r["suma"] == pytest.approx(r["circunferencia"], abs=0.01)


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_cada_clasificacion_conserva_su_color() -> None:
    """
    Tres arcos, tres colores distintos: es lo que hace legible el reparto.
    """
    bloque = _bloque(r"const arcosDeLaDona = computed\(\(\) => \{.*?\n      \}\);",
                     "arcosDeLaDona")
    guion = f"""
        const computed = (fn) => ({{ get value() {{ return fn(); }} }});
        const trackerKpis = {{ value: {{ anillo: [
            {{ etiqueta: 'A',   n: 309, color: 'var(--pan-clasi-a)' }},
            {{ etiqueta: 'AA',  n: 16,  color: 'var(--pan-clasi-aa)' }},
            {{ etiqueta: 'AAA', n: 11,  color: 'var(--pan-clasi-aaa)' }},
        ] }} }};
        {bloque}
        console.log(JSON.stringify(arcosDeLaDona.value.map(a => a.color)));
    """
    assert _node(guion) == [
        "var(--pan-clasi-a)", "var(--pan-clasi-aa)", "var(--pan-clasi-aaa)",
    ]


# ---------------------------------------------------------------------------
# Plegar el panel para que la tabla gane alto
# ---------------------------------------------------------------------------

def test_el_boton_de_plegar_existe_y_alterna_el_estado() -> None:
    fuente = _fuente()
    assert 'class="panorama-plegar"' in fuente
    assert '@click="alternarPanorama"' in fuente
    assert ":class=\"{plegado: panoramaPlegado}\"" in fuente


def test_el_boton_dice_que_hace_y_es_accesible() -> None:
    """
    `aria-expanded` y `aria-controls` porque es un plegable, y `title` porque
    el rótulo es de dos palabras y no alcanza a explicar el efecto.
    """
    boton = _bloque(r'<button type="button" class="panorama-plegar".*?</button>', "botón de plegar")
    assert ':aria-expanded="!panoramaPlegado"' in boton
    assert 'aria-controls="panorama-cuerpo"' in boton
    assert ":title=" in boton


def test_el_cuerpo_se_oculta_con_v_show_y_no_con_v_if() -> None:
    """
    `v-show` y no `v-if`: el SVG de la dona y sus cuatro cifras se recalcularían
    en cada despliegue sin ninguna ganancia, y `aria-controls` tiene que apuntar
    a un elemento que exista en el DOM.
    """
    assert 'v-show="!panoramaPlegado" id="panorama-cuerpo" class="panorama-cuerpo"' in _fuente()


def test_plegado_conserva_el_total_y_lo_retrasado() -> None:
    """
    Si al plegar desapareciera todo, habría que desplegar el panel para saber si
    hace falta desplegarlo. La tira deja las cuatro cifras.
    """
    tira = _bloque(r'<div v-if="panoramaPlegado" class="panorama-tira">.*?</div>\s*</div>', "tira plegada")
    for clave in ("totales", "terminadas", "retrasadas", "urgentes"):
        assert f"trackerKpis.{clave}.total" in tira


def test_el_acento_de_retrasadas_sigue_condicionado_en_la_tira() -> None:
    """Misma regla que el panel abierto: el rojo solo si hay algo retrasado."""
    tira = _bloque(r'<div v-if="panoramaPlegado" class="panorama-tira">.*?</div>\s*</div>', "tira plegada")
    assert "trackerKpis.retrasadas.total > 0" in tira


def test_la_preferencia_se_recuerda_entre_sesiones() -> None:
    assert "holtmont.panorama.plegado" in _fuente()


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_sin_localStorage_el_panel_sale_desplegado() -> None:
    """
    Modo privado o permisos denegados hacen que `localStorage` lance. Eso no
    puede tumbar la vista: se cae al panel abierto, como antes de esta opción.
    """
    bloque = _bloque(r"const CLAVE_PANORAMA = .*?\n      \};\n\n      const panoramaPlegado",
                     "lectura de la preferencia")
    guion = f"""
        const localStorage = {{ getItem() {{ throw new Error('denegado'); }} }};
        {bloque.replace('const panoramaPlegado', '')}
        console.log(JSON.stringify(_panoramaGuardado()));
    """
    assert _node(guion) is False


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_la_preferencia_guardada_se_respeta() -> None:
    bloque = _bloque(r"const CLAVE_PANORAMA = .*?\n      \};\n\n      const panoramaPlegado",
                     "lectura de la preferencia")
    guion = f"""
        const localStorage = {{ getItem: (k) => k === 'holtmont.panorama.plegado' ? '1' : null }};
        {bloque.replace('const panoramaPlegado', '')}
        console.log(JSON.stringify(_panoramaGuardado()));
    """
    assert _node(guion) is True


def test_la_tabla_se_queda_el_alto_que_suelta_el_panel() -> None:
    """
    `.excel-container` es `flex: 1` en la misma columna, así que el alto sale
    solo. Si alguien le pusiera un alto fijo, plegar dejaría de servir para lo
    único que se pidió.
    """
    reglas = re.findall(r"\n    \.excel-container \{([^}]*)\}", _fuente())
    assert reglas, "no se encontró ninguna regla de .excel-container"
    crecen = [r for r in reglas if "flex: 1" in r]
    assert crecen, f"ninguna regla de .excel-container crece; hay {len(reglas)}"
    for regla in reglas:
        assert not re.search(r"\b(height|max-height):\s*\d", regla), (
            f"la tabla tiene alto fijo y plegar el panel no le daría espacio: {regla.strip()}")


# ---------------------------------------------------------------------------
# El rediseño no cambia ninguna regla
# ---------------------------------------------------------------------------

def test_el_semaforo_conserva_sus_umbrales() -> None:
    """El rediseño es visual: los seis números del semáforo no se tocan."""
    m = re.search(r"if\(t==='A'\) \{ limit=(\d+); buffer=(\d+); \}\s*"
                  r"else if\(t==='AA'\) \{ limit=(\d+); buffer=(\d+); \}\s*"
                  r"else if\(t==='AAA'\) \{ limit=(\d+); buffer=(\d+); \}", _fuente())
    assert m and m.groups() == ("3", "1", "15", "3", "30", "5")


def test_las_columnas_ocultas_siguen_ocultas() -> None:
    """El panel no puede haber reintroducido columnas técnicas en la vista."""
    from api.services.sheets import COLUMNAS_TECNICAS

    declaradas = re.search(r"const COLUMNAS_OCULTAS = \[[^\]]*\];", _fuente())
    assert declaradas
    ocultas = {c.upper() for c in re.findall(r"'([^']+)'", declaradas.group(0))}
    assert {c.upper() for c in COLUMNAS_TECNICAS} - ocultas == set()


def test_los_botones_de_la_barra_conservan_su_accion() -> None:
    """
    Cambia la forma, no lo que hacen. Estos cuatro `@click` son el contrato.

    Es la prueba que atrapa el fallo clásico de un rediseño: dejar el botón
    precioso y desconectado.
    """
    fuente = _fuente()
    for accion in ("loadTrackerData", "addNewRow", "saveAllTrackerRows", "toggleTrackerSort"):
        assert f'@click="{accion}"' in fuente, f"el botón de {accion} perdió su acción"


def test_el_panorama_solo_sale_en_la_vista_de_actividades() -> None:
    """En la tabla de cotizaciones no se pinta: sus indicadores son otros."""
    m = re.search(r'<div v-if="trackerSubView === \'TASKS\'" class="panorama', _fuente())
    assert m, "el panorama debe estar condicionado a la vista de actividades"


# ---------------------------------------------------------------------------
# Las puertas de Hallmark (.agents/skills/SKILL.md)
# ---------------------------------------------------------------------------
# El rediseño se hizo con la skill `hallmark`, que impone reglas duras para que
# la interfaz no tenga el aspecto de generada. Las que se pueden comprobar sin
# ojo humano se comprueban aquí.

def _bloque_del_panorama() -> str:
    fuente = _fuente()
    ini = fuente.index("/* Hallmark · pre-emit critique")
    return fuente[ini:fuente.index(".excel-container tbody tr:hover", ini)]


def test_gate_48_ni_un_color_fuera_de_token() -> None:
    """
    Todo color pasa por `var(--pan-*)`. Es la puerta 48 de la skill.

    Su razón no es estética sino de erosión: en cuanto se cuela un hex en un
    `:hover`, a la tercera edición la página tiene ocho colores en vez de tres
    y la contención que hacía funcionar la paleta desaparece.
    """
    sueltos = re.findall(r"#[0-9a-fA-F]{3,6}\b|rgb\(|hsl\(", _bloque_del_panorama())
    assert sueltos == [], f"colores fuera de token: {sueltos}"


def test_la_paleta_esta_en_oklch_y_sin_extremos_puros() -> None:
    """
    OKLCH porque `hsl`/`rgb` mienten sobre el brillo, y nada de negro ni blanco
    puros: todos los tonos llevan la traza de azul del ancla para que los
    grises no choquen con el acento.
    """
    tokens = re.findall(r"--pan-[a-z0-9-]+:\s*([^;]+);", _bloque_del_panorama())
    assert tokens, "no se encontraron los tokens del panorama"
    for valor in tokens:
        assert valor.strip().startswith("oklch("), f"{valor!r} no está en OKLCH"
    claridades = [float(m) for m in re.findall(r"oklch\(\s*([\d.]+)%", _bloque_del_panorama())]
    assert max(claridades) < 100 and min(claridades) > 0, "hay un extremo puro"


def test_el_acento_solo_se_enciende_si_hay_algo_retrasado() -> None:
    """
    La postura del rediseño: el panel calla salvo cuando algo va tarde.

    La clase `tiene` es la que enciende el rojo, y se pone desde el dato. Si
    alguien colorea la tarjeta siempre, el acento deja de significar nada.
    """
    fuente = _fuente()
    assert "{tiene: trackerKpis[k.id].total > 0}" in fuente, (
        "el acento debe depender del dato, no ser fijo"
    )
    bloque = _bloque_del_panorama()
    assert ".cifra--tarde.tiene .cifra-dato" in bloque, (
        "el color de alerta tiene que ir condicionado a la clase `tiene`"
    )


def test_no_hay_encabezados_en_italica() -> None:
    """Un display en itálica es de los indicios más fiables de interfaz generada."""
    assert "font-style: italic" not in _bloque_del_panorama()


def test_la_autocritica_quedo_sellada_en_el_archivo() -> None:
    """
    La skill exige puntuarse en seis ejes y dejar el sello, para que la
    siguiente pasada encuentre la debilidad conocida en vez de repetirla.
    """
    m = re.search(r"Hallmark · pre-emit critique: P(\d) H(\d) E(\d) S(\d) R(\d) V(\d)",
                  _fuente())
    assert m, "falta el sello de autocrítica de Hallmark"
    assert all(int(n) >= 3 for n in m.groups()), (
        f"un eje por debajo de 3 exige otra pasada antes de emitir: {m.groups()}"
    )
