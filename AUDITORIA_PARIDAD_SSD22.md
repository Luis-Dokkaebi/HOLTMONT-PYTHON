# Auditoría de Paridad — Prework Order (FastAPI) vs. Holtmont Workspace (GAS)

**Base de auditoría:** `SSD_MAESTRO_CLONACION.md` §22 (Checklist de Verificación de Paridad, 92 ítems contados en 15 módulos) y §23 (12 anti-patrones).
**Código auditado:** `api/` (main.py, services/sheets.py, services/work_order.py, services/supabase_manager.py, ai_utils.py, engineering_agent.py, paperclip_agents.py, mcp_server.py — ~2,600 líneas), `index.html` (7,840 líneas), `api_service.js` (adaptador `google.script.run`), `tests/`.
**Fecha:** 2026-07-05.

---

## 1. Resumen numérico

| Módulo | Ítems | ✅ OK | ⚠️ DIFERENTE | ❌ FALTA |
|---|---|---|---|---|
| 22.1 Autenticación y Sesión | 9 | 1 | 2 | 6 |
| 22.2 Organigrama y Directorio | 6 | 1 | 1 | 4 |
| 22.3 Motor de Trackers | 10 | 1 | 2 | 7 |
| 22.4 Papa Caliente (cotizaciones) | 7 | 0 | 0 | 7 |
| 22.5 Enrutamiento / Caso Antonia | 5 | 0 | 2 | 3 |
| 22.6 Módulo PPC | 6 | 1 | 2 | 3 |
| **22.7 Work Orders (base de Prework Order)** | **5** | **1** | **4** | **0** |
| 22.8 Proyectos / Cascada | 5 | 0 | 0 | 5 |
| 22.9 KPIs Dashboard | 6 | 0 | 0 | 6 |
| 22.10 Agentes narrativos IA | 7 | 0 | 1 | 6 |
| 22.11 Integraciones externas | 6 | 0 | 2 | 4 |
| 22.12 Triggers y automatizaciones | 4 | 1 | 1 | 2 |
| 22.13 Banco de Información y Agenda | 5 | 0 | 0 | 5 |
| 22.14 Frontend / Paridad de UI | 6 | 2 | 3 | 1 |
| 22.15 Seguridad | 5 | 0 | 0 | 5 |
| **TOTAL** | **92** | **8 (9%)** | **20 (22%)** | **64 (70%)** |

Lectura honesta: la migración cubre hoy, de forma funcional end-to-end, **solo el flujo de Work Orders (captura → guardado → distribución) y la lectura de trackers**. El frontend aparenta mucho más porque es un fork completo de la SPA original, pero la mayoría de sus llamadas al backend son **stubs que devuelven `{success:true}` sin persistir nada**.

---

## 2. 🔴 URGENTE — Regresiones dentro y alrededor de Work Orders (§22.7)

Estas no son "trabajo pendiente normal": son cosas que en el original funcionan y en Prework Order están rotas o degradadas.

### 2.1 La secuencia de folios no es atómica y muere en producción serverless
`api/services/work_order.py:8-24` (`get_next_sequence`) guarda el contador en `sequences.json` **en el filesystem local, sin lock**. El original usa Script Properties + `LockService` (Anexo A §19.5). Consecuencias:
- Dos requests concurrentes leen el mismo valor → **folios duplicados** (el original tenía exactamente esta protección).
- El repo tiene `vercel.json` (deploy serverless): el filesystem es efímero → **el contador se reinicia a 1000 en cada cold start**. Los folios `SEQ(4)` dejan de ser únicos.
- Lo mismo aplica a `save_to_obsidian` (escribe `Notas/` en disco local): en Vercel esos .md desaparecen.

### 2.2 Mapa de abreviaturas de folio incompleto (⚠️ ítem 22.7-2)
`generate_work_order_folio` portó el mapa del original pero **omitió 3 entradas**: `FINANZAS→"Finanzas"`, `FACTURACION→"Factura"`, `FACTURACIÓN→"Factura"`. Una WO de Finanzas hoy genera `...Finan...` en vez de `...Finanzas...` (cae al fallback de truncado). Divergencia silenciosa de formato de folio — el identificador de negocio más visible del módulo.

