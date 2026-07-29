"""
Contrato de `tasks`: modelos Pydantic con las 28 columnas y sus tipos.

Esto es lo que sustituye a la matriz 2D de strings de
`api/services/sheets.py::_rows_to_values`, donde todo pasaba por `str()` y la
distinción entre el número `1` y el string `"1"` —de la que depende la regla de
`AVANCE`— desaparecía.

Separación deliberada en dos modelos:

* `TaskRead` expone las 28 columnas, incluidas las técnicas.
* `TaskWrite` es lo que se acepta **desde el cliente**, y sencillamente no
  declara `id`, `dedupe_key`, `assignee_id`, `source_sheet`, `folio_sintetico`
  ni `created_at`. No es una lista de campos ignorados: son campos que el
  modelo rechaza, porque `extra="forbid"` convierte el intento en un error de
  validación en vez de en un descarte silencioso.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.hoja import a_fecha, a_hora, columnas_desde_hoja, indice_de_alias
from backend.services.identity import normalize_avance

# Las 28 columnas de `tasks`, en el orden en que se documentan.
COLUMNAS_TASKS: tuple = (
    "id",
    "dedupe_key",
    "folio",
    "folio_sintetico",
    "source_sheet",
    "assignee_raw",
    "assignee_id",
    "departamento",
    "fecha_alta",
    "hora_alta",
    "clasificacion",
    "concepto",
    "avance",
    "fecha_estimada_fin",
    "hora_estimada_fin",
    "reloj",
    "restricciones",
    "prioridad",
    "riesgos",
    "fecha_respuesta",
    "carpeta",
    "correo",
    "cumplimiento",
    "comentarios",
    "comentarios_semana",
    "comentarios_semana_previa",
    "status",
    "created_at",
)

# Columnas que el servidor calcula y el cliente no puede tocar.
#
# `correo` está aquí por lo que contiene, no por su nombre: **ninguno** de sus
# 2.266 valores es una dirección de correo. Son enlaces de Google Drive (2.157)
# y de Google Sheets (el resto), igual que `carpeta`, y 2.084 filas traen las
# dos. Es una columna de archivos mal nombrada por la migración. Aceptarla
# desde el cliente invitaría a escribir un correo encima de un enlace, y además
# `SupabaseSync` nunca la escribe, así que hoy es un dato congelado. Los
# archivos de Drive quedan fuera del alcance de esta fase: se conservan como
# texto y no se tocan.
SOLO_LECTURA: frozenset = frozenset(
    {"id", "dedupe_key", "assignee_id", "source_sheet", "folio_sintetico", "created_at", "correo"}
)

# Tipos reales de `tasks`, leídos del esquema que publica PostgREST y
# verificados contra las 4.626 filas. `scripts/verificar_base_tasks.py` los
# comprueba y falla si el esquema cambia por debajo.
#
# Tres de los cuatro que se habían deducido sin evidencia estaban mal:
# `folio_sintetico` es boolean (no texto) y las dos columnas `hora_*` son
# `time`, no texto.
TIPOS_REALES: Dict[str, str] = {
    "id": "uuid",
    "folio": "text",
    "dedupe_key": "text",
    "folio_sintetico": "boolean",
    "assignee_id": "uuid",
    "assignee_raw": "text",
    "departamento": "text",
    "fecha_alta": "date",
    "hora_alta": "time without time zone",
    "clasificacion": "text",
    "concepto": "text",
    "avance": "numeric",
    "fecha_estimada_fin": "date",
    "hora_estimada_fin": "time without time zone",
    "reloj": "text",
    "restricciones": "text",
    "prioridad": "text",
    "riesgos": "text",
    "fecha_respuesta": "date",
    "correo": "text",
    "carpeta": "text",
    "cumplimiento": "text",
    "comentarios": "text",
    "comentarios_semana": "text",
    "comentarios_semana_previa": "text",
    "status": "text",
    "source_sheet": "text",
    "created_at": "timestamp with time zone",
}

# Las NUEVE columnas NOT NULL. El documento de partida solo mencionaba `status`.
NO_NULOS: frozenset = frozenset(
    {"id", "folio", "dedupe_key", "folio_sintetico", "concepto", "avance",
     "status", "source_sheet", "created_at"}
)

# De esas nueve, las que **no** tienen DEFAULT: en un INSERT hay que darlas o
# la base aborta con 23502. `id`, `folio_sintetico` (false), `avance` (0),
# `status` ('PENDIENTE') y `created_at` (now()) sí lo tienen.
OBLIGATORIAS_AL_INSERTAR: frozenset = frozenset(
    {"folio", "dedupe_key", "concepto", "source_sheet"}
)

# Nombre de columna -> alias de encabezado que usa el frontend/la hoja.
# Reutiliza los alias ya probados de `tracker_rules.COLUMN_ALIASES` cuando
# existen, para no mantener dos listas que se desincronicen.
ALIAS_DE_HOJA: Dict[str, List[str]] = {
    "folio": ["FOLIO", "ID"],
    "assignee_raw": ["RESPONSABLE", "RESPONSABLES", "INVOLUCRADOS", "VENDEDOR", "ENCARGADO", "ASIGNADO"],
    "departamento": ["AREA", "ESPECIALIDAD", "DEPARTAMENTO"],
    "fecha_alta": ["FECHA", "FECHA ALTA", "ALTA", "FECHA DE ALTA"],
    "clasificacion": ["CLASIFICACION", "CLASI"],
    "concepto": ["CONCEPTO", "DESCRIPCION", "ACTIVIDAD"],
    "avance": ["AVANCE", "AVANCE %", "% AVANCE"],
    "fecha_estimada_fin": ["FECHA ESTIMADA DE FIN", "FECHA ESTIMADA", "FECHA_FIN", "FECHA FIN"],
    "reloj": ["RELOJ"],
    "restricciones": ["RESTRICCIONES", "RESTRICCION"],
    "prioridad": ["PRIORIDAD", "PRIORIDADES"],
    "riesgos": ["RIESGOS", "RIESGO"],
    "fecha_respuesta": ["FECHA_RESPUESTA", "FECHA RESPUESTA", "DEADLINE"],
    "carpeta": ["ARCHIVO", "CARPETA", "LINK", "URL", "EVIDENCIA"],
    "cumplimiento": ["CUMPLIMIENTO", "CUMPL.", "CUMP"],
    "comentarios": ["COMENTARIOS", "COMENTARIO", "OBSERVACIONES", "NOTAS"],
    "comentarios_semana": ["COMENTARIOS SEMANA EN CURSO"],
    "comentarios_semana_previa": ["COMENTARIOS PREVIOS", "PREVIOS", "COMENTARIOS SEMANA PREVIA"],
    "status": ["ESTATUS", "STATUS"],
    "hora_alta": ["HORA ALTA", "HORA_ALTA"],
    "hora_estimada_fin": ["HORA ESTIMADA FIN", "HORA_ESTIMADA_FIN"],
}

# Encabezado normalizado -> columna. Se construye una vez: es el diccionario
# que usa `TaskWrite.desde_hoja()` en cada fila de cada lote.
INDICE_ALIAS: Dict[str, str] = indice_de_alias(ALIAS_DE_HOJA)


class TaskWrite(BaseModel):
    """
    Lo que el cliente puede mandar. Ni una columna técnica.

    `extra="forbid"`: si el frontend manda `id` o `dedupe_key` —hoy los
    devuelve la lectura, así que puede reenviarlos en un round-trip ingenuo— la
    petición falla con un 422 explícito en vez de dejar que el cliente reescriba
    la identidad de la fila.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    folio: Optional[str] = None
    assignee_raw: Optional[str] = None
    departamento: Optional[str] = None
    fecha_alta: Optional[date] = None
    hora_alta: Optional[time] = None
    clasificacion: Optional[str] = None
    concepto: Optional[str] = None
    avance: Optional[float] = None
    fecha_estimada_fin: Optional[date] = None
    hora_estimada_fin: Optional[time] = None
    # `reloj` es texto y su contenido es heterogéneo en los datos reales:
    # conviven horas ("17:00:00") y números sueltos ("70.0", "103.0"). Se
    # conserva tal cual; interpretarlo sería inventar.
    reloj: Optional[str] = None
    restricciones: Optional[str] = None
    prioridad: Optional[str] = None
    riesgos: Optional[str] = None
    fecha_respuesta: Optional[date] = None
    carpeta: Optional[str] = None
    cumplimiento: Optional[str] = None
    comentarios: Optional[str] = None
    comentarios_semana: Optional[str] = None
    comentarios_semana_previa: Optional[str] = None
    # `tasks.status` es NOT NULL en el esquema real: escribir nulo aborta el
    # upsert con 23502. La cadena vacía es el "sin estatus" de esta tabla.
    status: Optional[str] = None

    # Metadatos de la petición, no columnas. Viajan con guion bajo igual que en
    # el contrato del frontend y nunca llegan a la base.
    temp_id: Optional[str] = Field(default=None, alias="_tempId")

    @field_validator("avance", mode="before")
    @classmethod
    def _avance_a_escala_0_100(cls, valor: Any) -> Any:
        """
        El número `1` y el string `"1"` entran por aquí y salen distintos.

        Es el único punto donde la distinción de tipo sigue viva: después de
        esta validación el valor está en escala 0-100 y `1` significa 1 %.
        """
        return normalize_avance(valor)

    @field_validator("fecha_alta", "fecha_estimada_fin", "fecha_respuesta", mode="before")
    @classmethod
    def _fecha_de_hoja(cls, valor: Any) -> Any:
        """
        La hoja escribe `dd/mm/yy`, que Pydantic no sabe leer.

        Sin esto, todo guardado que viniera del frontend monolítico moría con un
        422 en la primera fecha, porque `index.html` no manda ISO.
        """
        return a_fecha(valor)

    @field_validator("hora_alta", "hora_estimada_fin", mode="before")
    @classmethod
    def _hora_de_hoja(cls, valor: Any) -> Any:
        return a_hora(valor)

    @classmethod
    def desde_hoja(cls, fila: Dict[str, Any]) -> "TaskWrite":
        """
        Construye el modelo desde una fila con encabezados de hoja.

        Es la entrada del camino legacy (`/api/legacy/saveTrackerBatch`), donde
        las claves llegan como `FOLIO`, `CONCEPTO` o `folio`, mezcladas con
        metadatos del frontend (`_tempId`) y con columnas que esta tabla no
        tiene (`CLIENTE`, `REQUISITOR`, …). Lo que no corresponde a una columna
        de `tasks` se descarta aquí, y solo aquí, en vez de estrellarse contra
        el `extra="forbid"` del modelo.
        """
        columnas = columnas_desde_hoja(fila, INDICE_ALIAS)
        temp_id = fila.get("_tempId") or fila.get("_tempid")
        if temp_id:
            columnas["_tempId"] = temp_id
        return cls.model_validate(columnas)

    def columnas(self) -> Dict[str, Any]:
        """Solo las columnas presentes en la petición, sin los metadatos."""
        crudo = self.model_dump(exclude_none=False, exclude_unset=True, by_alias=False)
        crudo.pop("temp_id", None)
        return crudo


