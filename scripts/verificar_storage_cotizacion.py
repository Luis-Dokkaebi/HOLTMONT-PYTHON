#!/usr/bin/env python3
"""
Comprueba, contra el Storage real, que la cotización en PDF se pueda archivar.

Gemelo de `scripts/verificar_base_quotes.py`: vive fuera de la suite porque
toca infraestructura real, y por eso no corre en CI (R7 — ninguna prueba toca
producción). Aquí la comprobación se pide a propósito.

Hace el viaje completo con un PDF de prueba —emitir, subir, leer de vuelta por
su URL pública y borrar— porque las tres formas de fallar del archivado viven
en la configuración del despliegue y desde la pantalla se ven igual (un aviso
al guardar la orden):

  1. `SUPABASE_URL` / `SUPABASE_KEY` sin definir: no se sube nada.
  2. El bucket no existe, o la política no permite escribir.
  3. El bucket existe pero es **privado**: la subida funciona, la URL pública
     que se guarda en la columna CARPETA no resuelve, y quien abra el adjunto
     recibe `{"statusCode":"404","error":"Bucket not found"}`.

Mirar si la variable está definida no distingue ninguna de las tres.

Uso:
    SUPABASE_URL=... SUPABASE_KEY=... python scripts/verificar_storage_cotizacion.py

    # o con las credenciales en el `.env` del proyecto
    python scripts/verificar_storage_cotizacion.py

Sale con 0 si el archivado funciona y con 1 si no. El objeto de prueba se sube
bajo `AÑO/MES/DIAGNOSTICO/` y se borra al final; si el borrado falla, la ruta
se imprime para borrarlo a mano.

Ninguna credencial se imprime.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VERDE = "\033[92m"
ROJO = "\033[91m"
GRIS = "\033[90m"
FIN = "\033[0m"


def _cargar_env() -> None:
    """Lee el `.env` del proyecto si existe, sin depender de python-dotenv."""
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.exists(ruta):
        return
    with open(ruta, encoding="utf-8") as archivo:
        for linea in archivo:
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, _, valor = linea.partition("=")
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def main() -> int:
    _cargar_env()

    from api.services import cotizacion_pdf

    print("Comprobando el archivado de la cotización en PDF...\n")
    reporte = cotizacion_pdf.diagnostico_storage()

    print(f"Bucket: {reporte['bucket']}\n")
    for paso in reporte["pasos"]:
        marca = f"{VERDE}OK  {FIN}" if paso["ok"] else f"{ROJO}FALLA{FIN}"
        print(f"  [{marca}] {paso['paso']}: {paso['detalle']}")
        for clave in ("ruta", "url", "bytes", "codigo"):
            if paso.get(clave) not in (None, "", 0):
                print(f"           {GRIS}{clave}: {paso[clave]}{FIN}")

    print()
    if reporte["ok"]:
        print(f"{VERDE}{reporte['detalle']}{FIN}")
        return 0
    print(f"{ROJO}{reporte['detalle']}{FIN}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
