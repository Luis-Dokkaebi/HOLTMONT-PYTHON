from mcp.server.fastmcp import FastMCP
import json
from api.paperclip_agents import run_paperclip_agency

# Inicializar FastMCP
mcp = FastMCP("PascalEditorMCP")

@mcp.tool()
def generar_habitacion_pascal(ancho: float, alto: float) -> str:
    """
    Genera un JSON básico de una habitación para Pascal Editor dado un ancho y alto en metros.

    Args:
        ancho: El ancho de la habitación en metros (X).
        alto: El alto de la habitación en metros (Y).

    Returns:
        str: Un JSON string representando la habitación en formato de Pascal Editor.
    """
    try:
        mitad_ancho = ancho / 2
        mitad_alto = alto / 2

        room = {
            "state": {
                "nodes": [
                    {"id": "n1", "type": "wall", "position": {"x": -mitad_ancho, "y": -mitad_alto, "z": 0}},
                    {"id": "n2", "type": "wall", "position": {"x": mitad_ancho, "y": -mitad_alto, "z": 0}},
                    {"id": "n3", "type": "wall", "position": {"x": mitad_ancho, "y": mitad_alto, "z": 0}},
                    {"id": "n4", "type": "wall", "position": {"x": -mitad_ancho, "y": mitad_alto, "z": 0}}
                ]
            }
        }
        return json.dumps(room)
    except Exception as e:
        return json.dumps({"error": str(e)})

@mcp.tool()
def ejecutar_agencia_pascal(descripcion_proyecto: str) -> str:
    """
    Ejecuta la agencia de inteligencia artificial Paperclip para analizar un proyecto
    y generar datos estructurados, incluyendo el modelo 3D base (arquitectura_3d_json) para Pascal Editor.

    Args:
        descripcion_proyecto: Una descripción natural del proyecto (ej. "Construye una habitación de 5x5 metros con piso de cerámica").

    Returns:
        str: Un JSON string con los resultados estructurados (Mano de obra, materiales, equipos, herramientas, y diseño 3D).
    """
    try:
        result = run_paperclip_agency(user_request=descripcion_proyecto)
        if result.get("success"):
            return result.get("structured_data", "{}")
        else:
            return json.dumps({"error": result.get("error", "Error desconocido ejecutando la agencia")})
    except Exception as e:
        return json.dumps({"error": str(e)})
