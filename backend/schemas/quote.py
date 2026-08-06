"""
Contrato de `quotes`: las 37 columnas de la tabla de cotizaciones con sus tipos.

Es el gemelo de `backend/schemas/task.py` para el otro lado del sistema: las
hojas de ventas (`ANTONIA_VENTAS` y las siete `<Vendedor> (VENTAS)`).

Los tipos NO se dedujeron del código. Se leyeron del esquema que publica
PostgREST y `scripts/verificar_base_quotes.py` los vuelve a comprobar contra la
base; la lección de `tasks` fue que tres de los cuatro tipos deducidos sin
evidencia estaban mal (§7.6 del plan).

Un detalle del esquema que gobierna toda la escritura de esta tabla:

    la clave primaria de `quotes` es `(folio, source_sheet)`.

Es decir, la misma cotización puede vivir en dos tablas: la de quien la reparte
y la de quien la trabaja, igual que una actividad asignada en `tasks`.

Fue `folio` **a secas** hasta el 2026-08-06, y esa forma se defendía con un dato
que era consecuencia del propio defecto: "los 661 folios son distintos y ninguno
se repite entre hojas". No se repetían porque la llave simple no dejaba —al
migrar, cada par de filas se colapsó en una y 25 folios `AV-` nacidos en la
tabla de Antonia acabaron viviendo solo en la del vendedor, fuera de su vista.

La consecuencia práctica está en `QuoteRepository.preparar_fila()`:
`source_sheet` se escribe siempre con la hoja que se está guardando, porque es
parte de la identidad de la fila. Antes se congelaba el valor almacenado, y esa
congelación era lo único que evitaba que el "Reverse Sync" hacia
`ANTONIA_VENTAS` se llevara la cotización de un vendedor; ahora esa defensa la
da la propia clave. Ver `docs/DDL_QUOTES_CLAVE_COMPUESTA.sql`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.hoja import (
    a_booleano,
    a_entero,
    a_fecha,
    a_numero,
    columnas_desde_hoja,
    indice_de_alias,
    numero_a_texto,
)
from backend.services.identity import normalize_avance

COLUMNAS_QUOTES: tuple = (
    "folio",
    "area",
    "cliente",
    "concepto",
    "clasificacion",
    "vendedor_id",
    "vendedor_raw",
    "f_visita",
    "f_inicio",
    "f_entrega",
    "dias",
    "avance",
    "estatus",
    "comentarios",
    "requisitor",
    "prioridad_cot",
    "info_cliente",
    "f2",
    "cotizacion",
    "timeline",
    "layout",
    "proceso",
    "proceso_log",
    "map_cot",
    "monto",
    "source_sheet",
    "extra",
    "created_at",
    "archivo",
    "fecha",
    "comentario",
    "estatus_2",
    "fecha_envio",
    "dias_2",
    "llamada_cliente",
    "reloj",
    "completada",
)

TIPOS_REALES: Dict[str, str] = {
    "folio": "text",
    "area": "text",
    "cliente": "text",
    "concepto": "text",
    "clasificacion": "text",
    "vendedor_id": "uuid",
    "vendedor_raw": "text",
    "f_visita": "date",
    "f_inicio": "date",
    "f_entrega": "date",
    "dias": "integer",
    "avance": "numeric",
    "estatus": "text",
    "comentarios": "text",
    "requisitor": "text",
    "prioridad_cot": "text",
    "info_cliente": "text",
    "f2": "text",
    "cotizacion": "text",
    "timeline": "text",
    "layout": "text",
    "proceso": "text",
    "proceso_log": "text",
    "map_cot": "text",
    "monto": "numeric",
    "source_sheet": "text",
    "extra": "jsonb",
    "created_at": "timestamp with time zone",
    "archivo": "text",
    "fecha": "date",
    "comentario": "text",
    "estatus_2": "text",
    "fecha_envio": "date",
    "dias_2": "integer",
    "llamada_cliente": "text",
    "reloj": "text",
    "completada": "boolean",
}

# Solo tres columnas NOT NULL, y las tres tienen dueño claro: `folio` es la PK,
# `source_sheet` dice de quién es la cotización y `created_at` tiene DEFAULT.
NO_NULOS: frozenset = frozenset({"folio", "source_sheet", "created_at"})

# De las NOT NULL, las que no tienen DEFAULT: hay que darlas en un alta.
OBLIGATORIAS_AL_INSERTAR: frozenset = frozenset({"folio", "source_sheet"})

# Columnas que el servidor calcula o resuelve; el cliente no las manda.
SOLO_LECTURA: frozenset = frozenset({"vendedor_id", "source_sheet", "created_at"})

# Nombre de columna -> encabezados con los que el frontend y `CODIGO.js` la
# llaman. Sale de `QUOTE_HEADER_MAP` (api/services/sheets.py), que es el mapa
# que ya se usa al leer, más los alias de `DEFAULT_SALES_HEADERS`.
ALIAS_DE_HOJA: Dict[str, List[str]] = {
    "folio": ["FOLIO", "ID"],
    "area": ["AREA", "ESPECIALIDAD", "DEPARTAMENTO"],
    "cliente": ["CLIENTE"],
    "concepto": ["CONCEPTO", "DESCRIPCION", "ACTIVIDAD"],
    # `CLAS` es como rotula la columna la vista de cotizaciones del original.
    "clasificacion": ["CLASIFICACION", "CLASI", "CLAS"],
    "vendedor_raw": ["VENDEDOR", "RESPONSABLE", "RESPONSABLES", "INVOLUCRADOS", "ASIGNADO"],
    "f_visita": ["F. VISITA", "F VISITA", "FECHA VISITA", "FECHA_VISITA"],
    "f_inicio": ["F. INICIO", "F INICIO", "FECHA INICIO", "FECHA_INICIO", "ALTA", "FECHA ALTA"],
    "f_entrega": ["F. ENTREGA", "F ENTREGA", "FECHA ENTREGA", "FECHA_ENTREGA"],
    # El encabezado completo de la hoja es `Días Finaliz. Cotiz`. `clave_encabezado`
    # quita acentos y puntuación, así que basta declararlo una vez para que casen
    # también `DIAS FINALIZ COTIZ` y la grafía sin acento.
    "dias": ["DIAS", "DÍAS", "DÍAS FINALIZ. COTIZ"],
    "avance": ["AVANCE", "AVANCE %", "% AVANCE"],
    "estatus": ["ESTATUS", "STATUS"],
    "comentarios": ["COMENTARIOS", "OBSERVACIONES", "NOTAS"],
    "requisitor": ["REQUISITOR"],
    "prioridad_cot": ["PRIO. COT.", "PRIO COT", "PRIORIDAD COT", "PRIORIDAD_COT", "PRIORIDAD"],
    "info_cliente": ["INFO CLIENTE", "INFO_CLIENTE"],
    "f2": ["F2"],
    "cotizacion": ["COTIZACION", "COTIZACIÓN"],
    "timeline": ["TIMELINE"],
    "layout": ["LAYOUT"],
    "proceso": ["PROCESO"],
    "proceso_log": ["PROCESO_LOG", "PROCESO LOG"],
    "map_cot": ["MAP COT", "MAP_COT", "MAPCOT"],
    "monto": ["MONTO", "IMPORTE", "TOTAL"],
    "archivo": ["ARCHIVO", "CARPETA", "LINK", "URL", "EVIDENCIA"],
    "fecha": ["FECHA"],
    "comentario": ["COMENTARIO"],
    "estatus_2": ["ESTATUS_2", "ESTATUS 2"],
    "fecha_envio": ["FECHA_ENVIO", "FECHA ENVIO", "F. ENVIO"],
    "dias_2": ["DIAS_2", "DIAS 2"],
    "llamada_cliente": ["LLAMADA_CLIENTE", "LLAMADA CLIENTE"],
    "reloj": ["RELOJ"],
    "completada": ["COMPLETADA", "CUMPLIMIENTO"],
}

INDICE_ALIAS: Dict[str, str] = indice_de_alias(ALIAS_DE_HOJA)


class QuoteWrite(BaseModel):
    """
    Lo que se acepta desde el cliente para una cotización.

    Igual que `TaskWrite`: `extra="forbid"`, y las columnas técnicas
    (`vendedor_id`, `source_sheet`, `created_at`) sencillamente no se declaran,
    así que mandarlas es un error de validación y no un descarte silencioso.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    folio: Optional[str] = None
    area: Optional[str] = None
    cliente: Optional[str] = None
    concepto: Optional[str] = None
    clasificacion: Optional[str] = None
    vendedor_raw: Optional[str] = None
    f_visita: Optional[date] = None
    f_inicio: Optional[date] = None
    f_entrega: Optional[date] = None
    dias: Optional[int] = None
    avance: Optional[float] = None
    estatus: Optional[str] = None
    comentarios: Optional[str] = None
    requisitor: Optional[str] = None
    prioridad_cot: Optional[str] = None
    info_cliente: Optional[str] = None
    f2: Optional[str] = None
    cotizacion: Optional[str] = None
    timeline: Optional[str] = None
    layout: Optional[str] = None
    proceso: Optional[str] = None
    proceso_log: Optional[str] = None
    map_cot: Optional[str] = None
    monto: Optional[float] = None
    archivo: Optional[str] = None
    fecha: Optional[date] = None
    comentario: Optional[str] = None
    estatus_2: Optional[str] = None
    fecha_envio: Optional[date] = None
    dias_2: Optional[int] = None
    llamada_cliente: Optional[str] = None
    reloj: Optional[str] = None
    completada: Optional[bool] = None

    temp_id: Optional[str] = Field(default=None, alias="_tempId")

    @field_validator("f_visita", "f_inicio", "f_entrega", "fecha", "fecha_envio", mode="before")
    @classmethod
    def _fecha_de_hoja(cls, valor: Any) -> Any:
        return a_fecha(valor)

    @field_validator("dias", "dias_2", mode="before")
    @classmethod
    def _entero_de_hoja(cls, valor: Any) -> Any:
        return a_entero(valor)

    @field_validator("monto", mode="before")
    @classmethod
    def _monto_de_hoja(cls, valor: Any) -> Any:
        """`"$ 1,250.50"` -> 1250.5. La hoja guarda el monto con formato."""
        return a_numero(valor)

    @field_validator("avance", mode="before")
    @classmethod
    def _avance_a_escala_0_100(cls, valor: Any) -> Any:
        """Misma regla que en `tasks`: el número `1` es 100 %, el string `"1"` es 1 %."""
        return normalize_avance(valor)

    @field_validator("completada", mode="before")
    @classmethod
    def _booleano_de_hoja(cls, valor: Any) -> Any:
        """La hoja escribe `SI`/`NO` en CUMPLIMIENTO; la columna es boolean."""
        return a_booleano(valor)

    @field_validator("reloj", mode="before")
    @classmethod
    def _texto_de_hoja(cls, valor: Any) -> Any:
        """
        `RELOJ` es `text` pero se edita con un input numérico.

        Una cotización recién creada nace con `RELOJ: 0` (`addNewRow`), así que
        sin esto no se podía dar de alta ni asignar ninguna. Ver `numero_a_texto`.
        """
        return numero_a_texto(valor)

    @classmethod
    def desde_hoja(cls, fila: Dict[str, Any]) -> "QuoteWrite":
        columnas = columnas_desde_hoja(fila, INDICE_ALIAS)
        temp_id = fila.get("_tempId") or fila.get("_tempid")
        if temp_id:
            columnas["_tempId"] = temp_id
        return cls.model_validate(columnas)

    def columnas(self) -> Dict[str, Any]:
        crudo = self.model_dump(exclude_none=False, exclude_unset=True, by_alias=False)
        crudo.pop("temp_id", None)
        return crudo


