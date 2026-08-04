#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador del mapa de arquitectura de los repositorios Holtmont.

Produce dos entregables a partir de un único modelo:
  * arquitectura.json  -> {nodes, edges, flows} para agentes de IA
  * arquitectura.html  -> diagrama interactivo autocontenido (sin CDN)

El modelo se escribe a mano a partir de la lectura del código fuente; el
script sólo lo valida (ids únicos, aristas con extremos existentes, pasos de
flujo conectados) y lo serializa.
"""

from __future__ import annotations

import json
import os
import sys

# ----------------------------------------------------------------------
# SISTEMAS Y CAPAS
# ----------------------------------------------------------------------

SYSTEMS = [
    {
        "id": "holtmont",
        "name": "Holtmont Workspace",
        "repo": "HOLTMONT-PYTHON",
        "tagline": "ERP operativo: tracker de tareas, cotizaciones, PPC y agentes de IA",
        "stack": "Vue 3 (CDN) + FastAPI + Supabase/PostgREST + LangGraph, desplegado en Vercel",
        "layers": [
            "Clientes",
            "Borde / Routing",
            "API (FastAPI)",
            "Agentes de IA",
            "Dominio y reglas",
            "Persistencia",
            "Motores de datos",
            "Servicios externos",
            "Verificación",
        ],
    },
    {
        "id": "mlclaude",
        "name": "Oficina Eficiencia",
        "repo": "MLCLAUDE",
        "tagline": "Visión por computadora on-premise: asistencia, zonas y eficiencia",
        "stack": "YOLOv8 + supervision/ByteTrack + face_recognition + SQLite cifrado, empaquetado con PyArmor/PyInstaller",
        "layers": [
            "UI de escritorio",
            "Captura de video",
            "Percepción (IA)",
            "Dominio",
            "Persistencia",
            "Análisis y reportes",
            "Seguridad y plataforma",
            "Sistema y externos",
            "Verificación",
        ],
    },
]

# ----------------------------------------------------------------------
# NODOS
# ----------------------------------------------------------------------
# type: ui | api | agent | rules | service | repo | engine | data | external
#       | security | build | test | legacy

N = []


def node(id, label, type, system, layer, desc, tech="", files=(), tags=()):
    N.append(
        {
            "id": id,
            "label": label,
            "type": type,
            "system": system,
            "layer": layer,
            "desc": desc,
            "tech": tech,
            "files": list(files),
            "tags": list(tags),
        }
    )


# ======================= HOLTMONT WORKSPACE ===========================

# --- L0 Clientes -------------------------------------------------------
node(
    "h_index", "index.html · Vue 3", "ui", "holtmont", 0,
    "Monolito de interfaz (~690 KB). Vue 3 cargado por CDN, sin build step: todo el CSS y el JS "
    "van en línea. Contiene 24 vistas (DASHBOARD, STAFF_TRACKER, PPC_FORM, PPC_DINAMICO, "
    "WEEKLY_PLAN, KPI_DASHBOARD, QUOTE_METRICS, PROJECTS, INFO_BANK, PERSONAL_AGENDA, "
    "DIRECTORY_VIEW, ECG_VIEW, WORKORDER_FORM…). Genera `_tempId` por fila nueva y bloquea "
    "envíos duplicados con la bandera reactiva `isSubmitting`.",
    "Vue 3 (CDN), HTML/CSS/JS en línea",
    ["index.html"],
    ["monolito", "sin-build"],
)
node(
    "h_workorder_html", "workorder_form.html", "ui", "holtmont", 0,
    "Formulario de Pre Work Order: materiales, herramienta, equipo, mano de obra, viáticos, "
    "transporte e ingeniería. Se sirve como estático y envía el lote completo al backend.",
    "HTML + JS",
    ["workorder_form.html"],
)
node(
    "h_streamlit", "streamlit_cotizador", "ui", "holtmont", 0,
    "Aplicación Streamlit paralela para cotizar por voz: graba audio, lo transcribe, permite "
    "editar los conceptos extraídos y exporta la cotización a PDF a partir de una plantilla.",
    "Streamlit",
    ["streamlit_app.py", "streamlit_cotizador/app.py", "streamlit_cotizador/work_order_view.py"],
)
node(
    "h_codigo", "CODIGO.js · Apps Script", "legacy", "holtmont", 0,
    "Backend original en Google Apps Script (210 KB, 37 funciones `apiX`). Ya no es la ruta de "
    "ejecución, pero sigue siendo la especificación viva: `tracker_rules.py` es su gemelo en "
    "Python y `tests/test_paridad_appscript.py` verifica la paridad regla por regla.",
    "Google Apps Script",
    ["CODIGO.js", "appsscript.json"],
    ["referencia", "paridad"],
)

# --- L1 Borde ----------------------------------------------------------
node(
    "h_apiservice", "api_service.js", "ui", "holtmont", 1,
    "Capa de compatibilidad del monolito: reemplaza las llamadas `google.script.run` del "
    "original por `fetch` contra FastAPI, conservando la forma de respuesta "
    "`{success, data, history, headers}` para no tocar index.html.",
    "JavaScript (fetch)",
    ["api_service.js"],
    ["contrato"],
)
node(
    "h_vercel", "vercel.json", "external", "holtmont", 1,
    "Enrutamiento de Vercel: `index.html`, `api_service.js` y `workorder_form.html` se sirven "
    "como estáticos con @vercel/static; todo lo demás cae en `api/main.py` con @vercel/python. "
    "Corrige el fallo en que Vercel servía el código fuente de la API en vez de ejecutarla.",
    "Vercel (builds + routes)",
    ["vercel.json"],
    ["despliegue"],
)

# --- L2 API ------------------------------------------------------------
node(
    "h_fastapi", "api/main.py · FastAPI", "api", "holtmont", 2,
    "Punto de entrada único (1.044 líneas): carga el `.env`, configura CORS, sirve los "
    "estáticos y expone ~70 endpoints. Monta además el router relacional v2 cuando la "
    "configuración lo permite.",
    "FastAPI + Pydantic",
    ["api/main.py"],
)
node(
    "h_ep_auth", "/api/login · logout", "api", "holtmont", 2,
    "Autenticación en tres saltos: (1) tabla `profiles` de Supabase — la única fuente real; "
    "(2) hoja/tabla `USERS` heredada; (3) login de desarrollo por variables de entorno, sólo si "
    "gspread está en modo mock. Cada intento, exitoso o no, se audita.",
    "FastAPI",
    ["api/main.py:368", "api/services/organigrama.py:267"],
    ["seguridad"],
)
node(
    "h_ep_data", "/api/data · /api/config", "api", "holtmont", 2,
    "Lectura genérica de una hoja como matriz de valores y configuración del sistema "
    "(directorio, departamentos, permisos). `/api/data` bloquea las tablas sensibles y elimina "
    "las columnas de credencial antes de responder.",
    "FastAPI",
    ["api/main.py:507", "api/main.py:121"],
    ["seguridad"],
)
node(
    "h_ep_legacy", "/api/legacy/* (≈35)", "api", "holtmont", 2,
    "Puerto uno a uno de las funciones `apiX` de Apps Script: saveTrackerBatch, updateTask, "
    "updatePPCV3, weeklyPlan, salesHistory, quoteMetrics, unifiedAgenda, cascadeTree, "
    "projectTasks, drafts, infoBank, upload, archiveQuote, addEmployee…",
    "FastAPI",
    ["api/main.py:613-970"],
)
node(
    "h_ep_ai", "/api/…agency · transcribe", "api", "holtmont", 2,
    "Endpoints de IA: `/api/run_paperclip_agency` (agencia de cotización), "
    "`/api/transcribe_and_analyze` (audio → conceptos) y "
    "`/api/generate-engineering-questions` (cuestionario de ingeniería).",
    "FastAPI (multipart)",
    ["api/main.py:103", "api/main.py:320", "api/main.py:345"],
)
node(
    "h_ep_v2", "/api/v2/tasks", "api", "holtmont", 2,
    "Router relacional nuevo. No sustituye a nada todavía: convive con `/api/legacy/*` e imita "
    "su contrato para que el día del corte `api_service.js` reapunte sin tocar el monolito. "
    "Resuelve un repositorio por petición vía dependencia de FastAPI.",
    "FastAPI APIRouter",
    ["backend/routers/tasks.py"],
    ["migración"],
)
node(
    "h_ep_cron", "/api/cron/dailyMetrics", "api", "holtmont", 2,
    "Trabajo programado: recalcula métricas de cotizaciones y dispara el correo de "
    "productividad. Protegido con la cabecera `X-Cron-Secret`.",
    "FastAPI + Vercel Cron",
    ["api/main.py:987"],
)
node(
    "h_mcp", "mcp_server.py · FastMCP", "api", "holtmont", 3,
    "Servidor MCP «PascalEditorMCP»: expone `generar_habitacion_pascal` (geometría de una "
    "habitación) y `ejecutar_agencia_pascal` como herramientas para agentes externos.",
    "MCP (FastMCP)",
    ["api/mcp_server.py"],
    ["agentes"],
)

# --- L3 Agentes --------------------------------------------------------
node(
    "h_paperclip", "paperclip_agents.py", "agent", "holtmont", 3,
    "Agencia de cotización en LangGraph, 6 nodos: levantamiento → architect → calculo → "
    "precios → evaluador → (integrador | reintento). El nodo `architect` produce la escena 3D "
    "de Pascal Editor (muros, puertas, ventanas, escaleras, techos, mobiliario).",
    "LangGraph + Groq / Gemini + Pydantic",
    ["api/paperclip_agents.py", "api/pascal_template.json"],
    ["llm", "grafo"],
)
node(
    "h_ai_utils", "ai_utils.py", "agent", "holtmont", 3,
    "Transcripción con Whisper en Groq (previo re-encode con ffmpeg) y extracción estructurada "
    "a `ExtractionSchema`: personal, material, actividades y herramienta.",
    "Groq Whisper + LangChain + ffmpeg",
    ["api/ai_utils.py"],
    ["llm", "audio"],
)
node(
    "h_eng_agent", "engineering_agent.py", "agent", "holtmont", 3,
    "Grafo entrevistador/evaluador con búsqueda: `interviewer_node` genera preguntas, "
    "`evaluator_node` decide si son suficientes y `route_after_evaluation` enruta a "
    "`research_node` (Tavily), de vuelta al entrevistador, o a END.",
    "LangGraph + Groq + Tavily",
    ["api/engineering_agent.py"],
    ["llm", "grafo", "ciclo"],
)

# --- L4 Dominio --------------------------------------------------------
node(
    "h_tracker_store", "tracker_store.py", "service", "holtmont", 4,
    "Orquestador del tracker (1.186 líneas): aplica las reglas sobre datos reales y los "
    "persiste. Resuelve secuencias de folio desde la base, arma el lote, audita el guardado y "
    "dispara la notificación. Sus imports de datos son perezosos a propósito para poder probar "
    "las reglas sin credenciales.",
    "Python",
    ["api/services/tracker_store.py"],
    ["núcleo"],
)
node(
    "h_tracker_rules", "tracker_rules.py", "rules", "holtmont", 4,
    "Motor de reglas puro (1.501 líneas), gemelo de CODIGO.js: «Ley de Antonia» (ruteo "
    "protegido de hojas (VENTAS)), prefijos de folio por titular, gatekeeper anti-duplicación "
    "por `_tempId`, recuperación por CONCEPTO+FECHA+RESPONSABLE, auto-archivado, Papa Caliente "
    "(PROCESO_LOG / MAP COT), Reverse Sync y payload ISO 8601 para Make.com. No depende de "
    "FastAPI ni de Supabase.",
    "Python puro (list[list])",
    ["api/services/tracker_rules.py"],
    ["núcleo", "paridad"],
)
node(
    "h_sheets", "sheets.py · GSheetsManager", "service", "holtmont", 4,
    "Reconstruye la matriz de una hoja a partir de las tablas relacionales (búsqueda dinámica "
    "de la fila de encabezados incluida) y mantiene el modo mock cuando no hay "
    "`credentials.json`. Reexporta el organigrama para no romper importadores previos.",
    "gspread + Supabase",
    ["api/services/sheets.py"],
)
node(
    "h_organigrama", "organigrama.py", "service", "holtmont", 4,
    "Organigrama oficial: 19 departamentos, perfiles y correos. Sin contraseñas en el fuente — "
    "la credencial vive en `profiles` y la valida `/api/login`. Sirve de semilla para reparar "
    "la tabla `people` desde `resyncDirectory`.",
    "Python",
    ["api/services/organigrama.py"],
    ["seguridad"],
)
node(
    "h_work_order", "work_order.py", "service", "holtmont", 4,
    "Pre Work Order: genera el folio por cliente y departamento, reparte los bloques del "
    "formulario a sus tablas hijas (`wo_materiales`, `wo_herramienta`, `wo_equipo`…), escribe "
    "la nota de Obsidian y distribuye tareas a los responsables. Tres bloques (viáticos, "
    "transporte, ingeniería) no tienen tabla: se avisa en la respuesta en vez de inventarla.",
    "Python",
    ["api/services/work_order.py", "sequences.json"],
)
node(
    "h_storage", "storage.py", "service", "holtmont", 4,
    "Archivos en Supabase Storage. Traduce la jerarquía de carpetas de Drive a prefijos de "
    "ruta: `2026/MARZO/ACME INDUSTRIAL/cotizacion.pdf`. Sustituye a `uploadFileToDrive` y al "
    "archivado por carpetas del original.",
    "Supabase Storage",
    ["api/services/storage.py"],
)
node(
    "h_correo", "correo.py", "service", "holtmont", 4,
    "Envío SMTP de los reportes de los agentes. Resuelve destinatarios **por rol** contra los "
    "perfiles, corrigiendo el fallo del original donde `USER_DB['ADMIN_CONTROL']` nunca existía "
    "y el reporte no llegaba a nadie. Si no hay credenciales no envía y lo dice.",
    "smtplib",
    ["api/services/correo.py"],
)
node(
    "h_identity", "identity.py", "service", "holtmont", 4,
    "Resolución de identidad: normaliza el usuario activo, su hoja y su rol para que las capas "
    "de datos no tengan que adivinar quién escribe.",
    "Python",
    ["backend/services/identity.py"],
)
node(
    "h_auditoria", "auditoria.py", "service", "holtmont", 4,
    "Bitácora en `system_log`, el puerto de `registrarLog()` de Apps Script (16.196 entradas "
    "históricas). Auditar nunca puede impedir la operación: los fallos se registran y se sigue.",
    "Python",
    ["backend/services/auditoria.py"],
)

# --- L5 Persistencia ---------------------------------------------------
node(
    "h_persistencia", "persistencia.py", "service", "holtmont", 5,
    "Traduce filas con forma de hoja a la tabla relacional que les toca: `quotes` si la hoja es "
    "de ventas, `tasks` en cualquier otro caso, y cada fila cae en la partición `source_sheet` "
    "de su dueño. Devuelve un `ResultadoGuardado` con tabla, hoja y filas escritas.",
    "Python",
    ["backend/services/persistencia.py"],
    ["núcleo"],
)
node(
    "h_repo_tasks", "TaskRepository", "repo", "holtmont", 5,
    "Repositorio de tareas: separa activas de historial, completa columnas obligatorias y "
    "agrupa por columnas para que un lote quepa siempre en una sola sentencia (requisito de "
    "PostgREST, que no expone BEGIN/COMMIT).",
    "Python",
    ["backend/repositories/tasks.py", "backend/schemas/task.py"],
)
node(
    "h_repo_quotes", "QuoteRepository", "repo", "holtmont", 5,
    "Repositorio de cotizaciones: clasificación de estatus, detección de cotizaciones cerradas "
    "y métricas mensuales.",
    "Python",
    ["backend/repositories/quotes.py", "backend/schemas/quote.py"],
)
node(
    "h_repo_agenda", "RepositorioAgenda / Borradores", "repo", "holtmont", 5,
    "Agenda unificada, eventos personales, hábitos y borradores del monolito.",
    "Python",
    ["backend/repositories/agenda.py"],
)
node(
    "h_repo_proyectos", "RepositorioProyectos", "repo", "holtmont", 5,
    "Árbol en cascada de proyectos: sitio → subproyecto → tareas, con auditoría de cada alta.",
    "Python",
    ["backend/repositories/proyectos.py"],
)

# --- L6 Motores --------------------------------------------------------
node(
    "h_engine", "core/engine.py · DataEngine", "engine", "holtmont", 6,
    "Protocolo de acceso a datos con tres implementaciones intercambiables y la bandera "
    "`soporta_transacciones`. Existen dos motores reales porque el entorno de desarrollo no "
    "tiene salida TCP fuera del 443: en Vercel sí hay TCP y ahí SQLAlchemy es lo correcto.",
    "typing.Protocol",
    ["backend/core/engine.py"],
    ["núcleo"],
)
node(
    "h_eng_sqla", "sqlalchemy_engine.py", "engine", "holtmont", 6,
    "Motor con pool de conexiones sobre `DATABASE_URL`. **Es el único camino con transacciones "
    "reales.** Se usa en producción (Vercel).",
    "SQLAlchemy",
    ["backend/core/engines/sqlalchemy_engine.py"],
)
node(
    "h_eng_postgrest", "postgrest.py", "engine", "holtmont", 6,
    "Motor HTTPS contra PostgREST/Supabase. Sólo garantiza atomicidad por sentencia, así que "
    "los repositorios están escritos para que un lote quepa en un único POST.",
    "PostgREST (HTTPS)",
    ["backend/core/engines/postgrest.py"],
)
node(
    "h_eng_mem", "memoria.py", "engine", "holtmont", 6,
    "Motor en memoria. `tests/conftest.py` fuerza `BACKEND_ENGINE=memoria` y desconecta las "
    "credenciales durante toda la sesión de pytest: ninguna prueba puede tocar producción.",
    "Python (dict)",
    ["backend/core/engines/memoria.py"],
    ["pruebas"],
)
node(
    "h_config", "core/config.py · Settings", "engine", "holtmont", 6,
    "Instantánea inmutable del entorno, releída en cada llamada porque en serverless cada "
    "invocación es un proceso nuevo. Ni un solo valor por defecto que sea una credencial; "
    "`BACKEND_TASKS_WRITE_ENABLED=0` es el interruptor de emergencia de la escritura.",
    "dataclass(frozen=True)",
    ["backend/core/config.py", ".env.example"],
    ["seguridad"],
)

# --- L7 Externos -------------------------------------------------------
node(
    "x_supabase", "Supabase · PostgreSQL", "data", "holtmont", 7,
    "Base de datos de la aplicación: `tasks`, `quotes`, `people`, `profiles`, `system_log`, "
    "`wo_*`, proyectos y agenda. Cada usuario escribe en su partición `source_sheet`.",
    "PostgreSQL / PostgREST",
    [],
    ["fuente-de-verdad"],
)
node(
    "x_storage", "Supabase Storage", "data", "holtmont", 7,
    "Bucket de adjuntos: cotizaciones, evidencias del tracker y banco de información, "
    "organizados por prefijo año/mes/cliente.",
    "Supabase Storage",
)
node(
    "x_gsheets", "Google Sheets", "external", "holtmont", 7,
    "Origen histórico de los datos. Hoy sólo queda como salida opcional de exportación; la "
    "fuente de verdad es Supabase.",
    "Google Sheets API (gspread)",
    [],
    ["heredado"],
)
node(
    "x_make", "Make.com → Outlook", "external", "holtmont", 7,
    "Webhook de notificación (`MAKE_WEBHOOK_URL`). Las fechas deben viajar en ISO 8601 con "
    "milisegundos y Z; el payload indica si la tarea nace de ANTONIA_VENTAS o del tracker "
    "general, porque de eso depende a quién se avisa.",
    "Webhook HTTPS",
    [],
    ["integración"],
)
node(
    "x_groq", "Groq", "external", "holtmont", 7,
    "Inferencia LLM y transcripción Whisper para las tres rutas de IA.",
    "Groq API",
)
node(
    "x_gemini", "Google Gemini", "external", "holtmont", 7,
    "Modelo alterno para la agencia y para el agente de métricas de cotizaciones.",
    "Gemini API",
)
node(
    "x_tavily", "Tavily Search", "external", "holtmont", 7,
    "Búsqueda web del `research_node` cuando el evaluador detecta que falta información "
    "técnica.",
    "Tavily API",
)
node(
    "x_smtp", "SMTP corporativo", "external", "holtmont", 7,
    "Salida de correo de los reportes automáticos hacia las cuentas @holtmont.com.",
    "SMTP",
)

# --- L8 Verificación ---------------------------------------------------
node(
    "h_tests", "tests/ · pytest (25 archivos)", "test", "holtmont", 8,
    "Paridad con Apps Script, contrato index.html → api_service.js → api/main.py, RBAC, "
    "integración Supabase, login contra `profiles`, reglas del tracker, organigrama, work "
    "order y flujo de asignación. `conftest.py` aísla la sesión de la base real.",
    "pytest",
    ["tests/", "pytest.ini", "run_tests.sh"],
)
node(
    "h_docs", "SSD / SDD / AGENTS.md", "test", "holtmont", 8,
    "Especificación viva: SSD_MAESTRO_CLONACION.md (389 KB), "
    "SDD_HOLTMONT_PLATFORM_COMPREHENSIVE.md (347 KB), auditoría de paridad, comparativa "
    "real-vs-Python y las reglas de trabajo para agentes en AGENTS.md.",
    "Markdown",
    ["AGENTS.md", "SSD_MAESTRO_CLONACION.md", "AUDITORIA_PARIDAD_SSD22.md"],
)

# ======================= OFICINA EFICIENCIA ===========================

# --- L0 UI -------------------------------------------------------------
node(
    "m_main_ui", "main_ui.py · AppMain", "ui", "mlclaude", 0,
    "Ventana principal en CustomTkinter con `ViewManager`: registra las vistas, gestiona la "
    "barra lateral, el selector de cámara (escaneo en hilo aparte) y el ciclo de vida del "
    "worker de video.",
    "CustomTkinter",
    ["src/main_ui.py"],
)
node(
    "m_bootloader", "Bootloader (Tenant)", "ui", "mlclaude", 0,
    "Primera pantalla: elige o crea el Tenant B2B. **Nada puede resolver rutas antes de esto** "
    "— `ConfigManager` lanza excepción si no hay tenant activo. El modo headless lo suple con "
    "`OE_TENANT_ID`.",
    "CustomTkinter",
    ["src/main_ui.py:348"],
    ["multi-tenant"],
)
node(
    "m_license_win", "LicenseWindow", "ui", "mlclaude", 0,
    "Pantalla de activación: muestra el Machine ID y acepta el archivo de licencia firmado.",
    "CustomTkinter",
    ["src/main_ui.py:274"],
)
node(
    "m_gui_app", "gui_app.py · SystemGUI", "ui", "mlclaude", 0,
    "Interfaz completa en Tkinter (1.094 líneas): registro de rostros con ráfaga y cuenta "
    "regresiva, semáforo de estado, reportes de asistencia y eficiencia, exportación a CSV/PDF, "
    "visor de snapshots, calibración de fondo, vista de administrador y política de privacidad.",
    "Tkinter + Pillow",
    ["src/gui_app.py"],
)
node(
    "m_views", "gui/views.py · dashboard.py", "ui", "mlclaude", 0,
    "Vistas y rejilla del panel: tarjetas de estado por empleado y disposición del dashboard.",
    "CustomTkinter",
    ["src/gui/views.py", "src/gui/dashboard.py"],
)
node(
    "m_zone_editor", "zone_editor.py", "ui", "mlclaude", 0,
    "Editor gráfico de zonas: dibuja polígonos sobre un frame capturado y los guarda en "
    "`zonas_config.json` del tenant.",
    "OpenCV",
    ["src/zones/zone_editor.py"],
)

# --- L1 Captura --------------------------------------------------------
node(
    "m_main", "main.py (headless)", "service", "mlclaude", 1,
    "Ejecución sin interfaz. Selecciona el tenant desde `OE_TENANT_ID`, prueba varias fuentes "
    "de video en orden y corre el mismo pipeline que la GUI.",
    "OpenCV",
    ["src/main.py"],
)
node(
    "m_camera_worker", "camera_worker.py", "service", "mlclaude", 1,
    "Hilo demonio por cámara con cola de frames y límite de FPS. Construye el pipeline de forma "
    "tolerante a fallos: si faltan dependencias nativas o no hay tenant montado, sigue "
    "mostrando video pero sin persistir.",
    "threading + queue + OpenCV",
    ["src/tracking/camera_worker.py"],
    ["concurrencia"],
)
node(
    "m_camera_enum", "camera_enumerator.py", "service", "mlclaude", 1,
    "Enumeración de cámaras disponibles y sondeo de índices, para el selector de la UI.",
    "OpenCV",
    ["src/acquisition/camera_enumerator.py"],
)
node(
    "m_video_stream", "video_stream.py", "service", "mlclaude", 1,
    "Envoltura fina de la fuente de video: índice USB local o URL RTSP remota.",
    "OpenCV",
    ["src/acquisition/video_stream.py"],
)

# --- L2 Percepción -----------------------------------------------------
node(
    "m_person_detector", "person_detector.py · YOLOv8", "agent", "mlclaude", 2,
    "Detección de personas (y celulares) con YOLOv8n, umbral de confianza 0.4. El peso se "
    "verifica por hash antes de cargarse.",
    "Ultralytics YOLOv8",
    ["src/detection/person_detector.py", "yolov8n.pt"],
)
node(
    "m_people_detector", "people_detector.py", "agent", "mlclaude", 2,
    "Variante autónoma de detección con prueba de punto-en-polígono propia, usada para "
    "validación rápida de zonas.",
    "OpenCV + YOLO",
    ["src/detection/people_detector.py"],
)
node(
    "m_tracker", "person_tracker.py · ByteTrack", "agent", "mlclaude", 2,
    "Asignación de identidades persistentes entre frames (`tracker_id`), sobre supervision/"
    "ByteTrack.",
    "supervision (ByteTrack)",
    ["src/tracking/person_tracker.py"],
)
node(
    "m_face_rec", "face_recognizer.py", "agent", "mlclaude", 2,
    "Reconocimiento facial con dlib/face_recognition. Los encodings se guardan **firmados**: se "
    "verifica la firma al cargar y se recarga en caliente cuando cambia el directorio de "
    "rostros. Soporta registro por ráfaga y borrado por persona.",
    "face_recognition (dlib) + HMAC",
    ["src/recognition/face_recognizer.py", "utils/register_face.py"],
    ["biometría", "integridad"],
)

# --- L3 Dominio --------------------------------------------------------
node(
    "m_pipeline", "tracking_pipeline.py", "rules", "mlclaude", 3,
    "Corazón del sistema y única ruta de persistencia. Por frame: tracking → centroide → zona → "
    "estado → escritura. Con cadencias deliberadas: las posiciones se escriben cada 15 frames "
    "(a 15 fps × N cámaras, insertar por frame satura SQLite), el reconocimiento facial corre "
    "cada 10 frames (Skip-Frame Biométrica) y el snapshot de ENTRADA a zona es por evento, sin "
    "throttle.",
    "Python",
    ["src/tracking/tracking_pipeline.py"],
    ["núcleo", "rendimiento"],
)
node(
    "m_zone_checker", "zone_checker.py", "rules", "mlclaude", 3,
    "Resuelve en qué zona cae un punto a partir de los polígonos del tenant.",
    "shapely",
    ["src/zones/zone_checker.py"],
)
node(
    "m_state_manager", "state_manager.py", "rules", "mlclaude", 3,
    "Máquina de estados por empleado: trabajando, inactivo, en el celular, en comida. Usa "
    "historial de movimiento (umbral 5 px), intersección de cajas con celulares detectados y un "
    "tiempo de espera de comida de 1.800 s.",
    "Python",
    ["src/analysis/state_manager.py"],
    ["núcleo"],
)

# --- L4 Persistencia ---------------------------------------------------
node(
    "m_db", "database_manager.py", "repo", "mlclaude", 4,
    "SQLite por tenant: `tracking`, `snapshots`, `states`, `attendance`, `employees`. Incluye "
    "reportes de asistencia y eficiencia por rango de fechas, consultas parametrizadas (hay una "
    "prueba dedicada a inyección SQL), anonimización y borrado de empleado.",
    "SQLite3 + pandas",
    ["src/storage/database_manager.py"],
)
node(
    "m_db_crypto", "db_crypto.py · EncryptedDBVault", "security", "mlclaude", 4,
    "Cifra la base en reposo con una llave derivada del Machine ID: se descifra al abrir y se "
    "vuelve a cifrar al cerrar. `is_sqlite_file` distingue una base en claro de una cifrada "
    "para poder migrar instalaciones previas.",
    "cryptography (AES)",
    ["src/security/db_crypto.py", "migrate_data.py"],
    ["cifrado"],
)

# --- L5 Análisis -------------------------------------------------------
node(
    "m_eff_calc", "efficiency_calculator.py", "service", "mlclaude", 5,
    "Calcula permanencia por persona y zona a partir de las tablas `tracking` y `snapshots`, "
    "con pandas.",
    "pandas + numpy",
    ["src/analysis/efficiency_calculator.py"],
)
node(
    "m_report_gen", "report_generator.py", "service", "mlclaude", 5,
    "Tablas y gráficos de barras de duración por empleado y zona.",
    "matplotlib + seaborn",
    ["src/analysis/report_generator.py"],
)
node(
    "m_report_out", "Exportación XLSX / PDF", "service", "mlclaude", 5,
    "Genera `Reporte_Asistencia.xlsx` y `Reporte_Eficiencia_Final.xlsx`, y exporta a CSV/PDF "
    "desde la GUI. La escritura corre fuera del hilo de la interfaz "
    "(`tests/test_async_excel.py`).",
    "openpyxl + reportlab",
    ["src/analysis/report_main.py", "src/analysis/generar_reporte.py"],
)

# --- L6 Seguridad y plataforma ----------------------------------------
node(
    "m_drm", "drm.py · DRMValidator", "security", "mlclaude", 6,
    "Licenciamiento offline B2B: huella de hardware (placa + CPU + disco vía WMI) con SHA-256 y "
    "sal ofuscada, verificación de firma RSA-2048 contra la clave pública embebida, cotejo del "
    "Machine ID, fecha de expiración y extracción del tier (máximo de cámaras).",
    "RSA-2048 + WMI + SHA-256",
    ["src/security/drm.py", "scripts/generar_llaves_maestras.py"],
    ["licencia"],
)
node(
    "m_crash_logger", "crash_logger.py", "security", "mlclaude", 6,
    "Excepthook global que cifra el volcado de fallos con una llave derivada del Machine ID: el "
    "soporte puede descifrarlo, el cliente no filtra datos sin querer.",
    "cryptography",
    ["src/security/crash_logger.py"],
)
node(
    "m_model_verifier", "model_verifier.py", "security", "mlclaude", 6,
    "Verifica el hash del peso YOLO antes de cargarlo y lanza `ModelIntegrityError` si no "
    "coincide: impide sustituir el modelo por uno manipulado.",
    "hashlib",
    ["src/models/model_verifier.py"],
    ["integridad"],
)
node(
    "m_path_utils", "path_utils.py · ConfigManager", "security", "mlclaude", 6,
    "Singleton del tenant activo. Valida el id (1-64 caracteres alfanuméricos) y aísla cada "
    "cliente en `%APPDATA%/OficinaEficiencia/Tenants/<id>/` con subcarpetas db, faces, zonas, "
    "snapshots y export. La licencia vive en la raíz, fuera de los tenants.",
    "Python",
    ["config/path_utils.py"],
    ["multi-tenant"],
)
node(
    "m_config", "config/config.py", "security", "mlclaude", 6,
    "Configuración por *getters*, no por constantes: las rutas no pueden evaluarse al importar "
    "porque el tenant aún no está elegido. Aquí viven FRAME_SKIP, el umbral de confianza y la "
    "versión.",
    "Python",
    ["config/config.py", "VERSION"],
)
node(
    "m_build", "Ofuscación y empaquetado", "build", "mlclaude", 6,
    "Cadena de distribución: PyArmor ofusca `drm.py` y los módulos sensibles, PyInstaller "
    "construye el ejecutable con `gui_app.spec` e Inno Setup arma el instalador "
    "(`setup_oficina.iss`).",
    "PyArmor + PyInstaller + Inno Setup",
    ["obfuscate.py", "gui_app.spec", "setup_oficina.iss", "compilar_exe.bat"],
)
node(
    "m_keygen", "keygen_b2b.py", "build", "mlclaude", 6,
    "Herramienta del proveedor: firma licencias con la llave privada RSA para un Machine ID, "
    "una fecha de expiración y un tier. La privada nunca se distribuye.",
    "cryptography (RSA)",
    ["scripts/keygen_b2b.py", "generate_license.py"],
)

# --- L7 Sistema --------------------------------------------------------
node(
    "x_camera", "Cámaras (USB / RTSP)", "external", "mlclaude", 7,
    "Fuentes de video: índice local o URL RTSP autenticada.",
    "V4L2 / RTSP",
)
node(
    "x_yolo", "yolov8n.pt", "data", "mlclaude", 7,
    "Peso del modelo de detección (6,5 MB), verificado por hash en cada arranque.",
    "Ultralytics",
)
node(
    "x_appdata", "%APPDATA%/OficinaEficiencia", "data", "mlclaude", 7,
    "Almacenamiento del cliente: `license.key` en la raíz y un árbol aislado por tenant con "
    "base, rostros, zonas, snapshots y exportaciones.",
    "Sistema de archivos",
    [],
    ["multi-tenant"],
)
node(
    "x_sqlite", "local_tracking.db", "data", "mlclaude", 7,
    "Base SQLite del tenant, cifrada en reposo.",
    "SQLite",
)
node(
    "x_office", "Excel / PDF de salida", "external", "mlclaude", 7,
    "Entregables para el cliente: reportes de asistencia y eficiencia.",
    "XLSX / PDF",
)

# --- L8 Verificación ---------------------------------------------------
node(
    "m_tests", "tests/ · pytest (27 archivos)", "test", "mlclaude", 8,
    "Cobertura por riesgo: DRM RSA y su respaldo, cifrado y migración de la base, fugas del "
    "worker de cámara, inyección SQL en reportes, verificación del modelo, enrutamiento de "
    "tenants, pipeline de tracking, máquina de estados, Excel asíncrono y auditoría del "
    "sprint 5.",
    "pytest",
    ["tests/"],
)
node(
    "m_spec", "SPEC/ · auditoría de seguridad", "test", "mlclaude", 8,
    "Especificación por fases (revisión → especificación → planeación → tareas → "
    "implementación → revisión → keygen → build) y el reporte de auditoría de seguridad en "
    "`docs/`.",
    "Markdown / PDF",
    ["SPEC/", "docs/security_audit_report.md"],
)

# ----------------------------------------------------------------------
# ARISTAS
# ----------------------------------------------------------------------
# kind: http | call | data | llm | event | build | verify | opcional

E = []


def edge(src, dst, label="", kind="call"):
    E.append({"id": f"e_{src}__{dst}", "source": src, "target": dst, "label": label, "kind": kind})


# ---- Holtmont ---------------------------------------------------------
edge("h_index", "h_apiservice", "invoca", "call")
edge("h_workorder_html", "h_apiservice", "invoca", "call")
edge("h_apiservice", "h_vercel", "HTTPS", "http")
edge("h_vercel", "h_fastapi", "rutea", "http")
edge("h_codigo", "h_tracker_rules", "especifica", "verify")

edge("h_fastapi", "h_ep_auth", "", "call")
edge("h_fastapi", "h_ep_data", "", "call")
edge("h_fastapi", "h_ep_legacy", "", "call")
edge("h_fastapi", "h_ep_ai", "", "call")
edge("h_fastapi", "h_ep_v2", "monta router", "call")
edge("h_fastapi", "h_ep_cron", "", "call")

edge("h_streamlit", "h_ai_utils", "audio", "call")
edge("h_streamlit", "h_work_order", "work order", "call")

edge("h_ep_auth", "h_organigrama", "valida credenciales", "call")
edge("h_ep_auth", "h_sheets", "hoja USERS (heredado)", "opcional")
edge("h_ep_auth", "h_auditoria", "registra acceso", "event")

edge("h_ep_data", "h_sheets", "matriz de la hoja", "call")
edge("h_ep_data", "h_organigrama", "directorio", "call")

edge("h_ep_legacy", "h_tracker_store", "delega", "call")
edge("h_ep_legacy", "h_work_order", "pre work order", "call")
edge("h_ep_legacy", "h_storage", "adjuntos", "call")
edge("h_ep_legacy", "h_repo_agenda", "agenda / borradores", "call")
edge("h_ep_legacy", "h_repo_proyectos", "cascada de proyectos", "call")
edge("h_ep_legacy", "h_organigrama", "resync directorio", "call")

edge("h_ep_ai", "h_paperclip", "agencia", "llm")
edge("h_ep_ai", "h_ai_utils", "transcribe", "llm")
edge("h_ep_ai", "h_eng_agent", "cuestionario", "llm")

edge("h_ep_v2", "h_repo_tasks", "repositorio por petición", "call")
edge("h_ep_cron", "h_tracker_store", "métricas del día", "call")

edge("h_mcp", "h_paperclip", "herramienta MCP", "llm")

edge("h_paperclip", "x_groq", "LLM", "llm")
edge("h_paperclip", "x_gemini", "LLM alterno", "llm")
edge("h_ai_utils", "x_groq", "Whisper + LLM", "llm")
edge("h_eng_agent", "x_groq", "LLM", "llm")
edge("h_eng_agent", "x_tavily", "búsqueda", "llm")

edge("h_tracker_store", "h_tracker_rules", "aplica reglas", "call")
edge("h_tracker_store", "h_sheets", "lee la matriz", "call")
edge("h_tracker_store", "h_persistencia", "escribe el lote", "call")
edge("h_tracker_store", "h_auditoria", "audita el guardado", "event")
edge("h_tracker_store", "x_make", "notificación ISO 8601", "event")
edge("h_tracker_store", "h_correo", "reporte de agentes", "event")
edge("h_tracker_store", "x_gemini", "agente de KPIs", "llm")

edge("h_tracker_rules", "h_organigrama", "perfiles y correos", "call")
edge("h_work_order", "h_persistencia", "tablas hijas", "call")
edge("h_work_order", "h_tracker_store", "distribuye tareas", "call")
edge("h_sheets", "h_engine", "consulta tablas", "data")
edge("h_sheets", "x_gsheets", "exportación opcional", "opcional")
edge("h_organigrama", "h_engine", "people / profiles", "data")
edge("h_storage", "x_storage", "sube el objeto", "data")
edge("h_correo", "x_smtp", "envía", "event")
edge("h_auditoria", "h_engine", "system_log", "data")
edge("h_identity", "h_organigrama", "resuelve la hoja", "call")

edge("h_persistencia", "h_repo_tasks", "tasks", "call")
edge("h_persistencia", "h_repo_quotes", "quotes (VENTAS)", "call")
edge("h_persistencia", "h_identity", "dueño de la fila", "call")

edge("h_repo_tasks", "h_engine", "select / upsert", "data")
edge("h_repo_quotes", "h_engine", "select / upsert", "data")
edge("h_repo_agenda", "h_engine", "select / upsert", "data")
edge("h_repo_proyectos", "h_engine", "select / upsert", "data")

edge("h_engine", "h_config", "lee el entorno", "call")
edge("h_engine", "h_eng_sqla", "si hay DATABASE_URL", "call")
edge("h_engine", "h_eng_postgrest", "si hay SUPABASE_URL", "call")
edge("h_engine", "h_eng_mem", "en pruebas", "call")
edge("h_eng_sqla", "x_supabase", "TCP 5432 (transacciones)", "data")
edge("h_eng_postgrest", "x_supabase", "HTTPS 443", "data")

edge("h_tests", "h_eng_mem", "fuerza motor en memoria", "verify")
edge("h_tests", "h_tracker_rules", "paridad con CODIGO.js", "verify")
edge("h_tests", "h_apiservice", "contrato de la API", "verify")
edge("h_docs", "h_tests", "criterios de aceptación", "verify")

# ---- Oficina Eficiencia ----------------------------------------------
edge("m_main_ui", "m_bootloader", "abre al arrancar", "call")
edge("m_bootloader", "m_path_utils", "fija el tenant activo", "call")
edge("m_main_ui", "m_license_win", "si no hay licencia", "call")
edge("m_license_win", "m_drm", "valida el archivo", "call")
edge("m_drm", "x_appdata", "lee license.key", "data")
edge("m_keygen", "x_appdata", "licencia firmada", "build")

edge("m_main_ui", "m_camera_worker", "arranca el hilo", "call")
edge("m_main_ui", "m_camera_enum", "escanea cámaras", "call")
edge("m_main_ui", "m_views", "registra vistas", "call")
edge("m_main_ui", "m_zone_editor", "editar zonas", "call")
edge("m_gui_app", "m_camera_worker", "video en vivo", "call")
edge("m_gui_app", "m_face_rec", "registro por ráfaga", "call")
edge("m_gui_app", "m_db", "reportes y borrado", "call")
edge("m_gui_app", "m_report_out", "exporta CSV / PDF", "call")
edge("m_gui_app", "m_crash_logger", "excepthook global", "event")

edge("m_main", "m_path_utils", "OE_TENANT_ID", "call")
edge("m_main", "m_pipeline", "bucle headless", "call")
edge("m_main", "m_video_stream", "abre la fuente", "call")
edge("m_camera_enum", "x_camera", "sondea índices", "data")
edge("m_video_stream", "x_camera", "captura", "data")
edge("m_camera_worker", "x_camera", "captura", "data")
edge("m_camera_worker", "m_person_detector", "cada frame", "call")
edge("m_camera_worker", "m_pipeline", "delega la lógica", "call")
edge("m_camera_worker", "m_face_rec", "identidad", "call")

edge("m_person_detector", "x_yolo", "carga el peso", "data")
edge("m_person_detector", "m_model_verifier", "verifica el hash", "verify")
edge("m_person_detector", "m_pipeline", "detecciones del frame", "data")
edge("m_model_verifier", "x_yolo", "hash del peso", "verify")
edge("m_people_detector", "x_yolo", "carga el peso", "data")
edge("m_pipeline", "m_tracker", "asigna track_id", "call")
edge("m_pipeline", "m_zone_checker", "zona del centroide", "call")
edge("m_pipeline", "m_state_manager", "estado por empleado", "call")
edge("m_pipeline", "m_face_rec", "cada 10 frames", "call")
edge("m_pipeline", "m_db", "cada 15 frames + eventos", "data")
edge("m_zone_checker", "x_appdata", "zonas_config.json", "data")
edge("m_zone_editor", "x_appdata", "guarda polígonos", "data")
edge("m_face_rec", "x_appdata", "encodings firmados", "data")
edge("m_state_manager", "m_db", "estados y asistencia", "data")

edge("m_db", "m_db_crypto", "abre y cierra cifrado", "call")
edge("m_db_crypto", "x_sqlite", "AES en reposo", "data")
edge("m_db", "x_sqlite", "SQL parametrizado", "data")
edge("m_path_utils", "x_appdata", "árbol del tenant", "data")
edge("m_config", "m_path_utils", "rutas por getter", "call")

edge("m_eff_calc", "x_sqlite", "tracking + snapshots", "data")
edge("m_eff_calc", "m_report_gen", "DataFrame", "data")
edge("m_report_gen", "m_report_out", "tablas y gráficos", "data")
edge("m_report_out", "x_office", "XLSX / PDF", "data")
edge("m_db", "m_eff_calc", "consulta por rango", "data")

edge("m_crash_logger", "x_appdata", "volcado cifrado", "data")
edge("m_build", "m_drm", "ofusca con PyArmor", "build")
edge("m_build", "x_appdata", "instalador", "build")

edge("m_tests", "m_pipeline", "pipeline y estados", "verify")
edge("m_tests", "m_drm", "DRM y respaldo", "verify")
edge("m_tests", "m_db_crypto", "cifrado y migración", "verify")
edge("m_spec", "m_tests", "criterios por sprint", "verify")

# ----------------------------------------------------------------------
# FLUJOS
# ----------------------------------------------------------------------

F = []


def flow(id, name, system, category, desc, steps):
    F.append(
        {
            "id": id,
            "name": name,
            "system": system,
            "category": category,
            "desc": desc,
            "steps": [{"node": n, "action": a} for n, a in steps],
        }
    )


flow(
    "f_login", "Inicio de sesión", "holtmont", "Autenticación",
    "Tres fuentes en cascada, siempre auditadas. `profiles` es la única real; la hoja USERS y el "
    "login por entorno son respaldos heredados.",
    [
        ("h_index", "El usuario envía usuario y contraseña desde el monolito"),
        ("h_apiservice", "`login()` hace POST /api/login"),
        ("h_vercel", "La ruta catch-all entrega la petición a la función Python"),
        ("h_fastapi", "FastAPI deserializa `LoginRequest`"),
        ("h_ep_auth", "Normaliza el usuario a MAYÚSCULAS y arranca la cascada"),
        ("h_organigrama", "`validar_credenciales` consulta la tabla `profiles`"),
        ("h_engine", "El motor activo ejecuta el SELECT"),
        ("x_supabase", "Devuelve el perfil: rol, etiqueta, hoja y correo"),
        ("h_auditoria", "Escribe el intento — exitoso o denegado — en `system_log`"),
    ],
)

flow(
    "f_data", "Lectura de una hoja", "holtmont", "Datos",
    "`/api/data` reconstruye la matriz que el monolito espera a partir de las tablas "
    "relacionales, filtrando antes las tablas sensibles y las columnas de credencial.",
    [
        ("h_index", "Una vista pide sus datos (STAFF_TRACKER, PPC, INFO_BANK…)"),
        ("h_apiservice", "GET /api/data?sheet=<hoja>"),
        ("h_fastapi", "Enruta al manejador"),
        ("h_ep_data", "Rechaza tablas sensibles y recorta columnas de credencial"),
        ("h_sheets", "`GSheetsManager` arma la matriz y localiza la fila de encabezados"),
        ("h_engine", "SELECT sobre la tabla que corresponde"),
        ("x_supabase", "Filas tipadas de vuelta"),
    ],
)

flow(
    "f_tracker_save", "Guardado del tracker (ruta crítica)", "holtmont", "Tracker",
    "El camino más delicado del sistema: gatekeeper anti-duplicación, prefijo de folio por "
    "titular, recuperación de la fila por CONCEPTO+FECHA cuando el FOLIO no aparece, y escritura "
    "en la partición `source_sheet` del dueño.",
    [
        ("h_index", "El usuario guarda filas; cada nueva lleva `_tempId` e `isSubmitting` bloquea el doble envío"),
        ("h_apiservice", "POST /api/legacy/saveTrackerBatch con el lote"),
        ("h_fastapi", "Valida `TrackerBatchRequest`"),
        ("h_ep_legacy", "Delega en el orquestador del tracker"),
        ("h_tracker_store", "Resuelve la secuencia de folio desde la base y arma el lote"),
        ("h_tracker_rules", "Gatekeeper por `_tempId`, prefijo por titular, ruteo protegido de (VENTAS), auto-archivado"),
        ("h_persistencia", "Elige tabla — `quotes` si es de ventas, `tasks` si no — y partición `source_sheet`"),
        ("h_repo_tasks", "Agrupa por columnas para que el lote quepa en una sola sentencia"),
        ("h_engine", "UPSERT con `en_conflicto`"),
        ("x_supabase", "Filas escritas y devueltas completas"),
        ("h_auditoria", "Registra qué se guardó y quién lo guardó"),
    ],
)

flow(
    "f_hot_potato", "Papa Caliente y Reverse Sync", "holtmont", "Tracker",
    "La regla de negocio más singular. Toda tarea nacida en ANTONIA_VENTAS (folio «AV-») exige "
    "sincronización de vuelta; para cualquier otro usuario está prohibido escribir en hojas "
    "«(VENTAS)» y el sufijo se elimina globalmente.",
    [
        ("h_index", "Un miembro del equipo actualiza una tarea delegada"),
        ("h_ep_legacy", "POST /api/legacy/updateTask"),
        ("h_tracker_store", "Localiza la fila maestra por folio"),
        ("h_tracker_rules", "`apply_hot_potato` actualiza PROCESO_LOG y reconstruye MAP COT"),
        ("h_organigrama", "Resuelve el correo real del siguiente responsable"),
        ("h_persistencia", "Escribe en la partición del nuevo responsable"),
        ("h_repo_quotes", "Si el origen es de ventas, actualiza también `quotes`"),
        ("x_supabase", "Ambas particiones quedan consistentes"),
    ],
)

flow(
    "f_notify", "Notificación a Outlook", "holtmont", "Integraciones",
    "El payload debe conservar ISO 8601 con milisegundos y Z, e indicar si la tarea nace de "
    "ANTONIA_VENTAS o del tracker general: de eso depende a quién avisa Make.com.",
    [
        ("h_tracker_store", "Tras persistir, evalúa si la hoja debe notificar"),
        ("h_tracker_rules", "`build_notification_payload` con fechas `to_iso_z`"),
        ("h_organigrama", "Traduce el nombre del responsable a su correo @holtmont.com"),
        ("x_make", "POST al webhook; el escenario de Make redacta y envía por Outlook"),
    ],
)

flow(
    "f_paperclip", "Agencia de cotización (Paperclip)", "holtmont", "IA",
    "Grafo LangGraph de seis nodos con reintento condicional. El nodo `architect` no sólo "
    "cotiza: genera la escena 3D de Pascal Editor con muros, vanos, escaleras y mobiliario.",
    [
        ("h_index", "El usuario describe el proyecto en lenguaje natural"),
        ("h_apiservice", "POST /api/run_paperclip_agency"),
        ("h_ep_ai", "Valida `PaperclipRequest` y toma la clave de API"),
        ("h_paperclip", "levantamiento → architect → calculo → precios → evaluador; si el crítico rechaza, vuelve a precios; si aprueba, integrador → END"),
        ("x_groq", "Inferencia estructurada con Pydantic (dos intentos por nodo)"),
        ("h_index", "Recibe conceptos, precios y la escena de Pascal Editor"),
    ],
)

flow(
    "f_audio", "Cotización por voz", "holtmont", "IA",
    "Del audio del levantamiento a conceptos editables: ffmpeg re-codifica, Whisper transcribe y "
    "el LLM extrae personal, material, actividades y herramienta.",
    [
        ("h_streamlit", "Se graba el audio del levantamiento en obra"),
        ("h_ai_utils", "`transcribir_audio` re-codifica con ffmpeg y llama a Whisper"),
        ("x_groq", "Transcripción y luego extracción a `ExtractionSchema`"),
        ("h_streamlit", "El usuario corrige los conceptos y exporta el PDF de la cotización"),
    ],
)

flow(
    "f_engineering", "Cuestionario de ingeniería", "holtmont", "IA",
    "Grafo con ciclo: el evaluador decide si las preguntas bastan; si falta fundamento técnico, "
    "manda a investigar y vuelve al entrevistador.",
    [
        ("h_index", "Se sube el audio o el documento del proyecto"),
        ("h_ep_ai", "POST /api/generate-engineering-questions"),
        ("h_eng_agent", "interviewer → evaluator → {research | interviewer | END}"),
        ("x_tavily", "Búsqueda web cuando el evaluador detecta huecos"),
        ("x_groq", "Redacta el cuestionario final"),
    ],
)

flow(
    "f_workorder", "Pre Work Order", "holtmont", "Operación",
    "Un formulario, muchas tablas. Tres bloques (viáticos, transporte, ingeniería) no tienen "
    "esquema: el endpoint lo avisa en vez de inventarlo, y el detalle queda en la nota de "
    "Obsidian.",
    [
        ("h_workorder_html", "Se captura el formulario completo"),
        ("h_apiservice", "POST del lote de partidas"),
        ("h_ep_legacy", "Entrega a `process_and_save_work_order`"),
        ("h_work_order", "Genera el folio por cliente y departamento y reparte los bloques"),
        ("h_persistencia", "Escribe `wo_materiales`, `wo_herramienta`, `wo_equipo`…"),
        ("h_tracker_store", "Distribuye la tarea a cada responsable"),
        ("x_supabase", "Work order registrada con sus hijos y sus tareas"),
    ],
)

flow(
    "f_v2", "Ruta relacional v2", "holtmont", "Migración",
    "El destino de la migración, ya en pie y conviviendo con lo heredado: imita el contrato "
    "actual para que el corte sea un cambio de URL en `api_service.js`.",
    [
        ("h_apiservice", "GET /api/v2/tasks?sheet=<hoja> (aún no cableado)"),
        ("h_ep_v2", "Resuelve un `TaskRepository` por petición; 503 si no hay motor"),
        ("h_repo_tasks", "Separa activas de historial y completa columnas obligatorias"),
        ("h_engine", "SELECT tipado"),
        ("x_supabase", "Responde `{success, data, history, headers}`"),
    ],
)

flow(
    "f_cron", "Métricas diarias por cron", "holtmont", "Operación",
    "Trabajo programado protegido por `X-Cron-Secret`: recalcula KPIs de cotizaciones y envía el "
    "reporte a quien tenga el rol, no a una cuenta inventada.",
    [
        ("h_ep_cron", "Vercel Cron dispara con la cabecera secreta"),
        ("h_tracker_store", "Recalcula métricas del mes en curso"),
        ("x_gemini", "Redacta el resumen ejecutivo del reporte"),
        ("h_correo", "Resuelve destinatarios por rol y arma el HTML"),
        ("x_smtp", "Entrega el correo a las cuentas corporativas"),
    ],
)

flow(
    "f_upload", "Adjuntos y archivado", "holtmont", "Datos",
    "La jerarquía de carpetas de Drive se volvió prefijos de ruta en Storage: mismo resultado "
    "para el usuario, sin crear nada antes de subir.",
    [
        ("h_index", "Se adjunta un archivo al tracker, al PPC o al banco de información"),
        ("h_ep_legacy", "POST /api/legacy/upload con la data URL"),
        ("h_storage", "Decodifica, sanea el nombre y arma `2026/MARZO/CLIENTE/archivo.pdf`"),
        ("x_storage", "Objeto almacenado; la URL vuelve a la fila"),
    ],
)

flow(
    "f_directory", "Resincronización del directorio", "holtmont", "Operación",
    "El organigrama en el fuente existe para poder reparar `people` cuando le falten registros; "
    "la fuente viva sigue siendo la tabla.",
    [
        ("h_index", "Un administrador pide resincronizar"),
        ("h_ep_legacy", "POST /api/legacy/resyncDirectory"),
        ("h_organigrama", "Compara `people` contra el organigrama semilla"),
        ("h_engine", "UPSERT de los registros faltantes"),
        ("x_supabase", "Directorio completo, 19 departamentos"),
    ],
)

flow(
    "f_parity", "Verificación de paridad", "holtmont", "Verificación",
    "CODIGO.js no se ejecuta, pero manda. Las pruebas comparan el motor Python contra el "
    "original regla por regla y ninguna toca la base de producción.",
    [
        ("h_codigo", "Regla original en Apps Script"),
        ("h_tracker_rules", "Gemelo en Python, sobre matrices de valores"),
        ("h_tests", "`test_paridad_appscript.py` y `test_tracker_rules.py`"),
        ("h_eng_mem", "`conftest.py` fuerza el motor en memoria y desconecta credenciales"),
    ],
)

# ---- Oficina Eficiencia ----------------------------------------------

flow(
    "f_boot", "Arranque: licencia y tenant", "mlclaude", "Arranque",
    "Nada funciona antes de estos dos pasos. Sin licencia válida no hay aplicación; sin tenant "
    "activo `ConfigManager` lanza excepción y ninguna ruta puede resolverse.",
    [
        ("m_main_ui", "Arranca la aplicación de escritorio"),
        ("m_license_win", "Muestra el Machine ID y pide el archivo de licencia"),
        ("m_drm", "Huella de hardware (placa + CPU + disco) y verificación RSA-2048"),
        ("x_appdata", "Lee `license.key` de la raíz, fuera de los tenants"),
        ("m_bootloader", "Se elige o se crea el Tenant B2B"),
        ("m_path_utils", "Fija el tenant activo y monta `Tenants/<id>/`"),
    ],
)

flow(
    "f_vision", "Pipeline de video en vivo", "mlclaude", "Visión",
    "La ruta caliente, con cadencias deliberadas: posiciones cada 15 frames, rostro cada 10, "
    "snapshot de entrada a zona siempre. Insertar por frame satura SQLite con varias cámaras.",
    [
        ("m_main_ui", "El usuario elige cámara y arranca"),
        ("m_camera_worker", "Hilo demonio con cola de frames y límite de FPS"),
        ("x_camera", "Frame BGR desde USB o RTSP"),
        ("m_person_detector", "YOLOv8n detecta personas y celulares (confianza 0.4)"),
        ("m_pipeline", "Orquesta el frame y decide qué se escribe en este ciclo"),
        ("m_tracker", "ByteTrack asigna `track_id` persistente"),
        ("m_zone_checker", "Resuelve la zona del centroide contra los polígonos del tenant"),
        ("m_state_manager", "Determina el estado: trabajando, inactivo, en el celular, en comida"),
        ("m_db", "INSERT en `tracking`, `states` y `attendance`"),
        ("x_sqlite", "Base del tenant, cifrada en reposo"),
    ],
)

flow(
    "f_face", "Identificación y registro de rostros", "mlclaude", "Visión",
    "El reconocimiento es caro (100-200 ms en CPU), así que corre cada 10 frames. Los encodings "
    "se guardan firmados y se verifican al cargar.",
    [
        ("m_gui_app", "Registro por ráfaga con cuenta regresiva"),
        ("m_face_rec", "Calcula encodings, los firma y los guarda"),
        ("x_appdata", "`faces/` del tenant activo"),
        ("m_pipeline", "Cada 10 frames pide identidad para el track vigente"),
        ("m_face_rec", "Verifica la firma, recarga en caliente si cambió el directorio y compara"),
        ("m_db", "Asocia el nombre al `track_id` y actualiza asistencia"),
    ],
)

flow(
    "f_snapshot", "Evidencia por entrada a zona", "mlclaude", "Visión",
    "Único evento sin throttle: entrar a una zona siempre deja imagen, porque es la evidencia "
    "que sostiene el reporte.",
    [
        ("m_pipeline", "Detecta la transición fuera→dentro de una zona"),
        ("m_zone_checker", "Confirma el polígono y su nombre"),
        ("x_appdata", "Guarda el recorte en `snapshots/` del tenant"),
        ("m_db", "INSERT en `snapshots` con track, zona, empleado y ruta"),
        ("m_gui_app", "El visor permite abrirlos desde el reporte de eficiencia"),
    ],
)

flow(
    "f_reports", "Reporte de eficiencia y asistencia", "mlclaude", "Reportes",
    "De la base al entregable del cliente. La escritura del Excel corre fuera del hilo de la "
    "interfaz y las consultas van parametrizadas — hay una prueba dedicada a inyección SQL.",
    [
        ("m_gui_app", "Se elige el rango de fechas y, opcionalmente, un empleado"),
        ("m_db", "`get_efficiency_report` / `get_attendance_report` con SQL parametrizado"),
        ("x_sqlite", "Lee `tracking`, `states` y `snapshots`"),
        ("m_eff_calc", "pandas calcula permanencia por persona y zona"),
        ("m_report_gen", "Tablas y gráficos con matplotlib/seaborn"),
        ("m_report_out", "Exporta XLSX/PDF en un hilo aparte"),
        ("x_office", "`Reporte_Eficiencia_Final.xlsx` listo para entregar"),
    ],
)

flow(
    "f_privacy", "Protección de datos en reposo", "mlclaude", "Seguridad",
    "Todo lo sensible que queda en la máquina del cliente está cifrado con llave derivada del "
    "Machine ID: la base, los volcados de fallo y la firma de los encodings.",
    [
        ("m_db_crypto", "Deriva la llave del Machine ID y descifra al abrir"),
        ("x_sqlite", "La base sólo existe en claro mientras la aplicación corre"),
        ("m_db", "Opera normalmente durante la sesión"),
        ("m_db_crypto", "Vuelve a cifrar al cerrar"),
        ("m_crash_logger", "El excepthook global cifra cualquier volcado de fallo"),
        ("x_appdata", "Sólo el proveedor puede descifrarlo para dar soporte"),
    ],
)

flow(
    "f_tenant", "Aislamiento multi-tenant", "mlclaude", "Arquitectura",
    "La razón de que la configuración sea por *getters* y no por constantes: las rutas no pueden "
    "existir antes de saber de qué cliente son.",
    [
        ("m_bootloader", "Selección del Tenant al arrancar (o `OE_TENANT_ID` en headless)"),
        ("m_path_utils", "Valida el id y lo fija en el singleton"),
        ("m_config", "`get_db_path`, `get_faces_dir`, `get_zonas_file`… se evalúan al llamarlas"),
        ("x_appdata", "`Tenants/<id>/{db,faces,zonas,snapshots,export}`"),
        ("m_db", "Cada cliente abre su propia base, sin cruces posibles"),
    ],
)

flow(
    "f_integrity", "Integridad del modelo", "mlclaude", "Seguridad",
    "Un peso de modelo sustituido cambiaría silenciosamente lo que el sistema ve. Se verifica "
    "por hash antes de cargarlo.",
    [
        ("m_person_detector", "Va a cargar el detector"),
        ("m_model_verifier", "Calcula el hash de `yolov8n.pt` y lo compara con el esperado"),
        ("x_yolo", "Sólo se carga si coincide; si no, `ModelIntegrityError`"),
        ("m_pipeline", "El pipeline arranca con un modelo verificado"),
    ],
)

flow(
    "f_build", "Distribución y licenciamiento", "mlclaude", "Entrega",
    "La cadena que convierte el repositorio en un instalador con DRM: la llave privada nunca "
    "sale del proveedor.",
    [
        ("m_keygen", "Se firma la licencia para un Machine ID, expiración y tier"),
        ("m_build", "PyArmor ofusca `drm.py`; PyInstaller construye con `gui_app.spec`"),
        ("m_drm", "El binario valida la firma contra la clave pública embebida"),
        ("x_appdata", "Inno Setup instala y deja `license.key` en su sitio"),
    ],
)

flow(
    "f_headless", "Ejecución sin interfaz", "mlclaude", "Arranque",
    "El modo servidor no pasa por el Bootloader, así que debe elegir tenant por variable de "
    "entorno antes de resolver una sola ruta.",
    [
        ("m_main", "Arranca con `OE_TENANT_ID` (o «Default»)"),
        ("m_path_utils", "Fija el tenant antes de tocar rutas"),
        ("m_video_stream", "Prueba las fuentes de video en orden"),
        ("x_camera", "Primera fuente que responde"),
        ("m_pipeline", "Mismo pipeline que la GUI, sin dibujar"),
        ("m_db", "Persiste igual que en modo escritorio"),
    ],
)

# ----------------------------------------------------------------------
# VALIDACIÓN
# ----------------------------------------------------------------------

def validar():
    ids = [n["id"] for n in N]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise SystemExit(f"IDs de nodo duplicados: {sorted(dup)}")
    conocidos = set(ids)

    for e in E:
        if e["source"] not in conocidos or e["target"] not in conocidos:
            raise SystemExit(f"Arista con extremo inexistente: {e['id']}")

    indice = {e["id"] for e in E}
    derivadas = 0
    for f in F:
        pasos = [s["node"] for s in f["steps"]]
        for p in pasos:
            if p not in conocidos:
                raise SystemExit(f"Flujo {f['id']}: nodo inexistente {p}")

        # `transitions` describe la ruta paso a paso. Cuando dos pasos
        # consecutivos no tienen una arista declarada —porque el salto es un
        # retorno o porque hay un intermediario que el flujo no menciona— la
        # transición queda marcada como "derivada" en vez de inventar una
        # dependencia que no existe en el código. El diagrama la dibuja como
        # conector punteado sólo mientras ese flujo está seleccionado.
        transiciones = []
        for a, b in zip(pasos, pasos[1:]):
            if a == b:
                continue
            directa = f"e_{a}__{b}" if f"e_{a}__{b}" in indice else None
            inversa = f"e_{b}__{a}" if (directa is None and f"e_{b}__{a}" in indice) else None
            eid = directa or inversa
            if eid is None:
                derivadas += 1
            transiciones.append(
                {
                    "from": a,
                    "to": b,
                    "edge": eid,
                    "tipo": "arista" if eid else "derivada",
                }
            )
        f["transitions"] = transiciones

    print(f"[info] {derivadas} transiciones de flujo sin arista declarada (se dibujan punteadas)")


validar()

MODELO = {
    "meta": {
        "titulo": "Mapa de arquitectura — repositorios Holtmont",
        "generado": "2026-08-04",
        "descripcion": (
            "Modelo de arquitectura extraído por lectura directa del código de dos sistemas "
            "independientes: Holtmont Workspace (ERP web) y Oficina Eficiencia (visión por "
            "computadora on-premise). Pensado para consumo por agentes de IA: cada nodo apunta "
            "a archivos reales y cada flujo es una ruta conectada del grafo."
        ),
        "systems": SYSTEMS,
        "tipos_de_nodo": {
            "ui": "Interfaz de usuario",
            "api": "Endpoint o aplicación HTTP",
            "agent": "Agente de IA o modelo de inferencia",
            "rules": "Motor de reglas / lógica de dominio",
            "service": "Servicio de aplicación",
            "repo": "Repositorio de datos",
            "engine": "Motor o configuración de acceso a datos",
            "data": "Almacén de datos",
            "external": "Servicio externo",
            "security": "Seguridad, licencia o aislamiento",
            "build": "Empaquetado y distribución",
            "test": "Verificación y especificación",
            "legacy": "Código heredado / referencia",
        },
        "tipos_de_arista": {
            "http": "Llamada HTTP",
            "call": "Invocación en proceso",
            "data": "Lectura o escritura de datos",
            "llm": "Inferencia de modelo",
            "event": "Efecto secundario / evento",
            "verify": "Verificación o especificación",
            "build": "Paso de construcción",
            "opcional": "Ruta heredada u opcional",
        },
        "nota_flujos": (
            "Cada flujo trae `steps` (nodo + acción) y `transitions` (paso a paso ya resuelto "
            "contra el grafo). Una transición con `edge` apunta a una arista real del grafo; "
            "una con `tipo: derivada` es un salto del relato — un retorno de respuesta o un "
            "intermediario que el flujo no menciona — y no debe leerse como dependencia."
        ),
        "conteos": {"nodes": len(N), "edges": len(E), "flows": len(F)},
    },
    "nodes": N,
    "edges": E,
    "flows": F,
}

OUT = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(OUT, exist_ok=True)

with open(os.path.join(OUT, "arquitectura.json"), "w", encoding="utf-8") as fh:
    json.dump(MODELO, fh, ensure_ascii=False, indent=2)
    fh.write("\n")

print(
    f"arquitectura.json -> {len(N)} nodos, {len(E)} aristas, {len(F)} flujos"
)

# ----------------------------------------------------------------------
# HTML
# ----------------------------------------------------------------------

HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plantilla.html")
with open(HTML_PATH, encoding="utf-8") as fh:
    plantilla = fh.read()

html = plantilla.replace(
    "/*__DATOS__*/", json.dumps(MODELO, ensure_ascii=False, separators=(",", ":"))
)
with open(os.path.join(OUT, "arquitectura.html"), "w", encoding="utf-8") as fh:
    fh.write(html)

print(f"arquitectura.html -> {len(html)//1024} KB (autocontenido)")
