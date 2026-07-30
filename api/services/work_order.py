import json
import os
import re
from datetime import datetime

SEQUENCES_FILE = "sequences.json"

# --- Persistencia de la Pre Work Order ------------------------------------
# Cada bloque del formulario tiene su tabla en el esquema relacional. Los
# nombres de hoja (`DB_WO_MATERIALES`) y los encabezados en mayúsculas siguen
# siendo los del formulario; aquí se traducen a tabla y columnas.
#
# Tres bloques del formulario —viáticos, transporte e ingeniería— **no tienen
# tabla** en la base. No se inventa una: se devuelve un aviso que llega hasta la
# respuesta del endpoint, y el detalle queda en la nota de Obsidian, que sí los
# recoge. Crear el esquema para ellos es trabajo aparte y con dueño (ver
# docs/PLAN_BACKEND_PYTHON.md, Fase 5).

TABLAS_WO = {
    "DB_WO_MATERIALES": ("wo_materiales", {
        "FOLIO": "folio", "CANTIDAD": "cantidad", "UNIDAD": "unidad", "TIPO": "tipo",
        "DESCRIPCION": "descripcion", "COSTO": "costo", "ESPECIFICACION": "especificacion",
        "TOTAL": "total", "RESIDENTE": "residente", "COMPRAS": "compras",
        "CONTROLLER": "controller", "ORDEN_COMPRA": "orden_compra", "PAGOS": "pagos",
        "ALMACEN": "almacen", "LOGISTICA": "logistica", "RESIDENTE_OBRA": "residente_obra",
    }),
    "DB_WO_MANO_OBRA": ("wo_mano_obra", {
        "FOLIO": "folio", "CATEGORIA": "categoria", "SALARIO": "salario",
        "PERSONAL": "personal", "SEMANAS": "semanas", "EXTRAS": "extras",
        "NOCTURNO": "nocturno", "FIN_SEMANA": "fin_semana", "OTROS": "otros",
        "TOTAL": "total",
    }),
    "DB_WO_HERRAMIENTAS": ("wo_herramientas", {
        "FOLIO": "folio", "CANTIDAD": "cantidad", "UNIDAD": "unidad",
        "DESCRIPCION": "descripcion", "COSTO": "costo", "TOTAL": "total",
        "RESIDENTE": "residente", "CONTROLLER": "controller", "ALMACEN": "almacen",
        "LOGISTICA": "logistica", "RESIDENTE_FIN": "residente_fin",
    }),
    "DB_WO_EQUIPOS": ("wo_equipos", {
        "FOLIO": "folio", "CANTIDAD": "cantidad", "UNIDAD": "unidad", "TIPO": "tipo",
        "DESCRIPCION": "descripcion", "ESPECIFICACION": "especificacion",
        "DIAS": "dias", "HORAS": "horas", "COSTO": "costo", "TOTAL": "total",
    }),
    "DB_WO_PROGRAMA": ("wo_programa", {
        "FOLIO": "folio", "DESCRIPCION": "descripcion", "FECHA": "fecha",
        "DURACION": "duracion", "UNIDAD_DURACION": "unidad_duracion", "UNIDAD": "unidad",
        "CANTIDAD": "cantidad", "PRECIO": "precio", "TOTAL": "total",
        "RESPONSABLE": "responsable", "SECCION": "seccion", "ESTATUS": "estatus",
    }),
}

# Columnas numéricas y de fecha de esas tablas: el formulario las manda como
# texto ("10", "$1,000.00", "01/01/25") y Postgres las rechaza así.
COLUMNAS_NUMERICAS = {
    "cantidad", "costo", "total", "salario", "personal", "semanas", "extras",
    "nocturno", "fin_semana", "otros", "dias", "horas", "duracion", "precio",
}
COLUMNAS_FECHA = {"fecha"}


def _engine():
    from backend.core.engine import construir_engine

    return construir_engine()


