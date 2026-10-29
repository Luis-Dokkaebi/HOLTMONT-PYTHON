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

1. **Se parece a la hoja de Google que la oficina ya lee.** Decisión del dueño
   (2026-10-29), tras ver la primera versión de seis columnas: las mismas
   columnas visibles de la hoja, en su orden, y el mismo semáforo rojo /
   amarillo / verde en las fechas y en DÍAS. `MONTO` sigue fuera: la pared la
   ve todo el piso y quien entre de visita. Se enciende con
   `PANTALLA_MOSTRAR_MONTO` si la empresa decide que sí.
2. **Lo que falta va primero, y dentro de eso lo más reciente arriba**, como en
   la hoja. Una pantalla que abre con lo que ya está al 100 % gasta su única
   página en trabajo terminado.
3. **Las filas que no caben siguen existiendo.** Se reparten en páginas para
   que la televisión las rote, y cuando se recorta se dice (`recortado`,
   `total`). Recortar en silencio esconde trabajo de alguien.
4. **Una pantalla congelada se ve exactamente igual que una viva.** Ese es el
   fallo peligroso de todo esto y no avisa de ninguna forma: la tabla se ve
   perfectamente normal mientras muestra datos de anteayer. Por eso sale
   `generado_en`, que es lo único con lo que la televisión puede decir cuándo
   se enteró por última vez.

Las reglas de negocio no se reescriben aquí. Qué hoja es de ventas lo decide
`tracker_rules.is_sales_sheet`; qué cuenta como 100 % de avance,
`tracker_rules.is_progress_complete` —incluido el `1` nativo de una celda con
formato de porcentaje (AGENTS.md §4)—; el color del semáforo,
`tracker_rules.traffic_light_color`; desde qué fecha se cuenta,
`tracker_rules.calendar_date`, y qué encabezado es cuál,
`tracker_rules.COLUMN_ALIASES`. Una segunda copia de cualquiera de ellas se
desincroniza y nadie se entera hasta que la pared miente.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from api.services import organigrama
from api.services import tracker_rules as rules
from backend.schemas.hoja import clave_encabezado
from backend.services.identity import normalize_avance

# Las columnas visibles de cada hoja, en su orden. Los nombres son los reales
# (`tracker_store.ENCABEZADOS_TAREA` / `ENCABEZADOS_VENTAS`); los que la hoja
# escribe distinto (`PRIORIDADES`, `STATUS`, `AVANCE %`, `ALTA`) se resuelven
# con `COLUMN_ALIASES`. `DIAS` no se lee: se calcula (ver `dias_desde`).
COLUMNAS_TRACKER: Tuple[str, ...] = (
    "FOLIO", "AREA", "FECHA", "CLASIFICACION", "CONCEPTO", "INVOLUCRADOS",
    "AVANCE", "FECHA_ESTIMADA_FIN", "DIAS", "PRIORIDAD", "ESTATUS",
)

COLUMNAS_VENTAS: Tuple[str, ...] = (
    "FOLIO", "AREA", "CLIENTE", "CONCEPTO", "CLASIFICACION", "VENDEDOR",
    "F. VISITA", "F. INICIO", "F. ENTREGA", "DIAS", "AVANCE", "ESTATUS",
)

# Las fechas que la hoja pinta con el semáforo, cada una por su propia fecha.
# `DIAS` se pinta con el color de la fecha de inicio de la fila.
FECHAS_CON_SEMAFORO: Dict[str, Tuple[str, ...]] = {
    "tracker": ("FECHA",),
    "ventas": ("F. VISITA", "F. INICIO"),
}

COLUMNAS_FECHA = frozenset({"FECHA", "F. VISITA", "F. INICIO", "F. ENTREGA",
                            "FECHA_ESTIMADA_FIN"})

# Encabezados que en la pared se leen mejor con otro nombre. El resto sale tal
# cual lo escribe la hoja.
ETIQUETAS: Dict[str, str] = {"FECHA_ESTIMADA_FIN": "F. FIN", "DIAS": "DÍAS",
                             "CLASIFICACION": "CLASIF."}

# `traffic_light_color` habla en los colores de la hoja; la pantalla, en
# niveles, para que el tono lo decida el CSS de la televisión.
NIVELES: Dict[str, str] = {"#FF0000": "rojo", "#FFFF00": "amarillo", "#00FF00": "verde"}

# La hora de la oficina. Vercel corre en UTC y de 18:00 a medianoche en
# Monterrey ya es mañana: los DÍAS saldrían con uno de más frente a la hoja,
# que cuenta con `TODAY()` en la hora local. Offset fijo y no `ZoneInfo`
# porque México quitó el horario de verano en 2022 (Monterrey incluido) y así
# no se depende de que el servidor traiga la base de zonas horarias.
ZONA_OFICINA = timezone(timedelta(hours=-6), "America/Monterrey")

