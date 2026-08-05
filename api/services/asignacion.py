"""
Asignación cruzada entre tablas y sincronización bilateral.

Reglas puras, sin I/O, igual que `tracker_rules`: quien las usa
(`tracker_store`) decide cuándo escribir. Aquí solo se responde *qué* hay que
escribir y *dónde*.

Tres decisiones que conviene entender juntas, porque se explican una a otra:

**1. Por qué existe `clave_de_copia()` y no basta `compute_dedupe_key()`.**
Un folio con prefijo de secuencia global (`AV-`, `PPC-`, `TG-`…) es su propia
clave de identidad: `compute_dedupe_key("AV-3250", hoja)` devuelve `"AV-3250"`
sea cual sea la hoja. Eso es correcto para la fila **dueña** —una cotización
`AV-` existe una sola vez— pero convierte en imposible la copia asignada: las
dos filas comparten clave, el upsert las colapsa y `_completar_obligatorias`
fija el `source_sheet` del primero que escribió. La delegación de papa caliente
llevaba así desde siempre: se guardaba sin error y no aparecía en la tabla del
trabajador. La copia necesita una identidad propia por hoja, que es justo el
caso 4 de `compute_dedupe_key` (`"<hoja>::<folio>"`) aplicado a un folio que
por prefijo no habría entrado ahí. Para los folios de persona (`AS-0001`) las
dos funciones coinciden y esta no inventa nada.

**2. Por qué la asignación normal y la papa caliente se separan.**
Se parecen —las dos ponen una fila en la tabla de otro— pero cierran distinto:

* Asignar una actividad es delegarla entera. El 100 % de quien la recibe la
  archiva en las dos tablas.
* La papa caliente delega una **fase** de una cotización. El 100 % de una fase
  no cierra la venta: solo pinta esa fase de verde, y únicamente cuando *todos*
  sus asignados terminaron. Hasta entonces no se delega la siguiente.

La diferencia se detecta por la marca de fase en el CONCEPTO
(`"Cotizar nave [Calculo y Diseño]"`), que es la que ya escribe
`apply_hot_potato`. No hace falta una bandera nueva.

**3. Por qué `ANTONIA_VENTAS` nunca es destino.**
Es la tabla de ventas, no la tabla de una persona: solo Toñita escribe ahí
(`resolve_tracker_target`, "La Ley de Antonia"). Una actividad asignada "a
Antonia" es trabajo suyo y va a su tracker personal, que es otra tabla.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from api.services.tracker_rules import (
    ANTONIA_PERSONAL_SHEET,
    PROCESS_STEPS,
    SALES_MASTER_SHEET,
    extract_phase_from_concepto,
    normalize_header,
    normalize_phase_id,
    normalize_staff_name,
    parse_proceso_log,
    pick_task_value,
)

# Columnas cuyo valor viaja entre las copias de una misma actividad.
#
# Son las tres que deciden el archivado (`is_row_complete`) más COMENTARIOS,
# que es donde se cuenta el porqué. Deliberadamente **no** viajan CONCEPTO
# —quien recibe reescribiría el texto de quien asignó— ni RESPONSABLE, que
# reasignaría la copia a sí misma en un bucle.
CAMPOS_BILATERALES = ("AVANCE", "ESTATUS", "CUMPLIMIENTO", "COMENTARIOS")

# Alias de encabezado por los que puede llegar cada campo bilateral.
_ALIAS_BILATERALES: Dict[str, List[str]] = {
    "AVANCE": ["AVANCE", "AVANCE %", "% AVANCE"],
    "ESTATUS": ["ESTATUS", "STATUS"],
    "CUMPLIMIENTO": ["CUMPLIMIENTO", "CUMPL.", "CUMP"],
    "COMENTARIOS": ["COMENTARIOS", "COMENTARIO", "OBSERVACIONES", "NOTAS"],
}

# Los tres que justifican por sí solos una escritura en la otra tabla. Un
# cambio solo en COMENTARIOS no dispara la sincronización: no altera el estado
# de nadie y multiplicaría las escrituras por cada tecleo.
_CAMPOS_QUE_DISPARAN = ("AVANCE", "ESTATUS", "CUMPLIMIENTO")

# Metadatos del frontend. Nunca se copian: `_tempId` identifica el evento de UI
# que creó la fila en la tabla de origen, y arrastrarlo haría que el gatekeeper
# tomara la copia por un duplicado de aquella alta y la descartara en silencio.
PREFIJO_METADATO = "_"

# Encabezados por los que puede llegar la columna de responsable.
_ENCABEZADOS_RESPONSABLE = frozenset({
    "RESPONSABLE", "RESPONSABLES", "INVOLUCRADOS", "VENDEDOR", "ENCARGADO", "ASIGNADO",
})


def clave_de_copia(folio: Any, hoja: Any) -> Optional[str]:
    """
    Identidad de una copia asignada: siempre `"<hoja>::<folio>"`.

    A diferencia de `compute_dedupe_key`, no consulta el prefijo: una copia se
    identifica por la tabla en la que vive, y ese es el punto. El nombre de
    hoja va sin recortar, igual que en la función original, porque hay hojas
    reales con espacio inicial y la clave almacenada lo conserva.
    """
    crudo = "" if folio is None else str(folio)
    limpio = crudo.strip()
    if not limpio:
        return None
    return ("" if hoja is None else str(hoja)) + "::" + limpio


def es_delegacion_de_fase(task: Dict[str, Any]) -> bool:
    """
    ¿Esta fila es una microtarea de papa caliente y no una actividad completa?

    Se responde por la marca de fase del CONCEPTO, que es la que escribe
    `apply_hot_potato` (`"Cotizar nave [Calculo y Diseño]"`), con el PROCESO
    explícito como respaldo para las filas que aún no la traen.
    """
    if not task:
        return False
    concepto = pick_task_value(task, ["CONCEPTO", "DESCRIPCION"])
    if extract_phase_from_concepto(concepto):
        return True
    explicito = task.get("_assignStep") or pick_task_value(task, ["PROCESO", "ETAPA", "FASE"])
    return bool(normalize_phase_id(explicito))


def hoja_de_persona(nombre: Any) -> str:
    """
    Tabla en la que trabaja una persona.

    Normaliza el sufijo `(VENTAS)` —"GERALDINE (VENTAS)" y "GERALDINE" son la
    misma persona y comparten tabla— y traduce el único nombre que no es una
    persona: `ANTONIA_VENTAS` es la tabla de ventas, y el trabajo que se le
    asigna a Antonia va a su tracker personal.
    """
    limpio = normalize_staff_name(nombre)
    if not limpio:
        return ""
    if limpio == normalize_staff_name(SALES_MASTER_SHEET):
        return ANTONIA_PERSONAL_SHEET
    return limpio


def responsables_de(task: Dict[str, Any]) -> List[str]:
    """Los nombres de la columna RESPONSABLE/INVOLUCRADOS, en orden y sin repetir."""
    crudo = pick_task_value(task, ["RESPONSABLE", "RESPONSABLES", "INVOLUCRADOS",
                                   "VENDEDOR", "ENCARGADO", "ASIGNADO"])
    if not crudo:
        return []
    nombres: List[str] = []
    for parte in str(crudo).replace("\n", ",").replace(";", ",").split(","):
        nombre = parte.strip()
        if nombre and nombre not in nombres:
            nombres.append(nombre)
    return nombres


def destinos_espejo(hoja_origen: Any, task: Dict[str, Any]) -> List[str]:
    """
    Tablas que deben recibir una copia de esta actividad.

    Es la lista de responsables menos el dueño de la hoja donde ya se está
    guardando: asignarse algo a uno mismo no duplica la fila. La papa caliente
    no pasa por aquí —tiene su propio reparto en `apply_hot_potato`, con fases
    y concepto marcado—, así que las microtareas se excluyen.
    """
    if es_delegacion_de_fase(task):
        return []

    propia = hoja_de_persona(hoja_origen) or normalize_staff_name(hoja_origen)
    destinos: List[str] = []
    for nombre in responsables_de(task):
        hoja = hoja_de_persona(nombre)
        if not hoja or hoja == propia or hoja in destinos:
            continue
        destinos.append(hoja)
    return destinos


def cambia_el_responsable(task: Dict[str, Any], responsable_actual: Any) -> bool:
    """
    ¿Esta captura está reasignando la actividad, o solo trabajándola?

    Compara conjuntos de nombres normalizados, no cadenas: "GERALDINE (VENTAS)"
    y "geraldine" son la misma persona, y "MIGUEL, ANA" y "ANA, MIGUEL" son la
    misma asignación escrita en otro orden.

    Si la captura no trae RESPONSABLE no hay reasignación: guardar sin tocar esa
    columna es lo más común que existe. Lo mismo aplica a "Guardar todo", que
    reenvía la tabla entera con el responsable intacto; si esto mirara solo la
    presencia de la columna, quien recibió una actividad no podría guardar nunca.
    """
    if not any(normalize_header(k) in _ENCABEZADOS_RESPONSABLE for k in (task or {})):
        return False
    nuevos = {normalize_staff_name(n) for n in responsables_de(task)}
    actuales = {normalize_staff_name(n)
                for n in responsables_de({"RESPONSABLE": responsable_actual})}
    return bool(nuevos) and nuevos != actuales


def construir_espejo(hoja_origen: Any, task: Dict[str, Any], destino: Any,
                     username: str = "") -> Dict[str, Any]:
    """
    La fila tal como debe quedar en la tabla de quien recibe la asignación.

    Conserva folio, concepto y estado —es la misma actividad, no una nueva— y
    descarta los metadatos del frontend.

    No lleva ninguna marca de "quién me asignó": el vínculo entre las copias es
    el **folio**, que ya viaja en la fila y sí está en la base. Un metadato con
    guion bajo no sobrevive al guardado (no es columna de `tasks`), así que en
    la siguiente edición desde la tabla de quien recibió no habría forma de
    volver. Buscar por folio no tiene ese problema y no añade estado nuevo.
    """
    espejo = {
        clave: valor
        for clave, valor in (task or {}).items()
        if not str(clave).startswith(PREFIJO_METADATO)
    }

    quien = normalize_staff_name(username)
    origen = normalize_staff_name(hoja_origen)
    nota = f"Asignada desde {origen}"
    if quien and quien != origen:
        nota += f" por {quien}"
    anterior = str(espejo.get("COMENTARIOS") or "").strip()
    espejo["COMENTARIOS"] = f"{anterior} · {nota}" if anterior else nota

    # El destino manda sobre lo que trajera la fila: la copia de Geraldine dice
    # que es de Geraldine aunque el original listara a varios responsables.
    if destino:
        espejo["RESPONSABLE"] = str(destino)
    return espejo


def campos_sincronizables(task: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Lo que hay que escribir en las otras copias de esta actividad.

    Devuelve `None` cuando no hay nada que propagar, que es el caso normal:
    editar el concepto o una fecha no toca el estado de nadie y no justifica
    escribir en la tabla de otra persona.

    Y devuelve `None` **siempre** para una microtarea de papa caliente. Las
    copias de una fase comparten folio con la cotización y entre sí, así que
    propagar por folio pondría el 100 % de Miguel encima de la microtarea de
    Rolando. Son trabajos distintos de la misma cotización: cada quien reporta
    lo suyo y la fase se pinta verde cuando están todos. Lo que sí llega a la
    maestra es el timeline, por la vía del reverse sync.
    """
    if es_delegacion_de_fase(task):
        return None

    folio = pick_task_value(task or {}, ["FOLIO", "ID"])
    if not folio or not str(folio).strip():
        return None

    presentes: Dict[str, Any] = {}
    for campo in CAMPOS_BILATERALES:
        valor = pick_task_value(task, _ALIAS_BILATERALES[campo])
        if valor not in (None, ""):
            presentes[campo] = valor

    if not any(campo in presentes for campo in _CAMPOS_QUE_DISPARAN):
        return None

    presentes["FOLIO"] = str(folio).strip()
    return presentes


