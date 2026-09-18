"""
Organigrama y perfiles: el port de `INITIAL_DIRECTORY`, `allDepts` y `USER_DB`
de `CODIGO.js`.

**Aquí no hay contraseñas y no deben aparecer nunca.** `USER_DB` del original
guarda `pass` en texto plano junto a los datos de organización; al portarlo se
tomaron solo los campos que describen a la persona en la empresa (rol,
etiqueta, correo, hoja, departamento, si vende). La credencial vive en la tabla
`profiles` de Supabase y la valida `/api/login`. `tests/test_api_contract.py`
verifica que ningún módulo del repo traiga credenciales embebidas.

Por qué estos datos están en el fuente y no solo en la base: son el organigrama
oficial, y `apiResyncDirectory` los necesita como semilla para poder reparar
`people` cuando le falten registros. Es la misma decisión que ya tomaba el
original, y su `test_departments.js` la verifica contra una transcripción del
organigrama en papel. `tests/test_organigrama.py` porta esa verificación.

La fuente viva sigue siendo la tabla `people` (54 filas): `get_directory_from_db`
la lee y solo cae a `INITIAL_DIRECTORY` si la base no responde.
"""

from __future__ import annotations

import secrets
from typing import Any, Dict, List, Optional

# --- Departamentos del organigrama (19) -------------------------------
# Espejo de `allDepts`. El frontend los usa para el menú lateral y para
# colorear las tarjetas por departamento.
ALL_DEPTS: Dict[str, Dict[str, str]] = {
    "CEO": {"label": "Dirección General (CEO)", "icon": "fa-crown", "color": "#b8860b"},
    "CONSTRUCCION": {"label": "Construcción", "icon": "fa-hard-hat", "color": "#e83e8c"},
    "COMPRAS": {"label": "Compras/Almacén", "icon": "fa-shopping-cart", "color": "#198754"},
    "PRESUPUESTOS": {"label": "Presupuestos", "icon": "fa-calculator", "color": "#6f42c1"},
    "PRECIOS UNITARIOS": {"label": "Precios Unitarios", "icon": "fa-dollar-sign", "color": "#20c997"},
    "SEGURIDAD": {"label": "Seguridad", "icon": "fa-shield-alt", "color": "#dc3545"},
    "EHS": {"label": "Seguridad (EHS)", "icon": "fa-shield-alt", "color": "#dc3545"},
    "DISEÑO": {"label": "Diseño & Ing.", "icon": "fa-drafting-compass", "color": "#0d6efd"},
    "ELECTROMECANICA": {"label": "Electromecánica", "icon": "fa-bolt", "color": "#ffc107"},
    "HVAC": {"label": "HVAC", "icon": "fa-fan", "color": "#fd7e14"},
    "LIMPIEZA": {"label": "Limpieza", "icon": "fa-broom", "color": "#0dcaf0"},
    "ALMACEN Y MAQUINARIA": {"label": "Almacén y Maquinaria", "icon": "fa-warehouse", "color": "#198754"},
    "ADMINISTRACION": {"label": "Administración", "icon": "fa-briefcase", "color": "#6f42c1"},
    "VENTAS": {"label": "Ventas", "icon": "fa-handshake", "color": "#0dcaf0"},
    "MAQUINARIA": {"label": "Maquinaria", "icon": "fa-truck", "color": "#20c997"},
    "FINANZAS": {"label": "Finanzas", "icon": "fa-coins", "color": "#198754"},
    "FACTURACION": {"label": "Facturación", "icon": "fa-file-invoice-dollar", "color": "#0d6efd"},
    "RH": {"label": "Recursos Humanos", "icon": "fa-users", "color": "#6610f2"},
    "CALIDAD": {"label": "Calidad", "icon": "fa-clipboard-check", "color": "#0dcaf0"},
}

# --- Directorio semilla (38 registros) -------------------------------
INITIAL_DIRECTORY: List[Dict[str, str]] = [
    {"name": "LUIS CARLOS", "dept": "CEO", "type": "ESTANDAR"},
    {"name": "JUAN JOSE SANCHEZ", "dept": "CEO", "type": "ESTANDAR"},
    {"name": "DIMAS ELIEL RAMOS GARCIA", "dept": "RH", "type": "ESTANDAR"},
    {"name": "LAURA EDITH HUERTA ROCHA", "dept": "RH", "type": "ESTANDAR"},
    {"name": "LILIANA AYLIN MARTINEZ IBARRA", "dept": "RH", "type": "ESTANDAR"},
    {"name": "FRANCISCO SANCHEZ SERNA", "dept": "RH", "type": "ESTANDAR"},
    {"name": "JUANA MARIA RODRIGUEZ JUAREZ", "dept": "FINANZAS", "type": "ESTANDAR"},
    {"name": "ZAIRA YAZMIN AGUILAR AGUILON", "dept": "FINANZAS", "type": "ESTANDAR"},
    {"name": "ROCIO ABIGAIL CASTRO COVARRUBIAS", "dept": "FINANZAS", "type": "ESTANDAR"},
    {"name": "DANIA LIZBETH GONZALEZ LORES", "dept": "FINANZAS", "type": "ESTANDAR"},
    {"name": "SONIA GARCIA PEREZ", "dept": "COMPRAS", "type": "ESTANDAR"},
    {"name": "JUDITH ECHAVARRIA", "dept": "COMPRAS", "type": "ESTANDAR"},
    {"name": "VANESSA DE LARA", "dept": "COMPRAS", "type": "ESTANDAR"},
    {"name": "EDUARDO TERAN", "dept": "PRESUPUESTOS", "type": "HIBRIDO"},
    {"name": "ANTONIA PINEDA LOPEZ", "dept": "PRESUPUESTOS", "type": "ESTANDAR"},
    {"name": "CARLOS MENDEZ", "dept": "CALIDAD", "type": "ESTANDAR"},
    {"name": "RUBI MORENO RODRIGUEZ", "dept": "SEGURIDAD", "type": "ESTANDAR"},
    {"name": "TERESA GARZA", "dept": "PRECIOS UNITARIOS", "type": "HIBRIDO"},
    {"name": "GERALDINE MARTINEZ HERNANDEZ", "dept": "PRECIOS UNITARIOS", "type": "ESTANDAR"},
    {"name": "ANGEL SALINAS", "dept": "DISEÑO", "type": "HIBRIDO"},
    {"name": "EDGAR URIMAR LOPEZ MALDONADO", "dept": "DISEÑO", "type": "ESTANDAR"},
    {"name": "ANTONIA_VENTAS", "dept": "VENTAS", "type": "VENTAS"},
    {"name": "EDUARDO MANZANARES", "dept": "VENTAS", "type": "HIBRIDO"},
    {"name": "RAMIRO RODRIGUEZ", "dept": "VENTAS", "type": "HIBRIDO"},
    {"name": "SEBASTIAN PADILLA", "dept": "VENTAS", "type": "HIBRIDO"},
    {"name": "JEHU MARTINEZ", "dept": "ELECTROMECANICA", "type": "ESTANDAR"},
    {"name": "MIGUEL GALLARDO", "dept": "ELECTROMECANICA", "type": "ESTANDAR"},
    {"name": "ROLANDO MORENO", "dept": "HVAC", "type": "ESTANDAR"},
    {"name": "EMILIANO ARREDONDO GOMEZ", "dept": "HVAC", "type": "ESTANDAR"},
    {"name": "JAIME OLIVO", "dept": "CONSTRUCCION", "type": "ESTANDAR"},
    {"name": "RICARDO MENDO", "dept": "CONSTRUCCION", "type": "ESTANDAR"},
    {"name": "ALFONSO CORREA", "dept": "CONSTRUCCION", "type": "ESTANDAR"},
    {"name": "CESAR EDUARDO GARCIA AVALOS", "dept": "CONSTRUCCION", "type": "ESTANDAR"},
    {"name": "EDUARDO BENITEZ", "dept": "LIMPIEZA", "type": "ESTANDAR"},
    {"name": "SONIA GARCIA PEREZ", "dept": "ALMACEN Y MAQUINARIA", "type": "ESTANDAR"},
    {"name": "ADMINISTRADOR", "dept": "ADMINISTRACION", "type": "HIBRIDO"},
    {"name": "DANIELA CASTRO", "dept": "GENERAL", "type": "ESTANDAR"},
    {"name": "CESAR GOMEZ", "dept": "GENERAL", "type": "ESTANDAR"},
]