# El importe, apagado. Ver el punto 1 del encabezado.
ENV_MONTO = "PANTALLA_MOSTRAR_MONTO"

# Techo de filas que viajan a la televisión. Una hoja con 800 filas son 54
# páginas: a 15 segundos por página, 13 minutos hasta volver a la primera. Eso
# no es una pantalla, es un protector de pantalla.
TOPE_FILAS = 200

# Cuántas filas caben de un vistazo, con la densidad de la hoja de Google. Es
# el valor que la vista usa para rotar; sale de aquí para que backend y
# pantalla no discrepen sobre dónde corta una página.
FILAS_POR_PAGINA = 15


@dataclass(frozen=True)
class Lectura:
    """Una fila de la hoja y lo que la pantalla calcula de ella."""

    fila: Mapping[str, Any]
    inicio: str            # ISO, o "" si la fila no trae fecha de inicio
    dias: Optional[int]    # días desde `inicio` hasta hoy
    nivel: str             # "rojo" | "amarillo" | "verde" | "" (sin semáforo)


def tipo_de(hoja: Any) -> str:
    """`"ventas"` para una hoja de cotizaciones, `"tracker"` para el resto."""
    return "ventas" if rules.is_sales_sheet(hoja) else "tracker"


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


def _valor(fila: Mapping[str, Any], indice: Mapping[str, str], columna: str) -> Any:
    """
    El valor de `columna` en la fila, probando su nombre y luego sus alias.

    Gana el primer encabezado que **existe**, aunque venga vacío: un `FOLIO`
    vacío no se rellena con el UUID de `ID`. Es la misma prioridad con la que
    `CODIGO.js` resuelve la columna del folio.
    """
    for nombre in (columna, *rules.COLUMN_ALIASES.get(columna, ())):
        real = indice.get(clave_encabezado(nombre))
        if real is not None:
            return fila.get(real, "")
    return ""


def solo_columnas(filas: Sequence[Mapping[str, Any]],
                  columnas: Sequence[str]) -> List[Dict[str, Any]]:
    """Las filas reducidas a `columnas`, en ese orden y sin nada más."""
    recortadas: List[Dict[str, Any]] = []
    for fila in filas:
        indice = _indice_de_encabezados(fila)
        recortadas.append({columna: _valor(fila, indice, columna) for columna in columnas})
    return recortadas


def esta_pendiente(fila: Mapping[str, Any]) -> bool:
    """Si a esa fila le falta trabajo, según la regla del Tracker."""
    avance = _valor(fila, _indice_de_encabezados(fila), "AVANCE")
    return not rules.is_progress_complete(avance)


def pendientes_primero(filas: Sequence[Any],
                       fila_de: Callable[[Any], Mapping[str, Any]] = lambda f: f) -> List[Any]:
    """
    Lo que falta arriba, lo terminado abajo, **sin barajar dentro de cada grupo**.

    El orden estable importa más de lo que parece: una tabla que cambia de sitio
    sus filas en cada refresco es ilegible desde el otro lado de la oficina.
    `fila_de` saca la fila de la hoja cuando lo que se ordena la envuelve.
    """
    return sorted(filas, key=lambda f: not esta_pendiente(fila_de(f)))


def dias_desde(valor: Any, ahora: datetime) -> Optional[int]:
    """Días de calendario desde esa fecha hasta hoy; `None` si no es fecha."""
    fecha = rules.parse_sheet_date(valor)
    if fecha is None:
        return None
    return (ahora.date() - fecha.date()).days


def nivel_de(clasificacion: Any, dias: Optional[int], pendiente: bool) -> str:
    """
    El color del semáforo, con la regla del Tracker.

    Sin días o sin clasificación no hay color: inventarlo pintaría de verde una
    fila que nadie clasificó. Lo terminado tampoco se pinta: un rojo en algo
    entregado grita un retraso que ya no existe.
    """
    if dias is None or not pendiente:
        return ""
    return NIVELES.get(rules.traffic_light_color(clasificacion, dias) or "", "")


def leer(fila: Mapping[str, Any], tipo: str, ahora: datetime) -> Lectura:
    """Fecha de inicio, días y color de una fila."""
    origen = rules.CALENDAR_ORIGIN_QUOTES if tipo == "ventas" else rules.CALENDAR_ORIGIN_TRACKER
    inicio = rules.calendar_date(dict(fila), origen)
    dias = dias_desde(inicio, ahora)
    clasificacion = _valor(fila, _indice_de_encabezados(fila), "CLASIFICACION")
    return Lectura(fila, inicio, dias, nivel_de(clasificacion, dias, esta_pendiente(fila)))


