import json
import os
from datetime import datetime
from api.services.sheets import gs_manager

SEQUENCES_FILE = "sequences.json"

def get_next_sequence(key, increment=False):
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

def format_date_value(val):
    if not val:
        return ""
    return str(val)

def save_child_data(sheet_name, items, headers):
    if not items:
        return

    # Ensure sheet exists or create headers
    current_values = gs_manager.get_sheet_values(sheet_name)
    if not current_values or len(current_values) == 0:
        # Sheet doesn't exist or is empty, add headers
        gs_manager.append_row(sheet_name, headers)

    # Map items to rows
    for item in items:
        row = []
        for h in headers:
            val = item.get(h)
            if val is None:
                val = item.get(h.replace(" ", "_"), "")
            row.append(str(val))
        gs_manager.append_row(sheet_name, row)

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

def process_and_save_work_order(items, active_user):
    generated_ids = []

    # Config (Mirrors APP_CONFIG)
    PPC_SHEET_NAME = "PPCV3"
    WO_MATERIALS_SHEET = "DB_WO_MATERIALES"
    WO_LABOR_SHEET = "DB_WO_MANO_OBRA"
    WO_TOOLS_SHEET = "DB_WO_HERRAMIENTAS"
    WO_EQUIP_SHEET = "DB_WO_EQUIPOS"
    WO_PROGRAM_SHEET = "DB_WO_PROGRAMA"

    # Ensure main sheet exists
    current_ppc = gs_manager.get_sheet_values(PPC_SHEET_NAME)
    if not current_ppc or len(current_ppc) == 0:
        gs_manager.append_row(PPC_SHEET_NAME, ["ID", "ESPECIALIDAD", "DESCRIPCION", "RESPONSABLE", "FECHA", "RELOJ", "CUMPLIMIENTO", "ARCHIVO", "COMENTARIOS", "COMENTARIOS PREVIOS", "ESTATUS", "AVANCE", "CLASIFICACION", "PRIORIDAD", "RIESGOS", "FECHA_RESPUESTA", "DETALLES_EXTRA", "CLIENTE", "TRABAJO", "REQUISITOR", "CONTACTO", "CELULAR", "FECHA_COTIZACION"])

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
            save_child_data(WO_MATERIALS_SHEET, mat_items, ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "COSTO", "ESPECIFICACION", "TOTAL", "RESIDENTE", "COMPRAS", "CONTROLLER", "ORDEN_COMPRA", "PAGOS", "ALMACEN", "LOGISTICA", "RESIDENTE_OBRA"])

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
                new_l["EXTRAS"] = l.get("overtime", "")
                new_l["NOCTURNO"] = l.get("night", "")
                new_l["FIN_SEMANA"] = l.get("weekend", "")
                new_l["OTROS"] = l.get("others", "")
                new_l["TOTAL"] = l.get("total", "")
                labor_items.append(new_l)
            save_child_data(WO_LABOR_SHEET, labor_items, ["FOLIO", "CATEGORIA", "SALARIO", "PERSONAL", "SEMANAS", "EXTRAS", "NOCTURNO", "FIN_SEMANA", "OTROS", "TOTAL"])

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
            save_child_data(WO_TOOLS_SHEET, tool_items, ["FOLIO", "CANTIDAD", "UNIDAD", "DESCRIPCION", "COSTO", "TOTAL", "RESIDENTE", "CONTROLLER", "ALMACEN", "LOGISTICA", "RESIDENTE_FIN"])

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
            save_child_data(WO_EQUIP_SHEET, eq_items, ["FOLIO", "CANTIDAD", "UNIDAD", "TIPO", "DESCRIPCION", "ESPECIFICACION", "DIAS", "HORAS", "COSTO", "TOTAL"])

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

                resp = p.get("responsable", "")
                if isinstance(resp, list):
                    resp = ", ".join(resp)
                new_p["RESPONSABLE"] = resp

                prog_items.append(new_p)
            save_child_data(WO_PROGRAM_SHEET, prog_items, ["FOLIO", "DESCRIPCION", "FECHA", "DURACION", "UNIDAD_DURACION", "UNIDAD", "CANTIDAD", "PRECIO", "TOTAL", "RESPONSABLE", "SECCION", "ESTATUS"])

        # F. Detalles Extra JSON
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

        # Save to PPCV3
        ppc_headers = ["ID", "ESPECIALIDAD", "DESCRIPCION", "RESPONSABLE", "FECHA", "RELOJ", "CUMPLIMIENTO", "ARCHIVO", "COMENTARIOS", "COMENTARIOS PREVIOS", "ESTATUS", "AVANCE", "CLASIFICACION", "PRIORIDAD", "RIESGOS", "FECHA_RESPUESTA", "DETALLES_EXTRA", "CLIENTE", "TRABAJO", "REQUISITOR", "CONTACTO", "CELULAR", "FECHA_COTIZACION"]

        ppc_row = []
        for h in ppc_headers:
            val = ""
            if h == "ID": val = task_data.get("FOLIO", "")
            elif h == "ESPECIALIDAD": val = task_data.get("AREA", "")
            elif h == "DESCRIPCION": val = task_data.get("CONCEPTO", "")
            elif h == "RESPONSABLE": val = task_data.get("INVOLUCRADOS", "")
            elif h == "FECHA_RESPUESTA": val = task_data.get("FECHA_RESPUESTA", "")
            else: val = task_data.get(h, "")

            ppc_row.append(str(val))

        gs_manager.append_row(PPC_SHEET_NAME, ppc_row)

        # Save to ADMINISTRADOR
        admin_sheet = "ADMINISTRADOR"
        current_admin = gs_manager.get_sheet_values(admin_sheet)
        if not current_admin or len(current_admin) == 0:
             gs_manager.append_row(admin_sheet, ppc_headers)

        gs_manager.append_row(admin_sheet, ppc_row)

        # Distribution logic (Staff sheets)
        responsables = str(item.get("responsable", "")).split(",")
        for resp in responsables:
            resp_name = resp.strip()
            if resp_name and "(VENTAS)" not in resp_name.upper():
                current_staff = gs_manager.get_sheet_values(resp_name)
                if not current_staff or len(current_staff) == 0:
                    gs_manager.append_row(resp_name, ppc_headers)
                gs_manager.append_row(resp_name, ppc_row)

    return {"success": True, "message": "Datos procesados y distribuidos correctamente.", "ids": generated_ids}