# --- Perfiles (41 cuentas, sin credenciales) -------------------------
# `staff_name` es el nombre de la hoja/partición de tracker de la persona,
# que no siempre coincide con `label` (el nombre para mostrar).
# `seller` habilita el módulo de cotizaciones "<NOMBRE> (VENTAS)".
PERFILES: Dict[str, Dict[str, Any]] = {
    "JESUS_CANTU": {"role": "PPC_ADMIN", "label": "PPC Manager", "email": "jesuscantu@empresa.com", "staff_name": "", "dept": "", "seller": False},
    "JAIME_OLIVO": {"role": "ADMIN_CONTROL", "label": "Jaime Olivo", "email": "jaimeolivo@empresa.com", "staff_name": "", "dept": "", "seller": False},
    "PREWORK_ORDER": {"role": "WORKORDER_USER", "label": "Workorder", "email": "workorder@empresa.com", "staff_name": "", "dept": "", "seller": False},
    "ANTONIA_VENTAS": {"role": "TONITA", "label": "Antonia Pineda", "email": "ventas@empresa.com", "staff_name": "ANTONIA PINEDA LOPEZ", "dept": "VENTAS", "seller": False},
    "JUDITH_ECHAVARRIA": {"role": "STAFF_USER", "label": "Cristian Judith Echavarria Rodriguez", "email": "", "staff_name": "JUDITH ECHAVARRIA", "dept": "COMPRAS", "seller": True},
    "EDUARDO_MANZANARES": {"role": "STAFF_USER", "label": "Eduardo Manzanares Sanchez", "email": "", "staff_name": "EDUARDO MANZANARES", "dept": "VENTAS", "seller": True},
    "RAMIRO_RODRIGUEZ": {"role": "STAFF_USER", "label": "Ramiro Rodriguez Escalante", "email": "", "staff_name": "RAMIRO RODRIGUEZ", "dept": "VENTAS", "seller": True},
    "SEBASTIAN_PADILLA": {"role": "STAFF_USER", "label": "Erick Sebastian Padilla Carrillo", "email": "", "staff_name": "SEBASTIAN PADILLA", "dept": "VENTAS", "seller": True},
    "ALFONSO_CORREA": {"role": "STAFF_USER", "label": "Alfonso Correa De Leon", "email": "", "staff_name": "ALFONSO CORREA", "dept": "CONSTRUCCION", "seller": True},
    "TERESA_GARZA": {"role": "STAFF_USER", "label": "Maria Teresa Hernandez Garza", "email": "", "staff_name": "TERESA GARZA", "dept": "PRECIOS UNITARIOS", "seller": True},
    "DANIELA_CASTRO": {"role": "STAFF_USER", "label": "Daniela Castro", "email": "", "staff_name": "DANIELA CASTRO", "dept": "GENERAL", "seller": False},
    "ANGEL_SALINAS": {"role": "STAFF_USER", "label": "Jose Angel Salinas Ramirez", "email": "", "staff_name": "ANGEL SALINAS", "dept": "DISEÑO", "seller": True},
    "JUAN_JOSE_SANCHEZ": {"role": "STAFF_USER", "label": "Juan Jose Sanchez Muñiz", "email": "", "staff_name": "JUAN JOSE SANCHEZ", "dept": "CEO", "seller": True},
    "LUIS_CARLOS": {"role": "ADMIN", "label": "Luis Carlos Holt Montero", "email": "luiscarlos@empresa.com", "staff_name": "LUIS CARLOS", "dept": "CEO", "seller": False, "soporte": True},
    "ANTONIA_PINEDA": {"role": "STAFF_USER", "label": "Antonia Pineda Lopez", "email": "", "staff_name": "ANTONIA PINEDA LOPEZ", "dept": "PRESUPUESTOS", "seller": False},
    "DANIA_GONZALEZ": {"role": "STAFF_USER", "label": "Dania Lizbeth Gonzalez Lores", "email": "", "staff_name": "DANIA LIZBETH GONZALEZ LORES", "dept": "FINANZAS", "seller": False},
    "JUANY_RODRIGUEZ": {"role": "STAFF_USER", "label": "Juana Maria Rodriguez Juarez", "email": "", "staff_name": "JUANA MARIA RODRIGUEZ JUAREZ", "dept": "FINANZAS", "seller": False},
    "EDUARDO_BENITEZ": {"role": "STAFF_USER", "label": "Eduardo Israel Benitez Garcia", "email": "", "staff_name": "EDUARDO BENITEZ", "dept": "LIMPIEZA", "seller": False},
    "ROLANDO_MORENO": {"role": "STAFF_USER", "label": "Jesus Rolando Moreno Perez", "email": "", "staff_name": "ROLANDO MORENO", "dept": "HVAC", "seller": False},
    # Cotiza desde Electromecánica, igual que Alfonso Correa desde Construcción:
    # la bandera es aditiva y no depende del departamento. Decisión del dueño
    # (2026-08-18) al reportar que su módulo "Cotizaciones" no aparecía; el
    # modal de delegación de `index.html` ya lo ofrecía como destino.
    "MIGUEL_GALLARDO": {"role": "STAFF_USER", "label": "Miguel Angel Gallardo Jaramillo", "email": "", "staff_name": "MIGUEL GALLARDO", "dept": "ELECTROMECANICA", "seller": True},
    "JEHU_MARTINEZ": {"role": "STAFF_USER", "label": "Jehu Arsenio Martinez Montes", "email": "", "staff_name": "JEHU MARTINEZ", "dept": "ELECTROMECANICA", "seller": False},
    "RICARDO_MENDO": {"role": "STAFF_USER", "label": "Ricardo Alonso Mendo Morales", "email": "", "staff_name": "RICARDO MENDO", "dept": "CONSTRUCCION", "seller": False},
    "CARLOS_MENDEZ": {"role": "STAFF_USER", "label": "Carlos Mendez Urbina", "email": "", "staff_name": "CARLOS MENDEZ", "dept": "CALIDAD", "seller": False},
    "INGE_OLIVO": {"role": "STAFF_USER", "label": "Jaime Antonio Olivo Guerrero", "email": "", "staff_name": "JAIME OLIVO", "dept": "CONSTRUCCION", "seller": False},
    "EDUARDO_TERAN": {"role": "STAFF_USER", "label": "Jesus Eduardo Teran Garcia", "email": "", "staff_name": "EDUARDO TERAN", "dept": "PRESUPUESTOS", "seller": True},
    "VANESSA_DE_LARA": {"role": "STAFF_USER", "label": "Erika Vanessa Rodriguez De Lara", "email": "", "staff_name": "VANESSA DE LARA", "dept": "COMPRAS", "seller": False},
    "DIMAS_RAMOS": {"role": "ADMIN_CONTROL", "label": "Dimas Eliel Ramos Garcia", "email": "dimas.ramos@holtmont.com", "staff_name": "DIMAS ELIEL RAMOS GARCIA", "dept": "RH", "seller": False},
    "RUBI_MORENO": {"role": "STAFF_USER", "label": "Rubi Moreno Rodriguez", "email": "", "staff_name": "RUBI MORENO RODRIGUEZ", "dept": "SEGURIDAD", "seller": False},
    "URIMAR_LOPEZ": {"role": "STAFF_USER", "label": "Edgar Urimar Lopez Maldonado", "email": "", "staff_name": "EDGAR URIMAR LOPEZ MALDONADO", "dept": "DISEÑO", "seller": False},
    "SAIRA": {"role": "STAFF_USER", "label": "Zaira Yazmin Aguilar Aguilon", "email": "", "staff_name": "ZAIRA YAZMIN AGUILAR AGUILON", "dept": "FINANZAS", "seller": False},
    "ZAIRA_AGUILAR": {"role": "STAFF_USER", "label": "Zaira Yazmin Aguilar Aguilon", "email": "", "staff_name": "ZAIRA YAZMIN AGUILAR AGUILON", "dept": "FINANZAS", "seller": False},
    "EMILIANO_AREDON": {"role": "STAFF_USER", "label": "Emiliano Arredondo Gomez", "email": "", "staff_name": "EMILIANO ARREDONDO GOMEZ", "dept": "HVAC", "seller": False},
    "SONIA_GARCIA": {"role": "STAFF_USER", "label": "Sonia Garcia Perez", "email": "", "staff_name": "SONIA GARCIA PEREZ", "dept": "COMPRAS", "seller": False},
    "FRANCISCO_SANCHEZ_SERNA": {"role": "STAFF_USER", "label": "Francisco Sanchez Serna", "email": "", "staff_name": "FRANCISCO SANCHEZ SERNA", "dept": "RH", "seller": False},
    "LILIANA_MARTINEZ": {"role": "STAFF_USER", "label": "Liliana Martinez Ibarra", "email": "", "staff_name": "LILIANA AYLIN MARTINEZ IBARRA", "dept": "RH", "seller": False},
    "LAURA_HUERTA": {"role": "STAFF_USER", "label": "Laura Huerta Rocha", "email": "", "staff_name": "LAURA EDITH HUERTA ROCHA", "dept": "RH", "seller": False},
    "ROCIO_CASTRO": {"role": "STAFF_USER", "label": "Rocio Castro Covarrubias", "email": "", "staff_name": "ROCIO ABIGAIL CASTRO COVARRUBIAS", "dept": "FINANZAS", "seller": False},
    "GERALDINE_MARTINEZ": {"role": "STAFF_USER", "label": "Geraldine Marie Martinez Hernandez", "email": "", "staff_name": "GERALDINE MARTINEZ HERNANDEZ", "dept": "PRECIOS UNITARIOS", "seller": False},
    "CESAR_EDUARDO_GARCIA": {"role": "STAFF_USER", "label": "Cesar Eduardo Garcia Avalos", "email": "", "staff_name": "CESAR EDUARDO GARCIA AVALOS", "dept": "CONSTRUCCION", "seller": False},
    # `agente_sql` es la tercera bandera aditiva. Solo la lleva esta cuenta:
    # el agente de consultas lee `tasks` y `quotes` COMPLETAS, sin filtrar por
    # hoja, así que quien lo ve ve el trabajo de todos los departamentos —y
    # puede pedir que se redacte un correo con eso—. Decisión del dueño
    # (2026-08-22): de momento solo ADMIN (por rol) y ANTONIO_SALAZAR.
    "ANTONIO_SALAZAR": {"role": "STAFF_USER", "label": "Antonio Salazar", "email": "", "staff_name": "ANTONIO SALAZAR", "dept": "GENERAL", "seller": False, "soporte": True, "prospeccion": True, "agente_sql": True},
    # Baja (2026-08): se retiró de `USER_DB` en Apps Script y no se migra a
    # `profiles`, así que no puede entrar a ninguna de las dos plataformas. Su
    # casilla se conserva aquí porque el organigrama lo registra en GENERAL y
    # `test_organigrama.py` verifica esa transcripción; sin contraseña, una
    # entrada en esta semilla no concede acceso a nada.
    "CESAR_GOMEZ": {"role": "STAFF_USER", "label": "Cesar Gomez", "email": "", "staff_name": "CESAR GOMEZ", "dept": "GENERAL", "seller": False},
}