class TaskRead(BaseModel):
    """Una fila de `tasks` tal como sale de la base, con sus tipos."""

    model_config = ConfigDict(extra="allow")

    id: Optional[str] = None
    dedupe_key: Optional[str] = None
    folio: Optional[str] = None
    # Boolean, no texto: marca los 204 folios que generó la migración con la
    # forma "HOJA::ROW1604" (caso 1 de `compute_dedupe_key`).
    folio_sintetico: Optional[bool] = None
    source_sheet: Optional[str] = None
    assignee_raw: Optional[str] = None
    assignee_id: Optional[str] = None
    departamento: Optional[str] = None
    fecha_alta: Optional[date] = None
    hora_alta: Optional[time] = None
    clasificacion: Optional[str] = None
    concepto: Optional[str] = None
    avance: Optional[float] = None
    fecha_estimada_fin: Optional[date] = None
    hora_estimada_fin: Optional[time] = None
    reloj: Optional[str] = None
    restricciones: Optional[str] = None
    prioridad: Optional[str] = None
    riesgos: Optional[str] = None
    fecha_respuesta: Optional[date] = None
    carpeta: Optional[str] = None
    correo: Optional[str] = None
    cumplimiento: Optional[str] = None
    comentarios: Optional[str] = None
    comentarios_semana: Optional[str] = None
    comentarios_semana_previa: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("fecha_alta", "fecha_estimada_fin", "fecha_respuesta", mode="before")
    @classmethod
    def _fecha_tolerante(cls, valor: Any) -> Any:
        """
        Una fecha corrupta no puede tumbar la lectura de la hoja entera.

        Hay al menos una fila real cuyo rango arranca en el año `0202`
        (docs/PLAN_BACKEND_PYTHON.md). Antes salía como texto y nadie se
        enteraba; ahora, con tipos, una fila mala haría fallar el `select` de
        las 4.626. Se degrada a `None` y se conserva el original en
        `TaskRead.model_extra` gracias a `extra="allow"`.
        """
        if valor in (None, ""):
            return None
        if isinstance(valor, (date, datetime)):
            return valor
        try:
            return date.fromisoformat(str(valor)[:10])
        except (ValueError, TypeError):
            return None
