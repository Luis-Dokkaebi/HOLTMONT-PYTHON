#!/usr/bin/env python3
"""
Contrasta la Fase 1 contra la base real. **Solo lee**: no escribe nada.

Existe porque la lección de las fases 0 y 0.5 fue que lo que más valor dio no
fueron los fixtures sino contrastar la lógica contra los datos de producción;
ahí aparecieron dos errores de especificación y el problema del espacio inicial
en el nombre de hoja.

Comprueba cinco cosas:

  1. **Esquema**: que `tasks` tenga exactamente las 28 columnas declaradas en
     `backend/schemas/task.py` y con los tipos que se dieron por buenos. Cuatro
     de ellas (`folio_sintetico`, `correo`, `hora_alta`, `hora_estimada_fin`)
     se dedujeron sin evidencia en el código, porque `SupabaseSync` nunca las
     escribe: si el esquema dice otra cosa, aquí se ve.
  2. **Conteos** de las tablas documentadas.
  3. **Paridad de `dedupe_key`** recalculando la clave de las 4.626 filas
     reales a partir de `folio` + `source_sheet` y comparándola con la
     almacenada. Es la verificación que decide si el upsert actualiza o duplica.
  4. **Restricciones**: `dedupe_key` única, `folio` no única (el mismo folio
     vive en varias filas por difusión lateral) y `status` sin nulos.
  5. **Escala de `avance`**: que siga en 0-100 y sin valores en (0,1], que es
     el supuesto del que depende `is_progress_complete_pct`.

Uso:
    python scripts/verificar_base_tasks.py
    python scripts/verificar_base_tasks.py --tabla tasks

Requiere SUPABASE_URL y SUPABASE_KEY (lee `.env` de la raíz si existe).
"""

from __future__ import annotations

import argparse
import collections
import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from backend.core.engines.postgrest import PostgrestEngine  # noqa: E402
from backend.core.errors import ErrorDeMotor  # noqa: E402
from backend.schemas.task import (  # noqa: E402
    COLUMNAS_TASKS,
    NO_NULOS,
    TIPOS_REALES,
)
from backend.services.identity import compute_dedupe_key  # noqa: E402

# Conteos que documentó la sesión anterior. No son la verdad: son lo que hay
# que volver a comprobar, porque la operación sigue viva.
CONTEOS_DOCUMENTADOS = {
    "tasks": 4626,
    "task_involucrados": 7246,
    "quotes": 661,
    "people": 54,
    "system_log": 16196,
    "plan_semanal": 1180,
    "profiles": 0,
    "sites": 1,
    "projects": 4,
    "catalogos": 75,
    "personal_agenda": 27,
    "kpi_cotizaciones": 24,
    "ppc_borradores": 11,
    "banco_datos": 3,
}

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


# ----------------------------------------------------------------------
# 1. Esquema
# ----------------------------------------------------------------------

def verificar_esquema(engine: PostgrestEngine, v: Verificacion) -> None:
    print("\n1. Esquema de `tasks`")
    try:
        definicion = engine.esquema_openapi()
    except ErrorDeMotor as exc:
        v.comprobar("Se pudo leer el esquema publicado por PostgREST", False, str(exc))
        return

    propiedades = (
        definicion.get("definitions", {}).get("tasks", {}).get("properties", {})
    )
    if not propiedades:
        v.comprobar("PostgREST publica la definición de `tasks`", False,
                    "no aparece en `definitions`")
        return

    reales = set(propiedades)
    declaradas = set(COLUMNAS_TASKS)

    v.comprobar("`tasks` tiene 28 columnas", len(reales) == 28, f"tiene {len(reales)}")
    faltan = declaradas - reales
    sobran = reales - declaradas
    v.comprobar("Las 28 columnas declaradas existen en la base", not faltan,
                f"no existen: {sorted(faltan)}" if faltan else "")
    v.comprobar("No hay columnas reales sin declarar", not sobran,
                f"sin declarar: {sorted(sobran)}" if sobran else "")

    # Los tipos, uno a uno. Tres de los cuatro que se dedujeron sin evidencia
    # en el código estaban mal; esto impide que vuelva a pasar en silencio.
    discrepantes = []
    for columna, esperado in TIPOS_REALES.items():
        info = propiedades.get(columna, {})
        real = info.get("format") or info.get("type") or "?"
        if real != esperado:
            discrepantes.append((columna, esperado, real))
    v.comprobar("Los 28 tipos declarados coinciden con el esquema", not discrepantes)
    for columna, esperado, real in discrepantes:
        print(f"     {columna:26} declarado={esperado!r}  real={real!r}")

    obligatorias = set(definicion.get("definitions", {}).get("tasks", {}).get("required", []))
    v.comprobar(
        f"Las columnas NOT NULL son las {len(NO_NULOS)} declaradas",
        obligatorias == NO_NULOS,
        f"en la base: {sorted(obligatorias)}" if obligatorias != NO_NULOS else "",
    )