# --- Fichas de persona: nombre completo, puesto y foto ----------------
# Transcripción del documento de RH "FOTOS CON PUESTO DE TRABAJO" (31 fichas).
# La clave es el **nombre del organigrama** (`INITIAL_DIRECTORY[*]["name"]`,
# columna `nombre` de `people`), no la cuenta: la misma persona puede tener dos
# cuentas (`SAIRA`/`ZAIRA_AGUILAR`) o ninguna, y el directorio se pinta con
# gente que no entra al sistema.
#
# Tres campos y ninguno es redundante:
#
#   `nombre` — el nombre completo **como lo escribe RH**, con acentos y con los
#              segundos nombres que la semilla recorta ("Liliana Martinez
#              Ibarra" -> "Liliana Aylin Martínez Ibarra"). Es para mostrar; el
#              canónico para abrir un tracker sigue siendo la clave.
#   `puesto` — el puesto tal cual aparece en el documento. No se traduce ni se
#              normaliza: "Compras" y "Coordinador Electromecanica" están así en
#              el original y `tests/test_fichas_personal.py` lo verifica contra
#              la misma transcripción.
#   `foto`   — ruta pública servida por `/fotos/<archivo>` (api/static/fotos).
#              El nombre del archivo es la única lista blanca del endpoint: lo
#              que no está aquí no se sirve.
#
# Quien no aparece en el documento (LUIS CARLOS, JUAN JOSE SANCHEZ, DANIELA
# CASTRO, CESAR GOMEZ, ANTONIO SALAZAR y las cuentas de control) simplemente no
# tiene ficha: la vista cae a la inicial del nombre, como antes.
FICHAS: Dict[str, Dict[str, str]] = {
    "DIMAS ELIEL RAMOS GARCIA": {
        "nombre": "Dimas Eliel Ramos García",
        "puesto": "Coordinador de Recursos Humanos",
        "foto": "/fotos/dimas-eliel-ramos-garcia.jpg"},
    "LAURA EDITH HUERTA ROCHA": {
        "nombre": "Laura Edith Huerta Rocha",
        "puesto": "Especialista en Nominas",
        "foto": "/fotos/laura-edith-huerta-rocha.jpg"},
    "FRANCISCO SANCHEZ SERNA": {
        "nombre": "Francisco Sánchez Serna",
        "puesto": "Auxiliar Recursos Humanos",
        "foto": "/fotos/francisco-sanchez-serna.jpg"},
    "LILIANA AYLIN MARTINEZ IBARRA": {
        "nombre": "Liliana Aylin Martínez Ibarra",
        "puesto": "Auxiliar Recursos Humanos",
        "foto": "/fotos/liliana-aylin-martinez-ibarra.jpg"},
    "SONIA GARCIA PEREZ": {
        "nombre": "Sonia Pérez García",
        "puesto": "Compras",
        "foto": "/fotos/sonia-garcia-perez.jpg"},
    "VANESSA DE LARA": {
        "nombre": "Vanessa Rodríguez de Lara",
        "puesto": "Auxiliar de compras",
        "foto": "/fotos/vanessa-de-lara.jpg"},
    "JUDITH ECHAVARRIA": {
        "nombre": "Cristian Judith Echavarria Rodríguez",
        "puesto": "Compras",
        "foto": "/fotos/judith-echavarria.jpg"},
    "ANGEL SALINAS": {
        "nombre": "José Ángel Salinas Ramírez",
        "puesto": "Diseño",
        "foto": "/fotos/angel-salinas.jpg"},
    "EDGAR URIMAR LOPEZ MALDONADO": {
        "nombre": "Edgar Urimar López Maldonado",
        "puesto": "Calculo Estructural",
        "foto": "/fotos/edgar-urimar-lopez-maldonado.jpg"},
    "TERESA GARZA": {
        "nombre": "María Teresa Hernández Garza",
        "puesto": "Precios Unitarios",
        "foto": "/fotos/teresa-garza.jpg"},
    "GERALDINE MARTINEZ HERNANDEZ": {
        "nombre": "Geraldine Marie Martínez Hernández",
        "puesto": "Auxiliar Técnico en precios unitarios",
        "foto": "/fotos/geraldine-martinez-hernandez.jpg"},
    "EDUARDO BENITEZ": {
        "nombre": "Eduardo Israel Benitez García",
        "puesto": "Coordinador de Limpieza y Jardinería",
        "foto": "/fotos/eduardo-benitez.jpg"},
    "CARLOS MENDEZ": {
        "nombre": "Carlos Méndez Urbina",
        "puesto": "Calidad",
        "foto": "/fotos/carlos-mendez.jpg"},
    "ROLANDO MORENO": {
        "nombre": "Jesús Rolando Moreno Pérez",
        "puesto": "Auxiliar Administrativo HVAC",
        "foto": "/fotos/rolando-moreno.jpg"},
    "EMILIANO ARREDONDO GOMEZ": {
        "nombre": "Emiliano Arredondo Gómez",
        "puesto": "Técnico HVAC",
        "foto": "/fotos/emiliano-arredondo-gomez.jpg"},
    "JEHU MARTINEZ": {
        "nombre": "Martínez Montes Jehu Arsenio",
        "puesto": "Auxiliar Administrativo Electromecánica",
        "foto": "/fotos/jehu-martinez.jpg"},
    "MIGUEL GALLARDO": {
        "nombre": "Miguel Ángel Gallardo Jaramillo",
        "puesto": "Coordinador Electromecanica",
        "foto": "/fotos/miguel-gallardo.jpg"},
    "SEBASTIAN PADILLA": {
        "nombre": "Erick Sebastián Padilla Carrillo",
        "puesto": "Ventas Electromecánica",
        "foto": "/fotos/sebastian-padilla.jpg"},
    "EDUARDO TERAN": {
        "nombre": "Jesús Eduardo Teran García",
        "puesto": "Coordinador de presupuestos",
        "foto": "/fotos/eduardo-teran.jpg"},
    "ANTONIA PINEDA LOPEZ": {
        "nombre": "Antonia Pineda López",
        "puesto": "Auxiliar de presupuestos",
        "foto": "/fotos/antonia-pineda-lopez.jpg"},
    "EDUARDO MANZANARES": {
        "nombre": "Eduardo Manzanares Sanchez",
        "puesto": "Coordinador HVAC",
        "foto": "/fotos/eduardo-manzanares.jpg"},
    "RAMIRO RODRIGUEZ": {
        "nombre": "Ramiro Rodríguez Escalante",
        "puesto": "Ventas construcción",
        "foto": "/fotos/ramiro-rodriguez.jpg"},
    "RUBI MORENO RODRIGUEZ": {
        "nombre": "Rubi Arelly Moreno Rodríguez",
        "puesto": "Supervisor de Seguridad",
        "foto": "/fotos/rubi-moreno-rodriguez.jpg"},
    "JAIME OLIVO": {
        "nombre": "Jaime Antonio Olivo Guerrero",
        "puesto": "Superintendente de construcción",
        "foto": "/fotos/jaime-olivo.jpg"},
    "RICARDO MENDO": {
        "nombre": "Ricardo Alonso Mendo Morales",
        "puesto": "Residente de obra",
        "foto": "/fotos/ricardo-mendo.jpg"},
    "ALFONSO CORREA": {
        "nombre": "Alfonso Correa de Leon",
        "puesto": "Supervisor de Obra",
        "foto": "/fotos/alfonso-correa.jpg"},
    "CESAR EDUARDO GARCIA AVALOS": {
        "nombre": "Cesar Eduardo García Avalos",
        "puesto": "Supervisor de Obra",
        "foto": "/fotos/cesar-eduardo-garcia-avalos.jpg"},
    "JUANA MARIA RODRIGUEZ JUAREZ": {
        "nombre": "Juana María Rodríguez Juarez",
        "puesto": "Coordinador de Finanzas",
        "foto": "/fotos/juana-maria-rodriguez-juarez.jpg"},
    "ROCIO ABIGAIL CASTRO COVARRUBIAS": {
        "nombre": "Rocio Abigail Castro Covarrubias",
        "puesto": "Facturación",
        "foto": "/fotos/rocio-abigail-castro-covarrubias.jpg"},
    "ZAIRA YAZMIN AGUILAR AGUILON": {
        "nombre": "Zaira Yazmin Aguilar Aguilon",
        "puesto": "Auxiliar de finanzas",
        "foto": "/fotos/zaira-yazmin-aguilar-aguilon.jpg"},
    "DANIA LIZBETH GONZALEZ LORES": {
        "nombre": "Dania Lizbeth González Lores",
        "puesto": "Auxiliar de finanzas",
        "foto": "/fotos/dania-lizbeth-gonzalez-lores.jpg"},
}

