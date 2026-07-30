#!/usr/bin/env python3
"""
Puebla `profiles` en Supabase con las cuentas de `USER_DB` de Apps Script.

**Se corre en tu máquina, no en CI.** Lee las contraseñas del `CODIGO.js` que ya
tienes y las escribe en la base; nunca las imprime ni las guarda en el repo. Ese
es el punto: son las credenciales que tu gente ya usa, y esta es la única forma
de llevarlas a Supabase sin que pasen por un archivo versionado ni por el
historial de una conversación.

Por qué hace falta: la migración nunca trajo los datos de autenticación. No
existe tabla `USERS` y `profiles` está en 0 filas, así que `/api/login` no
encontraba a nadie y solo se podía entrar con `DEV_LOGIN_USERS`.

Uso:

    # 1. Ver qué haría, sin escribir nada (por defecto)
    python scripts/migrar_perfiles.py

    # 2. Aplicarlo de verdad
    python scripts/migrar_perfiles.py --aplicar

    # Si el CODIGO.js está en otra ruta:
    python scripts/migrar_perfiles.py --codigo /ruta/a/CODIGO.js --aplicar

Requiere en el entorno (o en `.env`): SUPABASE_URL y SUPABASE_KEY, o DATABASE_URL.

Las contraseñas quedan en **texto plano**, por decisión del dueño (2026-07): se
migran a hash cuando se haga la migración completa. Mientras tanto, dos cosas ya
están cubiertas: `/api/data` no publica la tabla `profiles` ni ninguna columna de
credenciales, y `/api/config` nunca incluye la contraseña en su respuesta.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TABLA = "profiles"
CLAVE_UPSERT = "username"

# Ruta por omisión: el repo de Apps Script clonado al lado de este.
CODIGO_POR_DEFECTO = RAIZ.parent / "REAL-HOLTMONT" / "CODIGO.js"


def cargar_env() -> None:
    """Lee `.env` si existe, igual que los otros scripts del repo."""
    env = RAIZ / ".env"
    if not env.exists():
        return
    for linea in env.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        os.environ.setdefault(clave.strip(), valor.strip())


def leer_user_db(ruta: Path) -> List[Dict[str, Any]]:
    """
    Extrae `USER_DB` de `CODIGO.js`.

    Se parsea con expresiones regulares y no con un intérprete de JS porque el
    bloque es un literal plano: una llave por línea, con valores de cadena y dos
    booleanos. Meter un motor de JS para esto sería peor.
    """
    if not ruta.exists():
        raise SystemExit(
            f"No encuentro {ruta}.\n"
            "Pásame la ruta con --codigo /ruta/a/CODIGO.js"
        )

    fuente = ruta.read_text(encoding="utf-8")
    bloque = re.search(r"const USER_DB = \{(.*?)\n\};", fuente, re.S)
    if not bloque:
        raise SystemExit(f"No hay un bloque `const USER_DB = {{...}}` en {ruta}.")

    cuentas = []
    for linea in bloque.group(1).splitlines():
        m = re.match(r'\s*"([A-Z_0-9]+)":\s*\{(.*)\},?\s*$', linea)
        if not m:
            continue
        usuario, cuerpo = m.group(1), m.group(2)
        textos = dict(re.findall(r"(\w+):\s*\"([^\"]*)\"", cuerpo))
        bools = dict(re.findall(r"(\w+):\s*(true|false)", cuerpo))

        clave = textos.get("pass", "")
        if not clave:
            print(f"  ! {usuario}: sin contraseña en USER_DB, se omite")
            continue

        cuentas.append({
            "username": usuario,
            "password": clave,
            "role": textos.get("role", "STAFF_USER"),
            "label": textos.get("label", usuario),
            "email": textos.get("email", ""),
            "staff_name": textos.get("staffName", ""),
            "dept": textos.get("dept", ""),
            "seller": bools.get("seller") == "true",
        })
    return cuentas


def comparar_con_el_organigrama(cuentas: List[Dict[str, Any]]) -> None:
    """
    Avisa si `USER_DB` y la semilla del repo no coinciden.

    No bloquea: la base manda. Pero una diferencia aquí suele significar que
    `CODIGO.js` cambió y `api/services/organigrama.py` se quedó atrás.
    """
    from api.services.organigrama import PERFILES

    en_codigo = {c["username"] for c in cuentas}
    en_semilla = set(PERFILES)

    solo_codigo = sorted(en_codigo - en_semilla)
    solo_semilla = sorted(en_semilla - en_codigo)
    if solo_codigo:
        print(f"  ! En CODIGO.js y no en la semilla del repo: {solo_codigo}")
    if solo_semilla:
        print(f"  ! En la semilla del repo y no en CODIGO.js: {solo_semilla}")

    distintos = [
        c["username"] for c in cuentas
        if c["username"] in PERFILES
        and c["role"] != PERFILES[c["username"]].get("role")
    ]
    if distintos:
        print(f"  ! Rol distinto entre CODIGO.js y la semilla: {distintos}")


COLUMNAS_NECESARIAS = ("username", "password", "role", "label", "email",
                       "staff_name", "dept", "seller")

TIPOS_SUGERIDOS = {
    "username": "TEXT PRIMARY KEY",
    "password": "TEXT",
    "role": "TEXT NOT NULL DEFAULT 'STAFF_USER'",
    "label": "TEXT",
    "email": "TEXT",
    "staff_name": "TEXT",
    "dept": "TEXT",
    "seller": "BOOLEAN NOT NULL DEFAULT false",
}


def _falta_la_tabla(exc: Exception) -> bool:
    """
    ¿El error dice que la TABLA no existe?

    Se comprueba antes que la columna y con marcas propias, porque el texto
    "does not exist" aparece en los dos casos y confundirlos haría que el script
    pidiera un ALTER TABLE sobre una tabla que hay que crear.
    """
    texto = str(exc).lower()
    return ("pgrst205" in texto
            or "could not find the table" in texto
            or "no existe la tabla" in texto
            or 'relation "' in texto and "does not exist" in texto)


def _falta_la_columna(exc: Exception) -> bool:
    """¿El error dice que la COLUMNA no existe? (42703 en Postgres.)"""
    texto = str(exc).lower()
    return "42703" in texto or "column" in texto and "does not exist" in texto


def revisar_tabla() -> Dict[str, Any]:
    """
    Dice si `profiles` existe y qué columnas le faltan, **sin escribir nada**.

    Con la tabla vacía no se pueden deducir las columnas de los datos, así que se
    pregunta por cada una: PostgREST responde con error 42703 cuando la columna
    no existe, y eso basta para distinguir "no está" de "está y viene vacía".

    Existe para contestar la pregunta práctica de "¿tengo que entrar a Supabase a
    crear algo?" con un dato en vez de con una suposición.
    """
    from backend.core.engine import construir_engine

    engine = construir_engine()
    resultado: Dict[str, Any] = {"motor": engine.nombre, "existe": False,
                                 "faltantes": [], "filas": None}

    try:
        engine.select(TABLA, columnas=["username"], limite=1)
        resultado["existe"] = True
    except Exception as exc:  # noqa: BLE001
        if _falta_la_tabla(exc):
            return resultado  # existe=False: hay que crearla
        if _falta_la_columna(exc):
            # La tabla está, pero sin `username`: se sigue revisando el resto.
            resultado["existe"] = True
            resultado["faltantes"].append("username")
        else:
            resultado["error"] = str(exc)
            return resultado

    for columna in COLUMNAS_NECESARIAS:
        if columna in resultado["faltantes"]:
            continue
        try:
            engine.select(TABLA, columnas=[columna], limite=1)
        except Exception as exc:  # noqa: BLE001
            if _falta_la_columna(exc):
                resultado["faltantes"].append(columna)
            else:
                resultado["error"] = str(exc)
                return resultado

    try:
        resultado["filas"] = len(engine.select(TABLA, columnas=["username"]))
    except Exception:  # noqa: BLE001
        pass

    return resultado


def informar_tabla(revision: Dict[str, Any]) -> bool:
    """Imprime el diagnóstico. Devuelve True si se puede escribir."""
    if revision.get("error"):
        print(f"\n  No se pudo revisar `{TABLA}`: {revision['error']}")
        print("  Revisa SUPABASE_URL / SUPABASE_KEY (o DATABASE_URL).")
        return False

    if not revision["existe"]:
        print(f"\n  La tabla `{TABLA}` NO existe.")
        print("  Créala en Supabase con el bloque §3 de docs/DDL_PENDIENTE.sql.")
        return False

    print(f"\n  `{TABLA}` existe"
          + (f", {revision['filas']} fila(s)" if revision["filas"] is not None else ""))

    if revision["faltantes"]:
        print(f"  Le faltan {len(revision['faltantes'])} columna(s). "
              "Corre esto en el editor SQL de Supabase:\n")
        for columna in revision["faltantes"]:
            print(f"    ALTER TABLE public.{TABLA} "
                  f"ADD COLUMN IF NOT EXISTS {columna} {TIPOS_SUGERIDOS[columna]};")
        print()
        return False

    print("  Tiene las 8 columnas necesarias: no hace falta tocar Supabase.")
    return True


def aplicar(cuentas: List[Dict[str, Any]]) -> int:
    from backend.core.engine import construir_engine

    engine = construir_engine()
    print(f"  motor: {engine.nombre}")

    # Un solo upsert con todas las filas: en PostgREST es la única forma de que
    # la escritura sea atómica (no hay BEGIN/COMMIT), y con SQLAlchemy da igual.
    engine.upsert(TABLA, cuentas, en_conflicto=CLAVE_UPSERT)
    return len(cuentas)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--codigo", type=Path, default=CODIGO_POR_DEFECTO,
                        help="Ruta al CODIGO.js de Apps Script")
    parser.add_argument("--aplicar", action="store_true",
                        help="Escribe en la base. Sin esta bandera solo informa.")
    args = parser.parse_args()

    cargar_env()

    print(f"Leyendo {args.codigo}")
    cuentas = leer_user_db(args.codigo)
    if not cuentas:
        print("No se encontró ninguna cuenta con contraseña.")
        return 1

    print(f"  {len(cuentas)} cuenta(s) con credencial")
    por_rol: Dict[str, int] = {}
    for c in cuentas:
        por_rol[c["role"]] = por_rol.get(c["role"], 0) + 1
    for rol, n in sorted(por_rol.items()):
        print(f"    {rol}: {n}")
    print(f"  vendedores (seller=true): {sum(1 for c in cuentas if c['seller'])}")

    comparar_con_el_organigrama(cuentas)

    # Deliberadamente NO se imprime ninguna contraseña, ni truncada: este script
    # se corre en una terminal cuyo historial suele quedar guardado.
    print(f"\n  usuarios: {', '.join(sorted(c['username'] for c in cuentas))}")

    # Diagnóstico de la tabla antes de decidir nada. Necesita credenciales; si
    # no las hay, se dice y se sigue —el resumen de arriba ya es útil por sí solo.
    lista = None
    try:
        lista = informar_tabla(revisar_tabla())
    except Exception as exc:  # noqa: BLE001
        print(f"\n  Sin conexión a la base ({type(exc).__name__}): "
              "no se pudo revisar `profiles`.")
        print("  Define SUPABASE_URL y SUPABASE_KEY (o DATABASE_URL) en .env.")

    if not args.aplicar:
        print(f"\nSimulación. Nada se escribió en `{TABLA}`.")
        if lista:
            print("Todo listo: vuelve a correrlo con --aplicar.")
        else:
            print("Resuelve lo de arriba y vuelve a correrlo con --aplicar.")
        return 0

    if lista is False:
        print("\nNo se escribió nada: falta preparar la tabla (ver arriba).")
        return 1

    print(f"\nEscribiendo en `{TABLA}` (upsert por `{CLAVE_UPSERT}`)...")
    try:
        escritas = aplicar(cuentas)
    except Exception as exc:  # noqa: BLE001
        print(f"\nFalló: {type(exc).__name__}: {exc}")
        print("Revisa SUPABASE_URL/SUPABASE_KEY (o DATABASE_URL) y que `profiles` "
              "tenga las columnas username, password, role, label, email, "
              "staff_name, dept, seller.")
        return 1

    print(f"  {escritas} perfil(es) escrito(s).")
    print("\nListo. Ya se puede entrar con las credenciales de siempre.")
    print("Quita DEV_LOGIN_USERS del entorno para no dejar dos caminos de acceso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
