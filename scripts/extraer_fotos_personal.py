# -*- coding: utf-8 -*-
"""
Extrae las fotos del personal del PDF de RH a `api/static/fotos/`.

    python scripts/extraer_fotos_personal.py FOTOS_CON_PUESTO_DE_TRABAJO.pdf

El PDF **no vive en el repositorio** (es material de RH con datos de personas):
lo entrega el dueño y este script deja en el árbol solo los JPEG recortados que
la vista necesita. Se conserva porque las fotos son un dato derivado y hay que
poder rehacerlas —o rehacer una sola— sin adivinar de dónde salió cada archivo.

Tres cosas que este script sabe y el PDF no dice solo:

1. **El emparejamiento foto↔nombre.** Cada página lleva de dos a cuatro
   personas. El PDF numera sus imágenes (`/X4`, `/X7`, ...) en el mismo orden en
   que aparecen los nombres en el texto de la página, y ese es el orden de
   `MAPA`. Se verificó foto por foto contra el nombre antes de fijarlo: ponerle
   a alguien la cara de otro es el error caro de esta tarea.
2. **La rotación.** `/X56` (Dania) está guardada de costado; la página la
   endereza con la matriz de transformación, así que el archivo crudo sale
   acostado. `ROTACIONES` lo deja derecho.
3. **El recorte.** Tres fotos son de cuerpo entero y en un avatar circular de
   72 px la cara quedaba diminuta. `RECORTES` las lleva a cabeza y hombros, en
   coordenadas de la imagen **ya rotada**.

Al terminar imprime el catálogo en el formato de `organigrama.FICHAS` para
poder contrastarlo; el catálogo en sí se edita a mano, no lo genera esto.
"""

from __future__ import annotations

import io
import os
import sys
from typing import Dict, List, Tuple

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DESTINO = os.path.join(RAIZ, "api", "static", "fotos")

# (página, XObject, archivo destino sin extensión), en el orden del documento.
MAPA: List[Tuple[int, str, str]] = [
    (1, "X4", "dimas-eliel-ramos-garcia"),
    (1, "X7", "laura-edith-huerta-rocha"),
    (1, "X8", "francisco-sanchez-serna"),
    (1, "X9", "liliana-aylin-martinez-ibarra"),
    (2, "X12", "sonia-garcia-perez"),
    (2, "X13", "vanessa-de-lara"),
    (2, "X14", "judith-echavarria"),
    (3, "X17", "angel-salinas"),
    (3, "X18", "edgar-urimar-lopez-maldonado"),
    (4, "X21", "teresa-garza"),
    (4, "X22", "geraldine-martinez-hernandez"),
    (5, "X25", "eduardo-benitez"),
    (6, "X28", "carlos-mendez"),
    (6, "X29", "rolando-moreno"),
    (6, "X30", "emiliano-arredondo-gomez"),
    (7, "X33", "jehu-martinez"),
    (7, "X34", "miguel-gallardo"),
    (7, "X35", "sebastian-padilla"),
    (8, "X38", "eduardo-teran"),
    (8, "X39", "antonia-pineda-lopez"),
    (9, "X42", "eduardo-manzanares"),
    (9, "X43", "ramiro-rodriguez"),
    (9, "X44", "rubi-moreno-rodriguez"),
    (10, "X47", "jaime-olivo"),
    (10, "X48", "ricardo-mendo"),
    (10, "X49", "alfonso-correa"),
    (10, "X50", "cesar-eduardo-garcia-avalos"),
    (11, "X53", "juana-maria-rodriguez-juarez"),
    (11, "X54", "rocio-abigail-castro-covarrubias"),
    (11, "X55", "zaira-yazmin-aguilar-aguilon"),
    (11, "X56", "dania-lizbeth-gonzalez-lores"),
]

# Grados en sentido antihorario que hay que girar el archivo crudo.
ROTACIONES: Dict[str, int] = {"dania-lizbeth-gonzalez-lores": 90}

# Recorte a cabeza y hombros, sobre la imagen ya rotada: (izq, arriba, der, abajo).
RECORTES: Dict[str, Tuple[int, int, int, int]] = {
    "rolando-moreno": (60, 20, 190, 190),
    "zaira-yazmin-aguilar-aguilon": (85, 35, 225, 230),
    "dania-lizbeth-gonzalez-lores": (170, 140, 400, 450),
}

LADO_MAXIMO = 400  # El avatar se pinta a 72 px; más que esto es peso muerto.


def main(pdf: str) -> int:
    import pypdf
    from PIL import Image

    lector = pypdf.PdfReader(pdf)
    crudas = {}
    for numero, pagina in enumerate(lector.pages, start=1):
        for imagen in pagina.images:
            crudas[(numero, imagen.name.rsplit(".", 1)[0])] = imagen.data

    os.makedirs(DESTINO, exist_ok=True)
    for pagina, xobject, archivo in MAPA:
        datos = crudas.get((pagina, xobject))
        if datos is None:
            print(f"FALTA: página {pagina} no trae {xobject}", file=sys.stderr)
            return 1
        imagen = Image.open(io.BytesIO(datos)).convert("RGB")
        if archivo in ROTACIONES:
            imagen = imagen.rotate(ROTACIONES[archivo], expand=True)
        if archivo in RECORTES:
            imagen = imagen.crop(RECORTES[archivo])
        imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.LANCZOS)
        ruta = os.path.join(DESTINO, f"{archivo}.jpg")
        imagen.save(ruta, "JPEG", quality=85, optimize=True)
        print(f'    "{archivo}": {imagen.size}  ->  {ruta}')
    print(f"\n{len(MAPA)} fotos escritas en {DESTINO}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