def ordenar(lecturas: Sequence[Lectura]) -> List[Lectura]:
    """
    Lo pendiente primero; dentro, lo más reciente arriba, como en la hoja, y lo
    que no trae fecha al final. Los empates conservan el orden de la hoja.
    """
    fechadas = sorted((lec for lec in lecturas if lec.inicio),
                      key=lambda lec: lec.inicio, reverse=True)
    sin_fecha = [lec for lec in lecturas if not lec.inicio]
    return pendientes_primero(fechadas + sin_fecha, fila_de=lambda lec: lec.fila)


def _fecha_corta(valor: Any) -> Any:
    """`2026-09-20` -> `20/09/26`, como la lee la oficina. Lo demás, tal cual."""
    fecha = rules.parse_sheet_date(valor)
    return fecha.strftime("%d/%m/%y") if fecha else valor


def _porcentaje(valor: Any) -> str:
    numero = normalize_avance(valor)
    return "" if numero is None else f"{numero:g}%"


def _semaforo_de(lectura: Lectura, tipo: str, ahora: datetime,
                 celdas: Mapping[str, Any]) -> Dict[str, str]:
    """`{columna: nivel}` de las celdas que la hoja pinta. Sin color, no sale."""
    pendiente = esta_pendiente(lectura.fila)
    clasificacion = _valor(lectura.fila, _indice_de_encabezados(lectura.fila), "CLASIFICACION")
    colores = {columna: nivel_de(clasificacion, dias_desde(celdas.get(columna), ahora), pendiente)
               for columna in FECHAS_CON_SEMAFORO[tipo] if columna in celdas}
    colores["DIAS"] = lectura.nivel
    return {columna: nivel for columna, nivel in colores.items() if nivel}


def para_pantalla(lectura: Lectura, columnas: Sequence[str], tipo: str,
                  ahora: datetime) -> Dict[str, Any]:
    """La fila tal como se pinta: solo sus columnas, legibles, y su semáforo."""
    celdas = solo_columnas([lectura.fila], columnas)[0]
    semaforo = _semaforo_de(lectura, tipo, ahora, celdas)
    if "DIAS" in celdas:
        celdas["DIAS"] = "" if lectura.dias is None else lectura.dias
    if "AVANCE" in celdas:
        celdas["AVANCE"] = _porcentaje(celdas["AVANCE"])
    for columna in COLUMNAS_FECHA.intersection(celdas):
        celdas[columna] = _fecha_corta(celdas[columna])
    celdas["_semaforo"] = semaforo
    return celdas


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


def contar_semaforo(lecturas: Sequence[Lectura]) -> Dict[str, int]:
    """Cuántas pendientes hay de cada color. `sin` = sin fecha o sin clasificar."""
    conteo = {"rojo": 0, "amarillo": 0, "verde": 0, "sin": 0}
    for lectura in lecturas:
        if esta_pendiente(lectura.fila):
            conteo[lectura.nivel or "sin"] += 1
    return conteo


def persona_de(hoja: Any) -> Dict[str, str]:
    """
    Puesto y foto de la ficha de RH. `{}` si no tiene ficha.

    Solo lo que la pared pinta: esta ruta no pide sesión, y lo que no se
    muestra no tiene por qué viajar. La foto ya es pública en `/fotos/`.
    """
    ficha = organigrama.FICHAS.get(rules.normalize_staff_name(hoja))
    if not ficha:
        return {}
    return {"puesto": ficha["puesto"], "foto": ficha["foto"]}


def preparar(filas: Sequence[Mapping[str, Any]], hoja: Any,
             ahora: datetime) -> Dict[str, Any]:
    """
    Lo que consume la televisión: columnas, páginas, semáforo y cuándo se generó.

    `ahora` se inyecta y no se lee del reloj aquí (R8): una función que llama a
    `datetime.now()` no se puede probar sin medir el momento en que se corrió.
    """
    tipo = tipo_de(hoja)
    columnas = columnas_de(hoja)
    lecturas = [leer(fila, tipo, ahora) for fila in filas]
    visibles = ordenar(lecturas)[:TOPE_FILAS]

    return {
        "success": True,
        "hoja": str(hoja or ""),
        "tipo": tipo,
        "persona": persona_de(hoja),
        "columnas": list(columnas),
        "etiquetas": {c: ETIQUETAS[c] for c in columnas if c in ETIQUETAS},
        "paginas": paginar([para_pantalla(lec, columnas, tipo, ahora) for lec in visibles]),
        "filas_por_pagina": FILAS_POR_PAGINA,
        # `total` es el número REAL, no el mostrado: es lo que permite a la
        # pantalla decir "mostrando 200 de 340" en vez de mentir por omisión.
        "total": len(filas),
        "pendientes": sum(1 for fila in filas if esta_pendiente(fila)),
        "semaforo": contar_semaforo(lecturas),
        "limites": dict(rules.SLA_LIMITS),
        "recortado": len(lecturas) > len(visibles),
        "generado_en": ahora.isoformat(),
    }