# ----------------------------------------------------------------------
# PAPA CALIENTE: cuándo una fase está verde
# ----------------------------------------------------------------------

def _entradas_de_fase(log: Any, paso: str) -> List[Dict[str, Any]]:
    """
    Entradas del PROCESO_LOG que hablan de un paso.

    Acepta `step` y `to` porque las dos formas conviven en los datos reales:
    `to` es la del log original de `CODIGO.js` y `step` la que escribe
    `upsert_proceso_log_entry`. Es el mismo criterio de `build_map_cot`.
    """
    return [e for e in parse_proceso_log(log)
            if e.get("step") == paso or e.get("to") == paso]


def fase_completa(log: Any, paso: Any) -> bool:
    """
    ¿Terminaron **todos** los asignados de esa fase?

    Una fase sin delegar no está completa: no hay nada terminado, hay nada
    empezado. La distinción importa para `puede_delegar`, que solo bloquea por
    fases que de verdad se repartieron.
    """
    normalizado = normalize_phase_id(paso)
    if not normalizado:
        return False
    entradas = _entradas_de_fase(log, normalizado)
    if not entradas:
        return False
    return all(str(e.get("status", "")).upper() == "DONE" for e in entradas)


def fases_abiertas(log: Any) -> List[str]:
    """Fases ya repartidas a las que todavía les falta alguien, en orden de proceso."""
    return [paso for paso in PROCESS_STEPS
            if _entradas_de_fase(log, paso) and not fase_completa(log, paso)]


