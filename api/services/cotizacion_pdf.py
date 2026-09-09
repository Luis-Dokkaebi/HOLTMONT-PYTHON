"""
La cotización de una Pre Work Order, en PDF, archivada con la orden.

Pedido del dueño (2026-09-09):

    «Quiero que la cotización se transforme en un PDF y se guarde en los
    documentos de esa línea del tracker, en la sección de carpeta [...] es para
    que no se pierda toda la información que se va a trabajar.»

El problema que resuelve es de pérdida de información, no de formato. Hasta
ahora, todo lo que se captura en la Pre Work Order —materiales, herramientas,
mano de obra, equipo, programa y totales— se reparte al guardar entre cinco
tablas hijas (`wo_materiales`, `wo_herramientas`, `wo_mano_obra`, `wo_equipos`,
`wo_programa`) y ninguna pantalla las vuelve a juntar: quien abre la línea del
tracker ve la tarea, no la cotización que la originó. El único documento que
recomponía todo era la nota de Obsidian (`save_to_obsidian`), que en serverless
vive lo que vive el proceso.

Aquí ese mismo contenido se emite como PDF, se sube a Storage bajo
`AÑO/MES/CLIENTE/` —el mismo árbol donde vive el resto de los adjuntos— y su
URL se anexa a `archivoUrl`, que es lo que la fila del tracker guarda en la
columna **CARPETA** (alias de `carpeta`; ver `backend/schemas/task.py`) y lo que
heredan las tareas derivadas del programa (`tareas_de_programa`).

Dos decisiones que valen la pena leer antes de tocar esto:

* **El PDF se suma, no sustituye.** `archivoUrl` ya trae lo que subió la
  persona (la cotización del cliente, los planos). El PDF se añade al final de
  esa lista; borrar lo que subió un humano para poner algo generado sería
  exactamente la pérdida de información que este cambio quiere evitar.

* **Un fallo aquí no tumba el guardado.** Si Storage no está configurado o la
  subida falla, la orden se guarda igual y el problema viaja como *aviso* en la
  respuesta. Perder la orden entera por no poder archivar su PDF sería un
  cambio a peor.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Porcentaje de utilidad del tablero de la Pre Work Order.
#
# Solo se usa cuando el formulario no manda sus totales ya calculados
# (`item["totales"]`), que es el caso normal. La regla vive en `index.html`
# (`dashboardUtility`); aquí está el respaldo para los llamadores que no la
# traen —la API, un script— y para que el PDF nunca salga sin gran total.
PORCENTAJE_UTILIDAD_POR_DEFECTO = 0.15

# El PDF se emite con las fuentes base de PDF (Helvetica), que son latin-1.
# El español cabe entero ahí —acentos, ñ, ¿, ¡, símbolos de moneda— pero un
# emoji o un carácter cirílico pegado en una descripción reventaría la emisión
# con `UnicodeEncodeError`. Se sustituyen por '?' antes de escribir: un
# interrogante en una descripción es un defecto cosmético; una excepción a
# mitad del guardado es la orden sin archivar.
CODIFICACION_PDF = "latin-1"


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def _latin1(valor: Any) -> str:
    return _texto(valor).encode(CODIFICACION_PDF, "replace").decode(CODIFICACION_PDF)


def _numero(valor: Any, por_defecto: float = 0.0) -> float:
    """Número de un campo del formulario, que siempre llega como cadena."""
    texto = _texto(valor).replace(",", "").replace("$", "")
    if not texto:
        return por_defecto
    try:
        return float(texto)
    except ValueError:
        return por_defecto


def _moneda(valor: Any) -> str:
    return f"${_numero(valor):,.2f}"


def _filas_con_datos(filas: Optional[Iterable[Dict[str, Any]]],
                     campos: Sequence[str]) -> List[Dict[str, Any]]:
    """Las filas que tienen algo escrito en alguno de esos campos.

    El formulario arranca cada tabla con un renglón de ejemplo en blanco. Sin
    este filtro el PDF saldría con una fila de ceros en cada bloque, que es
    ruido en un documento que alguien va a leer para cotizar.
    """
    con_datos = []
    for fila in filas or []:
        if any(_texto(fila.get(campo)) for campo in campos):
            con_datos.append(fila)
    return con_datos


def _total_de(filas: Iterable[Dict[str, Any]]) -> float:
    return sum(_numero(f.get("total")) for f in filas)


def totales_de_la_orden(item: Dict[str, Any]) -> Dict[str, float]:
    """Subtotal, utilidad y gran total de la orden.

    Usa los que mandó el formulario (`item["totales"]`) si vienen: ahí el
    tablero es la fuente de verdad y el PDF debe decir el mismo número que vio
    quien cotizó. Si no vienen, se calculan desde las filas.
    """
    materiales = _filas_con_datos(item.get("materiales"), ("description", "cost", "quantity"))
    herramientas = _filas_con_datos(item.get("herramientas"), ("description", "cost", "quantity"))
    mano_obra = _filas_con_datos(item.get("manoObra"), ("category", "salary"))
    equipos = _filas_con_datos(item.get("equipos"), ("description", "cost", "quantity"))

    extras = item.get("additionalCosts") or {}
    adicionales = sum(_numero(extras.get(k)) for k in ("insumos", "viaticos", "transporte"))

    por_tabla = {
        "materiales": _total_de(materiales),
        "herramientas": _total_de(herramientas),
        "mano_obra": _total_de(mano_obra),
        "equipos": _total_de(equipos),
        "adicionales": adicionales,
    }

    del_formulario = item.get("totales") or {}
    if _texto(del_formulario.get("subtotal")) != "":
        subtotal = _numero(del_formulario.get("subtotal"))
        utilidad = _numero(del_formulario.get("utilidad"))
        total = _numero(del_formulario.get("total"), subtotal + utilidad)
    else:
        subtotal = sum(por_tabla.values())
        utilidad = subtotal * PORCENTAJE_UTILIDAD_POR_DEFECTO
        total = subtotal + utilidad

    por_tabla.update({"subtotal": subtotal, "utilidad": utilidad, "total": total})
    return por_tabla


def nombre_de_archivo(folio: Any) -> str:
    """`COTIZACION 1001AC Electro 090926.pdf`.

    Lleva el folio porque es el nombre con el que alguien lo va a buscar entre
    los adjuntos de la línea, y porque `storage.ruta_de_archivo` le añade una
    marca de tiempo: dos versiones de la misma orden conviven en vez de
    pisarse.
    """
    limpio = _texto(folio) or "SIN FOLIO"
    return f"COTIZACION {limpio}.pdf"


# --- Emisión del documento --------------------------------------------------

_CABECERA = (
    ("Cliente", "cliente"),
    ("Especialidad", "especialidad"),
    ("Clasificacion", "clasificacion"),
    ("Prioridad", "prioridad"),
    ("Elaboro", "responsable"),
    ("Requisitor", "requisitor"),
    ("Contacto", "contacto"),
    ("Celular", "celular"),
    ("Tipo de trabajo", "TRABAJO"),
    ("Fecha de entrega", "fechaRespuesta"),
)

# Cada bloque: título, campos de la fila que lo dan por vacío, y columnas
# (encabezado, clave, ancho en mm, alineación).
_BLOQUES: Tuple[Tuple[str, str, Tuple[str, ...], Tuple[Tuple[str, str, int, str], ...]], ...] = (
    ("MATERIALES REQUERIDOS", "materiales", ("description", "cost", "quantity"),
     (("Cant", "quantity", 15, "R"), ("Unidad", "unit", 20, "L"),
      ("Descripcion", "description", 95, "L"), ("Costo", "cost", 25, "R"),
      ("Total", "total", 30, "R"))),
    ("HERRAMIENTAS REQUERIDAS", "herramientas", ("description", "cost", "quantity"),
     (("Cant", "quantity", 15, "R"), ("Unidad", "unit", 20, "L"),
      ("Descripcion", "description", 95, "L"), ("Costo", "cost", 25, "R"),
      ("Total", "total", 30, "R"))),
    ("MANO DE OBRA", "manoObra", ("category", "salary"),
     (("Categoria", "category", 60, "L"), ("Salario", "salary", 25, "R"),
      ("Personal", "personnel", 25, "R"), ("Tiempo", "weeks", 25, "R"),
      ("Unidad", "unit", 20, "L"), ("Total", "total", 30, "R"))),
    ("EQUIPO ESPECIAL", "equipos", ("description", "cost", "quantity"),
     (("Cant", "quantity", 15, "R"), ("Unidad", "unit", 20, "L"),
      ("Descripcion", "description", 80, "L"), ("Dias", "days", 15, "R"),
      ("Costo", "cost", 25, "R"), ("Total", "total", 30, "R"))),
    ("PROGRAMA DEL PROYECTO", "programa", ("DESCRIPCION", "description", "RESPONSABLE"),
     (("Seccion", "seccion", 32, "L"), ("Descripcion", "DESCRIPCION", 78, "L"),
      ("Fecha", "FECHA", 25, "L"), ("Responsable", "RESPONSABLE", 35, "L"),
      ("Total", "TOTAL", 25, "R"))),
)

_COLUMNAS_DE_MONEDA = {"cost", "salary", "total", "TOTAL", "PRECIO"}


def _valor_de_celda(fila: Dict[str, Any], clave: str) -> str:
    valor = fila.get(clave)
    if valor is None and clave == "DESCRIPCION":
        valor = fila.get("description")
    if clave in _COLUMNAS_DE_MONEDA:
        return _moneda(valor)
    return _latin1(valor)


def construir_pdf(item: Dict[str, Any], folio: Any) -> bytes:
    """El PDF de la cotización: cabecera, los cuatro bloques, programa y totales.

    Devuelve los bytes. No sube nada ni toca la base: así se puede probar el
    documento sin Storage, y `archivar` se queda con una sola responsabilidad.
    """
    from fpdf import FPDF

    totales = totales_de_la_orden(item)

    pdf = FPDF(orientation="P", unit="mm", format="Letter")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_title(_latin1(f"Cotizacion {folio}"))
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 15)
    pdf.cell(0, 9, "PRE WORK ORDER - COTIZACION", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, _latin1(f"Folio: {folio}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 9)
    for etiqueta, clave in _CABECERA:
        valor = _latin1(item.get(clave))
        if not valor:
            continue
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(38, 5, f"{etiqueta}:")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, valor, new_x="LMARGIN", new_y="NEXT")

    concepto = _latin1(item.get("concepto"))
    if concepto:
        pdf.ln(2)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(0, 6, "DESCRIPCION DEL TRABAJO", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, concepto, new_x="LMARGIN", new_y="NEXT")

    for titulo, clave_bloque, campos, columnas in _BLOQUES:
        filas = _filas_con_datos(item.get(clave_bloque), campos)
        if not filas:
            continue
        _escribir_tabla(pdf, titulo, columnas, filas)

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, "RESUMEN", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    for etiqueta, clave in (("Materiales", "materiales"), ("Herramientas", "herramientas"),
                            ("Mano de obra", "mano_obra"), ("Equipo especial", "equipos"),
                            ("Costos adicionales", "adicionales")):
        pdf.cell(60, 5, etiqueta)
        pdf.cell(35, 5, _moneda(totales[clave]), align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(60, 6, "Subtotal")
    pdf.cell(35, 6, _moneda(totales["subtotal"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(60, 6, "Utilidad")
    pdf.cell(35, 6, _moneda(totales["utilidad"]), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(60, 7, "GRAN TOTAL")
    pdf.cell(35, 7, _moneda(totales["total"]), align="R", new_x="LMARGIN", new_y="NEXT")

    salida = pdf.output()
    return bytes(salida)


def _escribir_tabla(pdf, titulo: str, columnas, filas: List[Dict[str, Any]]) -> None:
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 6, _latin1(titulo), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(230, 230, 230)
    for encabezado, _clave, ancho, _alineacion in columnas:
        pdf.cell(ancho, 5, encabezado, border=1, fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 8)
    for fila in filas:
        for _encabezado, clave, ancho, alineacion in columnas:
            texto = _valor_de_celda(fila, clave)
            # Recorte por ancho: `cell` no parte el texto, así que una
            # descripción larga se montaría sobre la columna siguiente. El
            # dato completo vive en su tabla de la base; el PDF es la vista.
            maximo = max(1, int(ancho / 1.6))
            if len(texto) > maximo:
                texto = texto[:maximo - 1] + "."
            pdf.cell(ancho, 5, texto, border=1, align=alineacion)
        pdf.ln()

    pdf.set_font("Helvetica", "B", 8)
    ancho_total = sum(c[2] for c in columnas)
    ultimo = columnas[-1][2]
    pdf.cell(ancho_total - ultimo, 5, "Total", border=1, align="R")
    clave_total = "TOTAL" if columnas[-1][1] == "TOTAL" else "total"
    pdf.cell(ultimo, 5, _moneda(sum(_numero(f.get(clave_total)) for f in filas)),
             border=1, align="R")
    pdf.ln()


# --- Archivado --------------------------------------------------------------

def archivar(item: Dict[str, Any], folio: Any) -> Dict[str, Any]:
    """Emite el PDF, lo sube a `AÑO/MES/CLIENTE/` y devuelve su URL.

    `{"success": bool, "fileUrl": str, "message": str}`. Nunca lanza: el
    llamador guarda la orden pase lo que pase y convierte el `message` en aviso.
    """
    from api.services import storage

    try:
        contenido = construir_pdf(item, folio)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "fileUrl": "",
                "message": f"No se pudo generar el PDF de la cotización: {exc}"}

    datos = base64.b64encode(contenido).decode("ascii")
    resultado = storage.subir(
        datos, "application/pdf", nombre_de_archivo(folio),
        item.get("cliente"), item.get("fechaCotizacion"))

    if not resultado.get("success"):
        return {"success": False, "fileUrl": "",
                "message": ("La cotización en PDF no se archivó: "
                            + _texto(resultado.get("message")))}
    return {"success": True, "fileUrl": _texto(resultado.get("fileUrl")), "message": ""}


def anexar_a_documentos(archivo_url: Any, nueva_url: Any) -> str:
    """La URL nueva al final de los documentos de la orden, sin repetirla.

    `archivoUrl` es una lista de URLs separadas por salto de línea: es lo que
    `index.html` arma y lo que la columna CARPETA guarda. Se anexa —no se
    sustituye— para no borrar lo que subió una persona.
    """
    urls = [u for u in _texto(archivo_url).split("\n") if u.strip()]
    nueva = _texto(nueva_url)
    if nueva and nueva not in urls:
        urls.append(nueva)
    return "\n".join(urls)