def _hay_base():
    from backend.core.config import cargar_settings

    cfg = cargar_settings()
    return cfg.hay_sqlalchemy or cfg.hay_postgrest


def get_next_sequence(key, increment=False):
    """
    Siguiente consecutivo.

    Con base de datos, el de work orders se deduce de `work_orders`: el folio
    tiene la forma `####<INI-CLIENTE> <Depto> <ddmmyy>` y los cuatro primeros
    dígitos son la secuencia. `sequences.json` no sirve en el despliegue —vive
    en un filesystem efímero, así que cada arranque en frío volvía a empezar en
    1000 y repetía folios ya usados—, y ahora que `work_orders.folio` es clave
    primaria un folio repetido hace fallar el guardado en vez de duplicar en
    silencio. Sigue usándose el archivo cuando no hay base (desarrollo local).

    No es un candado: dos peticiones simultáneas pueden leer el mismo máximo.
    La solución definitiva es una secuencia de Postgres (Fase 2 del plan); esto
    quita el fallo sistemático, no la carrera.
    """
    if key == "WORKORDER_SEQ" and _hay_base():
        maximo = _max_secuencia_work_orders()
        if maximo is not None:
            return str(maximo + 1 if increment else maximo)

    sequences = {}
    if os.path.exists(SEQUENCES_FILE):
        try:
            with open(SEQUENCES_FILE, 'r') as f:
                sequences = json.load(f)
        except json.JSONDecodeError:
            pass

    current_val = int(sequences.get(key, 1000))
    if increment:
        current_val += 1
        sequences[key] = current_val
        with open(SEQUENCES_FILE, 'w') as f:
            json.dump(sequences, f)

    return str(current_val)


def _max_secuencia_work_orders():
    """Mayor consecutivo ya usado en `work_orders`, o None si no se pudo leer."""
    try:
        folios = _engine().select("work_orders", columnas=["folio"])
    except Exception as exc:  # noqa: BLE001
        print(f"[work_order] No se pudo leer la secuencia desde la base: {exc}")
        return None
    maximo = 1000
    for fila in folios:
        coincide = re.match(r"^(\d{4})", str(fila.get("folio") or ""))
        if coincide:
            maximo = max(maximo, int(coincide.group(1)))
    return maximo

def format_date_value(val):
    if not val:
        return ""
    return str(val)


def _numero(valor):
    """`"$ 1,250.50"` -> 1250.5; lo que no es número -> None (la columna admite nulo)."""
    from backend.schemas.hoja import a_numero

    return a_numero(valor)


def _fecha(valor):
    from backend.schemas.hoja import a_fecha

    fecha = a_fecha(valor)
    return fecha.isoformat() if fecha else None


def save_child_data(sheet_name, items, headers):
    """
    Guarda un bloque hijo de la work order (materiales, mano de obra, …).

    Antes escribía con `gs_manager.append_row(sheet_name, ...)`, que usaba el
    nombre de hoja como nombre de tabla: `public.DB_WO_MATERIALES` no existe,
    PostgREST devolvía PGRST205 y el bloque entero se perdía sin que nadie se
    enterara.

    Devuelve `None` si todo fue bien, o `(clase, texto)` con `clase` en
    `{"error", "aviso"}`: un rechazo de la base es un error que el usuario tiene
    que ver, y un bloque sin tabla en el esquema es un aviso, porque no hay nada
    que reintentar hasta que exista esa tabla.
    """
    if not items:
        return None

    destino = TABLAS_WO.get(sheet_name)
    if not destino:
        return ("aviso", f"{sheet_name} no tiene tabla en la base todavía: "
                         f"{len(items)} fila(s) solo quedaron en la nota de Obsidian")

    tabla, columnas = destino
    filas = []
    for item in items:
        fila = {}
        for encabezado, columna in columnas.items():
            valor = item.get(encabezado)
            if valor is None:
                valor = item.get(encabezado.replace(" ", "_"))
            if valor is None or str(valor).strip() == "":
                continue
            if columna in COLUMNAS_NUMERICAS:
                valor = _numero(valor)
            elif columna in COLUMNAS_FECHA:
                valor = _fecha(valor)
            if valor is not None:
                fila[columna] = valor
        if fila.get("folio"):
            filas.append(fila)

    if not filas:
        return None
    try:
        # PostgREST exige las mismas claves en todo el arreglo; se agrupa igual
        # que en los repositorios.
        grupos = {}
        for fila in filas:
            grupos.setdefault(tuple(sorted(fila)), []).append(fila)
        motor = _engine()
        for grupo in grupos.values():
            motor.insertar(tabla, grupo)
    except Exception as exc:  # noqa: BLE001
        return ("error", f"no se pudieron guardar {len(filas)} fila(s) de {tabla}: {exc}")
    return None

