"""
Paridad de la identidad de fila y de la escala de avance con `CODIGO.js`.

La verificación no compara contra una copia de la lógica escrita a mano: extrae
`computeDedupeKey` y `normalizeAvance` del `CODIGO.js` real y los **ejecuta en
Node**, para que el día que alguien toque el original la prueba se entere.

Si las dos implementaciones divergen, el upsert deja de encontrar la fila que
ya existe e inserta un duplicado. Es el fallo más caro de esta capa.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from api.services.tracker_rules import is_progress_complete, is_progress_complete_pct
from backend.services.identity import compute_dedupe_key, normalize_avance, primera_persona

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODIGO_JS = os.path.join(RAIZ, "CODIGO.js")

# Corpus elegido por las trampas que documenta el plan, no por cobertura de
# líneas: folios con iniciales de persona (que NO son globales), hojas con
# espacio inicial, folios timestamp con y sin sufijo ".0", y capitalización.
CASOS_DEDUPE = [
    ("JO-0009", "JAIME OLIVO"),
    ("JO-0009", " LILIANA AYLIN MARTINEZ IBARRA"),
    ("SP-0007", "SEBASTIAN PADILLA"),
    ("GM-0123", "MIGUEL GALLARDO"),
    ("PPC-1001", "PPCV3"),
    ("AV-0042", "ANTONIA_VENTAS"),
    ("TG-0005", "TERESA GARZA"),
    ("WO-0001", "WORKORDER"),
    ("SITE-1", "SITIOS"),
    ("PROJ-2", "PROYECTOS"),
    ("1772639658256", "ANTONIA_VENTAS"),
    ("1772639658256.0", "ANTONIA_VENTAS"),
    ("1772639658256.00", "X"),
    ("123456789", "HOJA"),
    ("HOJA::ROW123", "OTRA HOJA"),
    ("  JO-0009  ", "JAIME OLIVO"),
    ("", "JAIME OLIVO"),
    (None, "X"),
    ("av-0042", "ANTONIA_VENTAS"),
    ("ppc-9", "X"),
    ("AVX-1", "X"),
    ("A-1", " ESPACIO INICIAL"),
    ("JO-0009", None),
    ("JO-0009", ""),
    ("0009", "JAIME OLIVO"),
]

CASOS_AVANCE = [1, 1.0, 0.5, 0.01, 100, 0, "1", "1.0", "100", "100%", "50", "", None, "abc", 45.678]

_EXTRAER_JS = r"""
const fs = require("fs");
// argv[0] es node y argv[1] este script: los argumentos empiezan en argv[2].
const src = fs.readFileSync(process.argv[2], "utf8");
const cfg = src.match(/const SUPABASE_CONFIG = \{[\s\S]*?\n\};/)[0];
const dedupe = src.match(/  computeDedupeKey: function \(folio, sheetName\) \{[\s\S]*?\n  \},/)[0];
const avance = src.match(/  normalizeAvance: function \(value\) \{[\s\S]*?\n  \},/)[0];
eval(cfg
  + "\nglobalThis.computeDedupeKey = " + dedupe.replace(/^  computeDedupeKey: /, "").replace(/,\s*$/, "") + ";"
  + "\nglobalThis.normalizeAvance = " + avance.replace(/^  normalizeAvance: /, "").replace(/,\s*$/, "") + ";");
