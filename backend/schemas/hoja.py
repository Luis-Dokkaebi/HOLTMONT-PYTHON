"""
Traducción entre la forma de hoja y la forma relacional.

El frontend monolítico (`index.html`) y `tracker_rules.py` hablan en
encabezados de hoja (`FOLIO`, `CONCEPTO`, `F. VISITA`, `PRIO. COT.`) porque el
sistema nació sobre Google Sheets y esa es la decisión C del plan: `index.html`
no se toca. La base habla en columnas (`folio`, `concepto`, `f_visita`,
`prioridad_cot`).

Este módulo es el único punto donde se cruza esa frontera al **escribir**. Al
leer, el cruce inverso ya lo hacen `QUOTE_HEADER_MAP` / `TASK_HEADER_MAP` de
`api/services/sheets.py`.

Tres reglas que vienen de AGENTS.md §4 y de datos reales:

* La comparación es insensible a mayúsculas, acentos de puntuación y espacios
  repetidos: el frontend manda `folio` y la hoja tiene `FOLIO`, y hay
  encabezados con punto y espacio (`PRIO. COT.`, `F. VISITA`).
* Las claves que empiezan por `_` son metadatos del frontend (`_tempId`,
  `_rowIndex`, `_isNew`) y nunca son columnas.
* Un encabezado que ya coincide con el nombre real de la columna también vale:
  la lectura expone las columnas no curadas con su nombre crudo en mayúsculas
  (`build_header_map`), así que un round-trip las devuelve así.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, time
from typing import Any, Dict, Iterable, List, Mapping, Optional

_NO_ALFANUMERICO = re.compile(r"[^A-Z0-9]+")


def clave_encabezado(valor: Any) -> str:
    """
    `" F. Visita "` -> `"FVISITA"`; `"COTIZACIÓN"` -> `"COTIZACION"`.

    Se descomponen los acentos antes de tirar lo no alfanumérico, si no
    `"DÍAS"` daría `"DAS"` y no casaría con `"DIAS"`. En estas hojas conviven
    las dos grafías de la misma columna.
    """
    plano = unicodedata.normalize("NFKD", str(valor or "").upper())
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return _NO_ALFANUMERICO.sub("", plano)


def indice_de_alias(alias_de_hoja: Mapping[str, Iterable[str]]) -> Dict[str, str]:
    """
    `{columna: [encabezados]}` -> `{clave_encabezado: columna}`.

    El nombre real de la columna se registra también como alias de sí misma, y
    los alias declarados tienen prioridad sobre él: si dos columnas compitieran
    por la misma clave, gana la que lo declaró explícitamente.
    """
    indice: Dict[str, str] = {}
    for columna in alias_de_hoja:
        indice.setdefault(clave_encabezado(columna), columna)
    for columna, alias in alias_de_hoja.items():
        for encabezado in alias:
            indice[clave_encabezado(encabezado)] = columna
    return indice


def columnas_desde_hoja(fila: Mapping[str, Any], indice: Mapping[str, str]) -> Dict[str, Any]:
    """
    Fila con forma de hoja -> `{columna: valor crudo}`.

    Solo salen las columnas que la fila trajo de verdad. Es lo que permite que
    el upsert use `merge-duplicates` sin borrar en la base lo que el cliente no
    mandó: una columna ausente aquí es una columna que no se toca allá.
    """
    columnas: Dict[str, Any] = {}
    for clave, valor in (fila or {}).items():
        nombre = str(clave)
        if nombre.startswith("_"):
            continue
        columna = indice.get(clave_encabezado(nombre))
        if not columna or columna in columnas:
            continue
        columnas[columna] = valor
    return columnas


# ----------------------------------------------------------------------
# Coerciones de tipo
# ----------------------------------------------------------------------
# La hoja entrega todo como texto y con formatos humanos ("27/07/26",
# "1,250.50", "SI"). La base tiene `date`, `time`, `numeric`, `integer` y
# `boolean`. Estas funciones son las validaciones `mode="before"` de los
# modelos de escritura, así que la conversión ocurre una sola vez y da igual si
# la petición entró por `/api/v2` (JSON tipado) o por el camino legacy
# (encabezados de hoja).


VACIOS = {"", "-", "--", "---", "N/A", "NA", "NULL", "NONE", "NINGUNO", "SIN DATO"}


def _crudo(valor: Any) -> Optional[str]:
    """Texto normalizado, o `None` si el valor es uno de los "vacíos" de la hoja."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return None if texto.upper() in VACIOS else texto


def a_texto(valor: Any) -> Optional[str]:
    if valor is None or isinstance(valor, str):
        return None if valor == "" else valor
    if isinstance(valor, bool):
        return "SI" if valor else "NO"
    if isinstance(valor, float) and valor.is_integer():
        # `numeric` de Postgres y los números de la hoja llegan como float:
        # "45.0" en una columna de texto se ve mal donde antes había "45".
        return str(int(valor))
    return str(valor)