class QuoteRead(BaseModel):
    """Una fila de `quotes` tal como sale de la base."""

    model_config = ConfigDict(extra="allow")

    folio: Optional[str] = None
    source_sheet: Optional[str] = None
    area: Optional[str] = None
    cliente: Optional[str] = None
    concepto: Optional[str] = None
    clasificacion: Optional[str] = None
    vendedor_id: Optional[str] = None
    vendedor_raw: Optional[str] = None
    f_visita: Optional[date] = None
    f_inicio: Optional[date] = None
    f_entrega: Optional[date] = None
    dias: Optional[int] = None
    avance: Optional[float] = None
    estatus: Optional[str] = None
    comentarios: Optional[str] = None
    requisitor: Optional[str] = None
    prioridad_cot: Optional[str] = None
    info_cliente: Optional[str] = None
    f2: Optional[str] = None
    cotizacion: Optional[str] = None
    timeline: Optional[str] = None
    layout: Optional[str] = None
    proceso: Optional[str] = None
    proceso_log: Optional[str] = None
    map_cot: Optional[str] = None
    monto: Optional[float] = None
    archivo: Optional[str] = None
    fecha: Optional[date] = None
    comentario: Optional[str] = None
    estatus_2: Optional[str] = None
    fecha_envio: Optional[date] = None
    dias_2: Optional[int] = None
    llamada_cliente: Optional[str] = None
    reloj: Optional[str] = None
    completada: Optional[bool] = None
    extra: Optional[Any] = None
    created_at: Optional[datetime] = None

    @field_validator("f_visita", "f_inicio", "f_entrega", "fecha", "fecha_envio", mode="before")
    @classmethod
    def _fecha_tolerante(cls, valor: Any) -> Any:
        """
        Una fecha corrupta no puede tumbar la lectura de la hoja entera.

        Misma decisión que en `TaskRead`: se degrada a `None` y el original
        sobrevive en `model_extra` gracias a `extra="allow"`.
        """
        if valor in (None, ""):
            return None
        if isinstance(valor, (date, datetime)):
            return valor
        try:
            return date.fromisoformat(str(valor)[:10])
        except (ValueError, TypeError):
            return None
