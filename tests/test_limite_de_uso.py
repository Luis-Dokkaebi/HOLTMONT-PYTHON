"""
Aviso de «Límite de uso» cuando la plataforma se queda sin base de datos.

Decisión del dueño (2026-10-30): para desconectar la base se borran
`SUPABASE_URL`, `SUPABASE_KEY` y `DATABASE_URL` del despliegue (la "opción B").
Desde ese momento la plataforma tiene que decir **«Límite de uso»**, tanto a
quien ya tenía la sesión abierta como a quien intenta entrar.

Sin esto, una plataforma sin base no avisa de nada: el login contesta
«Usuario o contraseña incorrectos» a una contraseña correcta y quien ya estaba
dentro ve pantallas vacías creyendo que no hay datos.

`tests/test_limite_de_uso_ui.py` cubre lo que se ve en el navegador.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.services import estado_plataforma
from backend.core.config import Settings
from backend.core.engine import hay_base_configurada

MENSAJE = (
    "Límite de uso agotado por insuficiencia de espacio en base de datos. "
    "La plataforma detectó que el almacenamiento contratado ya no es suficiente "
    "para el volumen de datos del proyecto."
)

VARIABLES_DE_BASE = ("SUPABASE_URL", "SUPABASE_KEY", "DATABASE_URL", "BACKEND_ENGINE")


def _settings(**valores) -> Settings:
    base = {"database_url": None, "supabase_url": None, "supabase_key": None,
            "motor_forzado": None, "escritura_habilitada": True}
    base.update(valores)
    return Settings(**base)


@pytest.fixture
def sin_base(monkeypatch):
    """El despliegue tal como queda después de la opción B: ninguna variable de base."""
    for nombre in VARIABLES_DE_BASE:
        monkeypatch.delenv(nombre, raising=False)


# --- Cuándo hay base ---------------------------------------------------

def test_sin_ninguna_variable_no_hay_base():
    assert hay_base_configurada(_settings()) is False


def test_con_supabase_url_y_key_hay_base():
    assert hay_base_configurada(_settings(supabase_url="https://x.supabase.co",
                                          supabase_key="k")) is True


def test_supabase_url_sin_key_no_cuenta_como_base():
    assert hay_base_configurada(_settings(supabase_url="https://x.supabase.co")) is False


def test_con_database_url_hay_base():
    assert hay_base_configurada(_settings(database_url="postgresql://u:p@h/db")) is True


def test_el_motor_en_memoria_cuenta_como_base_elegida_a_proposito():
    assert hay_base_configurada(_settings(motor_forzado="memoria")) is True


def test_forzar_sqlalchemy_sin_database_url_no_hay_base():
    """Igual que `construir_engine`: forzar un motor sin su variable es no tener base."""
    assert hay_base_configurada(_settings(motor_forzado="sqlalchemy",
                                          supabase_url="https://x.supabase.co",
                                          supabase_key="k")) is False


def test_forzar_postgrest_sin_supabase_no_hay_base():
    assert hay_base_configurada(_settings(motor_forzado="postgrest",
                                          database_url="postgresql://u:p@h/db")) is False


# --- GET /api/estado ---------------------------------------------------

def test_sin_base_el_estado_dice_limite_de_uso(sin_base):
    cuerpo = TestClient(app).get("/api/estado").json()
    assert cuerpo == {"success": True, "disponible": False, "mensaje": MENSAJE}


def test_con_base_el_estado_no_lleva_mensaje(monkeypatch, sin_base):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "k")
    cuerpo = TestClient(app).get("/api/estado").json()
    assert cuerpo == {"success": True, "disponible": True, "mensaje": ""}


def test_el_texto_del_aviso_es_el_que_pidio_el_dueno():
    assert estado_plataforma.MENSAJE_LIMITE_DE_USO == MENSAJE


# --- POST /api/login ---------------------------------------------------

def test_sin_base_el_login_responde_limite_de_uso(sin_base):
    respuesta = TestClient(app).post("/api/login",
                                     json={"username": "LUIS_CARLOS", "password": "x"})
    assert respuesta.json() == {"success": False, "message": MENSAJE,
                                "limiteDeUso": True}


def test_sin_base_el_login_de_desarrollo_tampoco_entra(monkeypatch, sin_base):
    """`DEV_LOGIN_USERS` no puede saltarse el aviso: la plataforma está detenida."""
    monkeypatch.setenv("DEV_LOGIN_USERS", "PRUEBA:clave:ADMIN:Prueba")
    respuesta = TestClient(app).post("/api/login",
                                     json={"username": "PRUEBA", "password": "clave"})
    assert respuesta.json()["success"] is False
    assert respuesta.json()["message"] == MENSAJE


def test_con_base_el_login_sigue_validando_credenciales(monkeypatch):
    """Con el motor de la suite (memoria) el login se comporta como siempre."""
    from api.services import organigrama

    monkeypatch.setattr(organigrama, "validar_credenciales", lambda u, p: None)
    respuesta = TestClient(app).post("/api/login",
                                     json={"username": "NADIE", "password": "x"})
    assert respuesta.json() == {"success": False,
                                "message": "Usuario o contraseña incorrectos."}
