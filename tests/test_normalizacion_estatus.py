"""
Normalización de la columna de estatus.

La columna venía de captura libre: 45 valores distintos en `tasks` y 26 en
`quotes` para lo que son ~11 estatus reales. Estas pruebas fijan las reglas
para que la limpieza no se deshaga sola en la siguiente captura.

Los casos usan los valores **reales** encontrados en la base, no ejemplos
inventados.

Ejecución:  python -m pytest tests/test_normalizacion_estatus.py -v
"""

import pytest

from api.services.tracker_rules import (
    CANONICAL_STATUSES,
    is_status_like,
    is_terminal_status,
    normalize_status,
)


# ----------------------------------------------------------------------
# Variantes reales encontradas en producción
# ----------------------------------------------------------------------

VARIANTES_ASIGNADO = [
    "ASIGNADO", "Asignado", "asignado", "ASIGNADA", "asignada",
    "ASIGANDO", "ASIGANDA", "ASIGADO", "ASIGANDOA", "ASIGANADO",
    "ASIGANADA", "ASIGANDa", "asigando", "asigado", "asiganda",
    "asigndo", "aSIGNADO", "asignadO", "asignADO",
]

VARIANTES_PENDIENTE = ["PENDIENTE", "Pendiente", "PEDIENTE"]

VARIANTES_PERDIDA = [
    "Perdida x Tiempo", "perdida por tiempo", "Perdida x tiempo",
    "perdida x tiempo",
]


@pytest.mark.parametrize("variante", VARIANTES_ASIGNADO)
def test_todas_las_variantes_de_asignado_colapsan(variante):
    """19 formas distintas de escribir lo mismo, incluidas erratas y género."""
    assert normalize_status(variante) == "ASIGNADO"


@pytest.mark.parametrize("variante", VARIANTES_PENDIENTE)
def test_variantes_de_pendiente(variante):
    assert normalize_status(variante) == "PENDIENTE"


@pytest.mark.parametrize("variante", VARIANTES_PERDIDA)
def test_variantes_de_perdida_por_tiempo(variante):
    assert normalize_status(variante) == "PERDIDA POR TIEMPO"


@pytest.mark.parametrize("crudo,esperado", [
    ("Falta Información", "FALTA INFORMACION"),      # con acento
    ("En Revisión", "EN REVISION"),
    ("EN REVISION", "EN REVISION"),
    # Desde 2026-08-10 el motivo no se colapsa: `CANCELADA POR PLANTA` es uno
    # de los cinco cierres que el vendedor elige al 100 % y alimenta los KPI
    # (ver tests/test_estatus_final_cotizacion.py). Que cancele la planta y que
    # cancele el cliente dejaron de ser el mismo dato.
    ("Cancelada x Planta", "CANCELADA POR PLANTA"),
    ("Cancelada x Cliente", "CANCELADA"),
    ("Perdida x Precio", "PERDIDA POR PRECIO"),
    ("BIERTO", "ABIERTO"),                            # errata real
    ("abierto", "ABIERTO"),
    ("SUSPENDIDA", "SUSPENDIDA"),
    ("ENVIADA", "ENVIADA"),
    ("en proceso", "EN PROCESO"),
    ("Pendiente Visita", "PENDIENTE VISITA"),
    ("PENDIENTE VISITA", "PENDIENTE VISITA"),
    ("PENDIENTE INFORMACION POR PLANTA", "PENDIENTE INFORMACION"),
])
def test_casos_puntuales_reales(crudo, esperado):
    assert normalize_status(crudo) == esperado


# ----------------------------------------------------------------------
# Lo que NO es un estatus
# ----------------------------------------------------------------------

@pytest.mark.parametrize("basura", [
    "-", "-\n-", "-\n-\n-", "", "   ", None,
    "RAM", "TG", "MANZ",                       # iniciales de persona
    "Nickey Torres", "EDUARDO CASANOVA",       # nombres
    "100.0",                                   # un avance en la columna equivocada
    "ESTATUS",                                 # encabezado filtrado como dato
    "es referente al primer correo enviado",   # comentario
    "- Act 20/10-  Ya se tiene la ficha técnica, se  inicia con planos",
])
def test_lo_que_no_es_estatus_devuelve_none(basura):
    """
    Devolver None es deliberado: mapear `RAM` o un comentario a `PENDIENTE`
    fabricaría información que nadie capturó.
    """
    assert normalize_status(basura) is None
    assert is_status_like(basura) is False


# ----------------------------------------------------------------------
# Invariantes
# ----------------------------------------------------------------------

TODOS_LOS_VALORES_REALES = (
    VARIANTES_ASIGNADO + VARIANTES_PENDIENTE + VARIANTES_PERDIDA + [
        "Falta Información", "En Revisión", "Cancelada x Planta", "BIERTO",
        "abierto", "SUSPENDIDA", "ENVIADA", "en proceso", "Pendiente Visita",
        "PENDIENTE VISITA", "PENDIENTE INFORMACION POR PLANTA", "ABIERTO",
        "GANADA", "PERDIDA", "HECHO", "TERMINADO", "CERRADO",
        "-", "-\n-", "RAM", "TG", "MANZ", "100.0", "ESTATUS", None,
    ]
)


@pytest.mark.parametrize("valor", TODOS_LOS_VALORES_REALES)
def test_normalizar_no_cambia_si_una_tarea_es_terminal(valor):
    """
    El invariante que hace segura la migración: si `PERDIDA X TIEMPO` contaba
    como terminal (y por tanto la tarea estaba archivada), su forma canónica
    tiene que seguir contando igual. Verificado también contra las 5,287 filas
    reales antes de aplicar.
    """
    canonico = normalize_status(valor)
    assert is_terminal_status(valor) == is_terminal_status(canonico or "")


@pytest.mark.parametrize("valor", TODOS_LOS_VALORES_REALES)
def test_es_idempotente(valor):
    """Normalizar dos veces da lo mismo: el script se puede reejecutar."""
    una = normalize_status(valor)
    assert normalize_status(una) == una


@pytest.mark.parametrize("canonico", sorted(CANONICAL_STATUSES))
def test_los_canonicos_son_punto_fijo(canonico):
    assert normalize_status(canonico) == canonico


def test_los_terminales_se_conservan_intactos():
    """No se puede alterar el auto-archivado por normalizar."""
    for terminal in ["HECHO", "DONE", "REALIZADO", "COMPLETADO", "TERMINADO",
                     "CERRADO", "FINALIZADO"]:
        assert normalize_status(terminal) == terminal
        assert is_terminal_status(normalize_status(terminal)) is True


def test_tolera_espacios_y_saltos_de_linea():
    assert normalize_status("  ASIGNADO  ") == "ASIGNADO"
    assert normalize_status("ASIGNADO\n") == "ASIGNADO"
    assert normalize_status("EN\nREVISION") == "EN REVISION"


def test_no_hay_alias_duplicados_entre_canonicos():
    """Un alias apuntando a dos canónicos haría el resultado dependiente del orden."""
    visto = {}
    for canonico, alias in CANONICAL_STATUSES.items():
        for a in alias:
            assert a not in visto, f"{a!r} es alias de {visto.get(a)!r} y de {canonico!r}"
            visto[a] = canonico
