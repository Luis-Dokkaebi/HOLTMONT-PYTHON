from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
async def login(req: LoginRequest):
    # Simulated auth - replace with Supabase call when needed
    role = "ADMIN"
    if "cotizador" in req.username.lower():
        role = "COTIZADOR"
    elif "ventas" in req.username.lower():
        role = "VENTAS"

    config = {
        "departments": {
            "VENTAS": {"label": "Ventas", "icon": "fa-chart-line", "color": "#007bff"}
        },
        "specialModules": [
            {"id": 1, "type": "ppc", "label": "Papa Caliente", "icon": "fa-fire", "color": "#dc3545"}
        ],
        "staff": [],
        "directory": []
    }

    return {
        "status": "success",
        "username": req.username,
        "name": req.username.upper(),
        "role": role,
        "config": config
    }

@router.post("/logout")
async def logout():
    return {"status": "success"}
