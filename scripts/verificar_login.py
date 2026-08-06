#!/usr/bin/env python3
"""
Comprueba que `profiles` quedó migrada y que la gente puede entrar. **Solo lee.**

Es la contraparte de `scripts/migrar_perfiles.py`: aquel escribe, este verifica.
Existe porque «la base ya está migrada» no es algo que se pueda afirmar mirando
el repo —`profiles` vive en Supabase y el repo no la ve— y porque una migración
a medias no se nota hasta que alguien no puede entrar un lunes por la mañana.

Comprueba seis cosas, en orden de gravedad:

  1. **Nadie falta**: toda cuenta con credencial en `USER_DB` está en `profiles`.
     Si falta una, esa persona no puede entrar.
  2. **Nadie sobra**: ninguna fila de `profiles` corresponde a una cuenta que ya
     no está en `USER_DB`. Una baja que sobrevive a la migración conserva acceso
     al sistema nuevo — que es justo lo que pasó con `CESAR_GOMEZ` (baja del
     organigrama en 2026-06 que siguió en `USER_DB` hasta 2026-08).
  3. **Todas tienen contraseña**: una fila sin columna de credencial es una
     cuenta que existe y no puede autenticarse. `validar_credenciales` la
     rechaza, y desde el navegador se ve igual que una contraseña equivocada.
  4. **El perfil coincide**: `role`, `dept` y `seller` iguales a `USER_DB`. Un
     `role` distinto no impide entrar pero da los permisos equivocados, y un
     `seller` perdido deja a un vendedor sin su módulo `MY_SALES`.
  5. **Los roles son conocidos**: cada `role` es uno de los que `/api/config`
     sabe resolver. Un rol con una errata entra y no ve nada.
  6. **La autenticación real funciona**: se llama a
     `organigrama.validar_credenciales` con la credencial de cada cuenta y se
     comprueba además que una contraseña equivocada se rechaza. Es el único
     control que prueba el camino completo —el mismo que usa `/api/login`— en
     vez de inspeccionar filas.

**No imprime ninguna contraseña, ni truncada, ni en los mensajes de fallo.** Las
lee de `CODIGO.js` para poder probar la autenticación y no las saca de memoria.

Uso:
    python scripts/verificar_login.py                    # verifica todo
    python scripts/verificar_login.py --sin-autenticacion   # omite el control 6
    python scripts/verificar_login.py --codigo /ruta/a/CODIGO.js

Requiere SUPABASE_URL y SUPABASE_KEY, o DATABASE_URL (lee `.env` de la raíz).
Sale con 0 si todo pasa y con 1 si hay cualquier falla.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
from typing import Any, Dict, List, Optional, Sequence

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from api.services.organigrama import clave_usuario, columnas_de_credencial  # noqa: E402
from scripts.migrar_perfiles import (  # noqa: E402
    CODIGO_POR_DEFECTO,
    TABLA,
    cargar_env,
    filtrar_sin_credencial,
    leer_user_db,
)

# Los roles que `/api/config` sabe resolver. Un valor fuera de esta lista
# autentica pero cae a la rama por omisión y la persona entra sin sus módulos.
ROLES_CONOCIDOS = frozenset({
    "ADMIN",
    "ADMIN_CONTROL",
    "PPC_ADMIN",
    "STAFF_USER",
    "TONITA",
    "WORKORDER_USER",
})

# Contraseña deliberadamente incorrecta para el control de rechazo. No es la de
# nadie: lleva un sufijo que ninguna credencial real puede tener.
CLAVE_INCORRECTA = "no-es-la-contrasena-::control-de-rechazo"


def _contrasena_de(fila: Dict[str, Any]) -> Optional[str]:
    """La credencial guardada en una fila, sea cual sea el nombre de la columna."""
    for columna in columnas_de_credencial():
        valor = fila.get(columna)
        if valor is not None and str(valor) != "":
            return str(valor)
    return None


def comprobar_filas(cuentas: Sequence[Dict[str, Any]],
                    filas: Sequence[Dict[str, Any]]) -> List[str]:
    """
    Contrasta `USER_DB` contra las filas de `profiles`. Devuelve las fallas.

    Es una función pura sobre las dos listas —sin red ni entorno— para que la
    suite pueda ejercitar los cinco primeros controles sin tocar la base, que es
    lo que exige R7. El control 6 (autenticación real) no cabe aquí porque su
    valor está justamente en recorrer el camino de verdad.
    """
    fallas: List[str] = []

    esperadas = {clave_usuario(c["username"]): c for c in cuentas}
    presentes: Dict[str, Dict[str, Any]] = {}
    for fila in filas:
        clave = clave_usuario(fila.get("username"))
        if clave:
            presentes[clave] = fila

    # 1. Nadie falta.
    faltantes = sorted(set(esperadas) - set(presentes))
    if faltantes:
        fallas.append(
            f"{len(faltantes)} cuenta(s) de USER_DB no están en `{TABLA}` y no "
            f"podrán entrar: {', '.join(faltantes)}"
        )

    # 2. Nadie sobra. Se avisa aparte de las bajas porque el riesgo es distinto:
    #    no es que alguien no pueda entrar, es que alguien que no debería, sí.
    sobrantes = sorted(set(presentes) - set(esperadas))
    if sobrantes:
        fallas.append(
            f"{len(sobrantes)} cuenta(s) están en `{TABLA}` pero ya no en USER_DB; "
            f"conservan acceso al sistema nuevo: {', '.join(sobrantes)}"
        )

    for clave in sorted(set(esperadas) & set(presentes)):
        esperada, fila = esperadas[clave], presentes[clave]

        # 3. Todas tienen contraseña.
        if _contrasena_de(fila) is None:
            fallas.append(f"{clave}: sin contraseña en `{TABLA}`, no puede autenticarse")

        # 4. El perfil coincide.
        for campo in ("role", "dept"):
            almacenado = str(fila.get(campo) or "").strip()
            del_codigo = str(esperada.get(campo) or "").strip()
            if almacenado != del_codigo:
                fallas.append(
                    f"{clave}: `{campo}` es {almacenado!r} en `{TABLA}` y "
                    f"{del_codigo!r} en USER_DB"
                )

        if bool(fila.get("seller")) != bool(esperada.get("seller")):
            fallas.append(
                f"{clave}: `seller` es {bool(fila.get('seller'))} en `{TABLA}` y "
                f"{bool(esperada.get('seller'))} en USER_DB"
            )

        # 5. Los roles son conocidos.
        rol = str(fila.get("role") or "").strip()
        if rol and rol not in ROLES_CONOCIDOS:
            fallas.append(
                f"{clave}: rol {rol!r} no lo resuelve /api/config; entraría sin módulos"
            )

    return fallas


def comprobar_autenticacion(cuentas: Sequence[Dict[str, Any]]) -> List[str]:
    """
    Recorre el camino real de `/api/login` para cada cuenta. Devuelve las fallas.

    Se llama a `validar_credenciales`, que es exactamente lo que invoca el
    endpoint, en vez de reimplementar la comparación aquí: una verificación que
    usa su propia copia de la lógica puede pasar mientras el login falla.
    """
    from api.services import organigrama

    fallas: List[str] = []
    for cuenta in cuentas:
        usuario = cuenta["username"]

        if organigrama.validar_credenciales(usuario, cuenta["password"]) is None:
            fallas.append(f"{usuario}: la credencial de USER_DB no autentica contra `{TABLA}`")
            continue

        # Que acepte la buena no basta: si la comparación estuviera rota en el
        # sentido contrario, todo el mundo entraría con cualquier cosa.
        if organigrama.validar_credenciales(usuario, CLAVE_INCORRECTA) is not None:
            fallas.append(f"{usuario}: acepta una contraseña incorrecta")

    return fallas


def leer_profiles() -> List[Dict[str, Any]]:
    """Lee `profiles` con el motor configurado. Solo lectura."""
    from backend.core.engine import construir_engine

    engine = construir_engine()
    print(f"  motor: {engine.nombre}")
    return list(engine.select(TABLA) or [])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--codigo", type=pathlib.Path, default=CODIGO_POR_DEFECTO,
                        help="Ruta al CODIGO.js de Apps Script")
    parser.add_argument("--sin-autenticacion", action="store_true",
                        help="Omite el control 6 (no prueba el login real)")
    args = parser.parse_args()

    cargar_env()

    print(f"Leyendo {args.codigo}")
    cuentas = filtrar_sin_credencial(leer_user_db(args.codigo))
    print(f"  {len(cuentas)} cuenta(s) con credencial esperadas en `{TABLA}`")

    try:
        filas = leer_profiles()
    except Exception as exc:  # noqa: BLE001 - cualquier fallo aquí es "no se pudo verificar"
        print(f"\nNo se pudo leer `{TABLA}`: {exc}")
        print("Revisa SUPABASE_URL/SUPABASE_KEY o DATABASE_URL.")
        return 1

    print(f"  {len(filas)} fila(s) en `{TABLA}`")
    if not filas:
        print(
            f"\n`{TABLA}` está vacía: nadie puede entrar a la plataforma.\n"
            "Corre `python scripts/migrar_perfiles.py --aplicar` para poblarla."
        )
        return 1

    fallas = comprobar_filas(cuentas, filas)

    if args.sin_autenticacion:
        print("  (control de autenticación omitido por --sin-autenticacion)")
    else:
        print("  probando la autenticación real de cada cuenta...")
        fallas.extend(comprobar_autenticacion(cuentas))

    print()
    if fallas:
        print(f"{len(fallas)} FALLA(S):")
        for falla in fallas:
            print(f"  ✗ {falla}")
        return 1

    controles = 5 if args.sin_autenticacion else 6
    print(f"TODO BIEN — {controles}/{controles} controles.")
    print(f"`{TABLA}` tiene las {len(cuentas)} cuentas de USER_DB, sin sobrantes,")
    if not args.sin_autenticacion:
        print(f"y las {len(cuentas)} autentican por el mismo camino que /api/login.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