def generate_work_order_folio(client_name, dept_name):
    # Get next sequence
    seq_str = get_next_sequence('WORKORDER_SEQ', increment=True)
    seq_padded = seq_str.zfill(4)

    # Clean Client Name
    clean_client = (client_name or "XX").upper().strip()
    import re
    clean_client = re.sub(r'[^A-Z0-9 ]', '', clean_client)
    words = [w for w in clean_client.split() if w]

    client_str = "XX"
    if len(words) >= 2:
        client_str = words[0][0] + words[1][0]
    elif len(words) == 1:
        client_str = words[0][:2]

    # Department
    raw_dept = (dept_name or "General").strip().upper()
    abbr_map = {
        "ELECTROMECANICA": "Electro",
        "ELECTROMECÁNICA": "Electro",
        "CONSTRUCCION": "Const",
        "CONSTRUCCIÓN": "Const",
        "MANTENIMIENTO": "Mtto",
        "REMODELACION": "Remod",
        "REMODELACIÓN": "Remod",
        "REPARACION": "Repar",
        "REPARACIÓN": "Repar",
        "RECONFIGURACION": "Reconf",
        "RECONFIGURACIÓN": "Reconf",
        "POLIZA": "Poliza",
        "PÓLIZA": "Poliza",
        "INSPECCION": "Insp",
        "INSPECCIÓN": "Insp",
        "ADMINISTRACION": "Admin",
        "ADMINISTRACIÓN": "Admin",
        "MAQUINARIA": "Maq",
        "DISEÑO": "Diseño",
        "COMPRAS": "Compras",
        "VENTAS": "Ventas",
        "HVAC": "HVAC",
        # Estas tres faltaban frente al ABBR_MAP de `generateWorkOrderFolio`
        # (CODIGO.js:4193-4195). Sin ellas, "FINANZAS" caía al truncado de abajo
        # y salía "Finan" en vez de "Finanzas", y "FACTURACION" salía "Factu" en
        # vez de "Factura": el folio, que es el identificador de negocio más
        # visible de la Work Order, tenía un formato distinto según el
        # departamento.
        "FINANZAS": "Finanzas",
        "FACTURACION": "Factura",
        "FACTURACIÓN": "Factura",
        "SEGURIDAD": "EHS",
        "EHS": "EHS"
    }

    dept_str = abbr_map.get(raw_dept)
    if not dept_str:
        if len(raw_dept) > 6:
            dept_str = raw_dept[0] + raw_dept[1:5].lower()
        else:
            dept_str = raw_dept[0] + raw_dept[1:].lower()

    # Date
    now = datetime.now()
    date_str = now.strftime("%d%m%y")

    return f"{seq_padded}{client_str} {dept_str} {date_str}"

