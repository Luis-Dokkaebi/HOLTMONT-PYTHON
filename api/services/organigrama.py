"""
Organigrama y perfiles: el port de `INITIAL_DIRECTORY`, `allDepts` y `USER_DB`
de `CODIGO.js`.

**Aquí no hay contraseñas y no deben aparecer nunca.** `USER_DB` del original
guarda `pass` en texto plano junto a los datos de organización; al portarlo se
tomaron solo los campos que describen a la persona en la empresa (rol,
etiqueta, correo, hoja, departamento, si vende). La credencial vive en la tabla
`profiles` de Supabase y la valida `/api/login`. `tests/test_api_contract.py`
verifica que ningún módulo del repo traiga credenciales embebidas.

Por qué estos datos están en el fuente y no solo en la base: son el organigrama
oficial, y `apiResyncDirectory` los necesita como semilla para poder reparar
`people` cuando le falten registros. Es la misma decisión que ya tomaba el
original, y su `test_departments.js` la verifica contra una transcripción del
organigrama en papel. `tests/test_organigrama.py` porta esa verificación.

La fuente viva sigue siendo la tabla `people` (54 filas): `get_directory_from_db`
la lee y solo cae a `INITIAL_DIRECTORY` si la base no responde.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# --- Departamentos del organigrama (19) -------------------------------
# Espejo de `allDepts`. El frontend los usa para el menú lateral y para
# colorear las tarjetas por departamento.
ALL_DEPTS: Dict[str, Dict[str, str]] = {
    "CEO": {"label": "Dirección General (CEO)", "icon": "fa-crown", "color": "#b8860b"},
    "CONSTRUCCION": {"label": "Construcción", "icon": "fa-hard-hat", "color": "#e83e8c"},
    "COMPRAS": {"label": "Compras/Almacén", "icon": "fa-shopping-cart", "color": "#198754"},
    "PRESUPUESTOS": {"label": "Presupuestos", "icon": "fa-calculator", "color": "#6f42c1"},
    "PRECIOS UNITARIOS": {"label": "Precios Unitarios", "icon": "fa-dollar-sign", "color": "#20c997"},
    "SEGURIDAD": {"label": "Seguridad", "icon": "fa-shield-alt", "color": "#dc3545"},
    "EHS": {"label": "Seguridad (EHS)", "icon": "fa-shield-alt", "color": "#dc3545"},
    "DISEÑO": {"label": "Diseño & Ing.", "icon": "fa-drafting-compass", "color": "#0d6efd"},
    "ELECTROMECANICA": {"label": "Electromecánica", "icon": "fa-bolt", "color": "#ffc107"},
    "HVAC": {"label": "HVAC", "icon": "fa-fan", "color": "#fd7e14"},
    "LIMPIEZA": {"label": "Limpieza", "icon": "fa-broom", "color": "#0dcaf0"},
    "ALMACEN Y MAQUINARIA": {"label": "Almacén y Maquinaria", "icon": "fa-warehouse", "color": "#198754"},
    "ADMINISTRACION": {"label": "Administración", "icon": "fa-briefcase", "color": "#6f42c1"},
    "VENTAS": {"label": "Ventas", "icon": "fa-handshake", "color": "#0dcaf0"},
    "MAQUINARIA": {"label": "Maquinaria", "icon": "fa-truck", "color": "#20c997"},
    "FINANZAS": {"label": "Finanzas", "icon": "fa-coins", "color": "#198754"},
    "FACTURACION": {"label": "Facturación", "icon": "fa-file-invoice-dollar", "color": "#0d6efd"},
    "RH": {"label": "Recursos Humanos", "icon": "fa-users", "color": "#6610f2"},
    "CALIDAD": {"label": "Calidad", "icon": "fa-clipboard-check", "color": "#0dcaf0"},
}

# --- Directorio semilla (38 registros) -------------------------------
INITIAL_DIRECTORY: List[Dict[str, str]] = [
    {"name": "LUIS CARLOS", "dept": "CEO", "type": "ESTANDAR"},
    {"name": "JUAN JOSE SANCHEZ", "dept": "CEO", "type": "ESTANDAR"},
    {"name": "DIMAS ELIEL RAMOS GARCIA", "dept": "RH", "type": "ESTANDAR"},
    {"name": "LAURA EDITH HUERTA ROCHA", "dept": "RH", "type": "ESTANDAR"},
    {"name": "LILIANA AYLIN MARTINEZ IBARRA", "dept": "RH", "type": "ESTANDAR"},
    {"name": "FRANCISCO SANCHEZ SERNA", "dept": "RH", "type": "ESTANDAR"},
    {"name": "JUANA MARIA RODRIGUEZ JUAREZ", "dept": "FINANZAS", "type": "ESTANDAR"},
    {"name": "ZAIRA YAZMIN AGUILAR AGUILON", "dept": "FINANZAS", "type": "ESTANDAR"},
    {"name": "ROCIO ABIGAIL CASTRO COVARRUBIAS", "dept": "FINANZAS", "type": "ESTANDAR"},
    {"name": "DANIA LIZBETH GONZALEZ LORES", "dept": "FINANZAS", "type": "ESTANDAR"},
    {"name": "SONIA GARCIA PEREZ", "dept": "COMPRAS", "type": "ESTANDAR"},
    {"name": "JUDITH ECHAVARRIA", "dept": "COMPRAS", "type": "ESTANDAR"},
    {"name": "VANESSA DE LARA", "dept": "COMPRAS", "type": "ESTANDAR"},
    {"name": "EDUARDO TERAN", "dept": "PRESUPUESTOS", "type": "HIBRIDO"},
    {"name": "ANTONIA PINEDA LOPEZ", "dept": "PRESUPUESTOS", "type": "ESTANDAR"},
    {"name": "CARLOS MENDEZ", "dept": "CALIDAD", "type": "ESTANDAR"},
    {"name": "RUBI MORENO RODRIGUEZ", "dept": "SEGURIDAD", "type": "ESTANDAR"},
    {"name": "TERESA GARZA", "dept": "PRECIOS UNITARIOS", "type": "HIBRIDO"},
    {"name": "GERALDINE MARTINEZ HERNANDEZ", "dept": "PRECIOS UNITARIOS", "type": "ESTANDAR"},
    {"name": "ANGEL SALINAS", "dept": "DISEÑO", "type": "HIBRIDO"},
    {"name": "EDGAR URIMAR LOPEZ MALDONADO", "dept": "DISEÑO", "type": "ESTANDAR"},
    {"name": "ANTONIA_VENTAS", "dept": "VENTAS", "type": "VENTAS"},
    {"name": "EDUARDO MANZANARES", "dept": "VENTAS", "type": "HIBRIDO"},
    {"name": "RAMIRO RODRIGUEZ", "dept": "VENTAS", "type": "HIBRIDO"},
    {"name": "SEBASTIAN PADILLA", "dept": "VENTAS", "type": "HIBRIDO"},
    {"name": "JEHU MARTINEZ", "dept": "ELECTROMECANICA", "type": "ESTANDAR"},
    {"name": "MIGUEL GALLARDO", "dept": "ELECTROMECANICA", "type": "ESTANDAR"},
    {"name": "ROLANDO MORENO", "dept": "HVAC", "type": "ESTANDAR"},
    {"name": "EMILIANO ARREDONDO GOMEZ", "dept": "HVAC", "type": "ESTANDAR"},
    {"name": "JAIME OLIVO", "dept": "CONSTRUCCION", "type": "ESTANDAR"},
    {"name": "RICARDO MENDO", "dept": "CONSTRUCCION", "type": "ESTANDAR"},
    {"name": "ALFONSO CORREA", "dept": "CONSTRUCCION", "type": "ESTANDAR"},
    {"name": "CESAR EDUARDO GARCIA AVALOS", "dept": "CONSTRUCCION", "type": "ESTANDAR"},
    {"name": "EDUARDO BENITEZ", "dept": "LIMPIEZA", "type": "ESTANDAR"},
    {"name": "SONIA GARCIA PEREZ", "dept": "ALMACEN Y MAQUINARIA", "type": "ESTANDAR"},
    {"name": "ADMINISTRADOR", "dept": "ADMINISTRACION", "type": "HIBRIDO"},
    {"name": "DANIELA CASTRO", "dept": "GENERAL", "type": "ESTANDAR"},
    {"name": "CESAR GOMEZ", "dept": "GENERAL", "type": "ESTANDAR"},
]

# --- Perfiles (41 cuentas, sin credenciales) -------------------------
# `staff_name` es el nombre de la hoja/partición de tracker de la persona,
# que no siempre coincide con `label` (el nombre para mostrar).
# `seller` habilita el módulo de cotizaciones "<NOMBRE> (VENTAS)".
PERFILES: Dict[str, Dict[str, Any]] = {
    "JESUS_CANTU": {"role": "PPC_ADMIN", "label": "PPC Manager", "email": "jesuscantu@empresa.com", "staff_name": "", "dept": "", "seller": False},
    "JAIME_OLIVO": {"role": "ADMIN_CONTROL", "label": "Jaime Olivo", "email": "jaimeolivo@empresa.com", "staff_name": "", "dept": "", "seller": False},
    "PREWORK_ORDER": {"role": "WORKORDER_USER", "label": "Workorder", "email": "workorder@empresa.com", "staff_name": "", "dept": "", "seller": False},
    "ANTONIA_VENTAS": {"role": "TONITA", "label": "Antonia Pineda", "email": "ventas@empresa.com", "staff_name": "ANTONIA PINEDA LOPEZ", "dept": "VENTAS", "seller": False},
    "JUDITH_ECHAVARRIA": {"role": "STAFF_USER", "label": "Cristian Judith Echavarria Rodriguez", "email": "", "staff_name": "JUDITH ECHAVARRIA", "dept": "COMPRAS", "seller": True},
    "EDUARDO_MANZANARES": {"role": "STAFF_USER", "label": "Eduardo Manzanares Sanchez", "email": "", "staff_name": "EDUARDO MANZANARES", "dept": "VENTAS", "seller": True},
    "RAMIRO_RODRIGUEZ": {"role": "STAFF_USER", "label": "Ramiro Rodriguez Escalante", "email": "", "staff_name": "RAMIRO RODRIGUEZ", "dept": "VENTAS", "seller": True},
    "SEBASTIAN_PADILLA": {"role": "STAFF_USER", "label": "Erick Sebastian Padilla Carrillo", "email": "", "staff_name": "SEBASTIAN PADILLA", "dept": "VENTAS", "seller": True},
    "ALFONSO_CORREA": {"role": "STAFF_USER", "label": "Alfonso Correa De Leon", "email": "", "staff_name": "ALFONSO CORREA", "dept": "CONSTRUCCION", "seller": True},
    "TERESA_GARZA": {"role": "STAFF_USER", "label": "Maria Teresa Hernandez Garza", "email": "", "staff_name": "TERESA GARZA", "dept": "PRECIOS UNITARIOS", "seller": True},
    "DANIELA_CASTRO": {"role": "STAFF_USER", "label": "Daniela Castro", "email": "", "staff_name": "DANIELA CASTRO", "dept": "GENERAL", "seller": False},
    "ANGEL_SALINAS": {"role": "STAFF_USER", "label": "Jose Angel Salinas Ramirez", "email": "", "staff_name": "ANGEL SALINAS", "dept": "DISEÑO", "seller": True},
    "JUAN_JOSE_SANCHEZ": {"role": "STAFF_USER", "label": "Juan Jose Sanchez Muñiz", "email": "", "staff_name": "JUAN JOSE SANCHEZ", "dept": "CEO", "seller": True},
    "LUIS_CARLOS": {"role": "ADMIN", "label": "Luis Carlos Holt Montero", "email": "luiscarlos@empresa.com", "staff_name": "LUIS CARLOS", "dept": "CEO", "seller": False},
    "ANTONIA_PINEDA": {"role": "STAFF_USER", "label": "Antonia Pineda Lopez", "email": "", "staff_name": "ANTONIA PINEDA LOPEZ", "dept": "PRESUPUESTOS", "seller": False},
    "DANIA_GONZALEZ": {"role": "STAFF_USER", "label": "Dania Lizbeth Gonzalez Lores", "email": "", "staff_name": "DANIA LIZBETH GONZALEZ LORES", "dept": "FINANZAS", "seller": False},
    "JUANY_RODRIGUEZ": {"role": "STAFF_USER", "label": "Juana Maria Rodriguez Juarez", "email": "", "staff_name": "JUANA MARIA RODRIGUEZ JUAREZ", "dept": "FINANZAS", "seller": False},
    "EDUARDO_BENITEZ": {"role": "STAFF_USER", "label": "Eduardo Israel Benitez Garcia", "email": "", "staff_name": "EDUARDO BENITEZ", "dept": "LIMPIEZA", "seller": False},
    "ROLANDO_MORENO": {"role": "STAFF_USER", "label": "Jesus Rolando Moreno Perez", "email": "", "staff_name": "ROLANDO MORENO", "dept": "HVAC", "seller": False},
    "MIGUEL_GALLARDO": {"role": "STAFF_USER", "label": "Miguel Angel Gallardo Jaramillo", "email": "", "staff_name": "MIGUEL GALLARDO", "dept": "ELECTROMECANICA", "seller": False},
    "JEHU_MARTINEZ": {"role": "STAFF_USER", "label": "Jehu Arsenio Martinez Montes", "email": "", "staff_name": "JEHU MARTINEZ", "dept": "ELECTROMECANICA", "seller": False},
    "RICARDO_MENDO": {"role": "STAFF_USER", "label": "Ricardo Alonso Mendo Morales", "email": "", "staff_name": "RICARDO MENDO", "dept": "CONSTRUCCION", "seller": False},
    "CARLOS_MENDEZ": {"role": "STAFF_USER", "label": "Carlos Mendez Urbina", "email": "", "staff_name": "CARLOS MENDEZ", "dept": "CALIDAD", "seller": False},
    "INGE_OLIVO": {"role": "STAFF_USER", "label": "Jaime Antonio Olivo Guerrero", "email": "", "staff_name": "JAIME OLIVO", "dept": "CONSTRUCCION", "seller": False},
    "EDUARDO_TERAN": {"role": "STAFF_USER", "label": "Jesus Eduardo Teran Garcia", "email": "", "staff_name": "EDUARDO TERAN", "dept": "PRESUPUESTOS", "seller": True},
    "VANESSA_DE_LARA": {"role": "STAFF_USER", "label": "Erika Vanessa Rodriguez De Lara", "email": "", "staff_name": "VANESSA DE LARA", "dept": "COMPRAS", "seller": False},
    "DIMAS_RAMOS": {"role": "ADMIN_CONTROL", "label": "Dimas Eliel Ramos Garcia", "email": "dimas.ramos@holtmont.com", "staff_name": "DIMAS ELIEL RAMOS GARCIA", "dept": "RH", "seller": False},
    "RUBI_MORENO": {"role": "STAFF_USER", "label": "Rubi Moreno Rodriguez", "email": "", "staff_name": "RUBI MORENO RODRIGUEZ", "dept": "SEGURIDAD", "seller": False},
    "URIMAR_LOPEZ": {"role": "STAFF_USER", "label": "Edgar Urimar Lopez Maldonado", "email": "", "staff_name": "EDGAR URIMAR LOPEZ MALDONADO", "dept": "DISEÑO", "seller": False},
    "SAIRA": {"role": "STAFF_USER", "label": "Zaira Yazmin Aguilar Aguilon", "email": "", "staff_name": "ZAIRA YAZMIN AGUILAR AGUILON", "dept": "FINANZAS", "seller": False},
    "ZAIRA_AGUILAR": {"role": "STAFF_USER", "label": "Zaira Yazmin Aguilar Aguilon", "email": "", "staff_name": "ZAIRA YAZMIN AGUILAR AGUILON", "dept": "FINANZAS", "seller": False},
    "EMILIANO_AREDON": {"role": "STAFF_USER", "label": "Emiliano Arredondo Gomez", "email": "", "staff_name": "EMILIANO ARREDONDO GOMEZ", "dept": "HVAC", "seller": False},
    "SONIA_GARCIA": {"role": "STAFF_USER", "label": "Sonia Garcia Perez", "email": "", "staff_name": "SONIA GARCIA PEREZ", "dept": "COMPRAS", "seller": False},
    "FRANCISCO_SANCHEZ_SERNA": {"role": "STAFF_USER", "label": "Francisco Sanchez Serna", "email": "", "staff_name": "FRANCISCO SANCHEZ SERNA", "dept": "RH", "seller": False},
    "LILIANA_MARTINEZ": {"role": "STAFF_USER", "label": "Liliana Martinez Ibarra", "email": "", "staff_name": "LILIANA AYLIN MARTINEZ IBARRA", "dept": "RH", "seller": False},
    "LAURA_HUERTA": {"role": "STAFF_USER", "label": "Laura Huerta Rocha", "email": "", "staff_name": "LAURA EDITH HUERTA ROCHA", "dept": "RH", "seller": False},
    "ROCIO_CASTRO": {"role": "STAFF_USER", "label": "Rocio Castro Covarrubias", "email": "", "staff_name": "ROCIO ABIGAIL CASTRO COVARRUBIAS", "dept": "FINANZAS", "seller": False},
    "GERALDINE_MARTINEZ": {"role": "STAFF_USER", "label": "Geraldine Marie Martinez Hernandez", "email": "", "staff_name": "GERALDINE MARTINEZ HERNANDEZ", "dept": "PRECIOS UNITARIOS", "seller": False},
    "CESAR_EDUARDO_GARCIA": {"role": "STAFF_USER", "label": "Cesar Eduardo Garcia Avalos", "email": "", "staff_name": "CESAR EDUARDO GARCIA AVALOS", "dept": "CONSTRUCCION", "seller": False},
    "ANTONIO_SALAZAR": {"role": "STAFF_USER", "label": "Antonio Salazar", "email": "", "staff_name": "ANTONIO SALAZAR", "dept": "GENERAL", "seller": False},
    "CESAR_GOMEZ": {"role": "STAFF_USER", "label": "Cesar Gomez", "email": "", "staff_name": "CESAR GOMEZ", "dept": "GENERAL", "seller": False},
}


# --- Resolución de perfil ----------------------------------------------
# El original hacía `USER_DB[String(username).toUpperCase().trim()] || {}` en
# línea, dentro de `getSystemConfig`. Aquí se aísla porque además hay que
# preferir la base cuando la haya: `profiles` es la fuente que el dueño puede
# editar sin desplegar, y `PERFILES` la semilla que garantiza que el sistema
# arranque con el organigrama correcto.


def clave_usuario(username: Any) -> str:
    """Normaliza igual que el original: mayúsculas y sin espacios extremos."""
    return str(username or "").strip().upper()


def perfil(username: Any) -> Dict[str, Any]:
    """
    Perfil de una cuenta. Devuelve `{}` si no se conoce, como el original.

    Intenta primero `profiles` en Supabase y cae a la semilla. Un fallo de red
    no puede dejar sin permisos a quien acaba de autenticarse, así que la
    excepción se traga a propósito y se sigue con `PERFILES`.
    """
    clave = clave_usuario(username)
    if not clave:
        return {}

    desde_base = _perfil_desde_base(clave)
    if desde_base:
        return desde_base

    return dict(PERFILES.get(clave, {}))


# `profiles` se lee una vez por proceso: `/api/config` resuelve varios perfiles
# en una sola petición y no tiene sentido pagar una consulta por cada uno.
# Mismo patrón que `_PLAN_SEMANAL_CACHE` en `sheets.py`, con su reset para las
# pruebas y para cuando el dueño edite la tabla.
_CACHE_PROFILES: Dict[str, Any] = {}


def reset_cache_perfiles() -> None:
    _CACHE_PROFILES.clear()


def _filas_profiles() -> List[Dict[str, Any]]:
    if "filas" not in _CACHE_PROFILES:
        try:
            from api.services.supabase_manager import sb_manager

            _CACHE_PROFILES["filas"] = sb_manager.select("profiles") or []
        except Exception as exc:  # noqa: BLE001 - la semilla es respaldo suficiente
            # Se avisa una sola vez: en un entorno sin base esto se llamaría en
            # cada resolución de perfil y el aviso ahogaría el resto del log.
            print(f"[organigrama] No se pudo leer `profiles`, se usa la semilla: {exc}")
            _CACHE_PROFILES["filas"] = []
    return _CACHE_PROFILES["filas"]


def _perfil_desde_base(clave: str) -> Optional[Dict[str, Any]]:
    for fila in _filas_profiles():
        if clave_usuario(fila.get("username")) != clave:
            continue
        # `or` en vez de `.get(k, default)`: en la base una columna vacía llega
        # como cadena vacía o None, y ambas deben caer a la semilla.
        base = PERFILES.get(clave, {})
        return {
            "role": fila.get("role") or base.get("role", "STAFF_USER"),
            "label": fila.get("label") or base.get("label", clave),
            "email": fila.get("email") or base.get("email", ""),
            "staff_name": fila.get("staff_name") or base.get("staff_name", ""),
            "dept": fila.get("dept") or base.get("dept", ""),
            "seller": bool(fila.get("seller", base.get("seller", False))),
        }
    return None


def nombre_de_hoja(username: Any) -> str:
    """
    Hoja/partición de tracker de la persona.

    El original usa `u.staffName || u.label`: hay cuentas sin `staffName` cuyo
    tracker se llama como su etiqueta. Se conserva ese respaldo.
    """
    p = perfil(username)
    return p.get("staff_name") or p.get("label") or clave_usuario(username)


def es_vendedor(username: Any) -> bool:
    return bool(perfil(username).get("seller"))


def correo(username: Any) -> str:
    return perfil(username).get("email") or ""


def vendedores() -> List[str]:
    """
    Cuentas con `seller: true`.

    Reemplaza a las listas de vendedores repartidas por el código del original
    (anti-patrón §23.2): quien necesite saber quién vende pregunta aquí.
    """
    return sorted(u for u, p in PERFILES.items() if p.get("seller"))