def puede_delegar(log: Any, paso_nuevo: Any) -> bool:
    """
    ¿Se puede repartir esta fase, o hay una anterior sin cerrar?

    Sumar a alguien a la fase **en curso** siempre se puede: eso no es "pasar a
    la siguiente delegación", es reforzar la actual. Lo que se bloquea es
    saltar a una fase posterior dejando una abierta detrás.
    """
    normalizado = normalize_phase_id(paso_nuevo)
    if not normalizado:
        return False
    if normalizado not in PROCESS_STEPS:
        return True

    posicion = PROCESS_STEPS.index(normalizado)
    for abierta in fases_abiertas(log):
        if abierta == normalizado:
            continue
        if PROCESS_STEPS.index(abierta) < posicion:
            return False
    return True


def bloqueo_de_fase(log: Any, paso_nuevo: Any) -> str:
    """Mensaje de por qué no se puede delegar, o cadena vacía si sí se puede."""
    if puede_delegar(log, paso_nuevo):
        return ""
    pendientes = [p for p in fases_abiertas(log) if p != normalize_phase_id(paso_nuevo)]
    faltan = ", ".join(_quien_falta(log, p) for p in pendientes)
    return (f"No se puede delegar {normalize_phase_id(paso_nuevo)}: "
            f"la fase {pendientes[0]} sigue abierta ({faltan}).")


def _quien_falta(log: Any, paso: str) -> str:
    nombres = [str(e.get("assignee") or "?").strip()
               for e in _entradas_de_fase(log, paso)
               if str(e.get("status", "")).upper() != "DONE"]
    return f"{paso}: falta " + ", ".join(nombres) if nombres else paso


def sin_campos_de_cierre(fila: Dict[str, Any], campos: Iterable[str]) -> Dict[str, Any]:
    """Copia de la fila sin las columnas indicadas, comparando por encabezado normalizado."""
    prohibidos = {normalize_header(c) for c in campos}
    return {k: v for k, v in (fila or {}).items() if normalize_header(k) not in prohibidos}