# Lista blanca del endpoint `/fotos/<archivo>`: los nombres de archivo que
# `FICHAS` referencia y nada más. Se deriva del catálogo en vez de leer el
# directorio para que agregar un archivo suelto a `api/static/fotos` no lo
# publique solo.
FOTOS_PUBLICAS = frozenset(
    ficha["foto"].rsplit("/", 1)[-1] for ficha in FICHAS.values()
)


# --- Resolución de perfil ----------------------------------------------
# El original hacía `USER_DB[String(username).toUpperCase().trim()] || {}` en
# línea, dentro de `getSystemConfig`. Aquí se aísla porque además hay que
# preferir la base cuando la haya: `profiles` es la fuente que el dueño puede
# editar sin desplegar, y `PERFILES` la semilla que garantiza que el sistema
# arranque con el organigrama correcto.


def clave_usuario(username: Any) -> str:
    """Normaliza igual que el original: mayúsculas y sin espacios extremos."""
    return str(username or "").strip().upper()


def perfil(username: Any) -> Dict[str, Any]:
    """
    Perfil de una cuenta. Devuelve `{}` si no se conoce, como el original.

    Intenta primero `profiles` en Supabase y cae a la semilla. Un fallo de red
    no puede dejar sin permisos a quien acaba de autenticarse, así que la
    excepción se traga a propósito y se sigue con `PERFILES`.
    """
    clave = clave_usuario(username)
    if not clave:
        return {}

    desde_base = _perfil_desde_base(clave)
    if desde_base:
        return _con_ficha(desde_base)

    base = PERFILES.get(clave)
    if base is None:
        return {}
    return _con_ficha(dict(base))


