#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sube las fotos del personal a Supabase Storage y escribe su ficha en la base.

**Se corre a mano, contra producción.** Por eso, por omisión no escribe nada:
imprime lo que haría. Para aplicarlo de verdad hace falta `--aplicar`, igual
que `scripts/migrar_perfiles.py`.

    python scripts/migrar_fichas_personal.py            # simulacro
    python scripts/migrar_fichas_personal.py --aplicar  # sube y escribe

Requiere `SUPABASE_URL` y `SUPABASE_KEY` en el entorno (o en `.env`).

Qué hace y por qué:

1. **Sube los 31 JPEG de `api/static/fotos/` al bucket `fotos-personal`**, que
   crea público si no existe. El repositorio ya sirve esas mismas fotos por
   `/fotos/<archivo>`; el bucket es para lo que el repositorio no puede dar:
   que el dueño cambie la foto de alguien sin desplegar.

2. **Escribe la ficha en `people` y en `profiles`** — nombre completo, puesto y
   la URL pública de la foto. Ahí es donde el sistema ya las busca primero:
   `organigrama._perfil_desde_base` y `enriquecer_directorio` prefieren lo que
   traiga la base y solo caen a la transcripción de RH (`organigrama.FICHAS`)
   cuando la base no dice nada.

Las columnas **no** las crea este script: el `SUPABASE_KEY` habla PostgREST, que
no hace DDL. Si faltan, el script las detecta, imprime el `ALTER TABLE` exacto y
se detiene ahí sin escribir; las fotos del paso 1 sí quedan subidas. Una vez
creadas las columnas, se vuelve a correr y termina el trabajo.

