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
    cfg = config("STAFF_USER", "ROLANDO_MORENO")
    assert not [m for m in cfg["specialModules"] if m["id"] == "MY_SALES"]


def test_miguel_gallardo_recibe_su_tabla_de_cotizaciones():
    """
    Reporte del dueño (2026-08-18): entró a su cuenta y no tenía la tabla de
    Cotizaciones que sí tiene Sebastián Padilla.

    Cotiza desde ELECTROMECANICA, así que la bandera no puede depender del
    departamento —igual que Alfonso Correa desde CONSTRUCCION—. El módulo tiene
    que apuntar a su hoja con sufijo, no a su tracker: sin el sufijo estaría
    abriendo dos veces la misma tabla de actividades.
    """
    cfg = config("STAFF_USER", "MIGUEL_GALLARDO")
    ventas = [m for m in cfg["specialModules"] if m["id"] == "MY_SALES"]

    assert ventas, "MIGUEL_GALLARDO debe ver su módulo de Cotizaciones"
    assert ventas[0]["target"] == "MIGUEL GALLARDO (VENTAS)"
    assert ventas[0]["label"] == "Cotizaciones"

    # La misma forma que la de Sebastián, que es la referencia que dio el dueño.
    sebastian = next(m for m in config("STAFF_USER", "SEBASTIAN_PADILLA")["specialModules"]
                     if m["id"] == "MY_SALES")
    assert {k: v for k, v in ventas[0].items() if k != "target"} == \
           {k: v for k, v in sebastian.items() if k != "target"}