### 2.3 Guardado de tablas hijas frágil contra Supabase
`save_child_data` + `SupabaseManager.append_row`: si la tabla `DB_WO_*` **no existe o está vacía en Supabase**, `append_row` imprime un error/`None` y el dato **se pierde silenciosamente** (cae al fallback gspread/mock, que en producción no existe). El original creaba la hoja con headers en el momento. Además el "crear headers" de Python (`gs_manager.append_row(sheet, headers)`) inserta los headers **como fila de datos**, cosa que en Supabase (tablas con columnas reales) no tiene sentido y falla.

### 2.4 Esquema de tablas WO extendido sin documentar (⚠️ ítem 22.7-1)
Las 5 tablas del spec (§5.7) existen y están ligadas por FOLIO ✓, pero:
- `DB_WO_MANO_OBRA`: +4 columnas (`UNIDAD`, `EPP_6_PORCIENTO`, `COSTO_HORA`, `HORAS_REQUERIDAS`).
- `DB_WO_PROGRAMA`: +3 columnas (`FECHA_INICIO`, `FECHA_ENTREGA`, `ARCHIVO`) y un estado nuevo `BLOQUEADO_SIN_ARCHIVO`.
- 3 tablas nuevas: `DB_WO_VIATICOS`, `DB_WO_TRANSPORTE`, `DB_WO_INGENIERIA`.

Son extensiones razonables, pero el checklist exige documentarlas como cambio de diseño y no están documentadas en ningún lado (README/REFACTORING.md no las mencionan).

### 2.5 Lo que sí está bien en Work Orders
- ✅ Sub-objeto `papaCaliente` de aprobación (Residente→Compras→Controller→Almacén→Logística) preservado correctamente en materiales (8 campos) y herramientas (5 campos), sin confundirse con las otras dos acepciones de "papa caliente" (§10.4).
- ⚠️ Control vehicular duplicado: **la duplicación del original se replicó** (`vehicleControlData` y `vehicleControlData2` en el estado del frontend) en vez de resolverse a lista de N vehículos — permitido por el checklist, pero sin decisión documentada.
- ⚠️ `workorder_form.html`: el checklist dice que NO hacía falta replicar el artefacto huérfano; sin embargo el archivo fue copiado al repo, se sirve por el mount de StaticFiles **y hasta tiene tests** (`tests/test_workorder_template.py`) que lo validan. Deuda huérfana replicada y con mantenimiento activo.

### 2.6 Regresión colateral que golpea al flujo WO: uploads falsos
`uploadFileToDrive` en `api_service.js:153` es un stub que devuelve `fileUrl: "http://mock.url/file"`. El formulario de Work Order permite "subir" archivos, muestra "Archivo Subido ✔" y **guarda una URL falsa**. Pérdida de datos silenciosa en el módulo estrella.

---

## 3. Los 3 bugs conocidos (🐛): ¿corregidos o replicados?

| Bug del original | Estado en Prework Order |
|---|---|
| **§22.8 / §16.2** — `apiFetchProjectTasks` siempre falla (`ReferenceError`) | **Ni corregido ni replicado: el módulo no existe.** `apiFetchProjectTasks` es un stub en `api_service.js:168` que devuelve lista vacía. El checklist pedía implementarlo correctamente (idealmente con FK `project_id`); sigue pendiente al 100%. Veredicto: ❌. |
| **§22.10 / §19.18** — el reporte de productividad nunca llega a `ADMIN_CONTROL` (llave `USER_DB['ADMIN_CONTROL']` inexistente) | **No aplicable todavía:** no existe ningún agente de productividad, ni envío de correo, en la app Python. El bug no se replicó porque no se migró nada de ese módulo. Veredicto: ❌ (módulo faltante; al implementarlo, resolver destinatarios iterando usuarios por rol). |
| **§22.11 / §13** — API key de Gemini hardcodeada en `transcribirConGemini` | **❌ Replicado en espíritu y en letra.** (1) La key comprometida `AIzaSy...K6kkc` **sigue committeada en este repo** — está en `CODIGO.js:3145` (la copia del código GAS vive en la raíz del repo Python). (2) El anti-patrón se reprodujo con una credencial nueva: `api/services/supabase_manager.py:9` tiene la **service key secreta de Supabase hardcodeada como default** (`sb_secret_...`). Esa key da acceso total a la base. Ambas deben rotarse ya y leerse solo de entorno. |