def ficha(nombre: Any) -> Dict[str, str]:
    """
    Nombre completo, puesto y foto de una persona, por cualquiera de sus nombres.

    Primero la clave del catálogo (el nombre del organigrama) y, si no, los
    alias de `ALIAS_DE_FICHA`: `people` en producción tiene a la misma persona
    escrita de varias formas ("CARLOS MENDEZ" y "CARLOS MENDEZ URBINA", "JAIME
    OLIVO" e "INGE OLIVO") y las dos filas pintan tarjeta.

    Devuelve `{}` para quien no tiene ficha —el documento de RH cubre 31
    personas y `people` tiene 54 filas—, así que la vista siempre debe poder
    caer a la inicial.
    """
    clave = _clave_nombre(nombre)
    if not clave:
        return {}
    if clave in FICHAS:
        return dict(FICHAS[clave])
    return dict(FICHAS.get(ALIAS_DE_FICHA.get(clave, ""), {}))


def _con_ficha(datos: Dict[str, Any]) -> Dict[str, Any]:
    """
    Agrega `nombre`, `puesto` y `foto` a un perfil ya resuelto.

    La ficha se busca por `staff_name` —el nombre del organigrama, que es la
    clave del catálogo— y solo si falta, por `label`: las cuentas de control
    (`JAIME_OLIVO`, `JESUS_CANTU`) no tienen hoja y `label` es lo único que las
    nombra.

    Lo que ya traiga `datos` manda sobre el catálogo: `profiles` es lo que el
    dueño puede editar sin desplegar, y la transcripción de RH es el respaldo.
    `nombre` cae a `label` para que la vista nunca se quede sin qué mostrar.
    """
    f = ficha(datos.get("staff_name") or datos.get("label"))
    return {
        **datos,
        "nombre": datos.get("nombre") or f.get("nombre", "") or datos.get("label", ""),
        "puesto": datos.get("puesto") or f.get("puesto", ""),
        "foto": datos.get("foto") or f.get("foto", ""),
    }


