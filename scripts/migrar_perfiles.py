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

Lee por omisión el `CODIGO.js` de Apps Script (`../REAL-HOLTMONT/CODIGO.js`),
que tiene las 41 cuentas. **No uses el `CODIGO.js` de este repo**: es una copia
vieja con 12, y migrar con ella dejaría a 30 personas sin poder entrar. Si
faltan cuentas respecto de la semilla del organigrama, el script se niega a
escribir salvo que insistas con `--parcial`.

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
from typing import Any, Dict, List, Optional

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


def comparar_con_el_organigrama(cuentas: List[Dict[str, Any]]) -> List[str]:
    """
    Avisa si `USER_DB` y la semilla del repo no coinciden.

    Devuelve las cuentas que la semilla conoce y el `CODIGO.js` leído no trae:
    son las personas que se quedarían **sin poder entrar** si se aplicara este
    archivo. `main()` usa esa lista para negarse a hacer una migración parcial.

    Una diferencia aquí suele significar una de dos cosas: que `CODIGO.js`
    cambió y `api/services/organigrama.py` se quedó atrás, o —lo más probable—
    que se está leyendo el `CODIGO.js` de este repo, que es una copia vieja de
    12 cuentas, en vez del de Apps Script, que tiene las 41.
    """
    from api.services.organigrama import PERFILES

    en_codigo = {c["username"] for c in cuentas}
    en_semilla = set(PERFILES)

    solo_codigo = sorted(en_codigo - en_semilla)
    faltantes = sorted(en_semilla - en_codigo)
    if solo_codigo:
        print(f"  ! En CODIGO.js y no en la semilla del repo: {solo_codigo}")
    if faltantes:
        print(f"  ! En la semilla del repo y no en CODIGO.js: {faltantes}")

    distintos = [
        c["username"] for c in cuentas
        if c["username"] in PERFILES
        and c["role"] != PERFILES[c["username"]].get("role")
    ]
    if distintos:
        print(f"  ! Rol distinto entre CODIGO.js y la semilla: {distintos}")

    return faltantes


SQL_COLUMNA_CONTRASENA = """\
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS password TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS profiles_username_key
    ON public.profiles (username);"""


def columnas_reales() -> Optional[set]:
    """
    Columnas que `profiles` tiene de verdad, o None si no se pudo averiguar.

    Hace falta porque el esquema desplegado y el `docs/DDL_PENDIENTE.sql` de este
    repo no coinciden: la tabla real tiene `id` y `person_id`, no tiene
    `staff_name`, y —lo importante— no tiene `password`. Mandar una columna que
    no existe hace que PostgREST conteste 400 sin decir cuál, así que se
    comprueba antes y se avisa con el nombre.

    Se lee del OpenAPI que PostgREST publica en la raíz, que es la única forma de
    ver el esquema cuando la tabla está vacía: sin filas, un SELECT no revela
    ninguna columna.
    """
    import json
    import urllib.request

    base = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    clave = os.environ.get("SUPABASE_KEY", "").strip()
    if not base or not clave:
        return None  # con DATABASE_URL directo esto no aplica

    try:
        pedido = urllib.request.Request(
            f"{base}/rest/v1/",
            headers={"apikey": clave, "Authorization": f"Bearer {clave}",
                     "Accept": "application/openapi+json"},
        )
        with urllib.request.urlopen(pedido, timeout=30) as resp:
            spec = json.load(resp)
    except Exception as exc:  # noqa: BLE001
        print(f"  ! No se pudo leer el esquema de `{TABLA}`: {exc}")
        return None

    definicion = spec.get("definitions", {}).get(TABLA)
    if not definicion:
        return None
    return set(definicion.get("properties", {}))


def revisar_esquema(cuentas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Comprueba que se pueda escribir, y recorta los campos que la tabla no tiene.

    Aborta si falta la columna de contraseña: sin ella el upsert "funciona" pero
    deja a `profiles` sin credenciales, y `/api/login` sigue sin dejar entrar a
    nadie. Es justo el fallo silencioso que hay que evitar.
    """
    columnas = columnas_reales()
    if columnas is None:
        return cuentas  # no se pudo introspeccionar: se intenta tal cual

    from api.services.organigrama import columnas_de_credencial

    if not (columnas & set(columnas_de_credencial())):
        raise SystemExit(
            f"\n`{TABLA}` no tiene columna de contraseña.\n"
            f"  columnas actuales: {', '.join(sorted(columnas))}\n\n"
            "Sin ella no se pueden guardar las credenciales y el login seguirá\n"
            "rechazando a todo el mundo. Córrelo en el SQL Editor de Supabase y\n"
            "vuelve a lanzar este script:\n\n"
            f"{SQL_COLUMNA_CONTRASENA}\n"
        )

    sobran = sorted(set(cuentas[0]) - columnas)
    if not sobran:
        return cuentas

    # `staff_name` es el caso real: no existe en la tabla desplegada. No es
    # grave, `organigrama` lo resuelve contra la semilla cuando la base no lo
    # trae; pero mandarlo rompe la escritura entera.
    print(f"  ! `{TABLA}` no tiene estas columnas, se omiten: {sobran}")
    return [{k: v for k, v in c.items() if k in columnas} for c in cuentas]


def aplicar(cuentas: List[Dict[str, Any]]) -> int:
    from backend.core.engine import construir_engine

    engine = construir_engine()
    print(f"  motor: {engine.nombre}")

    cuentas = revisar_esquema(cuentas)

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
    parser.add_argument("--parcial", action="store_true",
                        help="Permite aplicar aunque falten cuentas de la semilla. "
                             "Sin esto, una migración incompleta se rechaza.")
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

    faltantes = comparar_con_el_organigrama(cuentas)

    # Deliberadamente NO se imprime ninguna contraseña, ni truncada: este script
    # se corre en una terminal cuyo historial suele quedar guardado.
    print(f"\n  usuarios: {', '.join(sorted(c['username'] for c in cuentas))}")

    if not args.aplicar:
        print(f"\nSimulación. Nada se escribió en `{TABLA}`.")
        if faltantes:
            print(f"OJO: así como está, {len(faltantes)} persona(s) no podrían entrar.")
        print("Vuelve a correrlo con --aplicar cuando quieras aplicarlo.")
        return 0

    # Una migración a medias es peor que ninguna: `/api/login` sólo sabe decir
    # "usuario o contraseña incorrectos", así que quien no quede en `profiles`
    # se queda fuera sin ninguna pista de por qué. Se prefiere no escribir.
    if faltantes and not args.parcial:
        print(f"\nCancelado: faltan {len(faltantes)} cuenta(s) que la semilla sí conoce.")
        print("Esas personas no podrían entrar si se aplicara este archivo.")
        if args.codigo.resolve() != CODIGO_POR_DEFECTO.resolve():
            print(f"\nCasi seguro es el archivo: estás leyendo {args.codigo}.")
            print(f"El bueno es el de Apps Script: {CODIGO_POR_DEFECTO}")
            print("(el CODIGO.js de este repo es una copia vieja, con 12 cuentas)")
        print("\nSi de verdad quieres migrar sólo estas, repite con --parcial.")
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
