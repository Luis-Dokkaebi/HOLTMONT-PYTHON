"""
Los esquemas que el agente SQL le describe al modelo, derivados de la base.

El bloque de columnas de cada prompt **no se escribe a mano**: se genera desde
`backend/schemas/task.py::TIPOS_REALES` y `backend/schemas/quote.py::TIPOS_REALES`,
que son los mismos diccionarios que `scripts/verificar_base_tasks.py` y
`scripts/verificar_base_quotes.py` comprueban contra Postgres. Un prompt escrito
a mano se desincroniza del esquema en silencio y el agente empieza a inventar
columnas; uno derivado falla ruidosamente cuando la base cambia, porque la
verificación ya existente lo detecta.

**Por qué esto importa aquí en concreto.** El notebook de origen
(`AgenteSQL_task_quotes_correo.ipynb`) describía las fechas de `tasks` como
`TEXT` en formato ISO y le ordenaba al modelo compararlas como cadenas:

    "Para filtrar por rangos, NO uses CAST (...). Compara directamente como
     cadenas de texto (ej. `WHERE fecha_alta >= '2026-01-01'`)"

En la tabla real `fecha_alta` es `date`, `hora_alta` es `time` y `avance` es
`numeric`. Esas instrucciones no eran una simplificación: eran falsas, y el
modelo las habría seguido. El notebook consultaba `tasks_rows_sql`, una copia
suelta; aquí se consulta `tasks`, que es la tabla que la aplicación escribe.

Las notas semánticas —qué significa una columna, qué basura de captura tiene—
sí vienen del notebook, porque eso es conocimiento del negocio que no está en
el tipo de dato y que su autor midió sobre los datos reales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ----------------------------------------------------------------------
# Notas semánticas por columna
# ----------------------------------------------------------------------
# Lo que el tipo de dato no dice. Portadas del notebook y ajustadas donde el
# esquema real las contradecía.

NOTAS_TASKS: Dict[str, str] = {
    "id": "Identificador interno de la tarea.",
    "folio": "Referencia pública de la tarea (ej. PPC-866957543, AV-1192).",
    "dedupe_key": "Clave con la que el sistema desduplica filas. No es de negocio.",
    "folio_sintetico": "true si el folio lo generó la migración, false si es real.",
    "assignee_id": "Identificador de la persona asignada.",
    "assignee_raw": (
        "Nombre de la persona asignada. ATENCIÓN: a veces trae varios nombres "
        "separados por comas en un solo registro."
    ),
    "departamento": (
        "Área encargada (FINANZAS, HVAC, CONSTRUCCION, RH...). ATENCIÓN: por "
        "errores de captura a veces contiene el nombre de una persona."
    ),
    "fecha_alta": "Fecha en que se registró la tarea.",
    "hora_alta": "Hora en que se registró la tarea.",
    "clasificacion": "Categoría o nivel de la tarea (A, AA, AAA, Media).",
    "concepto": "Descripción de la actividad: de qué trata la tarea.",
    "avance": "Porcentaje de progreso, de 0 a 100.",
    "fecha_estimada_fin": "Fecha límite para terminar la tarea.",
    "hora_estimada_fin": "Hora límite para terminar.",
    "reloj": (
        "Tiempo invertido. ADVERTENCIA: columna heterogénea; mezcla horas "
        "('00:00:00') con decimales ('7.0', '283.0'). NO la sumes ni la "
        "promedies; úsala solo para mostrar o para comprobar si existe."
    ),
    "restricciones": "Obstáculos o bloqueos detectados para completar la tarea.",
    "prioridad": (
        "Urgencia (ALTA, MEDIA, BAJA, URGENTE, NORMAL, ESTRATEGICA). Varía la "
        "capitalización entre filas."
    ),
    "riesgos": (
        "Nivel de riesgo (ALTO, MEDIO, BAJO, CATASTROFICO). Varía la "
        "capitalización y hay valores con y sin tilde."
    ),
    "fecha_respuesta": "Fecha de la última atención o respuesta técnica.",
    "correo": (
        "NO es un buzón: guarda enlaces de documentos (Drive, Sheets), igual "
        "que `carpeta`. Nunca la uses para buscar direcciones de correo."
    ),
    "carpeta": "Enlaces a los archivos o expedientes de la tarea.",
    "cumplimiento": "Indicador de cumplimiento o periodicidad (NO, MENSUAL).",
    "comentarios": "Observaciones generales.",
    "comentarios_semana": "Avances reportados en la semana en curso.",
    "comentarios_semana_previa": "Avances reportados la semana anterior.",
    "status": (
        "Estado del flujo (ASIGNADO, PENDIENTE, PENDIENTE VISITA...). "
        "ADVERTENCIA: hay ruido de captura, como roles o saltos de línea."
    ),
    "source_sheet": (
        "Hoja de origen: de quién es la fila. Junto con `dedupe_key` forma la "
        "identidad de la tarea; la misma actividad puede estar en la hoja de "
        "quien la reparte y en la de quien la trabaja."
    ),
    "created_at": "Cuándo se creó la fila en el servidor. NO es la fecha de la tarea.",
}

NOTAS_QUOTES: Dict[str, str] = {
    "folio": (
        "Referencia de la cotización. ATENCIÓN: hay prefijos (AV-0022) y "
        "sufijos '.0' heredados de Excel (10.0, 1013.0). Para un folio "
        "numérico usa `folio ILIKE '%10%'` o `folio IN ('10', '10.0')`."
    ),
    "area": "Área encargada: HVAC, CONSTRUCCION, ELECTROMECANICA, VENTAS, ADMINISTRACION, LIMPIEZA.",
    "cliente": (
        "Nombre del cliente. Hay variantes del mismo: 'PANASONIC', "
        "'PANASONIC MTY', 'PANASONIC NORTE'. Usa siempre ILIKE con comodines."
    ),
    "concepto": "Descripción de la cotización.",
    "clasificacion": "Categoría (AAA, AA, A). Muchos nulos: usa COALESCE al agrupar.",
    "vendedor_id": "Identificador del vendedor.",
    "vendedor_raw": (
        "Nombres de vendedores. A menudo trae varios separados por comas "
        "('ALFONSO CORREA, TERESA GARZA'). Usa siempre ILIKE."
    ),
    "f_visita": "Fecha de la visita. Muchas vacías.",
    "f_inicio": "Fecha de inicio. Muchas vacías.",
    "f_entrega": "Fecha de entrega. Muchas vacías.",
    "dias": (
        "Días transcurridos. ADVERTENCIA: hay errores de importación de Excel "
        "donde una fecha quedó guardada como número gigante (ej. 36558). Al "
        "promediar o sumar, excluye los valores atípicos: `WHERE dias < 1000`."
    ),
    "avance": "Porcentaje de progreso, de 0 a 100.",
    "estatus": (
        "Estado del flujo: PENDIENTE, PENDIENTE INFORMACION, PENDIENTE VISITA, "
        "SUSPENDIDA, ASIGNADO, CANCELADA, PERDIDA POR TIEMPO, EN REVISION, "
        "ENVIADA. Hay muchos nulos."
    ),
    "comentarios": "Observaciones libres.",
    "requisitor": "Quien solicitó la cotización.",
    "prioridad_cot": "Urgencia de la cotización (ALTA, MEDIA).",
    "info_cliente": "Información adicional del cliente.",
    "cotizacion": "Enlaces o referencias al documento de la cotización.",
    "monto": "Monto económico. Mayoritariamente nulo en la base.",
    "source_sheet": (
        "Hoja de origen. IMPORTANTE: la clave de esta tabla es "
        "(folio, source_sheet), así que la MISMA cotización puede aparecer en "
        "dos filas —la de quien la reparte y la del vendedor—. Para contar "
        "cotizaciones distintas usa COUNT(DISTINCT folio), no COUNT(*)."
    ),
    "created_at": (
        "Fecha de MIGRACIÓN de la fila a la base, no de la cotización. Para "
        "fechas reales usa f_visita, f_inicio o f_entrega."
    ),
    "estatus_2": (
        "Semáforo de procesos con emojis y códigos ('🟢 L | 🟡 CD | ⚪ EP'). "
        "L=Levantamiento, CD=Cálculo y Diseño, EP=Envío de Propuesta."
    ),
    "proceso_log": "JSON con el historial de pasos y asignados.",
    "completada": "true si la cotización se dio por terminada.",
}

# Columnas secundarias o redundantes: se listan con su tipo pero se le dice al
# modelo que las ignore salvo mención explícita. Es la misma advertencia del
# notebook, que las agrupaba en una sola línea.
SECUNDARIAS_QUOTES: frozenset = frozenset(
    {"f2", "timeline", "layout", "proceso", "map_cot", "extra", "archivo",
     "fecha", "comentario", "fecha_envio", "dias_2", "llamada_cliente", "reloj"}
)


# ----------------------------------------------------------------------
# Reglas de inferencia
# ----------------------------------------------------------------------

REGLAS_COMUNES: Tuple[str, ...] = (
    "Insensibilidad a mayúsculas y tildes: los datos se capturaron a mano y "
    "varían ('ALTA' vs 'Alta', 'CATASTROFICO' vs 'Catastrófico'). Usa SIEMPRE "
    "ILIKE con comodines para cualquier filtro de texto. Si el valor puede "
    "llevar tilde, incluye las dos variantes con OR.",
    "Nulos en agrupaciones: al hacer GROUP BY o COUNT por una categoría, usa "
    "COALESCE(columna, 'Sin Especificar') para no perder las filas sin dato.",
    "Nombres de columnas exactos: usa solo los nombres listados arriba. No "
    "inventes columnas, no las abrevies y no las truques.",
    "Fechas y horas son tipos nativos de Postgres (date, time, timestamptz), "
    "no texto. Compáralas con literales de fecha ('2026-01-01') o con "
    "funciones de fecha; usa DATE_TRUNC o EXTRACT para agrupar por mes o año. "
    "No uses SUBSTRING sobre ellas.",
    "Avance es numeric: compáralo con números (avance < 100, avance >= 90). "
    "Completado es avance = 100; en curso es avance < 100. Usa COALESCE(avance, 0) "
    "si necesitas asumir cero.",
)

REGLAS_TASKS: Tuple[str, ...] = (
    "Búsqueda de personas: `assignee_raw` puede traer varios nombres en una "
    "sola fila y algunos nombres acabaron en `departamento` por errores de "
    "captura. Si se busca a una persona, usa SIEMPRE "
    "`(assignee_raw ILIKE '%nombre%' OR departamento ILIKE '%nombre%')`.",
    "Temas y descripciones libres: cuando se pregunte de qué trata una tarea, "
    "busca en `concepto` con ILIKE.",
)

REGLAS_QUOTES: Tuple[str, ...] = (
    "Búsqueda de personas y clientes: usa siempre ILIKE con comodines, porque "
    "`vendedor_raw` puede traer varios nombres y `cliente` tiene variantes del "
    "mismo nombre.",
    "Para contar cotizaciones distintas usa COUNT(DISTINCT folio): la clave de "
    "la tabla es (folio, source_sheet) y la misma cotización vive en dos filas.",
    "Al promediar o sumar `dias`, excluye los atípicos de Excel: "
    "`AVG(CASE WHEN dias < 1000 THEN dias END)`.",
)

RESTRICCIONES_DE_SEGURIDAD: str = """RESTRICCIONES DE SEGURIDAD (el servidor las verifica y rechaza lo que no cumpla):
1. SOLO puedes generar sentencias SELECT (o WITH ... SELECT).
2. SOLO puedes leer la tabla {tabla}. Cualquier otra tabla se rechaza.
3. Una sola sentencia por respuesta. Nada de punto y coma intermedio.
4. Responde ÚNICAMENTE con el SQL dentro de un bloque markdown (```sql ... ```),
   sin explicaciones, saludos ni texto antes o después."""


# ----------------------------------------------------------------------
# El esquema
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class Esquema:
    """
    Todo lo que el agente necesita saber de una tabla.

    Inmutable a propósito: se comparte entre peticiones y una mutación
    accidental cambiaría el prompt de todos los usuarios siguientes.
    """

    clave: str
    tabla: str
    etiqueta: str
    tipos: Dict[str, str]
    notas: Dict[str, str]
    reglas: Tuple[str, ...]
    secundarias: frozenset = field(default=frozenset())

    def bloque_columnas(self) -> str:
        """Una línea por columna: `- nombre (tipo): nota`."""
        lineas = []
        for columna, tipo in self.tipos.items():
            nota = self.notas.get(columna, "")
            if not nota and columna in self.secundarias:
                nota = "Columna secundaria o redundante: ignórala salvo mención explícita."
            lineas.append(f"- {columna} ({tipo}): {nota}".rstrip())
        return "\n".join(lineas)

    def prompt_sistema(self) -> str:
        """El prompt del nodo generador de SQL."""
        reglas = "\n".join(
            f"{i}. {regla}" for i, regla in enumerate(self.reglas, start=1)
        )
        return (
            "Eres un Data Architect experto en PostgreSQL.\n"
            "Tu ÚNICA tarea es traducir la petición del usuario a una consulta "
            "SQL válida.\n\n"
            f"Esquema de la tabla {self.tabla} ({self.etiqueta}):\n"
            f"{self.bloque_columnas()}\n\n"
            "Reglas de inferencia (léelas antes de escribir):\n"
            f"{reglas}\n\n"
            f"{RESTRICCIONES_DE_SEGURIDAD.format(tabla=self.tabla)}"
        )


def _construir_esquemas() -> Dict[str, Esquema]:
    """
    Se arma al importar, leyendo los tipos de `backend/schemas/`.

    El import es diferido dentro de la función para que un fallo al cargar
    `backend` dé un error con nombre en vez de romper el import del módulo.
    """
    from backend.schemas.quote import TIPOS_REALES as TIPOS_QUOTES
    from backend.schemas.task import TIPOS_REALES as TIPOS_TASKS

    return {
        "tasks": Esquema(
            clave="tasks",
            tabla="tasks",
            etiqueta="las actividades del Tracker",
            tipos=dict(TIPOS_TASKS),
            notas=NOTAS_TASKS,
            reglas=REGLAS_COMUNES + REGLAS_TASKS,
        ),
        "quotes": Esquema(
            clave="quotes",
            tabla="quotes",
            etiqueta="las cotizaciones de las hojas de ventas",
            tipos=dict(TIPOS_QUOTES),
            notas=NOTAS_QUOTES,
            reglas=REGLAS_COMUNES + REGLAS_QUOTES,
            secundarias=SECUNDARIAS_QUOTES,
        ),
    }


ESQUEMAS: Dict[str, Esquema] = _construir_esquemas()

# Las únicas tablas que el agente puede leer. Se deriva de `ESQUEMAS` y no se
# escribe aparte: una lista blanca que hay que actualizar en dos sitios acaba
# desactualizada justo en el sitio que importa.
TABLAS_PERMITIDAS: frozenset = frozenset(e.tabla for e in ESQUEMAS.values())


def esquema(clave: str) -> Optional[Esquema]:
    """El esquema por su clave, o `None` si no existe. No lanza."""
    return ESQUEMAS.get(str(clave or "").strip().lower())


def claves_disponibles() -> List[str]:
    """Las claves de esquema que acepta el agente, para el contrato de la API."""
    return sorted(ESQUEMAS)
