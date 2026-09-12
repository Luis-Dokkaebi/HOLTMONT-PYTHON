"""
Las "Pantallas de McDonald's": la tabla de un ejecutivo en una televisión colgada.

Antonio las pidió para **ver**, no para capturar. Esa decisión, confirmada antes
de escribir una línea, es la que hace que este módulo sea tan pequeño: sin
escritura no hay concurrencia que resolver, ni permisos por fila, ni una segunda
copia de la capa de guardado. Se lee lo que el Tracker ya escribe, en las mismas
tablas particionadas por `source_sheet`. **Aquí no se crea ninguna tabla nueva.**

Tampoco hay sesión, y no es un descuido: una televisión colgada no puede teclear
una contraseña. La ruta se apoya en la puerta que `GET /api/data` ya tiene —la
lista de tablas sensibles— y por eso la única entrada es el nombre de la hoja.

Cuatro cosas que una pantalla de pared impone y una de escritorio no:

1. **Caben seis columnas, no veintiuna.** A cuatro metros una tabla de 21
   columnas no se lee, y una que no se lee no informa. `MONTO` no está entre
   las seis: la pared la ve todo el piso y quien entre de visita. Se enciende
   con `PANTALLA_MOSTRAR_MONTO` si la empresa decide que sí.
2. **Lo que falta va primero.** Una pantalla que abre con lo que ya está al
   100 % gasta su única página en trabajo terminado.
3. **Las filas que no caben siguen existiendo.** Se reparten en páginas para
   que la televisión las rote, y cuando se recorta se dice (`recortado`,
   `total`). Recortar en silencio esconde trabajo de alguien.
4. **Una pantalla congelada se ve exactamente igual que una viva.** Ese es el
   fallo peligroso de todo esto y no avisa de ninguna forma: la tabla se ve
   perfectamente normal mientras muestra datos de anteayer. Por eso sale
   `generado_en`, que es lo único con lo que la televisión puede decir cuándo
   se enteró por última vez.

Las reglas de negocio no se reescriben aquí. Qué hoja es de ventas lo decide
`tracker_rules.is_sales_sheet`, y qué cuenta como 100 % de avance,
`tracker_rules.is_progress_complete` —incluido el `1` nativo de una celda con
formato de porcentaje (AGENTS.md §4)—. Una segunda copia de cualquiera de las
dos se desincroniza y nadie se entera hasta que la pared miente.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from api.services import tracker_rules as rules
from backend.schemas.hoja import clave_encabezado

# Las seis que caben. Los nombres son los reales de la hoja
# (`tracker_store.ENCABEZADOS_TAREA` / `ENCABEZADOS_VENTAS`): inventarlos aquí
# pintaría seis columnas vacías sin ningún error.
COLUMNAS_TRACKER: Tuple[str, ...] = (
    "FOLIO", "CONCEPTO", "AVANCE", "FECHA_ESTIMADA_FIN", "PRIORIDAD", "ESTATUS",
)

COLUMNAS_VENTAS: Tuple[str, ...] = (
    "FOLIO", "CLIENTE", "CONCEPTO", "AVANCE", "F. ENTREGA", "ESTATUS",
)

# El importe, apagado. Ver el punto 1 del encabezado.
ENV_MONTO = "PANTALLA_MOSTRAR_MONTO"

# Techo de filas que viajan a la televisión. Una hoja con 800 filas son 67
# páginas: a 15 segundos por página, 17 minutos hasta volver a la primera. Eso
# no es una pantalla, es un protector de pantalla.
TOPE_FILAS = 200

# Cuántas filas caben de un vistazo en una televisión a cuatro metros. Es el
# valor que la vista usa para rotar; sale de aquí para que backend y pantalla no
# discrepen sobre dónde corta una página.
FILAS_POR_PAGINA = 12


def columnas_de(hoja: Any) -> Tuple[str, ...]:
    """Las columnas que se muestran para esa hoja."""
    if not rules.is_sales_sheet(hoja):
        return COLUMNAS_TRACKER
    if os.environ.get(ENV_MONTO, "").strip():
        return COLUMNAS_VENTAS + ("MONTO",)
    return COLUMNAS_VENTAS


def _indice_de_encabezados(fila: Mapping[str, Any]) -> Dict[str, str]:
    """
    `{clave_normalizada: nombre real en la fila}`.

    En estas hojas conviven `F. ENTREGA`, `F.ENTREGA` y las grafías con y sin
    acento. Comparar cadenas crudas deja la columna vacía en pantalla sin
    ningún error: se ve como una cotización a la que le falta la fecha.
    """
    return {clave_encabezado(nombre): nombre for nombre in fila}


def solo_columnas(filas: Sequence[Mapping[str, Any]],
                  columnas: Sequence[str]) -> List[Dict[str, Any]]:
    """Las filas reducidas a `columnas`, en ese orden y sin nada más."""
    recortadas: List[Dict[str, Any]] = []
    for fila in filas:
        indice = _indice_de_encabezados(fila)
        recortadas.append({
            columna: fila.get(indice.get(clave_encabezado(columna), ""), "")
            for columna in columnas
        })
    return recortadas


def esta_pendiente(fila: Mapping[str, Any]) -> bool:
    """Si a esa fila le falta trabajo, según la regla del Tracker."""
    indice = _indice_de_encabezados(fila)
    avance = fila.get(indice.get(clave_encabezado("AVANCE"), ""), "")
    return not rules.is_progress_complete(avance)


def pendientes_primero(filas: Sequence[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    """
    Lo que falta arriba, lo terminado abajo, **sin barajar dentro de cada grupo**.

    El orden estable importa más de lo que parece: una tabla que cambia de sitio
    sus filas en cada refresco es ilegible desde el otro lado de la oficina.
    """
    return sorted(filas, key=lambda fila: not esta_pendiente(fila))


def paginar(filas: Sequence[Any], tamano: int = FILAS_POR_PAGINA) -> List[List[Any]]:
    """
    Las filas repartidas en páginas que la televisión rota.

    Sin filas devuelve **una** página vacía y no cero: cero deja a la vista sin
    nada que pintar y al bucle de rotación dividiendo entre cero.
    """
    paso = max(1, int(tamano or 0))
    if not filas:
        return [[]]
    return [list(filas[i:i + paso]) for i in range(0, len(filas), paso)]


def preparar(filas: Sequence[Mapping[str, Any]], hoja: Any,
             ahora: datetime) -> Dict[str, Any]:
    """
    Lo que consume la televisión: columnas, páginas y cuándo se generó.

    `ahora` se inyecta y no se lee del reloj aquí (R8): una función que llama a
    `datetime.now()` no se puede probar sin medir el momento en que se corrió.
    """
    columnas = columnas_de(hoja)
    ordenadas = pendientes_primero(filas)
    visibles = ordenadas[:TOPE_FILAS]

    return {
        "success": True,
        "hoja": str(hoja or ""),
        "columnas": list(columnas),
        "paginas": paginar(solo_columnas(visibles, columnas)),
        "filas_por_pagina": FILAS_POR_PAGINA,
        # `total` es el número REAL, no el mostrado: es lo que permite a la
        # pantalla decir "mostrando 200 de 340" en vez de mentir por omisión.
        "total": len(filas),
        "pendientes": sum(1 for fila in filas if esta_pendiente(fila)),
        "recortado": len(ordenadas) > len(visibles),
        "generado_en": ahora.isoformat(),
    }