def save_to_obsidian(item, item_id):
    try:
        # Get project root to locate Notas directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(current_dir))
        notas_dir = os.path.join(project_root, "Notas", "Prework_Orders")
        
        # Ensure the directory exists
        if not os.path.exists(notas_dir):
            os.makedirs(notas_dir)

        cliente = item.get("cliente", "SinCliente")
        clean_cliente = "".join(c for c in cliente if c.isalnum() or c in " _-").strip()
        filename = f"{item_id}_{clean_cliente}.md"
        filepath = os.path.join(notas_dir, filename)

        md = f"# Folio: {item_id} - {cliente}\n\n"
        md += f"**Fecha Cotización:** {item.get('fechaCotizacion', '')}\n"
        md += f"**Especialidad:** {item.get('especialidad', '')}\n"
        md += f"**Requisitor:** {item.get('requisitor', '')}\n"
        md += f"**Contacto:** {item.get('contacto', '')} (Cel: {item.get('celular', '')})\n\n"

        md += "## 📝 Concepto Principal / Levantamiento\n"
        md += f"{item.get('concepto', 'Sin concepto')}\n\n"

        if item.get('riesgos') or item.get('restricciones'):
            md += "## ⚠️ Riesgos y Restricciones\n"
            md += f"- **Riesgos:** {item.get('riesgos', '')}\n"
            md += f"- **Restricciones:** {item.get('restricciones', '')}\n\n"

        if item.get("materiales"):
            md += "## 🛠️ Materiales y Precios Unitarios\n"
            md += "| Cantidad | Unidad | Descripción | Costo Unitario | Total |\n"
            md += "|---|---|---|---|---|\n"
            for m in item["materiales"]:
                md += f"| {m.get('quantity','')} | {m.get('unit','')} | {m.get('description','')} | ${m.get('cost','')} | ${m.get('total','')} |\n"
            md += "\n"

        if item.get("manoObra"):
            md += "## 👷 Mano de Obra\n"
            md += "| Categoría | Personal | Semanas | Costo Hora | Total |\n"
            md += "|---|---|---|---|---|\n"
            for l in item["manoObra"]:
                md += f"| {l.get('category','')} | {l.get('personnel','')} | {l.get('weeks','')} | ${l.get('costo_hora','')} | ${l.get('total','')} |\n"
            md += "\n"

        if item.get("equipos"):
            md += "## 🚜 Equipos\n"
            md += "| Cantidad | Descripción | Días | Costo | Total |\n"
            md += "|---|---|---|---|---|\n"
            for e in item["equipos"]:
                md += f"| {e.get('quantity','')} | {e.get('description','')} | {e.get('days','')} | ${e.get('cost','')} | ${e.get('total','')} |\n"
            md += "\n"
            
        if item.get("comentarios"):
            md += "## 💬 Comentarios Generales\n"
            md += f"{item.get('comentarios', '')}\n\n"

        md += "---\n*Generado automáticamente por el Sistema Holtmont*"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(md)
            
    except Exception as e:
        print(f"Error saving to Obsidian: {e}")