# ----------------------------------------------------------------------
# 2. Conteos
# ----------------------------------------------------------------------

def verificar_conteos(engine: PostgrestEngine, v: Verificacion) -> None:
    print("\n2. Conteos de filas")
    for tabla, esperado in CONTEOS_DOCUMENTADOS.items():
        try:
            filas = engine.select(tabla, columnas=["*"])
        except ErrorDeMotor as exc:
            v.comprobar(f"{tabla}", False, f"no se pudo leer: {exc}")
            continue
        real = len(filas)
        v.comprobar(f"{tabla:20} {real:>6} filas", real == esperado,
                    "" if real == esperado else f"el documento decía {esperado}")


# ----------------------------------------------------------------------
# 3, 4 y 5. Reglas sobre `tasks`
# ----------------------------------------------------------------------

def verificar_tasks(engine: PostgrestEngine, v: Verificacion) -> None:
    print("\n3. Paridad de `dedupe_key` contra los registros reales")
    filas = engine.select("tasks", columnas=["dedupe_key", "folio", "source_sheet", "status", "avance"])
    total = len(filas)
    if not total:
        v.comprobar("Hay filas en `tasks`", False, "la tabla vino vacía")
        return

    divergencias = []
    for fila in filas:
        calculada = compute_dedupe_key(fila.get("folio"), fila.get("source_sheet"))
        if calculada != fila.get("dedupe_key"):
            divergencias.append((fila.get("folio"), fila.get("source_sheet"),
                                 fila.get("dedupe_key"), calculada))
    v.comprobar(f"Paridad {total - len(divergencias)}/{total}", not divergencias)
    for folio, hoja, almacenada, calculada in divergencias[:10]:
        print(f"     folio={folio!r} hoja={hoja!r}\n"
              f"       almacenada: {almacenada!r}\n"
              f"       calculada:  {calculada!r}")
    if len(divergencias) > 10:
        print(f"     … y {len(divergencias) - 10} más")

    print("\n4. Restricciones")
    claves = collections.Counter(f.get("dedupe_key") for f in filas)
    repetidas = [k for k, n in claves.items() if n > 1 and k is not None]
    v.comprobar("`dedupe_key` es única", not repetidas,
                f"repetidas: {repetidas[:5]}" if repetidas else "")
    v.comprobar("`dedupe_key` no tiene nulos", claves.get(None, 0) == 0,
                f"{claves.get(None, 0)} nulos" if claves.get(None) else "")

    folios = collections.Counter(f.get("folio") for f in filas if f.get("folio"))
    multiples = {k: n for k, n in folios.items() if n > 1}
    v.comprobar("`folio` NO es única (difusión lateral)", bool(multiples),
                f"{len(multiples)} folios en más de una fila")
    if multiples:
        top = sorted(multiples.items(), key=lambda kv: -kv[1])[:3]
        print("     los más repartidos: " + ", ".join(f"{k} en {n}" for k, n in top))

    nulos = sum(1 for f in filas if f.get("status") is None)
    v.comprobar("`status` no tiene nulos (NOT NULL)", nulos == 0, f"{nulos} nulos")

    print("\n5. Escala de `avance`")
    valores = [f["avance"] for f in filas if f.get("avance") is not None]
    if not valores:
        v.aviso("Ninguna fila tiene avance: no se puede comprobar la escala")
        return
    minimo, maximo = min(valores), max(valores)
    v.comprobar(f"Rango {minimo}-{maximo} dentro de 0-100", 0 <= minimo and maximo <= 100)
    en_riesgo = [x for x in valores if 0 < x <= 1]
    v.comprobar(
        "Ningún valor en el intervalo (0,1]",
        not en_riesgo,
        f"{len(en_riesgo)} filas con avance en (0,1]: con la regla de la hoja "
        f"se archivarían como terminadas al 1 %" if en_riesgo else "",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tabla", default="", help="Verificar solo una tabla en los conteos")
    args = parser.parse_args()

    cargar_env()
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        print("Faltan SUPABASE_URL y SUPABASE_KEY (ver .env.example).", file=sys.stderr)
        return 2

    if args.tabla:
        for tabla in list(CONTEOS_DOCUMENTADOS):
            if tabla != args.tabla:
                CONTEOS_DOCUMENTADOS.pop(tabla)

    engine = PostgrestEngine(url, key)
    v = Verificacion()
    print("Verificación de la Fase 1 contra la base real (solo lectura)")
    verificar_esquema(engine, v)
    verificar_conteos(engine, v)
    verificar_tasks(engine, v)

    print(f"\n{'-' * 60}")
    if v.fallas:
        print(f"{ROJO}{v.fallas} comprobación(es) fallaron.{FIN} "
              f"Cada una contradice lo documentado y hay que resolverla antes de escribir.")
    else:
        print(f"{VERDE}Todo comprobado.{FIN}")
    return 1 if v.fallas else 0


if __name__ == "__main__":
    raise SystemExit(main())
