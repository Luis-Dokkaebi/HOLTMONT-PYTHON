"""
Organigrama oficial: port de `REAL-HOLTMONT/test_departments.js`.

`EXPECTED` es la transcripción literal del organigrama en papel y es la
autoridad sobre quién pertenece a qué departamento. El original la verifica
contra `INITIAL_DIRECTORY` y `USER_DB`; aquí se verifica contra
`api/services/organigrama.py`, que es donde viven esos dos datos en Python.

Por qué importa que esto tenga prueba: antes de portarlo, este repo mantenía su
propio directorio de 55 registros en 9 departamentos —una versión anterior del
organigrama, con nombres que ya no existen en la empresa (EDGAR HOLT, ALEXIS
TORRES, RUBEN PESQUEDA...) y sin ninguno de RH, FINANZAS, CALIDAD, SEGURIDAD ni
CEO. Nada lo detectaba porque no había con qué compararlo.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.services.organigrama import (  # noqa: E402
    ALL_DEPTS,
    INITIAL_DIRECTORY,
    PERFILES,
)

# --- Transcripción literal del organigrama oficial ---------------------
EXPECTED = {
    "CEO": ["LUIS CARLOS", "JUAN JOSE SANCHEZ"],
    "GENERAL": ["DANIELA CASTRO", "CESAR GOMEZ"],
    "RH": ["DIMAS ELIEL RAMOS GARCIA", "LAURA EDITH HUERTA ROCHA",
           "LILIANA AYLIN MARTINEZ IBARRA", "FRANCISCO SANCHEZ SERNA"],
    "FINANZAS": ["JUANA MARIA RODRIGUEZ JUAREZ", "ZAIRA YAZMIN AGUILAR AGUILON",
                 "ROCIO ABIGAIL CASTRO COVARRUBIAS", "DANIA LIZBETH GONZALEZ LORES"],
    "COMPRAS": ["SONIA GARCIA PEREZ", "JUDITH ECHAVARRIA", "VANESSA DE LARA"],
    "PRESUPUESTOS": ["EDUARDO TERAN", "ANTONIA PINEDA LOPEZ"],
    "CALIDAD": ["CARLOS MENDEZ"],
    "SEGURIDAD": ["RUBI MORENO RODRIGUEZ"],
    "PRECIOS UNITARIOS": ["TERESA GARZA", "GERALDINE MARTINEZ HERNANDEZ"],
    "DISEÑO": ["ANGEL SALINAS", "EDGAR URIMAR LOPEZ MALDONADO"],
    "VENTAS": ["EDUARDO MANZANARES", "RAMIRO RODRIGUEZ", "SEBASTIAN PADILLA"],
    "ELECTROMECANICA": ["JEHU MARTINEZ", "MIGUEL GALLARDO"],
    "HVAC": ["ROLANDO MORENO", "EMILIANO ARREDONDO GOMEZ"],
    "CONSTRUCCION": ["JAIME OLIVO", "RICARDO MENDO", "ALFONSO CORREA",
                     "CESAR EDUARDO GARCIA AVALOS"],
    "LIMPIEZA": ["EDUARDO BENITEZ"],
    "ALMACEN Y MAQUINARIA": ["SONIA GARCIA PEREZ"],
}

# No vienen de la imagen pero deben conservarse.
EXTRA_PERMITIDO = [
    ("ANTONIA_VENTAS", "VENTAS"),        # rol TONITA
    ("ADMINISTRADOR", "ADMINISTRACION"),  # hoja espejo de control, sin login
]

# Cuentas que el original ya dio de baja. Si alguna reaparece en la semilla es
# que se recuperó un organigrama viejo.
DEBEN_ESTAR_DE_BAJA = [
    "GUILLERMO_DAMICO", "REYNALDO_GARCIA", "EDGAR_HOLT", "ALEXIS_TORRES",
    "RUBEN_PESQUEDA", "GISELA_DOMINGUEZ", "CITLALI_GOMEZ", "AIMEE_RAMIREZ",
    "EDGAR_LOPEZ", "JUAN_ENRIQUE_PEREZ",
]


def _norm(v):
    return str(v or "").strip().upper()


def _directorio_por_nombre():
    indice = {}
    for e in INITIAL_DIRECTORY:
        indice.setdefault(_norm(e["name"]), set()).add(_norm(e["dept"]))
    return indice


def _casos():
    return [(dept, nombre) for dept, gente in EXPECTED.items() for nombre in gente]


@pytest.mark.parametrize("dept,nombre", _casos())
def test_cada_persona_esta_en_su_departamento(dept, nombre):
    depts = _directorio_por_nombre().get(_norm(nombre), set())
    assert dept in depts, (
        f"{nombre} debería estar en {dept}; en la semilla está en "
        f"{sorted(depts) or 'NINGUNO'}"
    )


def test_el_departamento_de_cada_perfil_es_coherente_con_el_organigrama():
    """
    Para cada persona, **al menos una** de sus cuentas debe declarar un
    departamento donde el organigrama la coloca.

    La comprobación es por persona y no por cuenta, igual que el original
    (`userDepts.some(...)`), porque una misma persona puede tener dos cuentas
    con departamentos distintos y ambos correctos:

      - SONIA GARCIA PEREZ vive en COMPRAS y en ALMACEN Y MAQUINARIA.
      - ANTONIA PINEDA LOPEZ tiene la cuenta `ANTONIA_PINEDA` en PRESUPUESTOS,
        que es su casilla del organigrama, y la cuenta de rol `ANTONIA_VENTAS`
        con dept=VENTAS, que describe la función y no la casilla. Exigirlo por
        cuenta marcaría esta segunda como error cuando no lo es.
    """
    por_hoja = {}
    for cuenta, p in PERFILES.items():
        if p.get("staff_name"):
            por_hoja.setdefault(_norm(p["staff_name"]), []).append(cuenta)

    incoherentes = []
    for nombre_norm, cuentas in por_hoja.items():
        permitidos = [d for d, gente in EXPECTED.items()
                      if nombre_norm in [_norm(n) for n in gente]]
        if not permitidos:
            continue  # no está en la imagen: lo cubre otra prueba

        declarados = [_norm(PERFILES[c].get("dept")) for c in cuentas]
        if not any(d in permitidos for d in declarados if d):
            incoherentes.append(
                f"{nombre_norm} ({'/'.join(cuentas)}): dept={declarados}, "
                f"organigrama={permitidos}"
            )

    assert not incoherentes, "Personas con departamento incoherente:\n" + "\n".join(incoherentes)


def test_no_hay_gente_en_la_semilla_que_no_este_en_el_organigrama():
    esperados = {_norm(n) for gente in EXPECTED.values() for n in gente}
    esperados |= {_norm(n) for n, _ in EXTRA_PERMITIDO}

    sobran = sorted({_norm(e["name"]) for e in INITIAL_DIRECTORY} - esperados)
    assert not sobran, f"En la semilla y no en el organigrama oficial: {sobran}"


def test_las_cuentas_dadas_de_baja_no_reaparecen():
    revividas = [c for c in DEBEN_ESTAR_DE_BAJA if c in PERFILES]
    assert not revividas, f"Cuentas dadas de baja que reaparecieron: {revividas}"


def test_los_departamentos_del_organigrama_tienen_etiqueta_y_color():
    """
    Cada departamento donde vive alguien debe existir en `ALL_DEPTS`, o la
    interfaz lo muestra sin nombre ni color.

    GENERAL es la excepción conocida: el original tampoco lo declara — es el
    cajón por defecto de `get_directory_from_db`, no un departamento del menú.
    """
    faltan = [d for d in EXPECTED if d not in ALL_DEPTS and d != "GENERAL"]
    assert not faltan, f"Departamentos sin entrada en ALL_DEPTS: {faltan}"


def test_los_perfiles_no_traen_credenciales():
    """
    `USER_DB` del original guarda `pass` en texto plano. Al portarlo se dejaron
    fuera a propósito: la credencial vive en `profiles` y la valida /api/login.
    """
    prohibidos = {"pass", "password", "contrasena", "contraseña", "pwd", "secret", "token"}
    con_credencial = [
        cuenta for cuenta, p in PERFILES.items()
        if prohibidos & {k.lower() for k in p}
    ]
    assert not con_credencial, f"Perfiles con credencial embebida: {con_credencial}"
