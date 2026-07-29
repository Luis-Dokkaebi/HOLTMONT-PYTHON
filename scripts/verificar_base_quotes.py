#!/usr/bin/env python3
"""
Contrasta el contrato de `quotes` contra la base real. **Solo lee**.

Gemelo de `scripts/verificar_base_tasks.py`, escrito por la razón que dejó
anotada la Fase 1 (§7.6 del plan): antes de escribir en `quotes` había que
repetir ahí la verificación de tipos y de columnas NOT NULL, porque en `tasks`
tres de los cuatro tipos deducidos del código estaban mal y el número de
columnas NOT NULL era nueve en vez de una.

Comprueba cuatro cosas:

  1. **Esquema**: que `quotes` tenga exactamente las 37 columnas declaradas en
     `backend/schemas/quote.py`, con sus tipos y sus NOT NULL.
  2. **Identidad**: que `folio` sea único y que ninguna cotización aparezca en
     más de una hoja. Es el supuesto del que depende toda la escritura de esta
     tabla: la clave primaria es `folio` a secas, así que una cotización vive
     en una sola `source_sheet` y `QuoteRepository` no la puede mover.
  3. **Hojas**: qué `source_sheet` existen y con qué grafía, que es lo que
     `resolver_hoja()` tiene que traducir.
  4. **Escala de `avance`**: que siga en 0-100 y sin valores en (0,1].

Uso:
    python scripts/verificar_base_quotes.py

Requiere SUPABASE_URL y SUPABASE_KEY (lee `.env` de la raíz si existe).
"""

from __future__ import annotations

import collections
import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.core.engines.postgrest import PostgrestEngine  # noqa: E402
from backend.core.errors import ErrorDeMotor  # noqa: E402
from backend.schemas.quote import (  # noqa: E402
    COLUMNAS_QUOTES,
    NO_NULOS,
    TIPOS_REALES,
)

VERDE, ROJO, AMARILLO, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[0m"


def cargar_env() -> None:
    env = RAIZ / ".env"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip())


def marca(ok: bool) -> str:
    return f"{VERDE}OK{FIN}" if ok else f"{ROJO}FALLA{FIN}"


class Verificacion:
    def __init__(self) -> None:
        self.fallas = 0

    def comprobar(self, titulo: str, ok: bool, detalle: str = "") -> None:
        print(f"  [{marca(ok)}] {titulo}" + (f" — {detalle}" if detalle else ""))
        if not ok:
            self.fallas += 1

    def aviso(self, texto: str) -> None:
        print(f"  [{AMARILLO}AVISO{FIN}] {texto}")


def verificar_esquema(engine: PostgrestEngine, v: Verificacion) -> None:
    print("\n1. Esquema de `quotes`")
    try:
        definicion = engine.esquema_openapi()
    except ErrorDeMotor as exc:
        v.comprobar("Se pudo leer el esquema publicado por PostgREST", False, str(exc))
        return

    tabla = definicion.get("definitions", {}).get("quotes", {})
    propiedades = tabla.get("properties", {})
    if not propiedades:
        v.comprobar("PostgREST publica la definición de `quotes`", False,
                    "no aparece en `definitions`")
        return

    reales = set(propiedades)
    declaradas = set(COLUMNAS_QUOTES)

    v.comprobar(f"`quotes` tiene {len(declaradas)} columnas", len(reales) == len(declaradas),
                f"tiene {len(reales)}")
    faltan = declaradas - reales
    sobran = reales - declaradas
    v.comprobar("Las columnas declaradas existen en la base", not faltan,
                f"no existen: {sorted(faltan)}" if faltan else "")
    v.comprobar("No hay columnas reales sin declarar", not sobran,
                f"sin declarar: {sorted(sobran)}" if sobran else "")

    discrepantes = []
    for columna, esperado in TIPOS_REALES.items():
        info = propiedades.get(columna, {})
        real = info.get("format") or info.get("type") or "?"
        if real != esperado:
            discrepantes.append((columna, esperado, real))
    v.comprobar("Los tipos declarados coinciden con el esquema", not discrepantes)
    for columna, esperado, real in discrepantes:
        print(f"     {columna:22} declarado={esperado!r}  real={real!r}")

    obligatorias = set(tabla.get("required", []))
    v.comprobar(
        f"Las columnas NOT NULL son las {len(NO_NULOS)} declaradas",
        obligatorias == NO_NULOS,
        f"en la base: {sorted(obligatorias)}" if obligatorias != NO_NULOS else "",
    )


def verificar_identidad(engine: PostgrestEngine, v: Verificacion) -> None:
    print("\n2. Identidad de la fila")
    filas = engine.select("quotes", columnas=["folio", "source_sheet", "avance", "estatus"])
    total = len(filas)
    if not total:
        v.comprobar("Hay filas en `quotes`", False, "la tabla vino vacía")
        return
    print(f"  {total} cotizaciones")

    folios = collections.Counter(f.get("folio") for f in filas)
    repetidos = [k for k, n in folios.items() if n > 1]
    v.comprobar("`folio` es única (es la clave primaria)", not repetidos,
                f"repetidos: {repetidos[:5]}" if repetidos else "")
    v.comprobar("`folio` no tiene nulos", folios.get(None, 0) == 0)

    por_folio = collections.defaultdict(set)
    for fila in filas:
        por_folio[fila.get("folio")].add(fila.get("source_sheet"))
    compartidos = {f: h for f, h in por_folio.items() if len(h) > 1}
    v.comprobar(
        "Ninguna cotización está en más de una hoja",
        not compartidos,
        f"{len(compartidos)} compartidas: {list(compartidos.items())[:3]}" if compartidos else
        "de esto depende que el reverse sync actualice en vez de cambiar de dueño",
    )

    sin_hoja = sum(1 for f in filas if not f.get("source_sheet"))
    v.comprobar("`source_sheet` no tiene nulos (NOT NULL)", sin_hoja == 0, f"{sin_hoja} nulos")

    print("\n3. Hojas de ventas y su grafía")
    for hoja, n in collections.Counter(f.get("source_sheet") for f in filas).most_common():
        print(f"     {n:5d}  {hoja!r}")

    print("\n4. Escala de `avance`")
    valores = [f["avance"] for f in filas if f.get("avance") is not None]
    if not valores:
        v.aviso("Ninguna cotización tiene avance: no se puede comprobar la escala")
        return
    minimo, maximo = min(valores), max(valores)
    v.comprobar(f"Rango {minimo}-{maximo} dentro de 0-100", 0 <= minimo and maximo <= 100)
    en_riesgo = [x for x in valores if 0 < x <= 1]
    v.comprobar("Ningún valor en el intervalo (0,1]", not en_riesgo,
                f"{len(en_riesgo)} filas en (0,1]" if en_riesgo else "")


def main() -> int:
    cargar_env()
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("Faltan SUPABASE_URL y SUPABASE_KEY (ver .env.example).", file=sys.stderr)
        return 2

    engine = PostgrestEngine(url, key)
    v = Verificacion()
    print("Verificación del contrato de `quotes` contra la base real (solo lectura)")
    verificar_esquema(engine, v)
    verificar_identidad(engine, v)

    print(f"\n{'-' * 60}")
    if v.fallas:
        print(f"{ROJO}{v.fallas} comprobación(es) fallaron.{FIN} "
              f"Cada una contradice lo declarado y hay que resolverla antes de escribir.")
    else:
        print(f"{VERDE}Todo comprobado.{FIN}")
    return 1 if v.fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())