def test_los_diez_vendedores_del_organigrama():
    """
    El original declara 9 cuentas con `seller: true`; Miguel Gallardo es el alta
    del dueño del 2026-08-18 y hace diez.

    El SSD pedía decidir entre "6 vendedores" y aquellas 9; la decisión tomada es
    que manda el atributo del perfil, no una lista aparte. Si alguien cambia un
    `seller`, esta prueba lo hace explícito en vez de que se note en permisos.
    """
    assert organigrama.vendedores() == [
        "ALFONSO_CORREA", "ANGEL_SALINAS", "EDUARDO_MANZANARES", "EDUARDO_TERAN",
        "JUAN_JOSE_SANCHEZ", "JUDITH_ECHAVARRIA", "MIGUEL_GALLARDO",
        "RAMIRO_RODRIGUEZ", "SEBASTIAN_PADILLA", "TERESA_GARZA",
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


# --- canManageTickets: bandera aditiva, igual que `seller` --------------
#
# Quien resuelve tickets de bug (docs/DDL_PENDIENTE.sql §5) necesita ver una
# vista nueva en index.html. La bandera no reemplaza el rol de nadie -- por
# eso se prueba en las siete ramas del endpoint, no solo en una.


def test_admin_y_admin_control_ven_tickets_sin_necesitar_la_bandera():
    assert config("ADMIN", "LUIS_CARLOS")["canManageTickets"] is True
    assert config("ADMIN_CONTROL", "JAIME_OLIVO")["canManageTickets"] is True
    assert config("ADMIN_CONTROL", "DIMAS_RAMOS")["canManageTickets"] is True


def test_luis_carlos_tiene_ademas_la_bandera_explicita():
    """No es solo que ADMIN lo cubra: el perfil real trae `soporte: True`."""
    assert organigrama.perfil("LUIS_CARLOS").get("soporte") is True


def test_antonio_salazar_ve_los_tickets_sin_ser_admin():
    """
    El primer caso real de la bandera haciendo su trabajo: `ANTONIO_SALAZAR`
    es STAFF_USER —no lo cubre ninguna rama de rol— y aun así entra al panel
    de tickets. Si alguien le quita `soporte` del perfil, esta prueba lo dice.
    """
    assert organigrama.perfil("ANTONIO_SALAZAR").get("role") == "STAFF_USER"
    assert config("STAFF_USER", "ANTONIO_SALAZAR")["canManageTickets"] is True


def test_la_bandera_no_le_da_nada_mas_que_los_tickets():
    """
    `soporte` es aditiva y acotada: enciende `canManageTickets` y **nada
    más**. Un STAFF_USER con la bandera sigue sin departamentos, sin
    proyectos y viendo solo su propia hoja.
    """
    antonio = config("STAFF_USER", "ANTONIO_SALAZAR")
    otro = config("STAFF_USER", "MIGUEL_GALLARDO")
    assert antonio["departments"] == {} == otro["departments"]
    assert antonio["accessProjects"] is False
    assert antonio["canSeeBancoJuntas"] is False
    assert [p["name"] for p in antonio["staff"]] == ["ANTONIO SALAZAR"]


@pytest.mark.parametrize("rol,cuenta", [
    ("STAFF_USER", "MIGUEL_GALLARDO"),
    ("PPC_ADMIN", "JESUS_CANTU"),
    ("WORKORDER_USER", "PREWORK_ORDER"),
    ("TONITA", "ANTONIA_VENTAS"),
])
def test_sin_bandera_ni_rol_admin_no_se_ve_la_vista_de_tickets(rol, cuenta):
    assert config(rol, cuenta)["canManageTickets"] is False


def test_la_bandera_explicita_alcanza_aunque_el_rol_no_sea_admin(monkeypatch):
    """
    `soporte: True` en un STAFF_USER cualquiera también debe encender
    `canManageTickets` -- no es un privilegio exclusivo de ADMIN/ADMIN_CONTROL,
    es aditivo como `seller`. Se simula con un perfil de prueba para fijar la
    regla con independencia de quién la traiga hoy en el organigrama.
    """
    monkeypatch.setattr(organigrama, "perfil", lambda cuenta: {"role": "STAFF_USER", "soporte": True})
    assert config("STAFF_USER", "QUIEN_SEA")["canManageTickets"] is True


# --- La bandera tiene que sobrevivir a la tabla `profiles` ---------------
#
# `perfil()` prefiere la fila de `profiles` sobre la semilla del código, y
# `_perfil_desde_base` reconstruye el diccionario clave por clave. `soporte`
# no estaba en esa lista, así que se descartaba en silencio: en cuanto la
# cuenta existía en la tabla, la bandera dejaba de existir.
#
# Medido contra el proyecto real el 2026-08-13: ANTONIO_SALAZAR salía con
# `canManageTickets: False` pese a tener `soporte: True` en la semilla.
# LUIS_CARLOS lo tapaba porque su rol ADMIN se lo concede igual.


def _con_fila_en_profiles(monkeypatch, **columnas):
    """Simula que la cuenta ya existe en la tabla `profiles`."""
    fila = {"username": "ANTONIO_SALAZAR", "role": "STAFF_USER", **columnas}
    organigrama.reset_cache_perfiles()
    monkeypatch.setattr(organigrama, "_filas_profiles", lambda: [fila])


def test_la_bandera_sobrevive_a_una_fila_en_profiles(monkeypatch):
    """La tabla no trae columna `soporte`: debe mandar la semilla, no perderse."""
    _con_fila_en_profiles(monkeypatch)
    assert organigrama.perfil("ANTONIO_SALAZAR").get("soporte") is True
    assert config("STAFF_USER", "ANTONIO_SALAZAR")["canManageTickets"] is True


def test_la_base_puede_revocar_la_bandera(monkeypatch):
    """
    Si algún día la tabla sí trae la columna, manda la tabla: es el punto de
    la migración a `profiles` — cambiar permisos sin desplegar código.
    """
    _con_fila_en_profiles(monkeypatch, soporte=False)
    assert organigrama.perfil("ANTONIO_SALAZAR").get("soporte") is False
    assert config("STAFF_USER", "ANTONIO_SALAZAR")["canManageTickets"] is False


def test_la_base_puede_conceder_la_bandera_a_quien_no_la_trae(monkeypatch):
    fila = {"username": "MIGUEL_GALLARDO", "role": "STAFF_USER", "soporte": True}
    organigrama.reset_cache_perfiles()
    monkeypatch.setattr(organigrama, "_filas_profiles", lambda: [fila])
    assert config("STAFF_USER", "MIGUEL_GALLARDO")["canManageTickets"] is True
