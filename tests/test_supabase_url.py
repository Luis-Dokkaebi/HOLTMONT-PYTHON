"""
`SUPABASE_URL` pegada con `/rest/v1/` al final (como la muestra el panel de
Supabase) dejaba a todo el mundo fuera.

Medido el 2026-11-09 contra el proyecto real: con esa URL, PostgREST contesta
`PGRST125 Invalid path specified in request URL`, `sb_manager.select("profiles")`
devuelve `[]` y `/api/login` responde «Usuario o contraseña incorrectos» a
**todas** las cuentas. La misma URL rompe la escritura de `system_log`, así que
el fallo tampoco deja rastro. Como la variable sí existe, la plataforma no
muestra el aviso de «Límite de uso»: parece una contraseña equivocada.

La URL se normaliza en un solo lugar (`backend.core.config`) y la usan los dos
clientes: `SupabaseManager` (login, tracker) y el motor PostgREST de `backend/`.
Aquí no se toca la red: el cliente se sustituye en la frontera (`create_client`).
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from backend.core.config import cargar_settings, normalizar_supabase_url

BASE = "https://proyecto.supabase.co"


@pytest.mark.parametrize("cruda", [
    BASE,
    BASE + "/",
    BASE + "/rest/v1",
    BASE + "/rest/v1/",
    "  " + BASE + "/rest/v1/  ",
    BASE + "/REST/V1/",
    BASE + "//rest/v1//",
])
def test_la_url_queda_en_la_raiz_del_proyecto(cruda: str) -> None:
    assert normalizar_supabase_url(cruda) == BASE


@pytest.mark.parametrize("cruda", [None, "", "   "])
def test_una_url_vacia_sigue_siendo_no_configurada(cruda: Any) -> None:
    assert normalizar_supabase_url(cruda) is None


def test_no_recorta_una_ruta_que_no_es_rest_v1() -> None:
    """Solo se quita el sufijo que PostgREST vuelve a añadir; lo demás se respeta."""
    assert normalizar_supabase_url(BASE + "/storage/v1/") == BASE + "/storage/v1"


def test_settings_entrega_la_url_normalizada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", BASE + "/rest/v1/")
    monkeypatch.setenv("SUPABASE_KEY", "clave")
    assert cargar_settings().supabase_url == BASE


def test_el_motor_postgrest_no_duplica_rest_v1(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.core.engine import construir_engine

    monkeypatch.setenv("SUPABASE_URL", BASE + "/rest/v1/")
    monkeypatch.setenv("SUPABASE_KEY", "clave")
    monkeypatch.setenv("BACKEND_ENGINE", "postgrest")

    assert construir_engine().base == BASE + "/rest/v1"


def test_el_cliente_del_login_recibe_la_url_normalizada(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.services.supabase_manager as sm

    recibidas: List[Dict[str, str]] = []
    monkeypatch.setattr(sm, "create_client",
                        lambda url, key: recibidas.append({"url": url}) or object())
    monkeypatch.setenv("SUPABASE_URL", BASE + "/rest/v1/")
    monkeypatch.setenv("SUPABASE_KEY", "clave")

    manager = sm.SupabaseManager()
    _ = manager.client

    assert recibidas == [{"url": BASE}]
    assert manager.url == BASE