En `people` la columna es `nombre_completo` y no `nombre`: `nombre` ya está
ocupada por el nombre canónico ("TERESA GARZA"), que es con el que se abre el
tracker de la persona. Pisarlo con el nombre de RH ("María Teresa Hernández
Garza") estrenaría una partición vacía.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from api.services.organigrama import FICHAS, PERFILES, ficha  # noqa: E402

BUCKET = "fotos-personal"
DIR_FOTOS = RAIZ / "api" / "static" / "fotos"

# Columna -> tipo, por tabla. `foto` guarda la URL pública completa del bucket.
COLUMNAS = {
    "people": {"nombre_completo": "text", "puesto": "text", "foto": "text"},
    "profiles": {"nombre": "text", "puesto": "text", "foto": "text"},
}


def cargar_env() -> None:
    """Lee `.env` si existe, igual que los otros scripts del repo."""
    env = RAIZ / ".env"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def url_publica(base: str, archivo: str) -> str:
    """URL de lectura de un objeto del bucket público."""
    return f"{base.rstrip('/')}/storage/v1/object/public/{BUCKET}/{archivo}"


def fotos_a_subir() -> List[Tuple[str, Path]]:
    """(nombre de archivo, ruta local) de cada foto que el catálogo referencia."""
    archivos = []
    for datos in FICHAS.values():
        archivo = datos["foto"].rsplit("/", 1)[-1]
        archivos.append((archivo, DIR_FOTOS / archivo))
    return sorted(archivos)


def columnas_faltantes(tabla: str, fila: Dict[str, Any]) -> List[str]:
    """
    Columnas de la ficha que la tabla todavía no tiene.

    Se mira una fila real en vez de consultar el catálogo del sistema porque
    PostgREST no expone `information_schema`: lo que la fila no trae, la tabla
    no lo tiene.
    """
    return sorted(c for c in COLUMNAS[tabla] if c not in fila)


def sql_para_crear(tabla: str, faltantes: List[str]) -> str:
    """El `ALTER TABLE` que hay que correr en el editor SQL de Supabase."""
    columnas = ",\n".join(
        f"  ADD COLUMN IF NOT EXISTS {c} {COLUMNAS[tabla][c]}" for c in faltantes
    )
    return f"ALTER TABLE public.{tabla}\n{columnas};"


def plan_people(filas: List[Dict[str, Any]], base: str) -> List[Dict[str, Any]]:
    """
    Qué escribir en `people`, una entrada por fila que tenga ficha.

    Se emparejan por `nombre`, el nombre canónico, que es justo la clave de
    `FICHAS`. Quien no tiene ficha no se toca: no se escriben cadenas vacías
    encima de lo que alguien pudo haber puesto a mano.
    """
    plan = []
    for fila in filas:
        datos = ficha(fila.get("nombre"))
        if not datos:
            continue
        plan.append({
            "id": fila.get("id"),
            "nombre": fila.get("nombre"),
            "nombre_completo": datos["nombre"],
            "puesto": datos["puesto"],
            "foto": url_publica(base, datos["foto"].rsplit("/", 1)[-1]),
        })
    return plan


def plan_profiles(filas: List[Dict[str, Any]], base: str) -> List[Dict[str, Any]]:
    """
    Qué escribir en `profiles`, una entrada por cuenta que tenga ficha.

    La ficha de una cuenta se busca por `staff_name` y, si no tiene (las cuentas
    de control), por `label`. Es la misma resolución que hace
    `organigrama._con_ficha`, para que la base y la semilla no discrepen.
    """
    plan = []
    for fila in filas:
        usuario = str(fila.get("username") or "").strip().upper()
        semilla = PERFILES.get(usuario, {})
        clave = (fila.get("staff_name") or semilla.get("staff_name")
                 or fila.get("label") or semilla.get("label"))
        datos = ficha(clave)
        if not datos:
            continue
        plan.append({
            "username": usuario,
            "nombre": datos["nombre"],
            "puesto": datos["puesto"],
            "foto": url_publica(base, datos["foto"].rsplit("/", 1)[-1]),
        })
    return plan


# --- Efectos (red). Lo de arriba es puro y tiene prueba. ----------------
def _subir_fotos(cliente: Any, aplicar: bool) -> int:
    almacen = cliente.storage
    existentes = {b.name for b in almacen.list_buckets()}
    if BUCKET not in existentes:
        print(f"  bucket `{BUCKET}`: no existe, se crea público")
        if aplicar:
            almacen.create_bucket(BUCKET, options={"public": True})
    else:
        print(f"  bucket `{BUCKET}`: ya existe")

    subidas = 0
    for archivo, ruta in fotos_a_subir():
        if not ruta.exists():
            print(f"  FALTA en disco: {ruta}", file=sys.stderr)
            return -1
        print(f"  {'sube' if aplicar else 'subiría'} {archivo} ({ruta.stat().st_size} B)")
        if aplicar:
            almacen.from_(BUCKET).upload(
                archivo,
                ruta.read_bytes(),
                {"content-type": "image/jpeg", "cache-control": "86400", "upsert": "true"},
            )
        subidas += 1
    return subidas


def _escribir(gestor: Any, tabla: str, plan: List[Dict[str, Any]], clave: str, aplicar: bool) -> None:
    for entrada in plan:
        valores = {k: v for k, v in entrada.items() if k not in ("id", clave)}
        print(f"  {tabla}[{entrada[clave]}] <- {valores['puesto']}")
        if aplicar:
            gestor.client.table(tabla).update(valores).eq(clave, entrada[clave]).execute()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aplicar", action="store_true",
                    help="escribe de verdad (por omisión solo simula)")
    args = ap.parse_args()

    cargar_env()
    from api.services.supabase_manager import sb_manager

    if not sb_manager.is_configured:
        print("Faltan SUPABASE_URL / SUPABASE_KEY en el entorno.", file=sys.stderr)
        return 2

    modo = "APLICANDO" if args.aplicar else "SIMULACRO (usa --aplicar para escribir)"
    print(f"== {modo} ==\n")

    print("1) Fotos al bucket")
    if _subir_fotos(sb_manager.client, args.aplicar) < 0:
        return 1

    print("\n2) Columnas de la ficha")
    filas = {t: sb_manager.select(t) for t in COLUMNAS}
    faltan = {t: columnas_faltantes(t, filas[t][0]) for t in COLUMNAS if filas[t]}
    if any(faltan.values()):
        print("  La base todavía no tiene dónde guardar la ficha. Corre esto en el")
        print("  editor SQL de Supabase y vuelve a lanzar el script:\n")
        for tabla, columnas in faltan.items():
            if columnas:
                print("\n".join("      " + linea for linea in sql_para_crear(tabla, columnas).splitlines()))
        print("\n  Las fotos del paso 1 ya quedaron subidas; nada más se escribió.")
        return 3
    print("  están las tres en las dos tablas")

    base = sb_manager.url
    print("\n3) Ficha en `people`")
    _escribir(sb_manager, "people", plan_people(filas["people"], base), "nombre", args.aplicar)
    print("\n4) Ficha en `profiles`")
    _escribir(sb_manager, "profiles", plan_profiles(filas["profiles"], base), "username", args.aplicar)

    print("\nListo." if args.aplicar else "\nSimulacro terminado: nada se escribió.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