def process_and_save_work_order(items, active_user):
    generated_ids = []
    errores = []
    avisos = []

    def guardar_hijos(sheet_name, items_hijos, headers):
        """Guarda un bloque y acumula lo que no se pudo guardar."""
        resultado = save_child_data(sheet_name, items_hijos, headers)
        if resultado:
            clase, texto = resultado
            (errores if clase == "error" else avisos).append(texto)

    # Config (Mirrors APP_CONFIG)
    WO_MATERIALS_SHEET = "DB_WO_MATERIALES"
    WO_LABOR_SHEET = "DB_WO_MANO_OBRA"
    WO_TOOLS_SHEET = "DB_WO_HERRAMIENTAS"
    WO_EQUIP_SHEET = "DB_WO_EQUIPOS"
    WO_PROGRAM_SHEET = "DB_WO_PROGRAMA"
    WO_VIATICOS_SHEET = "DB_WO_VIATICOS"
    WO_TRANSPORTE_SHEET = "DB_WO_TRANSPORTE"
    WO_INGENIERIA_SHEET = "DB_WO_INGENIERIA"

    for item in items:
        # ID Generation
        item_id = item.get("id") or item.get("FOLIO")
        if not item_id:
            if active_user == 'PREWORK_ORDER':
                item_id = generate_work_order_folio(item.get("cliente"), item.get("especialidad"))
            else:
                import random
                item_id = "PPC-" + str(random.randint(100000, 999999))

        generated_ids.append(item_id)

        # El folio se registra ANTES que los bloques hijos: `wo_materiales`,
        # `wo_mano_obra`, `wo_herramientas`, `wo_equipos` y `wo_programa`
        # apuntan a `work_orders.folio` con una clave foránea, así que
        # insertarlos primero los rechaza con un 409.
        _registrar_work_order(item_id)

        # Child Data Saving
        # A. Materiales
        if item.get("materiales"):
            mat_items = []
            for m in item["materiales"]:
                new_m = m.copy()
                new_m["FOLIO"] = item_id
                # Map Keys
                new_m["CANTIDAD"] = m.get("quantity", "")
                new_m["UNIDAD"] = m.get("unit", "")
                new_m["TIPO"] = m.get("type", "")
                new_m["DESCRIPCION"] = m.get("description", "")
                new_m["COSTO"] = m.get("cost", "")
                new_m["ESPECIFICACION"] = m.get("spec", "")
                new_m["TOTAL"] = m.get("total", "")

                pc = m.get("papaCaliente", {})
                new_m.update({
                    "RESIDENTE": pc.get("residente", ""),
                    "COMPRAS": pc.get("compras", ""),
                    "CONTROLLER": pc.get("controller", ""),
                    "ORDEN_COMPRA": pc.get("ordenCompra", ""),
                    "PAGOS": pc.get("pagos", ""),
                    "ALMACEN": pc.get("almacen", ""),
                    "LOGISTICA": pc.get("logistica", ""),
                    "RESIDENTE_OBRA": pc.get("residenteObra", "")
                })
                mat_items.append(new_m)
            guardar_hijos(WO_MATERIALS_SHEET, mat_items, ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "COSTO", "ESPECIFICACION", "TOTAL", "RESIDENTE", "COMPRAS", "CONTROLLER", "ORDEN_COMPRA", "PAGOS", "ALMACEN", "LOGISTICA", "RESIDENTE_OBRA"])

        # B. Mano de Obra
        if item.get("manoObra"):
            labor_items = []
            for l in item["manoObra"]:
                new_l = l.copy()
                new_l["FOLIO"] = item_id
                # Map Keys
                new_l["CATEGORIA"] = l.get("category", "")
                new_l["SALARIO"] = l.get("salary", "")
                new_l["PERSONAL"] = l.get("personnel", "")
                new_l["SEMANAS"] = l.get("weeks", "")
                new_l["UNIDAD"] = l.get("unit", "")
                new_l["EXTRAS"] = l.get("overtime", "")
                new_l["NOCTURNO"] = l.get("night", "")
                new_l["FIN_SEMANA"] = l.get("weekend", "")
                new_l["OTROS"] = l.get("others", "")
                new_l["EPP_6_PORCIENTO"] = l.get("epp_6", "")
                new_l["COSTO_HORA"] = l.get("costo_hora", "")
                new_l["HORAS_REQUERIDAS"] = l.get("horas_req", "")
                new_l["TOTAL"] = l.get("total", "")
                labor_items.append(new_l)
            guardar_hijos(WO_LABOR_SHEET, labor_items, ["FOLIO", "CATEGORIA", "SALARIO", "PERSONAL", "SEMANAS", "UNIDAD", "EXTRAS", "NOCTURNO", "FIN_SEMANA", "OTROS", "EPP_6_PORCIENTO", "COSTO_HORA", "HORAS_REQUERIDAS", "TOTAL"])

        # C. Herramientas
        if item.get("herramientas"):
            tool_items = []
            for t in item["herramientas"]:
                new_t = t.copy()
                new_t["FOLIO"] = item_id
                # Map Keys
                new_t["CANTIDAD"] = t.get("quantity", "")
                new_t["UNIDAD"] = t.get("unit", "")
                new_t["DESCRIPCION"] = t.get("description", "")
                new_t["COSTO"] = t.get("cost", "")
                new_t["TOTAL"] = t.get("total", "")

                pc = t.get("papaCaliente", {})
                new_t.update({
                    "RESIDENTE": pc.get("residente", ""),
                    "CONTROLLER": pc.get("controller", ""),
                    "ALMACEN": pc.get("almacen", ""),
                    "LOGISTICA": pc.get("logistica", ""),
                    "RESIDENTE_FIN": pc.get("residenteFin", "")
                })
                tool_items.append(new_t)
            guardar_hijos(WO_TOOLS_SHEET, tool_items, ["FOLIO", "CANTIDAD", "UNIDAD", "DESCRIPCION", "COSTO", "TOTAL", "RESIDENTE", "CONTROLLER", "ALMACEN", "LOGISTICA", "RESIDENTE_FIN"])

        # D. Equipos
        if item.get("equipos"):
            eq_items = []
            for e in item["equipos"]:
                new_e = e.copy()
                new_e["FOLIO"] = item_id
                # Map Keys
                new_e["CANTIDAD"] = e.get("quantity", "")
                new_e["UNIDAD"] = e.get("unit", "")
                new_e["TIPO"] = e.get("type", "")
                new_e["DESCRIPCION"] = e.get("description", "")
                new_e["ESPECIFICACION"] = e.get("spec", "")
                new_e["DIAS"] = e.get("days", "")
                new_e["HORAS"] = e.get("hours", "")
                new_e["COSTO"] = e.get("cost", "")
                new_e["TOTAL"] = e.get("total", "")
                eq_items.append(new_e)
            guardar_hijos(WO_EQUIP_SHEET, eq_items, ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "ESPECIFICACION", "DIAS", "HORAS", "COSTO", "TOTAL"])

        # E. Programa
        if item.get("programa"):
            prog_items = []
            for p in item["programa"]:
                new_p = p.copy()
                new_p["FOLIO"] = item_id
                new_p["SECCION"] = p.get("seccion", "")
                new_p["ESTATUS"] = p.get("checkStatus") or ('APPLY' if p.get("isActive") else 'PENDING')

                # Map Keys
                new_p["DESCRIPCION"] = p.get("description", "")
                new_p["FECHA"] = p.get("date", "")
                new_p["DURACION"] = p.get("duration", "")
                new_p["UNIDAD_DURACION"] = p.get("durationUnit", "")
                new_p["UNIDAD"] = p.get("unit", "")
                new_p["CANTIDAD"] = p.get("quantity", "")
                new_p["PRECIO"] = p.get("price", "")
                new_p["TOTAL"] = p.get("total", "")

                new_p["FECHA_INICIO"] = p.get("fechaInicio", "")
                new_p["FECHA_ENTREGA"] = p.get("fechaEntrega", "")
                new_p["ARCHIVO"] = p.get("fileUrl", "")

                resp = p.get("responsable", "")
                if isinstance(resp, list):
                    resp = ", ".join(resp)
                new_p["RESPONSABLE"] = resp

                avance = p.get("avance", "")
                archivo = p.get("archivo", "") or p.get("archivoSubido", "")
                if avance == "100%" and not archivo:
                    new_p["ESTATUS"] = "BLOQUEADO_SIN_ARCHIVO"

                prog_items.append(new_p)
            guardar_hijos(WO_PROGRAM_SHEET, prog_items, ["FOLIO", "DESCRIPCION", "FECHA", "DURACION", "UNIDAD_DURACION", "UNIDAD", "CANTIDAD", "PRECIO", "TOTAL", "RESPONSABLE", "FECHA_INICIO", "FECHA_ENTREGA", "ARCHIVO", "SECCION", "ESTATUS"])

        # F. Viaticos
        if item.get("viaticos"):
            viaticos_items = []
            for v in item["viaticos"]:
                new_v = v.copy()
                new_v["FOLIO"] = item_id
                new_v["CONCEPTO"] = v.get("concepto", "")
                new_v["CANTIDAD"] = v.get("cantidad", "")
                new_v["COSTO_UNITARIO"] = v.get("costo_unitario", "")
                new_v["TOTAL"] = v.get("total", "")
                viaticos_items.append(new_v)
            guardar_hijos(WO_VIATICOS_SHEET, viaticos_items, ["FOLIO", "CONCEPTO", "CANTIDAD", "COSTO_UNITARIO", "TOTAL"])

        # G. Transporte
        if item.get("transporte"):
            transporte_items = []
            for t in item["transporte"]:
                new_t = t.copy()
                new_t["FOLIO"] = item_id
                new_t["VEHICULO"] = t.get("vehiculo", "")
                new_t["CHOFER"] = t.get("chofer", "")
                new_t["TIEMPO"] = t.get("tiempo", "")
                new_t["LTS_GASOLINA"] = t.get("lts_gasolina", "")
                new_t["COSTO_TOTAL"] = t.get("costo_total", "")
                new_t["NOTAS_CONTROL"] = t.get("notas_control", "")
                transporte_items.append(new_t)
            guardar_hijos(WO_TRANSPORTE_SHEET, transporte_items, ["FOLIO", "VEHICULO", "CHOFER", "TIEMPO", "LTS_GASOLINA", "COSTO_TOTAL", "NOTAS_CONTROL"])

        # H. Ingenieria
        if item.get("ingenieria"):
            ingenieria_items = []
            for i in item["ingenieria"]:
                new_i = i.copy()
                new_i["FOLIO"] = item_id
                new_i["ENTREGABLE"] = i.get("entregable", "")
                new_i["HORAS_DISENO"] = i.get("horas_diseno", "")
                new_i["COSTO_HORA"] = i.get("costo_hora", "")
                new_i["TOTAL"] = i.get("total", "")
                ingenieria_items.append(new_i)
            guardar_hijos(WO_INGENIERIA_SHEET, ingenieria_items, ["FOLIO", "ENTREGABLE", "HORAS_DISENO", "COSTO_HORA", "TOTAL"])

        # I. Detalles Extra JSON
        detalles_extra = ""
        if item.get("checkList") or item.get("additionalCosts"):
            detalles_extra = json.dumps({
                "checkList": item.get("checkList"),
                "costs": item.get("additionalCosts")
            })

        # Main Task Data
        now_str = datetime.now().strftime("%d/%m/%y")

        task_data = {
            'FOLIO': item_id,
            'CONCEPTO': item.get("concepto", ""),
            'CLASIFICACION': item.get("clasificacion", "Media"),
            'AREA': item.get("especialidad", ""),
            'INVOLUCRADOS': item.get("responsable", ""),
            'FECHA': now_str,
            'RELOJ': item.get("horas", "0"),
            'ESTATUS': "ASIGNADO",
            'PRIORIDAD': item.get("prioridad") or item.get("prioridades", ""),
            'RESTRICCIONES': item.get("restricciones", ""),
            'RIESGOS': item.get("riesgos", ""),
            'FECHA_RESPUESTA': item.get("fechaRespuesta", ""),
            'AVANCE': "0%",
            'COMENTARIOS': item.get("comentarios", ""),
            'ARCHIVO': item.get("archivoUrl", ""),
            'CUMPLIMIENTO': item.get("cumplimiento", "NO"),
            'COMENTARIOS PREVIOS': item.get("comentariosPrevios", ""),
            'REQUISITOR': item.get("requisitor", ""),
            'CONTACTO': item.get("contacto", ""),
            'CELULAR': item.get("celular", ""),
            'FECHA_COTIZACION': item.get("fechaCotizacion", ""),
            'CLIENTE': item.get("cliente", ""),
            'TRABAJO': item.get("TRABAJO", ""),
            'DETALLES_EXTRA': detalles_extra
        }

        # --- Persistencia de la tarea ---------------------------------
        # `task_data` ya viene con encabezados de hoja; el puente lo traduce a
        # columnas y decide en qué partición cae.
        errores.extend(_distribuir_tarea(task_data, item, item_id, active_user))

        # Save to Obsidian automatically
        save_to_obsidian(item, item_id)

    if errores:
        return {
            "success": False,
            "message": "No se guardó todo: " + "; ".join(errores),
            "ids": generated_ids,
            "warnings": avisos,
        }
    mensaje = "Datos procesados y distribuidos correctamente."
    if avisos:
        mensaje += " Aviso: " + "; ".join(dict.fromkeys(avisos)) + "."
    return {"success": True, "message": mensaje, "ids": generated_ids, "warnings": avisos}