---

## 4. Decisiones de diseño requeridas (⚠️ del checklist): qué decidió Prework Order

| Decisión | Estado |
|---|---|
| §22.1 — hash+salt vs texto plano | **No tomada (por omisión).** El login compara texto plano contra la tabla `USERS` de Supabase, y además hay 3 cuentas mock con contraseñas en texto plano hardcodeadas en `api/main.py:309-313`. Sin bcrypt/argon2/passlib en `requirements.txt`. |
| §22.2 — `CESAR_GOMEZ` activo o baja | **No tomada.** Figura activo en el `INITIAL_DIRECTORY` de Python (`sheets.py:21`, en VENTAS) — resuelto por accidente, exactamente lo que el checklist pedía evitar. |
| §22.9 — 6 vendedores vs 9 `seller:true` en KPIs | **No tomada** (no hay módulo KPI). |
| §22.11 — transcripción con Gemini u otro proveedor | **Tomada de facto, no documentada:** se reemplazó Gemini por **Groq** (Whisper para transcripción, Llama para extracción) en `ai_utils.py`. Válido, pero debe quedar escrito. |
| §22.13 — fallback demo de Agenda | **No tomada.** Peor: la vista PERSONAL_AGENDA llama `apiFetchUnifiedAgenda`, que **ni siquiera existe como stub** en el adaptador → TypeError al abrir la vista. |
| §22.7 — control vehicular duplicado | **Duplicación preservada** (`vehicleControlData`/`vehicleControlData2`), sin documentar. |
| §22.3 — alias de columnas resuelto estructuralmente | **A medias y sin documentar:** `find_header_row` (sheets.py) hace matching heurístico de headers, pero no existe ni el diccionario de 15 grupos ni un modelo de datos con columnas fijas que lo vuelva innecesario. |

---

## 5. Detalle por módulo (solo ❌/⚠️ con su incumplimiento)

### 22.1 Autenticación y Sesión — ✅1 ⚠️2 ❌6
- ✅ `POST /api/login` devuelve `{success, role, name, username}` (forma correcta).
- ❌ Sin auditoría `LOGIN`/`LOGIN_FAIL` — no existe equivalente de `LOG_SISTEMA` en toda la app.
- ❌ Sin endpoint de logout (el frontend llama `apiLogout`, que es un stub que solo hace `console.log`).
- ⚠️ Roles: 5 de 6 reconocidos en `/api/config`. **`STAFF_USER` no tiene rama y cae en el default, que es la configuración ADMIN** → los 34 usuarios staff verían todos los departamentos, todo el directorio y `accessProjects:true`. En el original el default también es ADMIN, pero STAFF_USER **sí** tiene rama explícita; aquí se perdió. Es la brecha de permisos más grave del sistema actual.
- ⚠️ `getSystemConfig`: existe pero recibe **solo `role`, no `username`** → estructuralmente imposible implementar los casos por usuario. Solo 9 de 19 departamentos en `ALL_DEPTS` (faltan CEO, PRESUPUESTOS, PRECIOS UNITARIOS, SEGURIDAD, LIMPIEZA, ALMACEN Y MAQUINARIA, FINANZAS, FACTURACION, RH, CALIDAD). El mirror de TONITA apunta a `ANTONIA_VENTAS` en vez de `ANTONIA PINEDA LOPEZ`.
- ❌ Excepción `JUANY_RODRIGUEZ` (COMPRAS/FACTURACION/FINANZAS): perdida — tal como el SSD predijo.
- ❌ Relabel `JESUS_CANTU` → "INTERDICIPLINARIA": perdido.
- ❌ `restrictedUsers` (6 vendedores): no existe en el backend.
- ❌ Decisión de hashing: no tomada (ver §4).