def a_fecha(valor: Any) -> Optional[date]:
    """
    Acepta lo que manda la hoja (`dd/mm/yy`, `dd/mm/yyyy`) y lo que manda un
    cliente moderno (ISO, `datetime`). Reutiliza `parse_sheet_date`, que es la
    función con paridad probada contra `CODIGO.js`.
    """
    if valor is None or isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    if _crudo(valor) is None:
        return None
    from api.services.tracker_rules import parse_sheet_date

    parseada = parse_sheet_date(valor)
    return parseada.date() if parseada else None


def a_hora(valor: Any) -> Optional[time]:
    """
    `"17:33"`, `"17:33:00"` y `datetime.time` valen. Un número suelto no: la
    columna `reloj` de los datos reales mezcla horas ("17:00:00") con números
    ("70.0"), y convertir 70 en una hora sería inventar.
    """
    if valor is None or isinstance(valor, time):
        return valor
    if isinstance(valor, datetime):
        return valor.time()
    crudo = _crudo(valor)
    if crudo is None:
        return None
    for formato in ("%H:%M:%S", "%H:%M", "%H:%M:%S.%f"):
        try:
            return datetime.strptime(crudo, formato).time()
        except ValueError:
            continue
    return None


def a_numero(valor: Any) -> Optional[float]:
    """`"1,250.50"` y `"$ 1250.5"` -> 1250.5. Lo que no es un número -> `None`."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    crudo = _crudo(valor)
    if crudo is None:
        return None
    limpio = re.sub(r"[^\d,.\-]", "", crudo)
    # Separador de miles: "1,250.50" -> "1250.50"; decimal europeo: "1250,50".
    if "," in limpio and "." in limpio:
        limpio = limpio.replace(",", "")
    elif "," in limpio:
        limpio = limpio.replace(",", ".")
    try:
        return float(limpio)
    except ValueError:
        return None


def a_entero(valor: Any) -> Optional[int]:
    numero = a_numero(valor)
    return None if numero is None else int(round(numero))


def numero_a_texto(valor: Any) -> Any:
    """
    Un número en una columna `text` se guarda como su texto; lo demás no se toca.

    `index.html` pinta cuatro encabezados con `<input type="number">` —`DIAS`,
    `RELOJ` y las dos formas de `DÍAS FINALIZ. COTIZ`, línea 2616— y Vue aplica
    el modificador `.number` solo por ser ese el tipo del input, así que la
    celda viaja como número en el JSON. Además `addNewRow` las inicializa en
    `0` y `calculateDiasCounter` escribe en ellas los días transcurridos. En la
    hoja daba igual: una celda de Sheets acepta cualquier tipo. En Postgres,
    `reloj` es `text`, y Pydantic rechazaba el `int` con un 422 que tumbaba el
    lote entero.

    Solo se convierten `int` y `float`. Un `dict` o una lista sigue siendo un
    error de validación: `str()` los guardaría como `"{'a': 1}"`, que es
    justamente el descarte silencioso que `extra="forbid"` viene a evitar. Los
    `bool` tampoco: `"True"` no es un valor que ninguna hoja escriba.

    No se reutiliza `a_texto` —que vive más arriba y hoy no tiene llamadores—
    porque su contrato es otro: convierte `bool` en `"SI"`/`"NO"`, colapsa la
    cadena vacía a `None` y recorta `70.0` a `"70"`. Aplicarlo a `reloj`
    cambiaría el valor de celdas que hoy se guardan tal cual.
    """
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return valor
    return str(valor)


def a_booleano(valor: Any) -> Optional[bool]:
    """La hoja escribe `SI`/`NO`; el frontend, `true`/`false`."""
    if valor is None or isinstance(valor, bool):
        return valor
    crudo = _crudo(valor)
    if crudo is None:
        return None
    arriba = crudo.upper()
    if arriba in {"SI", "SÍ", "TRUE", "1", "X", "YES", "VERDADERO"}:
        return True
    if arriba in {"NO", "FALSE", "0", "FALSO"}:
        return False
    return None


def lista_de_personas(valor: Any) -> List[str]:
    """
    `"RAMIRO RODRIGUEZ, ALFONSO CORREA"` -> `["RAMIRO RODRIGUEZ", "ALFONSO CORREA"]`.

    Decisión D del plan: `INVOLUCRADOS` sigue siendo un string con comas y
    `task_involucrados` es una proyección derivada. Esta es la función que
    produce esa proyección.
    """
    crudo = str(valor or "").strip()
    if not crudo:
        return []
    vistos = []
    for parte in re.split(r"[,\n;]+", crudo):
        nombre = " ".join(parte.split()).upper()
        if nombre and nombre not in vistos:
            vistos.append(nombre)
    return vistos
