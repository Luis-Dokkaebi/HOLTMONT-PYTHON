"""
Login contra `profiles` y protección de `/api/data`.

Antes de esto **nadie podía entrar al backend Python**: `/api/login` consultaba
la hoja `USERS`, que nunca se migró (`api/services/sheets.py` lo dice explícito),
y `profiles` estaba en 0 filas. El único acceso era `DEV_LOGIN_USERS`, un puente
de desarrollo que además se apaga si aparece un `credentials.json` de Google.

Las dos mitades van juntas a propósito: poblar `profiles` con contraseñas sin
cerrar `/api/data` las volvería descargables con `?sheet=profiles`.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import organigrama  # noqa: E402


@pytest.fixture(autouse=True)
def _limpiar_cache():
    organigrama.reset_cache_perfiles()
    yield
    organigrama.reset_cache_perfiles()


def _con_profiles(monkeypatch, filas):
    """Sustituye la lectura de `profiles` por filas fijas."""
    class FalsoManager:
        is_configured = True

        def select(self, tabla, filters=None):
            return filas if tabla == "profiles" else []

    import api.services.supabase_manager as sm
    monkeypatch.setattr(sm, "sb_manager", FalsoManager())
    return filas


# --- Validación de credenciales ---------------------------------------

def test_entra_con_su_usuario_y_contrasena(monkeypatch):
    _con_profiles(monkeypatch, [{
        "username": "LUIS_CARLOS", "password": "admin2025", "role": "ADMIN",
        "label": "Luis Carlos Holt Montero", "email": "luiscarlos@empresa.com",
        "staff_name": "LUIS CARLOS", "dept": "CEO", "seller": False,
    }])

    perfil = organigrama.validar_credenciales("luis_carlos", "admin2025")
    assert perfil is not None
    assert perfil["role"] == "ADMIN"
    assert perfil["label"] == "Luis Carlos Holt Montero"


def test_el_usuario_es_insensible_a_mayusculas_la_contrasena_no(monkeypatch):
    _con_profiles(monkeypatch, [
        {"username": "LUIS_CARLOS", "password": "admin2025", "role": "ADMIN"}])

    assert organigrama.validar_credenciales("Luis_Carlos", "admin2025") is not None
    assert organigrama.validar_credenciales("  luis_carlos  ", "admin2025") is not None
    # La contraseña sí distingue mayúsculas.
    assert organigrama.validar_credenciales("LUIS_CARLOS", "ADMIN2025") is None


def test_contrasena_incorrecta_no_entra(monkeypatch):
    _con_profiles(monkeypatch, [
        {"username": "LUIS_CARLOS", "password": "admin2025", "role": "ADMIN"}])
    assert organigrama.validar_credenciales("LUIS_CARLOS", "otra") is None


def test_usuario_inexistente_no_entra(monkeypatch):
    _con_profiles(monkeypatch, [
        {"username": "LUIS_CARLOS", "password": "admin2025", "role": "ADMIN"}])
    assert organigrama.validar_credenciales("NO_EXISTE", "admin2025") is None


@pytest.mark.parametrize("password", ["", None])
def test_sin_contrasena_no_entra(monkeypatch, password):
    _con_profiles(monkeypatch, [
        {"username": "LUIS_CARLOS", "password": "admin2025", "role": "ADMIN"}])
    assert organigrama.validar_credenciales("LUIS_CARLOS", password) is None


def test_una_cuenta_sin_contrasena_guardada_no_deja_entrar_con_nada(monkeypatch):
    """
    Si la fila existe pero no tiene columna de contraseña, se rechaza.

    El fallo a evitar es el contrario: tratar "no hay contraseña" como
    "cualquier contraseña vale".
    """
    _con_profiles(monkeypatch, [{"username": "SIN_CLAVE", "role": "ADMIN"}])
    assert organigrama.validar_credenciales("SIN_CLAVE", "") is None
    assert organigrama.validar_credenciales("SIN_CLAVE", "loquesea") is None


@pytest.mark.parametrize("columna", ["password", "pass", "contrasena", "clave"])
def test_se_acepta_el_nombre_que_tenga_la_columna_de_contrasena(monkeypatch, columna):
    """El esquema real no se pudo introspeccionar: se resuelve entre variantes."""
    _con_profiles(monkeypatch, [
        {"username": "LUIS_CARLOS", columna: "admin2025", "role": "ADMIN"}])
    assert organigrama.validar_credenciales("LUIS_CARLOS", "admin2025") is not None


def test_los_campos_que_faltan_en_la_base_caen_a_la_semilla(monkeypatch):
    """Una fila mínima sigue dando rol y etiqueta correctos."""
    _con_profiles(monkeypatch, [
        {"username": "JUDITH_ECHAVARRIA", "password": "x"}])

    perfil = organigrama.validar_credenciales("JUDITH_ECHAVARRIA", "x")
    assert perfil["role"] == "STAFF_USER"
    assert perfil["staff_name"] == "JUDITH ECHAVARRIA"
    assert perfil["seller"] is True


def test_un_fallo_de_base_no_deja_entrar(monkeypatch):
    """Ante un error de red se niega el acceso, no se concede."""
    class Roto:
        is_configured = True

        def select(self, tabla, filters=None):
            raise RuntimeError("red caída")

    import api.services.supabase_manager as sm
    monkeypatch.setattr(sm, "sb_manager", Roto())
    assert organigrama.validar_credenciales("LUIS_CARLOS", "admin2025") is None


def test_la_validacion_no_usa_la_cache_de_perfiles(monkeypatch):
    """
    Un cambio de contraseña tiene que surtir efecto sin reiniciar.

    `_filas_profiles()` cachea por proceso para que /api/config no consulte una
    vez por perfil; usar esa caché al autenticar dejaría viva la clave anterior.
    """
    consultas = {"n": 0}

    class Contador:
        is_configured = True

        def select(self, tabla, filters=None):
            consultas["n"] += 1
            return [{"username": "X", "password": "p", "role": "ADMIN"}]

    import api.services.supabase_manager as sm
    monkeypatch.setattr(sm, "sb_manager", Contador())

    organigrama.validar_credenciales("X", "p")
    organigrama.validar_credenciales("X", "p")
    assert consultas["n"] == 2, "cada intento debe leer la base"


# --- La contraseña no se filtra ---------------------------------------

def test_perfil_no_expone_la_contrasena(monkeypatch):
    """
    `perfil()` alimenta `/api/config`, que el frontend recibe entero. Si la
    contraseña entrara en ese diccionario, saldría por la API.
    """
    _con_profiles(monkeypatch, [{
        "username": "LUIS_CARLOS", "password": "admin2025", "role": "ADMIN",
        "label": "Luis Carlos",
    }])

    datos = organigrama.perfil("LUIS_CARLOS")
    assert datos["role"] == "ADMIN"
    for prohibida in organigrama.columnas_de_credencial():
        assert prohibida not in datos


def test_la_config_del_sistema_no_incluye_credenciales(monkeypatch):
    _con_profiles(monkeypatch, [{
        "username": "LUIS_CARLOS", "password": "admin2025", "role": "ADMIN"}])

    from api.main import api_get_system_config

    texto = repr(api_get_system_config(role="ADMIN", username="LUIS_CARLOS"))
    assert "admin2025" not in texto


# --- /api/data ---------------------------------------------------------

@pytest.mark.parametrize("nombre", [
    "profiles", "PROFILES", "Profiles", "  profiles  ",
    "USERS", "users", "usuarios", "credenciales", "auth",
])
def test_las_tablas_de_cuentas_no_se_publican(nombre):
    from api.main import _es_tabla_sensible

    assert _es_tabla_sensible(nombre) is True


@pytest.mark.parametrize("nombre", ["tasks", "quotes", "people", "PPCV3",
                                    "ANTONIA_VENTAS", "sites", "projects"])
def test_las_tablas_normales_siguen_disponibles(nombre):
    from api.main import _es_tabla_sensible

    assert _es_tabla_sensible(nombre) is False


def test_el_endpoint_rechaza_una_tabla_sensible():
    from fastapi import HTTPException

    from api.main import get_data

    with pytest.raises(HTTPException) as exc:
        get_data(sheet="profiles")
    assert exc.value.status_code == 403


def test_una_columna_de_contrasena_se_quita_de_cualquier_tabla():
    """
    Segunda barrera: aunque la tabla no esté en la lista de nombres, si trae una
    columna de credenciales no se publica. Cubre el caso de que alguien añada
    mañana un `password` a una tabla existente.
    """
    from api.main import _sin_columnas_de_credencial

    values = [
        ["NOMBRE", "PASSWORD", "ROL"],
        ["LUIS", "admin2025", "ADMIN"],
        ["ANTONIA", "tonita2025", "TONITA"],
    ]
    limpio = _sin_columnas_de_credencial(values)

    assert limpio[0] == ["NOMBRE", "ROL"]
    assert "admin2025" not in repr(limpio)
    assert "tonita2025" not in repr(limpio)


def test_el_filtro_no_toca_una_tabla_sin_credenciales():
    from api.main import _sin_columnas_de_credencial

    values = [["FOLIO", "CONCEPTO"], ["MG-1", "Cambiar tablero"]]
    assert _sin_columnas_de_credencial(values) == values


@pytest.mark.parametrize("values", [None, [], [[]]])
def test_el_filtro_tolera_matrices_vacias(values):
    from api.main import _sin_columnas_de_credencial

    assert _sin_columnas_de_credencial(values) == values


# --- El script de migración -------------------------------------------

def test_el_script_de_migracion_lee_las_41_cuentas():
    """
    Se comprueba contra el `CODIGO.js` real si está al lado; si no, se salta.
    """
    from pathlib import Path

    import scripts.migrar_perfiles as migrar

    if not migrar.CODIGO_POR_DEFECTO.exists():
        pytest.skip("REAL-HOLTMONT/CODIGO.js no está disponible")

    cuentas = migrar.leer_user_db(Path(migrar.CODIGO_POR_DEFECTO))
    assert len(cuentas) == 41
    assert all(c["username"] and c["password"] for c in cuentas)
    assert sum(1 for c in cuentas if c["seller"]) == 9

    campos = set(cuentas[0])
    assert campos == {"username", "password", "role", "label", "email",
                      "staff_name", "dept", "seller"}


def test_el_script_no_versiona_ninguna_contrasena():
    """
    El script lee las contraseñas del CODIGO.js del otro repo, no las trae
    escritas. Si alguna apareciera en el fuente, este archivo dejaría de ser
    seguro de commitear.
    """
    from pathlib import Path

    fuente = Path(__file__).parent.parent / "scripts" / "migrar_perfiles.py"
    texto = fuente.read_text(encoding="utf-8")
    for sospechosa in ("admin2025", "tonita2025", "workorder2026", "ppc2025"):
        assert sospechosa not in texto