### 22.2 Organigrama y Directorio — ✅1 ⚠️1 ❌4
- ✅ Modelo `DB_DIRECTORY` (`NOMBRE`/`DEPARTAMENTO`/`TIPO_HOJA`, con `ESTANDAR`/`HIBRIDO`/`VENTAS`) leído por `get_directory_from_db`.
- ⚠️ Semilla: `INITIAL_DIRECTORY` de Python tiene **55 entradas repartidas en 9 departamentos** vs. las 36 entradas/19 deptos del spec §6.4. Nombres distintos (aparecen EDGAR HOLT, ALEXIS TORRES, INGE OLIVO, RUBEN PESQUEDA...; desaparecen todo RH, FINANZAS, PRESUPUESTOS, CALIDAD, SEGURIDAD, PRECIOS UNITARIOS, LIMPIEZA, CEO). Parece una versión anterior del organigrama, no la vigente.
- ❌ Las 41 cuentas de `USER_DB` con `role/label/email/staffName/dept/seller`: solo hay 3-4 usuarios mock; no hay campos `email`/`staffName`/`seller` en ningún lado.
- ❌ `apiResyncDirectory` (solo ADMIN): no existe.
- ❌ `apiAddEmployee`/`apiDeleteEmployee`: stubs.
- ❌ Decisión `CESAR_GOMEZ`: no tomada.

### 22.3 Motor de Trackers — ✅1 ⚠️2 ❌7
- ✅ Lectura: `GET /api/data` separa activas/histórico por el separador `TAREAS REALIZADAS`, devuelve `_rowIndex` — equivalente fiel de `internalFetchSheetData`.
- ❌ `apiSaveTrackerBatch`: **stub** — no hay guardado por lotes en el backend. Con él caen: ❌ `_tempId`+Gatekeeper 120s, ❌ búsqueda por folio con fallback CONCEPTO+FECHA, ❌ generación atómica de folios, ❌ auto-sanación `AV-XXXX`, ❌ auto-archivado al 100% (el frontend espera `res.moved`, que nunca llega).
- ❌ `internalUpdateTask`: `apiUpdateTask` es stub que devuelve `{success:true}` sin guardar → **el usuario edita una celda, ve el toast "Guardado", y el dato se pierde al refrescar**. Regresión de pérdida silenciosa de datos en la vista principal del sistema.
- ❌ Guardia de inmutabilidad de `PPCV3`: no solo falta — `process_and_save_work_order` **escribe directamente en PPCV3** en cada guardado, violando la regla "solo lectura fuera de Planeación Semanal".
- ⚠️ Alias de columnas: heurística parcial en `find_header_row`, sin decisión documentada.
- ⚠️ Interpretación `100/'100%'/'SI'/1.0`: solo existe en el cliente (check del confetti y semáforos); el backend no interpreta avance en absoluto.

### 22.4 Papa Caliente — ❌7 (0% migrado)
No existe nada: ni las 7 etapas `L, CD, EP, CI, EV, CEC, RCC`, ni `PROCESO_LOG`, ni delegación, ni reverse-sync, ni `MAP COT` (o su reemplazo), ni cierre `RCC` con `GANADA/PERDIDA X PRECIO/DESCUENTO`, ni el caso de prueba e2e de §10.2. `grep PROCESO_LOG` da **cero** resultados en `api/` y en `index.html` — incluso el timeline visual desapareció del frontend (ver 22.14). Ojo: el `papaCaliente` que sí existe en `work_order.py` es la *tercera* acepción (aprobación WO) — correcto que esté separada, pero las otras dos no existen.