def enriquecer_directorio(personas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Suma a cada fila del directorio su ficha: nombre completo, puesto y foto.

    **`name` no se toca.** Es el nombre canónico con el que se abre el tracker
    de la persona y el que está guardado en `source_sheet`; sustituirlo por el
    nombre con acentos estrenaría una partición vacía (misma trampa que
    documenta `_nombres_de_la_cuenta`). `nombre` es solo para mostrar.
    """
    return [
        {
            **persona,
            "nombre": persona.get("nombre") or ficha(persona.get("name")).get("nombre", "")
            or persona.get("name", ""),
            "puesto": persona.get("puesto") or ficha(persona.get("name")).get("puesto", ""),
            "foto": persona.get("foto") or ficha(persona.get("name")).get("foto", ""),
        }
        for persona in personas
    ]


# `profiles` se lee una vez por proceso: `/api/config` resuelve varios perfiles
# en una sola petición y no tiene sentido pagar una consulta por cada uno.
# Mismo patrón que `_PLAN_SEMANAL_CACHE` en `sheets.py`, con su reset para las
# pruebas y para cuando el dueño edite la tabla.
_CACHE_PROFILES: Dict[str, Any] = {}


def reset_cache_perfiles() -> None:
    _CACHE_PROFILES.clear()


def _filas_profiles() -> List[Dict[str, Any]]:
    if "filas" not in _CACHE_PROFILES:
        try:
            from api.services.supabase_manager import sb_manager

            _CACHE_PROFILES["filas"] = sb_manager.select("profiles") or []
        except Exception as exc:  # noqa: BLE001 - la semilla es respaldo suficiente
            # Se avisa una sola vez: en un entorno sin base esto se llamaría en
            # cada resolución de perfil y el aviso ahogaría el resto del log.
            print(f"[organigrama] No se pudo leer `profiles`, se usa la semilla: {exc}")
            _CACHE_PROFILES["filas"] = []
    return _CACHE_PROFILES["filas"]


def _bandera_aditiva(fila: Dict[str, Any], base: Dict[str, Any], nombre: str) -> bool:
    """
    Valor de una bandera del perfil, prefiriendo `profiles` y cayendo a la semilla.

    `is None` en vez de `.get(nombre, default)`: hoy la tabla puede no tener la
    columna y hay que caer a la semilla, pero si mañana se agrega y llega en
    nulo, también debe caer — un nulo no es "revocada".

    Está fuera de `_perfil_desde_base` porque esa función ya estaba en B (10) y
    resolver aquí las dos banderas en línea la habría subido a C (11). Una
    función existente sale igual o mejor (RESTRICCIONES_EXTREMAS.md §5).
    """
    return bool(fila[nombre] if fila.get(nombre) is not None else base.get(nombre, False))


def _perfil_desde_base(clave: str) -> Optional[Dict[str, Any]]:
    for fila in _filas_profiles():
        if clave_usuario(fila.get("username")) != clave:
            continue
        # `or` en vez de `.get(k, default)`: en la base una columna vacía llega
        # como cadena vacía o None, y ambas deben caer a la semilla.
        base = PERFILES.get(clave, {})
        return {
            "role": fila.get("role") or base.get("role", "STAFF_USER"),
            "label": fila.get("label") or base.get("label", clave),
            "email": fila.get("email") or base.get("email", ""),
            "staff_name": fila.get("staff_name") or base.get("staff_name", ""),
            "dept": fila.get("dept") or base.get("dept", ""),
            # Las tres columnas de la ficha. Si la tabla no las tiene —hoy no
            # las tiene— llegan vacías y `_con_ficha` las rellena con la
            # transcripción de RH; si mañana se agregan, la base manda.
            "nombre": fila.get("nombre") or base.get("nombre", ""),
            "puesto": fila.get("puesto") or base.get("puesto", ""),
            "foto": fila.get("foto") or base.get("foto", ""),
            # `seller` se suma, no se sustituye: si la semilla marca a alguien
            # como vendedor, una fila de `profiles` que traiga la columna
            # apagada no puede quitarle el módulo. Es el mismo accidente que ya
            # se midió con `soporte` (ANTONIO_SALAZAR, 2026-08-13): la bandera
            # queda encendida en el repo y apagada en producción, sin aviso,
            # porque `profiles` se pobló una vez desde `USER_DB` y no se vuelve
            # a tocar al desplegar. La base sí puede **conceder** la bandera a
            # quien la semilla no marca; para retirarla se edita la semilla.
            "seller": bool(fila.get("seller")) or bool(base.get("seller", False)),
            # Las dos banderas aditivas. Van listadas aquí y no heredadas
            # porque este diccionario se reconstruye clave por clave: la que no
            # aparezca se pierde en cuanto la cuenta existe en `profiles`
            # —encendida en la semilla, apagada en producción, sin aviso—.
            # Medido contra el proyecto real el 2026-08-13 con ANTONIO_SALAZAR,
            # que es justamente quien lleva las dos.
            #
            #   `soporte`     -> la vista de tickets de bug
            #   `prospeccion` -> el módulo del mapa del DENUE
            #   `agente_sql`  -> el agente de consultas en lenguaje natural
            "soporte": _bandera_aditiva(fila, base, "soporte"),
            "prospeccion": _bandera_aditiva(fila, base, "prospeccion"),
            "agente_sql": _bandera_aditiva(fila, base, "agente_sql"),
        }
    return None


def nombre_de_hoja(username: Any) -> str:
    """
    Hoja/partición de tracker de la persona.

    El original usa `u.staffName || u.label`: hay cuentas sin `staffName` cuyo
    tracker se llama como su etiqueta. Se conserva ese respaldo.
    """
    p = perfil(username)
    return p.get("staff_name") or p.get("label") or clave_usuario(username)


def _clave_nombre(nombre: Any) -> str:
    """Normaliza un nombre **solo para comparar**: mayúsculas y un solo espacio."""
    return " ".join(str(nombre or "").replace("_", " ").split()).upper()


def _nombres_de_la_cuenta(datos: Dict[str, Any]) -> List[str]:
    """
    Los nombres con los que una misma persona aparece por el sistema.

    Son dos y se guardan por separado porque **no son iguales**: `staff_name`
    es la hoja de su tracker ("VANESSA DE LARA") y `label` el nombre completo
    con el que la registra el directorio ("Erika Vanessa Rodriguez De Lara").

    El canónico es siempre `staff_name`, que es el que abre su vista
    (`nombre_de_hoja`) y el que está almacenado en `source_sheet`. El `label`
    solo sirve para **reconocerla**; devolverlo como canónico estrenaría una
    partición con su capitalización ("Jaime Olivo").

    Una cuenta sin `staff_name` no tiene tracker propio (las de control:
    `JAIME_OLIVO`, `JESUS_CANTU`, `PREWORK_ORDER`) y no entra aquí.
    """
    hoja = str(datos.get("staff_name") or "").strip()
    # `ANTONIA_VENTAS` es el core de ventas, no el tracker de una persona
    # (AGENTS.md §3): traducir hacia o desde esa hoja metería cotizaciones en un
    # tracker personal.
    if not hoja or "VENTAS" in _clave_nombre(hoja):
        return []

    nombres = [hoja]
    etiqueta = str(datos.get("label") or "").strip()
    if etiqueta and _clave_nombre(etiqueta) != _clave_nombre(hoja):
        nombres.append(etiqueta)
    return nombres


def hoja_de_cotizaciones(username: Any) -> str:
    """
    Partición de `quotes` de la persona, o cadena vacía si no vende.

    No es `nombre_de_hoja` con un sufijo pegado, porque hay dos excepciones que
    importan:

    * **Antonia.** Su tabla de cotizaciones es `ANTONIA_VENTAS`, el core de
      ventas, y su tracker es `ANTONIA PINEDA LOPEZ` (AGENTS.md §3). Darle
      "ANTONIA PINEDA LOPEZ (VENTAS)" la dejaría preguntando contra una
      partición que no existe.
    * **Quien no vende.** Devuelve cadena vacía y no el nombre de su tracker:
      acotar `quotes` por una hoja que ahí no existe respondería siempre cero,
      y "no tengo cotizaciones" no es lo mismo que "esta pregunta no es para
      ti". Quien llama decide qué hacer con el vacío; lo que no puede es
      quedarse sin acotar.
    """
    clave = clave_usuario(username)
    datos = perfil(clave)
    if not datos:
        return ""
    if clave == "ANTONIA_VENTAS":
        return "ANTONIA_VENTAS"
    if not datos.get("seller"):
        return ""
    hoja = nombre_de_hoja(clave)
    return f"{hoja} (VENTAS)" if hoja else ""


def hojas_de_persona(nombre: Any) -> tuple:
    """
    Hojas de tracker que corresponden a una persona, la canónica primero.

    Existe porque el nombre de la hoja se decidía en dos sitios que podían no
    coincidir: la vista abre `nombre_de_hoja(cuenta)` (el `staff_name`) y el
    selector de involucrados ofrece los nombres de `people` (que suelen ser el
    `label`). Cuando los dos textos difieren, guardar por un lado y leer por el
    otro deja la actividad archivada en una partición que nadie abre: se guarda
    de verdad, con éxito, y la persona no la vuelve a ver.

    Devuelve `()` para un nombre que el organigrama no conoce —ahí no hay nada
    que traducir— y para la hoja maestra de ventas.
    """
    clave = _clave_nombre(nombre)
    if not clave:
        return ()

    por_etiqueta: tuple = ()
    for cuenta, semilla in PERFILES.items():
        nombres = _nombres_de_la_cuenta(perfil(cuenta) or semilla)
        if not nombres:
            continue
        # La hoja gana sobre la etiqueta: dos cuentas pueden compartir etiqueta
        # y solo una tiene ese tracker.
        if _clave_nombre(nombres[0]) == clave:
            return tuple(nombres)
        if not por_etiqueta and any(_clave_nombre(n) == clave for n in nombres[1:]):
            por_etiqueta = tuple(nombres)
    return por_etiqueta


def hoja_canonica(nombre: Any) -> str:
    """
    La **única** hoja de tracker de una persona, a partir de cualquiera de sus
    nombres. Cadena vacía si el organigrama no la conoce.

    Es `hojas_de_persona()[0]` con nombre propio, y existe porque quien decide
    *a dónde escribir* necesita un solo destino, no la lista de todos los
    nombres con los que a alguien se le puede llamar. Usar la lista para leer y
    el texto crudo para escribir es justo lo que partió en dos el tracker de
    Carlos Méndez: sus tareas se guardaron mitad en `CARLOS MENDEZ`
    (`staff_name`) y mitad en `CARLOS MENDEZ URBINA` (`label`, que es lo que
    ofrece el selector de involucrados), y como la lectura une las dos
    particiones, cada tarea aparecía **dos veces** en su tabla.

    Devolver "" y no el nombre recibido es deliberado: quien llama tiene que
    poder distinguir "el organigrama dice que su hoja es esta" de "no sé quién
    es", que son decisiones distintas.
    """
    hojas = hojas_de_persona(nombre)
    return hojas[0] if hojas else ""


def es_vendedor(username: Any) -> bool:
    return bool(perfil(username).get("seller"))


def correo(username: Any) -> str:
    return perfil(username).get("email") or ""


def vendedores() -> List[str]:
    """
    Cuentas con `seller: true`.

    Reemplaza a las listas de vendedores repartidas por el código del original
    (anti-patrón §23.2): quien necesite saber quién vende pregunta aquí.
    """
    return sorted(u for u, p in PERFILES.items() if p.get("seller"))


# --- Credenciales -------------------------------------------------------
# `profiles` es la tabla de cuentas. Guarda la contraseña en texto plano por
# decisión explícita del dueño (2026-07): se migran a hash cuando se haga la
# migración completa. Hasta entonces, dos reglas que sí se respetan aquí:
#
#   1. La contraseña **nunca** sale de este módulo. `perfil()` no la incluye en
#      el diccionario que devuelve, así que no puede filtrarse por /api/config.
#   2. La comparación usa `compare_digest`, que no filtra la longitud ni el
#      prefijo correcto por tiempo de respuesta.

# Nombres posibles de la columna de contraseña. Como el resto del esquema, no se
# puede introspeccionar desde el entorno de desarrollo.
_COLUMNAS_CLAVE = ("password", "pass", "contrasena", "contraseña", "clave")


def columnas_de_credencial() -> tuple:
    """Los nombres que este módulo considera contraseña. Los usa el filtro de /api/data."""
    return _COLUMNAS_CLAVE


def validar_credenciales(username: Any, password: Any) -> Optional[Dict[str, Any]]:
    """
    Comprueba usuario y contraseña contra `profiles`. Devuelve el perfil o None.

    **Lee sin caché, a propósito.** `_filas_profiles()` guarda las filas por
    proceso para que `/api/config` no consulte una vez por perfil; usar esa caché
    aquí haría que un cambio de contraseña no tuviera efecto hasta reiniciar.
    """
    clave = clave_usuario(username)
    if not clave or password is None:
        return None

    try:
        from api.services.supabase_manager import sb_manager

        filas = sb_manager.select("profiles") or []
    except Exception as exc:  # noqa: BLE001
        print(f"[organigrama] No se pudo leer `profiles` para autenticar: {exc}")
        return None

    for fila in filas:
        if clave_usuario(fila.get("username")) != clave:
            continue

        guardada = next((str(fila[c]) for c in _COLUMNAS_CLAVE
                         if c in fila and fila[c] is not None), None)
        if guardada is None:
            # La cuenta existe pero no tiene contraseña guardada. No se deja
            # entrar con cualquier cosa: se rechaza y queda constancia.
            print(f"[organigrama] `profiles` no tiene columna de contraseña para {clave}.")
            return None

        if not secrets.compare_digest(guardada, str(password)):
            return None

        semilla = PERFILES.get(clave, {})
        return {
            "role": fila.get("role") or semilla.get("role", "STAFF_USER"),
            "label": fila.get("label") or semilla.get("label", clave),
            "email": fila.get("email") or semilla.get("email", ""),
            "staff_name": fila.get("staff_name") or semilla.get("staff_name", ""),
            "dept": fila.get("dept") or semilla.get("dept", ""),
            "seller": bool(fila.get("seller", semilla.get("seller", False))),
        }
    return None


# --- Alias: los otros nombres con los que `people` llama a la misma persona ---
#
# El catálogo se indexa por el nombre del organigrama, pero la tabla real no es
# tan limpia: tiene 54 filas para 38 personas y la misma gente aparece con el
# nombre completo, con "INGE" delante o con una errata. Cada una de esas filas
# pinta su tarjeta en el directorio, y sin alias saldría sin foto ni puesto.
#
# Esto **no** deduplica `people` ni toca el nombre canónico: solo dice qué ficha
# mostrar para cada texto. Unir las filas es otra tarea, y más delicada, porque
# `source_sheet` guarda tareas contra esos mismos textos.
ALIAS_MANUALES: Dict[str, str] = {
    # Fila -> clave de FICHAS.  El motivo va al lado: sin él esta tabla se
    # vuelve un cajón donde cualquiera puede meter una suposición.
    "DIMAS RAMOS": "DIMAS ELIEL RAMOS GARCIA",          # cuenta DIMAS_RAMOS
    "ROCIO CASTRO": "ROCIO ABIGAIL CASTRO COVARRUBIAS",  # cuenta ROCIO_CASTRO
    # Errata en la base: le falta la "S" final a COVARRUBIAS.
    "ROCIO ABIGAIL CASTRO COVARRUBIA": "ROCIO ABIGAIL CASTRO COVARRUBIAS",
    "INGE OLIVO": "JAIME OLIVO",                        # cuenta INGE_OLIVO
    "INGE GALLARDO": "MIGUEL GALLARDO",                 # único Gallardo del organigrama
    "EDGAR LOPEZ": "EDGAR URIMAR LOPEZ MALDONADO",      # cuenta EDGAR_LOPEZ de USER_DB
    # Fila duplicada, con un "2" pegado al final del nombre.
    "CESAR EDUARDO GARCIA AVALOS2": "CESAR EDUARDO GARCIA AVALOS",
}


def _alias_desde_los_perfiles() -> Dict[str, str]:
    """
    El `label` de cada cuenta apunta a la ficha de su hoja.

    Se deriva en vez de escribirse a mano porque ya existe la relación: el
    selector de involucrados ofrece los `label` de `people` ("MARIA TERESA
    HERNANDEZ GARZA") mientras el tracker se llama como el `staff_name`
    ("TERESA GARZA"). Es la misma dualidad que documenta `hoja_canonica`, y
    dejarla derivada evita que las dos listas se separen con el tiempo.
    """
    derivados: Dict[str, str] = {}
    for datos in PERFILES.values():
        hoja = _clave_nombre(datos.get("staff_name"))
        etiqueta = _clave_nombre(datos.get("label"))
        if hoja in FICHAS and etiqueta and etiqueta not in FICHAS:
            derivados.setdefault(etiqueta, hoja)
    return derivados


# Los manuales al final: una fila real de la base gana a una derivada.
ALIAS_DE_FICHA: Dict[str, str] = {**_alias_desde_los_perfiles(), **ALIAS_MANUALES}
