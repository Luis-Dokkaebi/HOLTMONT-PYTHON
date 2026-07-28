#!/usr/bin/env python3
"""
Normaliza la columna de estatus de `tasks` y `quotes` en Supabase.

La columna venía de captura libre en la hoja: 45 valores distintos en `tasks` y
26 en `quotes` para lo que son ~11 estatus reales. Mezcla mayúsculas, acentos,
género (ASIGNADO/ASIGNADA), erratas (ASIGANDO, PEDIENTE, BIERTO), marcadores de
vacío ("-", "-\\n-") y texto que no es un estatus (iniciales de persona,
nombres, comentarios enteros).

Qué hace con cada fila:

  · Reconocible  -> se escribe el canónico (`api.services.tracker_rules.
                    normalize_status`, la misma regla que usa el backend).
  · Marcador de
    vacío        -> se vacía el estatus. No hay texto que perder.
  · Texto que no
    es estatus   -> el original se copia a `comentarios` con el prefijo
                    [ESTATUS ORIGINAL] y el estatus se vacía. Así la columna
                    queda limpia sin tirar lo que alguien escribió.

"Vaciar" depende de la tabla: `quotes.estatus` admite NULL, pero
`tasks.status` tiene NOT NULL y hay que escribir cadena vacía. El frontend
trata ambos igual.

Garantía verificada antes de aplicar: ninguna fila cambia de estado terminal,
es decir, la normalización no altera qué tareas se consideran archivadas.

Uso:
    python scripts/normalizar_estatus.py                  # simulación (por defecto)
    python scripts/normalizar_estatus.py --aplicar        # escribe en la base
    python scripts/normalizar_estatus.py --aplicar --solo tasks

Requiere SUPABASE_URL y SUPABASE_KEY (lee `.env` de la raíz si existe).
Antes de escribir deja una copia de los valores actuales en
`scripts/respaldos/estatus_<tabla>_<marca>.json`, suficiente para revertir.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from api.services.tracker_rules import is_terminal_status, normalize_status  # noqa: E402

# Marcadores de "sin estatus": no aportan texto, se anulan sin conservar nada.
PLACEHOLDERS = {"-", "--", "---", "-\n-", "-\n-\n-", ".", "..", "...",
                "N/A", "NA", "#N/A"}

PREFIJO_RESCATE = "[ESTATUS ORIGINAL] "

# `vacio` es lo que se escribe cuando el valor no representa un estatus.
# No es cosmético: `tasks.status` tiene NOT NULL y rechaza el nulo, mientras
# que `quotes.estatus` sí lo admite. Ambos se leen igual (cadena vacía) desde
# el frontend, que trata "" y NULL como "sin estatus".
TABLAS = {
    "tasks": {"pk": "id", "columna": "status", "vacio": ""},
    "quotes": {"pk": "folio", "columna": "estatus", "vacio": None},
}


# ----------------------------------------------------------------------
# Acceso a Supabase (PostgREST)
# ----------------------------------------------------------------------

def cargar_env():
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                clave, valor = linea.split("=", 1)
                os.environ.setdefault(clave.strip(), valor.strip())

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        sys.exit("Faltan SUPABASE_URL / SUPABASE_KEY (ver .env.example).")
    return url, key


class Cliente:
    def __init__(self, url, key):
        self.url = url
        self.cabeceras = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def _peticion(self, metodo, ruta, cuerpo=None, prefer="return=minimal"):
        req = urllib.request.Request(
            f"{self.url}/rest/v1/{ruta}",
            data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
            headers={**self.cabeceras, "Prefer": prefer},
            method=metodo,
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            texto = r.read().decode()
            return json.loads(texto) if texto else None

    def leer_todo(self, tabla, columnas):
        filas, offset = [], 0
        while True:
            pagina = self._peticion(
                "GET", f"{tabla}?select={columnas}&limit=1000&offset={offset}",
                prefer="count=none",
            ) or []
            filas.extend(pagina)
            if len(pagina) < 1000:
                return filas
            offset += 1000

    def actualizar_por_valor(self, tabla, columna, valor_actual, nuevo):
        """PATCH masivo de todas las filas que comparten un mismo valor."""
        filtro = f"{columna}=eq.{urllib.parse.quote(valor_actual, safe='')}"
        self._peticion("PATCH", f"{tabla}?{filtro}", {columna: nuevo})

    def actualizar_fila(self, tabla, pk, valor_pk, cambios):
        filtro = f"{pk}=eq.{urllib.parse.quote(str(valor_pk), safe='')}"
        self._peticion("PATCH", f"{tabla}?{filtro}", cambios)


# ----------------------------------------------------------------------
# Plan de cambios
# ----------------------------------------------------------------------

def construir_plan(filas, columna, vacio):
    """
    Devuelve (por_valor, rescates, sin_cambio).

    `por_valor`  {valor_actual: canonico_o_vacio}  -> PATCH masivo
    `rescates`   [(fila, texto_original)]          -> texto a `comentarios`
    """
    por_valor = {}
    rescates = []
    sin_cambio = 0

    for fila in filas:
        actual = fila.get(columna)
        canonico = normalize_status(actual)

        if canonico == actual:
            sin_cambio += 1
            continue

        if canonico is not None:
            por_valor[actual] = canonico
            continue

        if actual is None or actual == vacio:
            sin_cambio += 1
            continue

        if actual.strip() in PLACEHOLDERS or not actual.strip():
            por_valor[actual] = vacio
            continue

        # Texto que no es un estatus: se conserva antes de anular.
        rescates.append((fila, actual))

    return por_valor, rescates, sin_cambio


def verificar_invariante(filas, columna):
    """Normalizar no puede cambiar si una fila se considera terminal."""
    problemas = []
    for fila in filas:
        actual = fila.get(columna)
        canonico = normalize_status(actual)
        if is_terminal_status(actual) != is_terminal_status(canonico or ""):
            problemas.append((actual, canonico))
    return problemas


def respaldar(tabla, filas, columna, pk):
    carpeta = RAIZ / "scripts" / "respaldos"
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destino = carpeta / f"estatus_{tabla}_{marca}.json"
    destino.write_text(json.dumps(
        [{pk: f.get(pk), columna: f.get(columna)} for f in filas],
        ensure_ascii=False, indent=1,
    ), encoding="utf-8")
    return destino


# ----------------------------------------------------------------------

def procesar(cli, tabla, aplicar):
    meta = TABLAS[tabla]
    columna, pk, vacio = meta["columna"], meta["pk"], meta["vacio"]
    filas = cli.leer_todo(tabla, f"{pk},{columna},comentarios")

    print(f"\n=== {tabla} ({len(filas)} filas, columna `{columna}`) ===")

    problemas = verificar_invariante(filas, columna)
    if problemas:
        print(f"  ABORTADO: {len(problemas)} filas cambiarian de estado terminal:")
        for p in problemas[:10]:
            print(f"    {p}")
        return False
    print("  Invariante de auto-archivado: ninguna fila cambia de estado terminal.")

    distintos_antes = len({f.get(columna) for f in filas})
    por_valor, rescates, sin_cambio = construir_plan(filas, columna, vacio)

    a_canonico = {k: v for k, v in por_valor.items() if v not in (None, "")}
    a_nulo = {k: v for k, v in por_valor.items() if v in (None, "")}
    afectadas = collections.Counter()
    for f in filas:
        if f.get(columna) in por_valor:
            afectadas[f.get(columna)] += 1

    print(f"  Valores distintos actuales : {distintos_antes}")
    print(f"  Ya correctos               : {sin_cambio}")
    print(f"  A canonico                 : {sum(afectadas[k] for k in a_canonico)} filas, {len(a_canonico)} variantes")
    print(f"  Marcadores de vacio         : {sum(afectadas[k] for k in a_nulo)} filas")
    print(f"  Texto rescatado a comentarios: {len(rescates)} filas")

    if a_canonico:
        print("\n  Mapeo a canonico:")
        for viejo in sorted(a_canonico, key=lambda k: -afectadas[k]):
            print(f"    {afectadas[viejo]:>5}  {viejo!r:44} -> {a_canonico[viejo]!r}")
    if rescates:
        print("\n  Rescates (estatus -> NULL, texto a comentarios):")
        for _, texto in rescates[:12]:
            print(f"           {texto!r}")

    if not aplicar:
        print("\n  [simulacion] Nada escrito. Usa --aplicar para ejecutarlo.")
        return True

    destino = respaldar(tabla, filas, columna, pk)
    print(f"\n  Respaldo: {destino.relative_to(RAIZ)}")

    # Los rescates van primero: si algo falla despues, no se pierde el texto.
    for fila, texto in rescates:
        nota = PREFIJO_RESCATE + " ".join(str(texto).split())
        actuales = fila.get("comentarios")
        cli.actualizar_fila(tabla, pk, fila[pk], {
            columna: vacio,
            "comentarios": nota if not actuales else f"{actuales}\n{nota}",
        })
    if rescates:
        print(f"  {len(rescates)} textos preservados en `comentarios`.")

    for viejo, nuevo in por_valor.items():
        cli.actualizar_por_valor(tabla, columna, viejo, nuevo)
    print(f"  {len(por_valor)} variantes actualizadas.")

    despues = cli.leer_todo(tabla, f"{pk},{columna}")
    distintos = sorted({f[columna] for f in despues if f[columna]})
    print(f"  Resultado: {len(distintos)} valores distintos -> {distintos}")
    restantes = [f[columna] for f in despues
                 if f[columna] and normalize_status(f[columna]) != f[columna]]
    print(f"  Sin normalizar tras aplicar: {len(restantes)}")
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--aplicar", action="store_true",
                   help="escribe en la base (por defecto solo simula)")
    p.add_argument("--solo", choices=sorted(TABLAS), help="limitar a una tabla")
    args = p.parse_args()

    url, key = cargar_env()
    cli = Cliente(url, key)

    print("NORMALIZACION DE ESTATUS" + ("" if args.aplicar else "  [SIMULACION]"))
    ok = True
    for tabla in ([args.solo] if args.solo else sorted(TABLAS)):
        try:
            ok = procesar(cli, tabla, args.aplicar) and ok
        except urllib.error.HTTPError as e:
            print(f"  ERROR HTTP {e.code}: {e.read().decode()[:300]}")
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