### 22.5 Enrutamiento / Caso Antonia — ⚠️2 ❌3
- ❌ Prefijo `AV-` exclusivo (no existe `generatePrefix`; los folios no-WO son `PPC-<random>`).
- ❌ Redirección forzosa a la tabla maestra de Ventas (no hay lógica de ruteo).
- ⚠️ Filtro `(VENTAS)`: `work_order.py:447` salta responsables cuyo nombre contiene `(VENTAS)` al distribuir — un eco del filtro original, pero solo en el flujo WO.
- ⚠️ `VENDEDOR/RESPONSABLE/INVOLUCRADOS`: en WO, `responsable` se mapea a `INVOLUCRADOS`/`RESPONSABLE` a la vez (no separado en 3 flujos ✓), pero no existe la lógica general de distribución.
- ❌ `allowedBase` de 45 columnas: no existe.

### 22.6 Módulo PPC — ✅1 ⚠️2 ❌3
- ⚠️ Distinción PPC vs Papa Caliente: no hay riesgo de fusión con el pipeline de Ventas (porque no existe), pero **PPC y Work Order sí quedaron fusionados**: `POST /api/savePPC` llama a `process_and_save_work_order` para ambos; el "módulo PPC" no tiene guardado propio.
- ⚠️ `apiSavePPCData`: parcial — guarda en PPCV3 ✓, respalda en `ADMINISTRADOR` ✓, distribuye a trackers por responsables separados por coma ✓; falta variante `PPCV4` con mapeo alterno y respaldo en tabla de control/borrador.
- ❌ Auto-migración de columnas de `JESUS_CANTU` / ❌ filtrado de 9 campos: nada de JESUS_CANTU existe en el backend.
- ✅ `CUMPLIMIENTO` con fallback `'NO'` (`work_order.py:407`).
- ❌ 3 subtipos PPC en la estructura estándar de subproyectos: no hay cascada.

### 22.7 Work Orders — ver sección 2 (urgente). ✅1 ⚠️4 ❌0.

### 22.8 Proyectos / Cascada — ❌5 (0% migrado)
Sin modelos `DB_SITIOS`/`DB_PROYECTOS`, sin 10 subproyectos estándar, sin `apiFetchCascadeTree` (stub), sin `apiFetchProjectTasks` (el bug queda "resuelto" por inexistencia, no por corrección), sin relación tarea↔proyecto (ni tag `[PROY:]` ni FK). Las vistas PROJECTS/PROJECT_TASKS_VIEW existen en el frontend pero reciben listas vacías. Curiosidad: `find_header_row` ya reconoce headers `ID_SITIO`/`ID_PROYECTO` — preparación de lectura sin nada detrás.

### 22.9 KPIs — ❌6 (0% migrado)
No hay `apiFetchAdminKPIs` ni nada equivalente (ni siquiera stub en el adaptador). La vista KPI_DASHBOARD existe en el frontend y el módulo se ofrece al rol ADMIN en `/api/config`, pero al abrirla no hay método que la alimente. Fórmulas (% Ganadas, % Cierre, semaforización de eficiencia, productividad L-V) — todas ausentes. Decisión 6 vs 9 vendedores: no tomada.

### 22.10 Agentes IA — ⚠️1 ❌6
- ⚠️ La app tiene IA real pero **distinta a la del SSD**: transcripción/extracción con Groq-Whisper (`ai_utils.py`), agente entrevistador de ingeniería (`engineering_agent.py`), y la "Paperclip Agency" LangGraph (levantamiento→arquitecto 3D→cálculo→precios con crítica reflexiva, `paperclip_agents.py`) para cotizaciones y escenas Pascal. Nada de esto equivale a los agentes narrativos del SSD.
- ❌ Métricas de cotizaciones con SLA A/AA/AAA (3/14/30 días), ❌ 4 reglas de alerta, ❌ métricas de productividad de trackers, ❌ 3 reglas de productividad, ❌ envío de reporte HTML por correo (no hay ningún canal de email en la app), ❌ bug de destinatarios ADMIN_CONTROL (ver §3).

