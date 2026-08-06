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

# Cuentas que existen en `USER_DB` pero **no** reciben credencial propia aquí.
# No es una lista de bajas: una baja se quita de `USER_DB` y desaparece sola.
# Es la lista de cuentas que son un duplicado de otra persona que ya tiene
# acceso, y que por eso no deben poder autenticarse por separado.
SIN_CREDENCIAL: Dict[str, str] = {
    # Antonia Pineda Lopez es una sola persona con dos tablas: `ANTONIA_VENTAS`
    # (cotizaciones) y su tracker `ANTONIA PINEDA LOPEZ`. El rol TONITA ya
    # entrega las dos vistas con un solo login —el módulo `MY_TRACKER` de
    # `api/main.py` apunta a su tracker—, así que una segunda credencial no
    # abriría nada nuevo: sólo sería otra contraseña que mantener.
    "ANTONIA_PINEDA": "duplicado de ANTONIA_VENTAS (rol TONITA ya trae su tracker)",
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


def filtrar_sin_credencial(cuentas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Aparta las cuentas de `SIN_CREDENCIAL` y explica por qué se queda cada una.

    Va aparte de `leer_user_db()` a propósito: esa función describe lo que dice
    `CODIGO.js` y no debe opinar. La decisión de a quién se le da credencial en
    la plataforma nueva es de aquí, y así se puede leer y probar sola.
    """
    conservadas = []
    for cuenta in cuentas:
        motivo = SIN_CREDENCIAL.get(cuenta["username"])
        if motivo:
            print(f"  - {cuenta['username']}: sin credencial propia — {motivo}")
            continue
        conservadas.append(cuenta)
    return conservadas


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

    print(f"  {len(cuentas)} cuenta(s) con credencial en USER_DB")

    # La comparación va antes del filtro: describe `CODIGO.js` frente a la
    # semilla, y el filtro es una decisión posterior que no debe ocultarla.
    comparar_con_el_organigrama(cuentas)

    cuentas = filtrar_sin_credencial(cuentas)
    if not cuentas:
        print("No queda ninguna cuenta que migrar.")
        return 1

    print(f"  {len(cuentas)} cuenta(s) a escribir")
    por_rol: Dict[str, int] = {}
    for c in cuentas:
        por_rol[c["role"]] = por_rol.get(c["role"], 0) + 1
    for rol, n in sorted(por_rol.items()):
        print(f"    {rol}: {n}")
    print(f"  vendedores (seller=true): {sum(1 for c in cuentas if c['seller'])}")

    # Deliberadamente NO se imprime ninguna contraseña, ni truncada: este script
    # se corre en una terminal cuyo historial suele quedar guardado.
    print(f"\n  usuarios: {', '.join(sorted(c['username'] for c in cuentas))}")

    if not args.aplicar:
        print(f"\nSimulación. Nada se escribió en `{TABLA}`.")
        print("Vuelve a correrlo con --aplicar cuando quieras aplicarlo.")
        return 0

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
