#!/usr/bin/env python3
"""
Escribe las escenas de referencia que valida el repositorio del editor 3D.

Las mismas descripciones que se prueban en
`tests/test_arquitectura_pascal_contrato.py` se exportan a JSON para que
`holtmont-3d-editor` las valide contra su esquema Zod real y las dibuje en su
prueba de humo con navegador. Que las dos orillas comprueben el mismo JSON es lo
que impide que el contrato se rompa por un lado sin que el otro se entere.

    python scripts/generar_escenas_pascal.py ../holtmont-3d-editor/apps/editor/public/holtmont-fixtures
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.paperclip_agents import (  # noqa: E402
    ArchitectExtraction,
    DoorOpening,
    FurnitureItem,
    RoofConfig,
    StaircaseConfig,
    WallSegment,
    WindowOpening,
    _build_pascal_scene,
)
from api.services.plano import generar_plano  # noqa: E402


def _cuarto(ancho: float, largo: float, nivel: int = 0):
    mx, my = ancho / 2, largo / 2
    esquinas = [(-mx, -my), (mx, -my), (mx, my), (-mx, my)]
    return [WallSegment(start=list(esquinas[i]), end=list(esquinas[(i + 1) % 4]), level=nivel)
            for i in range(4)]


def _desde_texto(descripcion: str) -> dict:
    resultado = generar_plano(descripcion)
    if not resultado.get("success"):
        raise SystemExit(f"'{descripcion}': {resultado.get('message')}")
    return resultado["escena_3d"]


def _casa_de_dos_pisos() -> dict:
    extraccion = ArchitectExtraction(
        walls=_cuarto(8, 6, nivel=0) + _cuarto(8, 6, nivel=1),
        ceiling_height=2.7,
        num_levels=2,
        doors=[DoorOpening(wall_index=0, position_along_wall=0.25)],
        windows=[
            WindowOpening(wall_index=0, position_along_wall=0.6),
            WindowOpening(wall_index=2, position_along_wall=0.5),
            WindowOpening(wall_index=4, position_along_wall=0.5),
            WindowOpening(wall_index=6, position_along_wall=0.5),
        ],
        staircases=[StaircaseConfig(position=[2.5, 0], from_level=0, to_level=1)],
        roof=RoofConfig(roof_type="gabled", pitch=30.0),
    )
    return _de_extraccion(extraccion)


def _cuarto_amueblado() -> dict:
    extraccion = ArchitectExtraction(
        walls=_cuarto(5, 4),
        doors=[DoorOpening(wall_index=0, position_along_wall=0.5)],
        windows=[WindowOpening(wall_index=1, position_along_wall=0.5)],
        furniture=[
            FurnitureItem(name="cama", position=[-1.0, 1.0], rotation=90),
            FurnitureItem(name="escritorio", position=[1.5, -1.0]),
            FurnitureItem(name="unicornio", position=[0, 0]),  # no está en el catálogo
        ],
    )
    return _de_extraccion(extraccion)


def _de_extraccion(extraccion: ArchitectExtraction) -> dict:
    return _build_pascal_scene(
        extraccion.walls, extraccion.ceiling_height, extraccion.doors,
        extraccion.windows, extraccion.staircases, extraccion.roof,
        extraccion.furniture, extraccion.num_levels)


ESCENAS = {
    "cuarto-5x4-con-puerta": lambda: _desde_texto("Cuarto de 5 x 4 m con una puerta"),
    "bodega-12x8-dos-puertas-cuatro-ventanas": lambda: _desde_texto(
        "Bodega de 12 x 8 metros con dos puertas y cuatro ventanas"),
    "oficina-sin-vanos": lambda: _desde_texto(
        "Oficina de 3,5 x 2,5 m, altura 3 m, sin puertas ni ventanas"),
    "casa-dos-pisos-ventanas-frente-y-atras": _casa_de_dos_pisos,
    "cuarto-amueblado": _cuarto_amueblado,
}


def main() -> int:
    destino = sys.argv[1] if len(sys.argv) > 1 else "escenas_pascal"
    os.makedirs(destino, exist_ok=True)
    for nombre, construir in ESCENAS.items():
        ruta = os.path.join(destino, f"{nombre}.json")
        with open(ruta, "w", encoding="utf-8") as archivo:
            json.dump(construir(), archivo, indent=2, ensure_ascii=False)
            archivo.write("\n")
        print(f"escrito {ruta}")
    indice = os.path.join(destino, "index.json")
    with open(indice, "w", encoding="utf-8") as archivo:
        json.dump(sorted(ESCENAS), archivo, indent=2)
        archivo.write("\n")
    print(f"escrito {indice}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