def _registrar_work_order(folio):
    """Alta idempotente del folio en `work_orders` (su clave primaria)."""
    try:
        _engine().upsert("work_orders", [{"folio": folio}], en_conflicto="folio")
    except Exception as exc:  # noqa: BLE001
        print(f"[work_order] No se pudo registrar el folio {folio}: {exc}")


def _distribuir_tarea(task_data, item, item_id, active_user):
    """
    Guarda la tarea en la tabla de cada responsable y la indexa en el PPC.

    Qué cambia frente a la versión de hoja, y por qué:

    * La hoja `PPCV3` no existe como partición: es un índice en `plan_semanal`
      (§7.7 del plan). Guardar aquí con `source_sheet='PPCV3'` habría estrenado
      una partición que la vista de Planeación Semanal no lee. El puente se
      encarga: manda la tarea a la hoja de su responsable y añade el renglón
      del índice.
    * Los folios `PPC-` son de secuencia global, así que en la base son **una
      sola fila** aunque la tarea se reparta entre varias personas: es lo que
      dice `computeDedupeKey` y lo que muestran los datos migrados (ninguno de
      los 1.143 folios `PPC-` está en más de una hoja). El reparto entre varias
      personas queda registrado en `task_involucrados`, que el puente proyecta
      desde el string de responsables.
    * El sufijo `(VENTAS)` se sigue filtrando: AGENTS.md §3 prohíbe enrutar
      tareas generales a hojas de ventas.
    """
    from backend.services.persistencia import PersistenciaTracker

    errores = []
    try:
        persistencia = PersistenciaTracker()
    except Exception as exc:  # noqa: BLE001 - sin base configurada
        return [f"Folio {item_id}: no hay base de datos configurada ({exc})"]

    # El PPC maestro decide el dueño y añade el índice de `plan_semanal`.
    resultado = persistencia.guardar("PPCV3", [task_data])
    if not resultado.exito:
        return [f"Folio {item_id}: {resultado.mensaje}"]

    destinos = []
    for resp in str(item.get("responsable", "")).split(","):
        nombre = resp.strip()
        if nombre and "(VENTAS)" not in nombre.upper():
            destinos.append(nombre)

    for nombre in destinos:
        hoja = persistencia.resolver_hoja(nombre)
        parcial = persistencia.guardar(hoja, [task_data])
        if not parcial.exito:
            errores.append(f"Folio {item_id} hacia {hoja}: {parcial.mensaje}")

    _auditar_alta(persistencia, item_id, resultado.hoja, active_user)
    return errores


def _auditar_alta(persistencia, folio, hoja, usuario):
    from backend.services import auditoria

    auditoria.registrar_lote(
        [auditoria.evento(usuario, auditoria.ACCION_CREAR,
                          auditoria.detalle_tarea(folio, hoja, es_alta=True))],
        engine=persistencia.engine,
    )