### 22.11 Integraciones — ⚠️2 ❌4
- ❌ Notificación de asignación a Outlook/365: no existe ningún canal (ni Make.com, ni Graph, ni SMTP). ❌ Los 3 puntos de disparo, por consecuencia. ❌ `findUserEmailByLabel` (no hay emails en el modelo de usuario).
- ⚠️ Gemini→Groq (decisión de facto sin documentar). Las keys de Groq se leen de env/parámetro ✓ (aunque `apiKey` recibido por Form se escribe en `os.environ` — mala práctica, contamina el proceso global).
- ❌ Key de Gemini: comprometida y aún committeada (ver §3).

### 22.12 Triggers — ✅1 ⚠️1 ❌2
- ⚠️ `incrementarContadorDias`: el frontend recalcula on-the-fly (`calculateDiasCounter`, index.html:6112, se ejecuta al cargar tracker) — es la solución que el checklist sugiere, pero no está documentada como decisión y el valor nunca se persiste/expone server-side.
- ❌ `autoUpdateQuoteMetrics`: no hay job ni scheduler alguno (no hay APScheduler/cron/celery en requirements).
- ❌ Menú admin de Sheets: la funcionalidad que exponía (alta/actualización rápida) no está cubierta por ningún endpoint/panel.
- ✅ Folio legado `generarFolioAutomatico`: correctamente NO migrado (deuda técnica descartada).

### 22.13 Banco de Información y Agenda — ❌5 (0% migrado)
- ❌ Estructura `[Año]/[Mes]/[Cliente]`: no hay storage de archivos (los uploads devuelven URL mock — ver 2.6). Lo más cercano es `Notas/Prework_Orders/*.md` (export Obsidian por folio), que es otra cosa y además efímero en serverless.
- ❌ Archivado automático por `COTIZACION`/`ARCHIVO`: no existe.
- ❌ `apiFetchInfoBankCompanies/Data/DistinctClients`: stubs; la vista INFO_BANK existe y renderiza vacía.
- ❌ `AGENDA_PERSONAL`/`HABITOS_LOG`: sin backend; `apiFetchUnifiedAgenda` **ni siquiera está en el adaptador** → abrir "Mi Agenda Personal" lanza TypeError en consola y la vista queda vacía. `apiSaveHabitLog`/`apiSavePersonalEvent` son stubs (otro caso de "guardado" que no guarda).
- ❌ Decisión fallback demo: no tomada.

### 22.14 Frontend — ✅2 ⚠️3 ❌1
- ⚠️ Estado reactivo: 107 `ref()`/`reactive()` — cobertura amplia (fork evolucionado del original, con vistas nuevas: PASCAL_DESIGNER, OBSIDIAN_GRAPH, PERSONAL_AGENDA, INFO_BANK, DIRECTORY_VIEW, INSTRUCCIONES*). Pero hay un módulo **perdido**: todo el estado del timeline Papa Caliente.
- ⚠️ Vistas: las 10 activas del original existen (incluso ECG_VIEW), pero solo STAFF_TRACKER (lectura), WORKORDER_FORM y PPC_DINAMICO (guardado) funcionan end-to-end; el resto opera contra stubs.
- ✅ Tipografía: `text-transform` en CSS (cabeceras minúsculas / datos mayúsculas) heredado del original.
- ✅ Semáforo por `CLASIFICACION`: exacto (`A`=3/1, `AA`=15/3, `AAA`=30/5 — index.html:7229-7231 y duplicado en 6181/6213). Solo client-side, aceptable según el checklist.
- ❌ Timeline Papa Caliente (7 pasos, 3 estados): **desapareció por completo** (`getProcessTimeline`, `PROCESO_LOG`, `MAP COT`: 0 apariciones).
- ⚠️ `isFieldEditable`: existe **solo** en el cliente. El checklist pedía una única fuente de verdad *en el backend*; hoy hay una única fuente pero en el lado equivocado — el backend no valida permisos de campo en absoluto (cualquier `POST` directo a la API escribe lo que quiera).

