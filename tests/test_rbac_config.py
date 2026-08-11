"""
`/api/config` — port de `getSystemConfig(role, username)`.

La prueba que da nombre a este archivo es `test_staff_user_no_hereda_config_de_admin`:
mientras `STAFF_USER` no tuvo rama propia, caía al `return` final del endpoint,
que es el de ADMIN, y las 30+ cuentas de personal recibían los 19 departamentos,
el directorio completo y `accessProjects: True`. Era la brecha de permisos más
grave del sistema y no había nada que la detectara.

El resto compara contra `REAL-HOLTMONT/CODIGO.js` las ramas que dependen de la
cuenta y no solo del rol, que es lo que el endpoint no podía expresar cuando su
firma recibía únicamente `role`.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services import organigrama  # noqa: E402


@pytest.fixture(autouse=True)
def _sin_base(monkeypatch):
    """
    Fuerza la semilla como fuente de perfiles.

    Sin esto la prueba dependería de que `profiles` esté poblada, y lo que se
    verifica aquí es la lógica de permisos, no el contenido de la base.
    """
    organigrama.reset_cache_perfiles()
    monkeypatch.setattr(organigrama, "_filas_profiles", lambda: [])
    yield
    organigrama.reset_cache_perfiles()


def config(role, username=""):
    from api.main import api_get_system_config

    return api_get_system_config(role=role, username=username)


# --- La brecha ---------------------------------------------------------

def test_staff_user_no_hereda_config_de_admin():
    staff = config("STAFF_USER", "MIGUEL_GALLARDO")

    assert staff["departments"] == {}, "un STAFF_USER no ve ningún departamento"
    assert staff["accessProjects"] is False
    assert staff["canSeeBancoJuntas"] is False
    # Solo se ve a sí mismo en `staff`; `directory` sí es completo porque el
    # frontend lo usa para los desplegables de responsables.
    assert [p["name"] for p in staff["staff"]] == ["MIGUEL GALLARDO"]

    admin = config("ADMIN", "LUIS_CARLOS")
    assert staff["departments"] != admin["departments"]
    assert staff["accessProjects"] != admin["accessProjects"]


def test_staff_user_apunta_a_su_propia_hoja():
    """`target` debe ser el `staffName` del perfil, no el nombre de la cuenta."""
    modulos = {m["id"]: m for m in config("STAFF_USER", "JUANY_RODRIGUEZ_NO_EXISTE")["specialModules"]}
    assert "MY_TRACKER" in modulos

    cfg = config("STAFF_USER", "LILIANA_MARTINEZ")
    tracker = next(m for m in cfg["specialModules"] if m["id"] == "MY_TRACKER")
    # La cuenta es LILIANA_MARTINEZ y su etiqueta "Liliana Martinez Ibarra",
    # pero su hoja se llama con el nombre completo del organigrama.
    assert tracker["target"] == "LILIANA AYLIN MARTINEZ IBARRA"


# --- Vendedores --------------------------------------------------------

def test_vendedor_recibe_modulo_de_cotizaciones():
    cfg = config("STAFF_USER", "JUDITH_ECHAVARRIA")
    ventas = [m for m in cfg["specialModules"] if m["id"] == "MY_SALES"]
    assert ventas, "seller:true debe habilitar MY_SALES"
    assert ventas[0]["target"] == "JUDITH ECHAVARRIA (VENTAS)"


def test_no_vendedor_no_recibe_modulo_de_cotizaciones():
    cfg = config("STAFF_USER", "MIGUEL_GALLARDO")
    assert not [m for m in cfg["specialModules"] if m["id"] == "MY_SALES"]


def test_los_nueve_vendedores_del_organigrama():
    """
    El original declara 9 cuentas con `seller: true`.

    El SSD pedía decidir entre "6 vendedores" y estas 9; la decisión tomada es
    que manda el atributo del perfil, no una lista aparte. Si alguien cambia un
    `seller`, esta prueba lo hace explícito en vez de que se note en permisos.
    """
    assert organigrama.vendedores() == [
        "ALFONSO_CORREA", "ANGEL_SALINAS", "EDUARDO_MANZANARES", "EDUARDO_TERAN",
        "JUAN_JOSE_SANCHEZ", "JUDITH_ECHAVARRIA", "RAMIRO_RODRIGUEZ",
        "SEBASTIAN_PADILLA", "TERESA_GARZA",
    ]


# --- Ramas cableadas por cuenta ---------------------------------------

def test_juany_rodriguez_ve_tres_departamentos():
    cfg = config("STAFF_USER", "JUANY_RODRIGUEZ")
    assert sorted(cfg["departments"]) == ["COMPRAS", "FACTURACION", "FINANZAS"]
    # La rama por cuenta gana sobre la rama de rol: es STAFF_USER y aun así ve
    # departamentos. Ese orden es el del original.
    assert cfg["departments"] != {}
    assert cfg["accessProjects"] is False


def test_jesus_cantu_renombra_el_modulo_ppc():
    cfg = config("PPC_ADMIN", "JESUS_CANTU")
    etiquetas = [m["label"] for m in cfg["specialModules"] if m["id"] == "PPC_MASTER"]
    assert etiquetas == ["INTERDICIPLINARIA"]

    otro = config("PPC_ADMIN", "OTRA_CUENTA")
    assert [m["label"] for m in otro["specialModules"] if m["id"] == "PPC_MASTER"] == ["PPC Maestro"]


def test_tonita_tiene_espejo_de_su_tracker_personal():
    """
    Su tabla maestra de ventas y su tracker personal son dos hojas distintas.

    `ANTONIA_VENTAS` es la maestra; `ANTONIA PINEDA LOPEZ` su tracker. El módulo
    MY_TRACKER apuntando al segundo faltaba, y sin él no tenía acceso a sus
    propias tareas.
    """
    cfg = config("TONITA", "ANTONIA_VENTAS")
    espejo = next(m for m in cfg["specialModules"] if m["id"] == "MY_TRACKER")
    assert espejo["target"] == "ANTONIA PINEDA LOPEZ"
    assert [p["name"] for p in cfg["staff"]] == ["ANTONIA_VENTAS"]


# --- Contrato general -------------------------------------------------

@pytest.mark.parametrize("role", ["ADMIN", "ADMIN_CONTROL", "PPC_ADMIN", "TONITA",
                                  "STAFF_USER", "WORKORDER_USER"])
def test_todas_las_ramas_declaran_can_see_banco_juntas(role):
    """El original lo devuelve en las seis ramas; el port lo omitía en todas."""
    cfg = config(role, "CUENTA_CUALQUIERA")
    assert "canSeeBancoJuntas" in cfg
    assert isinstance(cfg["canSeeBancoJuntas"], bool)


@pytest.mark.parametrize("role", ["ADMIN", "ADMIN_CONTROL", "PPC_ADMIN", "TONITA",
                                  "STAFF_USER", "WORKORDER_USER"])
def test_todas_las_ramas_publican_los_19_departamentos(role):
    """
    `allDepartments` es el catálogo, independiente de lo que el rol pueda ver.

    Eran 9 de 19: faltaban CEO, PRESUPUESTOS, PRECIOS UNITARIOS, SEGURIDAD,
    LIMPIEZA, ALMACEN Y MAQUINARIA, FINANZAS, FACTURACION, RH y CALIDAD, así que
    una persona de RH no tenía ni etiqueta ni color en la interfaz.
    """
    cfg = config(role, "CUENTA_CUALQUIERA")
    assert len(cfg["allDepartments"]) == 19
    for clave in ("CEO", "RH", "FINANZAS", "FACTURACION", "CALIDAD", "SEGURIDAD",
                  "LIMPIEZA", "PRESUPUESTOS", "PRECIOS UNITARIOS", "ALMACEN Y MAQUINARIA"):
        assert clave in cfg["allDepartments"], clave


def test_workorder_user_solo_ve_su_formulario():
    cfg = config("WORKORDER_USER", "PREWORK_ORDER")
    assert [m["id"] for m in cfg["specialModules"]] == ["WORK_ORDER_FORM"]
    assert cfg["accessProjects"] is False


def test_el_modulo_de_workorder_declara_el_tipo_que_el_frontend_sabe_abrir():
    """
    `type` es el contrato real, no `id`: `openModule()` de `index.html` rutea por
    tipo y `loadConfig()` busca el módulo con `find(m => m.type === ...)`.

    Un tipo que el frontend no conozca no da error: cae al final de la cadena de
    `else if` y el clic no hace nada. Por eso se fija aquí, en la única prueba
    que mira la forma del módulo.
    """
    for rol, cuenta in (("WORKORDER_USER", "PREWORK_ORDER"), ("ADMIN", "LUIS_CARLOS")):
        modulos = config(rol, cuenta)["specialModules"]
        wo = [m for m in modulos if m["id"] == "WORK_ORDER_FORM"]
        assert wo, f"{rol} perdió el módulo Pre Work Order"
        assert wo[0]["type"] == "work_order_form", (
            f"{rol}: el tipo del módulo cambió y `openModule()` ya no lo enruta"
        )
        assert wo[0]["label"] == "Pre Work Order"


def test_sin_username_no_se_conceden_permisos_de_mas():
    """
    Un cliente viejo que solo mande `role` degrada a "sin rama por usuario".

    Lo que no puede pasar es que la ausencia de `username` suba privilegios: un
    STAFF_USER sin cuenta identificada sigue sin departamentos.
    """
    cfg = config("STAFF_USER")
    assert cfg["departments"] == {}
    assert cfg["accessProjects"] is False
