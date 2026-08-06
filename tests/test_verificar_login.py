"""
Pruebas de `scripts/verificar_login.py`.

La verificación existe para responder «¿ya está migrada la base?» sin tener que
mirarla a ojo. Estas pruebas ejercitan los cinco controles sobre filas usando la
función pura `comprobar_filas`, sin red ni credenciales: la lógica se separó de
la lectura precisamente para poder probarla sin tocar la base (R7).

El control de autenticación se prueba aparte, sustituyendo `validar_credenciales`
por un doble, porque su valor está en llamar al mismo camino que `/api/login` y
eso es lo que hay que comprobar que hace.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from scripts import verificar_login


def _cuenta(username: str, **extra: Any) -> Dict[str, Any]:
    """Una cuenta como la devuelve `leer_user_db`."""
    base = {
        "username": username,
        "password": "irrelevante-para-estas-pruebas",
        "role": "STAFF_USER",
        "label": username.title(),
        "email": "",
        "staff_name": username.replace("_", " "),
        "dept": "RH",
        "seller": False,
    }
    base.update(extra)
    return base


def _fila(username: str, **extra: Any) -> Dict[str, Any]:
    """Una fila como la devuelve `profiles`."""
    fila = {
        "username": username,
        "password": "irrelevante-para-estas-pruebas",
        "role": "STAFF_USER",
        "label": username.title(),
        "email": "",
        "staff_name": username.replace("_", " "),
        "dept": "RH",
        "seller": False,
    }
    fila.update(extra)
    return fila


def test_una_migracion_completa_no_reporta_ninguna_falla() -> None:
    cuentas = [_cuenta("LUIS_CARLOS", role="ADMIN", dept="CEO"), _cuenta("LAURA_HUERTA")]
    filas = [_fila("LUIS_CARLOS", role="ADMIN", dept="CEO"), _fila("LAURA_HUERTA")]

    assert verificar_login.comprobar_filas(cuentas, filas) == []


def test_una_cuenta_que_falta_en_profiles_se_reporta() -> None:
    """Es el caso que deja a alguien sin poder entrar."""
    cuentas = [_cuenta("LUIS_CARLOS"), _cuenta("LAURA_HUERTA")]
    filas = [_fila("LUIS_CARLOS")]

    fallas = verificar_login.comprobar_filas(cuentas, filas)

    assert len(fallas) == 1
    assert "LAURA_HUERTA" in fallas[0]
    assert "no podrán entrar" in fallas[0]


def test_una_baja_que_sobrevive_en_profiles_se_reporta() -> None:
    """
    El caso `CESAR_GOMEZ`: baja del organigrama en 2026-06 que siguió en
    `USER_DB` hasta 2026-08. Si la migración se hubiera corrido en medio, su
    credencial habría quedado en `profiles` y conservaría acceso al sistema
    nuevo aun después de quitarla del de Apps Script.
    """
    cuentas = [_cuenta("LUIS_CARLOS")]
    filas = [_fila("LUIS_CARLOS"), _fila("CESAR_GOMEZ")]

    fallas = verificar_login.comprobar_filas(cuentas, filas)

    assert len(fallas) == 1
    assert "CESAR_GOMEZ" in fallas[0]
    assert "conservan acceso" in fallas[0]


def test_una_fila_sin_contrasena_se_reporta() -> None:
    """Existe pero no autentica: desde el navegador se ve como contraseña mala."""
    cuentas = [_cuenta("LUIS_CARLOS")]
    filas = [_fila("LUIS_CARLOS", password=None)]

    fallas = verificar_login.comprobar_filas(cuentas, filas)

    assert len(fallas) == 1
    assert "sin contraseña" in fallas[0]


def test_la_contrasena_se_reconoce_con_cualquiera_de_sus_nombres_de_columna() -> None:
    """
    `validar_credenciales` acepta password/pass/contrasena/clave porque el nombre
    real de la columna no se pudo verificar. La verificación tiene que mirar los
    mismos nombres o reportaría una falla falsa.
    """
    cuentas = [_cuenta("LUIS_CARLOS")]
    filas = [{"username": "LUIS_CARLOS", "clave": "algo", "role": "STAFF_USER",
              "dept": "RH", "seller": False}]

    assert verificar_login.comprobar_filas(cuentas, filas) == []


@pytest.mark.parametrize(
    ("campo", "valor_en_profiles"),
    [("role", "ADMIN"), ("dept", "VENTAS")],
)
def test_un_perfil_que_no_coincide_se_reporta(campo: str, valor_en_profiles: str) -> None:
    """Entra, pero con los permisos equivocados."""
    cuentas = [_cuenta("LUIS_CARLOS")]
    filas = [_fila("LUIS_CARLOS", **{campo: valor_en_profiles})]

    fallas = verificar_login.comprobar_filas(cuentas, filas)

    assert len(fallas) == 1
    assert campo in fallas[0]


def test_un_vendedor_que_pierde_su_bandera_se_reporta() -> None:
    """Sin `seller` no ve su módulo MY_SALES ni su hoja NOMBRE (VENTAS)."""
    cuentas = [_cuenta("EDUARDO_MANZANARES", dept="VENTAS", seller=True)]
    filas = [_fila("EDUARDO_MANZANARES", dept="VENTAS", seller=False)]

    fallas = verificar_login.comprobar_filas(cuentas, filas)

    assert len(fallas) == 1
    assert "seller" in fallas[0]


def test_un_rol_que_api_config_no_conoce_se_reporta() -> None:
    """Una errata en el rol autentica y deja a la persona sin módulos."""
    cuentas = [_cuenta("LUIS_CARLOS", role="ADMINN")]
    filas = [_fila("LUIS_CARLOS", role="ADMINN")]

    fallas = verificar_login.comprobar_filas(cuentas, filas)

    assert any("no lo resuelve /api/config" in f for f in fallas)


def test_los_seis_roles_del_sistema_se_aceptan() -> None:
    """Espejo de las ramas de `/api/config`: si se agrega una, esto lo recuerda."""
    roles = ["ADMIN", "ADMIN_CONTROL", "PPC_ADMIN", "STAFF_USER", "TONITA", "WORKORDER_USER"]
    cuentas = [_cuenta(f"CUENTA_{i}", role=r) for i, r in enumerate(roles)]
    filas = [_fila(f"CUENTA_{i}", role=r) for i, r in enumerate(roles)]

    assert verificar_login.comprobar_filas(cuentas, filas) == []


def test_el_nombre_de_usuario_se_normaliza_antes_de_comparar() -> None:
    """
    `clave_usuario` normaliza mayúsculas y espacios, igual que el original. Sin
    esto, una fila guardada como ` luis_carlos ` se reportaría a la vez como
    faltante y como sobrante.
    """
    cuentas = [_cuenta("LUIS_CARLOS")]
    filas = [_fila(" luis_carlos ")]

    assert verificar_login.comprobar_filas(cuentas, filas) == []


def test_la_autenticacion_usa_el_mismo_camino_que_api_login(monkeypatch: Any) -> None:
    """
    El control 6 tiene que llamar a `organigrama.validar_credenciales`, no a una
    copia de la comparación: una verificación con su propia lógica puede pasar
    mientras el login real falla.
    """
    from api.services import organigrama

    llamadas: List[tuple] = []

    def falso_validar(username: Any, password: Any) -> Any:
        llamadas.append((username, password))
        return {"role": "STAFF_USER"} if password == "la-buena" else None

    monkeypatch.setattr(organigrama, "validar_credenciales", falso_validar)

    cuentas = [_cuenta("LUIS_CARLOS", password="la-buena")]
    assert verificar_login.comprobar_autenticacion(cuentas) == []

    # Se probó la credencial buena y además una incorrecta.
    assert ("LUIS_CARLOS", "la-buena") in llamadas
    assert any(clave == verificar_login.CLAVE_INCORRECTA for _, clave in llamadas)


def test_se_reporta_la_cuenta_que_no_autentica(monkeypatch: Any) -> None:
    from api.services import organigrama

    monkeypatch.setattr(organigrama, "validar_credenciales", lambda u, p: None)

    fallas = verificar_login.comprobar_autenticacion([_cuenta("LUIS_CARLOS")])

    assert len(fallas) == 1
    assert "no autentica" in fallas[0]


def test_se_reporta_si_una_contrasena_incorrecta_es_aceptada(monkeypatch: Any) -> None:
    """
    Que acepte la buena no basta. Si la comparación estuviera invertida o rota,
    todo el mundo entraría con cualquier cosa y los otros controles pasarían.
    """
    from api.services import organigrama

    monkeypatch.setattr(organigrama, "validar_credenciales",
                        lambda u, p: {"role": "STAFF_USER"})

    fallas = verificar_login.comprobar_autenticacion([_cuenta("LUIS_CARLOS")])

    assert len(fallas) == 1
    assert "acepta una contraseña incorrecta" in fallas[0]


def test_la_verificacion_no_imprime_ninguna_contrasena(capsys: Any) -> None:
    """
    R7 y §23 de AGENTS.md: el script se corre en una terminal cuyo historial
    queda guardado. Ninguna credencial puede salir por stdout, ni siquiera
    dentro de un mensaje de falla.
    """
    secreta = "contrasena-secreta-de-produccion"
    cuentas = [_cuenta("LUIS_CARLOS", password=secreta, role="ADMIN")]
    filas = [_fila("LUIS_CARLOS", password=secreta, role="STAFF_USER")]

    fallas = verificar_login.comprobar_filas(cuentas, filas)
    for falla in fallas:
        print(falla)

    assert fallas, "se esperaba al menos una falla para que el control sea significativo"
    assert secreta not in capsys.readouterr().out