### 22.15 Seguridad — ❌5
- ❌ Contraseñas: texto plano en Supabase + mocks en texto plano committeados (`main.py:309-313`).
- ❌ Rotación de las 41 contraseñas: no evidenciada; los mocks reutilizan el patrón de credenciales del original (`admin2025`, `tonita2025`, `workorder2026`).
- ❌ Key de Gemini: sigue en el repo (CODIGO.js:3145), sin rotar.
- ❌ Autorización server-side: **no hay ninguna** — y hay un agujero crítico nuevo: `GET /api/data?sheet=USERS` **devuelve la tabla de usuarios completa, contraseñas incluidas, sin autenticación**. Cualquier nombre de tabla es legible por cualquiera. Además CORS `allow_origins=["*"]` con `allow_credentials=True`, y la service key de Supabase hardcodeada (§3) da escritura total a quien lea el repo.
- ❌ Webhooks con secreto: N/A todavía (no hay webhooks), pendiente al implementar notificaciones.

---

## 6. §23 — Anti-patrones: ¿cuáles siguen y cuáles se evitaron?

| # | Anti-patrón | Estado en Prework Order |
|---|---|---|
| 23.1 | Lógica por nombre de persona | **Sigue** (menos volumen): `if active_user == 'PREWORK_ORDER'` en work_order.py:199 decide el algoritmo de folio. Las excepciones JUANY/JESUS_CANTU no se migraron — pero por omisión, no por diseño de datos. |
| 23.2 | Listas de vendedores/restricciones hardcodeadas | **Sigue en germen**: `INITIAL_DIRECTORY` (55 entradas) y `MOCK_USER_DB` hardcodeados en código; no existe `get_sellers()` ni atributo `seller` consultable. |
| 23.3 | Doble fuente de verdad string vs JSON | **Evitado por vacancia** (no hay MAP COT), pero reaparece en miniatura: `DETALLES_EXTRA` guarda JSON serializado como string dentro de una celda de texto. |
| 23.4 | Enums repetidos por función | **Sigue**: `ppc_headers` (23 columnas) copiado literal 2 veces en work_order.py (líneas 193 y 419); la lista de estados "completado" vive duplicada en el frontend. |
| 23.5 | Nombres de tabla como strings dispersos | **Sigue**: `"PPCV3"`, `"ADMINISTRADOR"`, `"USERS"`, `"DB_DIRECTORY"`, `"DB_WO_*"` como literales locales por función; no hay `constants.py` ni ORM. |
| 23.6 | God functions | **Sigue**: `process_and_save_work_order` (~280 líneas) hace folio + 8 tablas hijas + fila maestra + respaldo admin + distribución + export Obsidian. Es la `apiSaveTrackerBatch` nueva en pequeño. |
| 23.7 | Estado global sin DI | **Sigue**: `gs_manager` y `sb_manager` son singletons de módulo creados al importar (el cliente Supabase se conecta en el import). Cero `Depends()`. Los tests dependen de `gs_manager.is_mock` global — la versión Python del `sed` sobre el fuente. |
| 23.8 | Errores silenciados | **Sigue**: `except Exception: print(...); return None` en supabase_manager, sheets y work_order (save_to_obsidian traga todo). Un fallo de persistencia se ve idéntico a un éxito. |
| 23.9 | Validación manual vs Pydantic | **Mitad y mitad**: hay modelos Pydantic en el borde (`LoginRequest`, `SavePPCRequest`, y los agentes IA usan schemas ricos), pero el payload de negocio es `List[Dict[str, Any]]` y se mapea a mano con `.get()` campo por campo — el patrón original con sintaxis Python. |
| 23.10 | Sin paginación | **Sigue**: `select("*")` sin límite en Supabase; `/api/data` trae la tabla completa y filtra en Python. |
| 23.11 | Sin migraciones versionadas | **Sigue**: el patrón "crear hoja con headers si no existe" está replicado (work_order.py:192, 438; save_child_data). Sin Alembic. |
| 23.12 | Aprovechar FastAPI | **Parcial**: OpenAPI /docs viene gratis y hay algo de Pydantic; pero sin `response_model`, sin `Depends()` de auth, y los tests (unittest/pytest) validan HTML por regex (`test_workorder_template.py`) — el mismo anti-patrón de testeo que §14 criticaba — con una única prueba de lógica API real (`test_backend_refactor.py`). |