const entrada = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
console.log(JSON.stringify({
  dedupe: entrada.dedupe.map(c => computeDedupeKey(c[0], c[1])),
  avance: entrada.avance.map(v => normalizeAvance(v)),
}));
"""

hace_falta_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="Node no está disponible para ejecutar CODIGO.js"
)


@pytest.fixture(scope="module")
def resultados_js(tmp_path_factory):
    directorio = tmp_path_factory.mktemp("paridad")
    script = directorio / "extraer.js"
    script.write_text(_EXTRAER_JS, encoding="utf-8")
    entrada = directorio / "entrada.json"
    entrada.write_text(
        json.dumps({"dedupe": [list(c) for c in CASOS_DEDUPE], "avance": CASOS_AVANCE}),
        encoding="utf-8",
    )
    salida = subprocess.run(
        ["node", str(script), CODIGO_JS, str(entrada)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert salida.returncode == 0, f"No se pudo ejecutar CODIGO.js: {salida.stderr}"
    return json.loads(salida.stdout)


@hace_falta_node
def test_dedupe_key_tiene_paridad_exacta_con_codigo_js(resultados_js):
    esperado = resultados_js["dedupe"]
    obtenido = [compute_dedupe_key(folio, hoja) for folio, hoja in CASOS_DEDUPE]
    divergencias = [
        (caso, py, js)
        for caso, py, js in zip(CASOS_DEDUPE, obtenido, esperado)
        if py != js
    ]
    assert not divergencias, f"Python y CODIGO.js difieren en: {divergencias}"


@hace_falta_node
def test_normalize_avance_tiene_paridad_con_codigo_js(resultados_js):
    esperado = resultados_js["avance"]
    obtenido = [normalize_avance(v) for v in CASOS_AVANCE]
    divergencias = [
        (caso, py, js) for caso, py, js in zip(CASOS_AVANCE, obtenido, esperado) if py != js
    ]
    assert not divergencias, f"Python y CODIGO.js difieren en: {divergencias}"


# --- Las trampas, verificadas explícitamente ---------------------------


def test_los_folios_con_iniciales_de_persona_no_son_globales():
    """`JO-0009` vive en diez trackers y cada copia es una fila legítima."""
    assert compute_dedupe_key("JO-0009", "JAIME OLIVO") == "JAIME OLIVO::JO-0009"
    assert compute_dedupe_key("JO-0009", "TERESA GARZA") == "TERESA GARZA::JO-0009"
    assert compute_dedupe_key("JO-0009", "JAIME OLIVO") != compute_dedupe_key("JO-0009", "TERESA GARZA")


def test_el_nombre_de_hoja_conserva_el_espacio_inicial():
    """Recortarlo genera otra clave y el upsert insertaría un duplicado."""
    con_espacio = compute_dedupe_key("A-1", " LILIANA AYLIN MARTINEZ IBARRA")
    assert con_espacio == " LILIANA AYLIN MARTINEZ IBARRA::A-1"
    assert con_espacio != compute_dedupe_key("A-1", "LILIANA AYLIN MARTINEZ IBARRA")


def test_el_folio_si_se_recorta_aunque_la_hoja_no():
    assert compute_dedupe_key("  JO-0009  ", "JAIME OLIVO") == "JAIME OLIVO::JO-0009"


@pytest.mark.parametrize("folio", ["PPC-1", "AV-2", "TG-3", "WO-4", "SITE-5", "PROJ-6"])
def test_los_prefijos_de_secuencia_global_valen_por_si_mismos(folio):
    assert compute_dedupe_key(folio, "CUALQUIER HOJA") == folio


def test_un_prefijo_global_no_se_confunde_con_uno_que_solo_lo_empieza():
    assert compute_dedupe_key("AVX-1", "HOJA") == "HOJA::AVX-1"


def test_el_timestamp_necesita_diez_digitos():
    assert compute_dedupe_key("1772639658256", "HOJA") == "1772639658256"
    assert compute_dedupe_key("123456789", "HOJA") == "HOJA::123456789"


def test_folio_vacio_no_produce_clave():
    assert compute_dedupe_key("", "HOJA") is None
    assert compute_dedupe_key(None, "HOJA") is None
    assert compute_dedupe_key("   ", "HOJA") is None


# --- La distinción entre el número 1 y el string "1" -------------------


def test_el_numero_uno_es_cien_por_ciento_y_el_string_uno_es_uno_por_ciento():
    """AGENTS.md §4. Colapsarlos archivaría como terminadas las tareas al 1 %."""
    assert normalize_avance(1) == 100
    assert normalize_avance(1.0) == 100
    assert normalize_avance("1") == 1
    assert normalize_avance("1.0") == 1


def test_en_la_base_el_uno_ya_no_significa_cien():
    """
    La regla de la hoja aplicada a un valor ya normalizado archiva al 1 %.

    Es la trampa que hace peligroso preservar tipos sin separar los dominios:
    `is_progress_complete` está escrita para la entrada (donde el número 1
    viene de una celda porcentual) y `is_progress_complete_pct` para la base
    (escala 0-100 ya resuelta).
    """
    assert is_progress_complete(1.0) is True  # dominio HOJA: correcto
    assert is_progress_complete_pct(1.0) is False  # dominio BASE: 1 % no está terminada
    assert is_progress_complete_pct(100.0) is True
    assert is_progress_complete_pct(99.99) is True  # tolerancia
    assert is_progress_complete_pct(45.0) is False


@pytest.mark.parametrize("valor", [None, "", True, False, "abc"])
def test_valores_que_no_son_avance_no_estan_completos(valor):
    assert is_progress_complete_pct(valor) is False


# --- INVOLUCRADOS ------------------------------------------------------


def test_solo_se_toma_la_primera_persona_del_string():
    """Guardar el compuesto ya ensució `people` con filas de dos nombres."""
    assert primera_persona("RAMIRO RODRIGUEZ, ALFONSO CORREA") == "RAMIRO RODRIGUEZ"
    assert primera_persona("JAIME OLIVO") == "JAIME OLIVO"
    assert primera_persona("A\nB") == "A"
    assert primera_persona("") == ""
