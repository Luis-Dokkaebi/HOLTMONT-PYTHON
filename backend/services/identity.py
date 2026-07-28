"""
Identidad de fila y escala de avance: el port a Python de
`SupabaseSync.computeDedupeKey()` y `SupabaseSync.normalizeAvance()`
(`CODIGO.js`).

Las dos funciones tienen que dar **exactamente** el mismo resultado que su
gemela en JavaScript. Si divergen, el upsert deja de encontrar la fila que ya
existe e inserta un duplicado, que es el fallo más caro posible en esta capa.
`tests/test_backend_identidad.py` compara ambas implementaciones ejecutando la
de `CODIGO.js` en Node sobre el mismo corpus.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

# Folios con secuencia global: son únicos en todo el sistema y valen como
# clave por sí mismos. Espejo de `SUPABASE_CONFIG.globalFolioPrefixes`.
PREFIJOS_GLOBALES = ("PPC-", "AV-", "TG-", "WO-", "SITE-", "PROJ-")

# IDs tipo timestamp. El sufijo ".0" es real: Google Sheets entrega los folios
# numéricos como número y al serializarlos aparece "1772639658256.0".
RE_TIMESTAMP = re.compile(r"^\d{10,}(?:\.0+)?$")


def compute_dedupe_key(folio: Any, sheet_name: Any) -> Optional[str]:
    """
    Clave de identidad de una fila de `tasks`.

    El orden de evaluación importa:

      1. El folio ya trae "::" -> es sintético ("HOJA::ROW123"), se usa tal cual.
      2. Prefijo de secuencia global (PPC-, AV-, TG-, WO-, SITE-, PROJ-) -> el folio.
      3. Folio tipo timestamp (10+ dígitos) -> el folio.
      4. Cualquier otro -> "<hoja>::<folio>".

    Dos trampas que el caso 4 hace explícitas:

    * **Los folios con iniciales de persona NO son globales.** `JO-0009`,
      `SP-0007` y `GM-0123` caen aquí. `JO-0009` vive en diez trackers
      distintos por difusión lateral ("papa caliente") y cada copia es una fila
      legítima; tratarlos como globales las colapsaría en una sola.
    * **El nombre de hoja va SIN recortar**, aunque el folio sí se recorta. Hay
      hojas reales con espacio inicial (" LILIANA AYLIN MARTINEZ IBARRA") y la
      migración lo conservó dentro de la clave. Normalizarlo genera una clave
      distinta a la almacenada y el upsert inserta un duplicado en vez de
      actualizar.
    """
    if isinstance(folio, bool):
        # En JS un booleano nunca llega aquí; en Python `str(True)` daría
        # "True" y fabricaría una clave. Se descarta explícitamente.
        return None
    if isinstance(folio, float) and folio.is_integer():
        # `str(1772639658256.0)` en Python da "1772639658256.0" y en JS
        # `String(1772639658256)` da "1772639658256". Sin esto, un mismo folio
        # numérico produciría claves distintas en cada lenguaje.
        crudo = str(int(folio))
    elif folio is None:
        crudo = ""
    else:
        crudo = str(folio)

    f = crudo.strip()
    if not f:
        return None
    if "::" in f:
        return f
    arriba = f.upper()
    if any(arriba.startswith(p) for p in PREFIJOS_GLOBALES):
        return f
    if RE_TIMESTAMP.match(f):
        return f
    return ("" if sheet_name is None else str(sheet_name)) + "::" + f


def normalize_avance(value: Any) -> Optional[float]:
    """
    AVANCE a la escala 0-100 con la que se almacena en la base.

    AGENTS.md §4: el **número** nativo `1` viene de una celda con formato
    porcentual y significa 100 %; el **string** `"1"` lo tecleó una persona y
    significa 1 %. Colapsar ambos casos archivaría como terminadas las tareas
    al 1 %, así que la distinción de tipo se respeta en la entrada.

    Corolario que gobierna el resto de la Fase 1: una vez normalizado, el valor
    guardado está en 0-100 y ahí `1` significa 1 % sin ambigüedad. Ver
    `is_progress_complete_pct()` en `api/services/tracker_rules.py`.
    """
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (datetime, date)):
        return None

    if isinstance(value, (int, float)):
        numero = float(value)
        if numero != numero or numero in (float("inf"), float("-inf")):  # NaN / infinito
            return None
        # Celda con formato porcentual: 1 = 100 %, 0.5 = 50 %.
        if 0 < numero <= 1:
            numero *= 100
        return round(numero, 2)

    crudo = str(value).strip()
    if not crudo:
        return None
    try:
        numero = float(crudo.replace("%", "").replace(",", ".").strip())
    except ValueError:
        return None
    # Texto: se toma tal cual, ya viene en escala 0-100.
    return round(numero, 2)


def primera_persona(valor: Any) -> str:
    """
    Primer nombre de una lista de involucrados.

    `INVOLUCRADOS` es una columna de texto con nombres separados por coma y, en
    el código vivo, un alias de `RESPONSABLE` (`CODIGO.js:926`). Guardar el
    compuesto como si fuera una persona ya ensució `people` con filas del tipo
    "RAMIRO RODRIGUEZ, ALFONSO CORREA"; por eso aquí siempre se toma el primero.
    """
    crudo = str(valor or "").strip()
    if not crudo:
        return ""
    return re.split(r"[,\n;]", crudo)[0].strip()