**Balance §23: 8 siguen, 3 a medias, 1 evitado (23.3, y en parte por vacancia).**

---

## 7. Veredicto

**Prework Order hoy NO es un reemplazo de Holtmont Workspace: es un módulo de Work Orders funcional (con las regresiones de la sección 2) + un lector de trackers + una suite de agentes IA nueva, todo montado detrás de un frontend completo cuyos guardados, en su mayoría, simulan éxito sin persistir.** El 70% del checklist está en ❌, incluyendo el 100% de Papa Caliente, Proyectos/Cascada, KPIs, Banco/Agenda y Seguridad.

### Orden de ataque recomendado

**Fase 0 — Hoy mismo (seguridad, 1 día):**
1. Rotar la service key de Supabase y la key de Gemini; sacarlas del repo (env only). Purgar `CODIGO.js`/historial o al menos invalidar la key.
2. Cerrar `GET /api/data?sheet=USERS` (bloquear tablas sensibles + exigir sesión).
3. Hash de contraseñas (passlib/bcrypt) y eliminar los mocks con contraseñas reales del código.

**Fase 1 — Frenar la pérdida de datos y las regresiones WO (1 semana):**
4. Reemplazar todos los stubs "exitosos" del adaptador por errores visibles ("función no disponible") — que el usuario no crea que guardó.
5. Secuencia de folios atómica en Supabase (tabla `sequences` + RPC/transacción), eliminando `sequences.json`; completar el mapa de abreviaturas (FINANZAS/FACTURACION).
6. Endurecer `save_child_data`/`append_row` contra tablas inexistentes (migraciones Alembic o SQL versionado para las 8 tablas DB_WO_*).
7. Upload real de archivos (Supabase Storage) — hoy las WO guardan URLs falsas.

**Fase 2 — El corazón del sistema (Trackers + RBAC, 2-4 semanas):**
8. `apiSaveTrackerBatch` + `apiUpdateTask` reales (Gatekeeper, matching por folio, auto-archivado, guardia PPCV3), con los remedios de §23 (servicios inyectables, enums únicos).
9. RBAC completo: rama STAFF_USER (urgente: hoy caen en config ADMIN), `USER_DB` completo en Supabase con `seller`/`email`/`staffName`, `restrictedUsers` como datos, excepciones JUANY/JESUS_CANTU como `role_overrides`, 19 departamentos, y `isFieldEditable` respaldado server-side.
10. Auditoría (`LOG_SISTEMA` equivalente) + logout.

**Fase 3 — Ventas (3-4 semanas):** Papa Caliente completo (etapas, PROCESO_LOG estructurado, delegación, reverse-sync, timeline UI — usar el payload de §10.2 como test e2e), enrutamiento/Caso Antonia, prefijos de folio (`AV-`), Banco de Información + archivado automático.

**Fase 4 — Gestión y dirección (2-3 semanas):** Proyectos/Cascada (con FK real, corrigiendo el bug de `apiFetchProjectTasks` por diseño), módulo PPC separado de WO (PPCV4, reglas JESUS_CANTU como configuración), KPIs (decidiendo 6 vs 9 vendedores).

**Fase 5 — Periferia (2 semanas):** notificaciones Outlook/email (con secreto en webhooks), agentes narrativos (reusando la infraestructura Groq/LangGraph ya construida — es la parte donde Prework Order va *adelante* del original), jobs programados, Agenda/Hábitos.

Con eso, el sistema no solo alcanza paridad: la corrige donde el original estaba roto (los 3 bugs 🐛) y evita re-pagar la deuda de §23.
