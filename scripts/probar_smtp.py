#!/usr/bin/env python3
"""
Comprueba que el canal de correo funciona **antes** de esperar al cron de las
07:00. Con `--a` manda un correo de prueba de verdad.

Existe porque hasta ahora "el SMTP está bien configurado" era una afirmación que
nadie podía verificar sin provocar un reporte: `api/services/correo.py` no lanza
nunca —un fallo de correo no puede tumbar al agente que lo genera—, así que un
host mal escrito o una contraseña que no es la de aplicación se traducían en un
silencio, no en un error visible.

Uso:

    python scripts/probar_smtp.py                      # conecta, cifra y autentica
    python scripts/probar_smtp.py --a dueno@holtmont.com   # además manda un correo

Lee la configuración del entorno (`.env` no se carga solo: exporta las variables
o usa el panel del despliegue):

    SMTP_USER=cuenta@gmail.com
    SMTP_PASSWORD=<contraseña de aplicación, 16 caracteres>
    SMTP_HOST=          # opcional con Gmail: se deduce smtp.gmail.com
    SMTP_PORT=587       # 465 conmuta a SSL directo
    SMTP_FROM=          # opcional; si se deja vacío se usa SMTP_USER

Sale con 0 si el canal responde y 1 si no, para poder encadenarlo.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import correo  # noqa: E402

# Qué significa que un paso no se haya completado. El diagnóstico útil no es el
# error de Google, es saber en qué punto se cortó.
DIAGNOSTICO = {
    "conexion": ("No se pudo abrir la conexión. Revisa SMTP_HOST y SMTP_PORT, y "
                 "que la red del despliegue deje salir por ese puerto: muchos "
                 "proveedores bloquean el 587 y el 465 por omisión."),
    "tls": ("La conexión se abrió pero no se pudo cifrar. Si el servidor no "
            "ofrece STARTTLS en el 587, prueba SMTP_PORT=465."),
    "autenticacion": ("El servidor rechazó las credenciales. Con Gmail casi "
                      "siempre es esto: hace falta una contraseña de "
                      "APLICACIÓN de 16 caracteres (Cuenta de Google → "
                      "Seguridad → Verificación en dos pasos → Contraseñas de "
                      "aplicación). La contraseña normal de la cuenta lleva sin "
                      "funcionar desde mayo de 2022."),
    "envio": ("Autenticó pero rechazó el mensaje. Con Gmail suele ser un "
              "SMTP_FROM que no es la cuenta autenticada ni un alias "
              "verificado de esa cuenta."),
}

PASOS = ["conexion", "tls", "autenticacion", "envio"]


def imprimir(informe: dict, destino: str | None) -> None:
    print("== Canal de correo ==")
    print(f"  host       : {informe['host'] or '(sin configurar)'}")
    print(f"  puerto     : {informe['puerto']}")
    print(f"  usuario    : {informe['usuario'] or '(vacío)'}")
    print(f"  remitente  : {informe['remitente'] or '(vacío)'}")
    if informe["host"] == correo.HOST_GMAIL and not os.environ.get(correo.SMTP_HOST_ENV, "").strip():
        print(f"  ({correo.SMTP_HOST_ENV} está vacío: se dedujo de la cuenta de Gmail)")
    print()

    if not informe["configurado"]:
        # Faltan variables de entorno: enumerar pasos que ni se intentaron
        # sugeriría un fallo de red que no existe.
        print("RESULTADO: el canal NO está configurado.")
        print(f"  {informe['message']}")
        return

    esperados = PASOS if destino else PASOS[:-1]
    for paso in esperados:
        if paso in informe["pasos"]:
            print(f"  [ok]    {paso}")
        else:
            print(f"  [FALLA] {paso}")
            print(f"          {DIAGNOSTICO[paso]}")
            break

    print()
    if informe["success"]:
        print("RESULTADO: el canal funciona.", informe["message"])
    else:
        print("RESULTADO: el canal NO funciona.")
        if informe["message"]:
            print(f"  Error del servidor: {informe['message']}")


def main(argv: Optional[List[str]] = None) -> int:
    analizador = argparse.ArgumentParser(
        description="Prueba el canal SMTP de los reportes de los agentes.")
    analizador.add_argument(
        "--a", dest="destino", default=None,
        help="Dirección a la que mandar un correo de prueba. Sin esto solo se "
             "conecta y autentica, sin enviar nada.")
    argumentos = analizador.parse_args(argv)

    informe = correo.probar_conexion(destino=argumentos.destino)
    imprimir(informe, argumentos.destino)
    return 0 if informe["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
