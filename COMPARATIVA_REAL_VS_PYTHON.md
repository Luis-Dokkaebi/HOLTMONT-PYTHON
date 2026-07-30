# Comparativa HOLTMONT-PYTHON vs. REAL-HOLTMONT

> **ESTADO AL 2026-07-30, TRAS LA MIGRACIÓN.** Este documento se escribió como
> auditoría *antes* de cerrar las brechas. Lo de abajo describe el punto de
> partida y se conserva como registro; **el estado actual está en §0.**

**Fecha:** 2026-07-30
**Repos comparados:**
- `REAL-HOLTMONT` @ `fba96e1` (Apps Script + Sheets — sistema en producción)
- `HOLTMONT-PYTHON` @ `d6d006a` (FastAPI + Supabase — migración)

**Método:** inventario cruzado de las 51 funciones server-side `api*`/`get*`/`run*`/`upload*` de
`CODIGO.js` contra los endpoints de `api/main.py` y los métodos del adaptador `api_service.js`;
diff completo de `index.html`; comparación contra el contrato en `REAL-HOLTMONT/docs/API_CONTRACT.md`
y `docs/ARQUITECTURA_Y_BASE_DE_DATOS.md`.

> Esta comparativa reemplaza a `AUDITORIA_PARIDAD_SSD22.md` (2026-07-05), que quedó desactualizada:
> buena parte de lo que ahí figuraba como ❌ (Papa Caliente, PROCESO_LOG, MAP COT, reverse sync,
> Gatekeeper, prefijos de folio, SLA, auditoría, notificación a Outlook, keys hardcodeadas) ya está
> implementado. También corrige dos conclusiones equivocadas de esa auditoría (ver §6).

---

## 0. Estado actual (después de la migración)

De las **40 funciones que `index.html` invoca del backend original, las 40 están
conectadas.** Cero stubs. `tests/test_paridad_appscript.py` lo verifica en cada
corrida.

| Eje | Antes | Ahora |
|---|---|---|
| Funciones conectadas | 21 de 40 (54%) | **40 de 40 (100%)** |
| Stubs en el adaptador | 16 | **0** |
| Pruebas | 464 | **617** (+153) |
| Suite GAS | 85/85 | **87/87** (2 nuevas de contrato) |

### Lo que se cerró, por módulo

| Módulo | Qué se hizo |
|---|---|
| Autenticación / RBAC | Rama `STAFF_USER` (cerraba el agujero que daba config de ADMIN a todo el personal), 19 departamentos, `canSeeBancoJuntas`, ramas `JUANY_RODRIGUEZ` y `JESUS_CANTU`, `MY_SALES` para los 9 vendedores, espejo de TONITA, `apiLogout` con registro. |
| Proyectos / Cascada | Los 5 métodos, sobre `sites` y `projects`. |
| Borradores PPC | Los 3 métodos, sobre `ppc_borradores`, con semántica de reemplazo. |
| Agenda / Hábitos | Escrituras sobre `personal_agenda` y `habits_log`. |
| Banco de Información | `apiFetchInfoBankData` con la comparación bidireccional de cliente. |
| Directorio | Alta y baja de empleados sobre `people`. |
| Lecturas sueltas | `apiFetchPPCData`, `apiFetchCombinedCalendarData`. |
| Archivos | Supabase Storage + archivado `[Año]/[Mes]/[Cliente]`. |
| Agentes / correo | Productividad real con las 3 reglas, canal SMTP, cron diario. |

### Cinco bugs corregidos que la auditoría no había visto

Salieron al escribir el código, no al leerlo:

1. **`internalUpdateTask` ausente del adaptador.** Es el botón de guardar de cada
   fila del tracker. `TypeError` sincrónico que `withFailureHandler` no captura,
   dejando `isSubmitting` en `true` para siempre: **bloqueaba todo guardado
   posterior de la aplicación** hasta recargar.
2. **`transcribirConGemini` ausente.** Mismo fallo, rompiendo las dos rutas de voz.
3. **`getSystemConfig` perdía el `username`.** El adaptador lo declaraba con un
   solo parámetro mientras el frontend pasa dos, así que las ramas de RBAC por
   cuenta eran **inalcanzables por construcción**.
4. **Dos `find_header_row` divergentes.** La de `sheets.py` reconocía los
   encabezados de agenda y hábitos; la de `tracker_rules.py` no. Como
   `rows_to_dicts` usa la segunda, `fetch_unified_agenda` devolvía agenda y
   hábitos **siempre vacíos**, con 27 eventos en la base.
5. **Destinatarios del reporte de productividad.** `USER_DB['ADMIN_CONTROL']` no
   existe: es un rol, no una cuenta. El reporte nunca llegó a JAIME_OLIVO ni a
   DIMAS_RAMOS. Es uno de los tres bugs 🐛 del original; se resuelve por rol.

Y el bug documentado del original, el `ReferenceError` de `apiFetchProjectTasks`,
se corrigió por diseño en vez de replicarse.

### Lo que sigue pendiente y por qué

| Pendiente | Estado |
|---|---|
| **Contraseñas en texto plano** | **Decisión explícita del dueño (2026-07):** se migran en la migración completa. No es un olvido. |
| **`habits_log` no existe en la base** | El código está escrito y falla con un mensaje que dice qué crear. DDL en `docs/DDL_PENDIENTE.sql`. |
| **`GET /api/data` sin autenticación** | Sigue abierto; `?sheet=USERS` expone la tabla de usuarios. Requiere sesión/JWT, que va con el punto 1. |
| **Key de Gemini en `CODIGO.js:3347`** | Sigue versionada. Rotarla y purgarla. |
| **Carrera en los folios** | Se lee el máximo y se suma, sin candado. La solución es una secuencia de Postgres. |
| **Esquema no verificable** | Sin credenciales, los repositorios nuevos *resuelven* los nombres de columna entre candidatos en vez de declararlos. Fijar el mapa cuando alguien corra `scripts/verificar_base_tasks.py` con acceso. |
| **`bucket` de Storage** | Debe ser público: el original publicaba con `ANYONE_WITH_LINK`. |
| **Higiene** | `HOLTMONT-PYTHON-main/` (copia del repo dentro del repo, 4.6 MB) y 24 scripts de andamiaje siguen versionados. |

**Veredicto:** todo lo que se usa en el de AppScript se puede usar aquí. Lo que
falta no es funcionalidad: es endurecimiento (autenticación, atomicidad de
folios) y dos cosas que requieren acceso a la base.

---

## 1. Resumen ejecutivo

| Eje | Estado |
|---|---|
| **Apariencia (UI)** | **~99% a la par.** 24/24 vistas y 328/328 funciones del frontend presentes. Solo 4 deltas reales, 1 de ellas un bug. |
| **Funcionalidad conectada** | **21 de 39 funciones vivas** (~54%; 47% ponderado por uso). Núcleo ~85-90%, periferia ~15% — ver §5. |
| **Modelo de datos** | Esquema Supabase **más avanzado que los endpoints**: `sites`, `projects`, `ppc_borradores`, `banco_datos`, `personal_agenda`, `habits_log` ya existen y están mapeadas, pero nadie las lee/escribe. |
| **RBAC / Seguridad** | **El punto más débil.** Hay un agujero de permisos que hoy da configuración de ADMIN a todo el personal. |
| **Automatizaciones** | Sin equivalente: no hay scheduler ni canal de correo. |

La migración está mucho más adelantada de lo que sugiere la auditoría anterior. El núcleo del
sistema — trackers, PPC, ventas con Papa Caliente y reverse sync, Work Orders, métricas de
cotizaciones — está portado y con pruebas. Lo que falta se concentra en **cuatro módulos periféricos**
(Proyectos, Banco de Información, Borradores, escrituras de Agenda), **archivos** (no hay storage) y
**RBAC**.

---

## 2. Apariencia: qué falta para que se vea igual

El `index.html` de Python es un fork fiel y actualizado del real:

- **24 vistas en ambos**, cero diferencias: `CERTIFICADO_HOLTZAR`, `DASHBOARD`, `DEPT`,
  `DIRECTORY_VIEW`, `ECG_VIEW`, `INFO_BANK`, `INSTRUCCIONES`, `INSTRUCCIONES_ADMIN`,
  `INSTRUCCIONES_ADMIN_CONTROL`, `INSTRUCCIONES_PPC`, `KPI_DASHBOARD`, `MANUAL_USO`,
  `PERSONAL_AGENDA`, `POLITICAS`, `PPC_DINAMICO`, `PPC_FORM`, `PPC_MENU`,
  `PRODUCTIVIDAD_ACTIVIDADES`, `PROJECTS`, `PROJECT_TASKS_VIEW`, `QUOTE_METRICS`,
  `STAFF_TRACKER`, `WEEKLY_PLAN`, `WORKORDER_FORM`.
- **Las 328 funciones/computed del script del real están todas en Python**, más 5 propias
  (`runPaperclipAgents`, `runActivityPaperclipAgents`, `download3DJson`, `onIframeLoaded`,
  `startDateRaw`).
- Semáforos, `text-transform`, `isFieldEditable`, `getProcessTimeline`: idénticos.

### 2.1 Los 4 deltas reales

| # | Delta | Detalle | Acción |
|---|---|---|---|
| 1 | 🐛 **Índice con coma inválido** | `index.html:2546`: `row['F. ENTREGA', 'F_ENTREGA']`. En JS el operador coma dentro de `[]` evalúa solo al último término → **se pierde el fallback a `'F. ENTREGA'`** y la columna sale vacía para filas con el encabezado antiguo. Las dos líneas vecinas (2544, 2545) sí usan la forma correcta con `\|\|`. | Corregir a `(row['F. ENTREGA'] \|\| row['F_ENTREGA'])`. |
| 2 | ❌ **Guarda de 35 MB en subidas, ausente** | REAL la tiene en 4 puntos (`index.html:5789, 6658, 8388, 8394`, commit `5269f66` "Add 35MB file size limit for uploads to prevent 'Script Invocation' error"). En Python **no hay ninguna** guarda de tamaño. | Portar las 4 validaciones. En FastAPI el error será distinto al de GAS, pero el límite de UX debe existir igual. |
| 3 | ⚠️ **`defaultReqCotizacion` vacío** | REAL precarga 8 actividades estándar de pre-diseño (Arquitectura, Eléctrico, HVAC, Pre-Análisis de Riesgo, Precios Unitarios, 3 Cotizadores Jr) en el paso 2 del PPC. En Python es `const defaultReqCotizacion = []` (`index.html:6494`) → **el formulario abre en blanco**. | Decisión del dueño: la sección se rediseñó en Python (ver 2.2). Si el rediseño no la sustituye, restaurar las 8 filas. |
| 4 | ⚠️ **CSS del date-picker divergente** | REAL (commit `74d60eb`, el más reciente): `color/background: transparent` + `right/bottom: 0`. Python: `opacity: 0` al inicio del CSS. Ambos amplían el área clicable, pero con técnicas distintas — el de Python oculta el ícono nativo por completo. | Unificar con la versión de REAL o documentar la divergencia. |

### 2.2 Divergencia donde Python va *adelante* (no es falta, es decisión sin documentar)

El **paso 2 del PPC** ("Requerimiento para Cotización") se rediseñó en Python: cabecera negra con
título largo ("Requerimiento Pre-Diseños, Pre-Análisis de Riesgos y Precios Unitarios"), botón `+`
para agregar filas, dropdown de responsables con checkboxes contra `config.directory`, y layout
`col-md-3 / col-md-9` en vez de `col-lg-5` + columnas sueltas. REAL sigue con la cabecera amarilla
(`#ffffcc`) y los campos T/Und/Cant/P.U./Total en línea.

**Esto no se puede "igualar" sin decidir en qué dirección**: o el real adopta el rediseño, o Python
vuelve atrás. Es la única diferencia visual que un usuario notaría al cambiar de sistema.

---

## 3. Funcionalidad: mapa completo de las 51 funciones

### 3.1 ✅ Funcionan de extremo a extremo (21)

| Función GAS | Endpoint Python | Nota |
|---|---|---|
| `apiLogin` | `POST /api/login` | Con auditoría en `system_log` (equivalente de `registrarLog`). |
| `getDirectoryFromDB` | `get_directory_from_db()` | Lee `DB_DIRECTORY`. |
| `apiResyncDirectory` | `POST /api/legacy/resyncDirectory` | Agrega faltantes de `INITIAL_DIRECTORY`. |
| `apiFetchStaffTrackerData` | `GET /api/data` | Separa activas/histórico por `TAREAS REALIZADAS`, devuelve `_rowIndex`. |
| `apiSaveTrackerBatch` | `POST /api/legacy/saveTrackerBatch` | **Completo**: Gatekeeper por `_tempId`, match FOLIO→CONCEPTO+FECHA, prefijos (`generate_prefix`), Papa Caliente (`apply_hot_potato`), reverse sync (`build_reverse_sync_payload`), notificación. |
| `apiUpdateTask` | `POST /api/legacy/updateTask` | Persiste de verdad — pero solo en 3 de sus 4 puntos de uso (ver §4.0: `internalUpdateTask`). |
| `apiUpdatePPCV3` | `POST /api/legacy/updatePPCV3` | Con la variante `PPCV4` para `ANTONIA_VENTAS`. |
| `apiSavePPCData` | `POST /api/savePPC` | Escribe maestro + distribuye + respalda. |
| `apiGetNextWorkOrderSeq` | `GET /api/nextSeq` | ⚠️ ver §4.3 (carrera). |
| `generateWorkOrderFolio` | `work_order.generate_work_order_folio` | ⚠️ ver §4.4 (mapa incompleto). |
| `apiFetchWeeklyPlanData` | `GET /api/legacy/weeklyPlan` | `build_weekly_plan` + `map_weekly_plan_header`. |
| `apiFetchSalesHistory` | `GET /api/legacy/salesHistory` | Agrupado por vendedor. |
| `apiFetchQuoteAgentMetrics` | `GET /api/legacy/quoteMetrics` | `compute_quote_metrics` con SLA A/AA/AAA (3/14/30) y buffers (1/2/5). |
| `runQuoteMetricsAgent` | `POST /api/legacy/runQuoteAgent` | Reglas + Gemini. |
| `apiGetLastAgentReport` | `GET /api/legacy/lastAgentReport` | |
| `apiWriteQuoteMetricsToSheet` | `POST /api/legacy/writeQuoteMetrics` | Vuelca a `kpi_cotizaciones`. |
| `apiCheckGeminiKey` | `GET /api/legacy/geminiKey` | Solo preview, nunca la key completa. |
| `apiSaveGeminiKey` | `POST /api/legacy/geminiKey` | |
| `apiFetchInfoBankCompanies` | `GET /api/legacy/infoBankCompanies` | |
| `apiFetchUnifiedAgenda` | `GET /api/legacy/unifiedAgenda` | **Lectura** sí; escrituras no (§3.3). Filtra por usuario (antes no lo hacía). |
| `apiLogDateChange` | `POST /api/legacy/logDateChange` | |
| `NotifierService.sendToOutlook` | `tracker_store.send_to_outlook` | Webhook a Make.com vía `MAKE_WEBHOOK_URL`, payload ISO-Z, `should_notify_sheet`. |

### 3.2 ⚠️ Portado a medias (3)

| Función | Qué falta |
|---|---|
| `getSystemConfig` | Ver §4.1 — es el hueco más grave del sistema. |
| `runTrackerProductivityAgent` | Existe una versión simplificada **inline en `api/main.py:530-575`** (activas/cerradas/% cumplimiento por persona). Faltan las **3 reglas de productividad** del original y el envío del reporte (`_sendTrackerProductivityEmail`). Devuelve `emailSent: false` fijo. |
| `findUserEmailByLabel` | Reemplazado por `rules.resolve_user_email`, pero contra un **diccionario `USER_EMAILS` hardcodeado** + dominio corporativo, no contra un campo `email` de la tabla de usuarios. Anti-patrón §23.2 replicado. |

### 3.3 ❌ Stubs — el frontend los llama y no hacen nada (16)

Están honestamente marcados (`_noPortado` devuelve error visible, `_lecturaVacia` devuelve vacío
avisando), así que **no hay pérdida silenciosa de datos** — eso ya se corrigió. Pero la función no está.

| Función | Usos en UI | Tabla Supabase | Falta |
|---|---|---|---|
| `uploadFileToDrive` | 3 | — | **No hay storage.** Es el stub de mayor impacto: bloquea adjuntos en tracker, WO y banco. |
| `apiFetchCascadeTree` | 4 | `sites`, `projects` ✅ | Endpoint de lectura del árbol. |
| `apiSaveSite` | 1 | `sites` ✅ | Escritura. |
| `apiSaveSubProject` | 2 | `projects` ✅ | Escritura. |
| `apiFetchProjectTasks` | 1 | `tasks` ✅ | Relación tarea↔proyecto (FK `project_id` o tag). **Aquí vive el bug 🐛 del original** (`ReferenceError` permanente): al implementarlo, resolverlo por diseño, no replicarlo. |
| `apiSaveProjectTask` | 1 | `tasks` ✅ | Escritura. |
| `apiSavePersonalEvent` | 3 | `personal_agenda` ✅ | Solo la escritura (la lectura ya funciona). |
| `apiSaveHabitLog` | 2 | `habits_log` ✅ | Ídem. |
| `apiFetchDrafts` | 1 | `ppc_borradores` ✅ | Lectura. |
| `apiSyncDrafts` | 1 | `ppc_borradores` ✅ | Escritura. |
| `apiClearDrafts` | 1 | `ppc_borradores` ✅ | Borrado. |
| `apiFetchInfoBankData` | 1 | `banco_datos` ✅ | Lectura (las empresas ya se leen). |
| `apiFetchPPCData` | 2 | `tasks`/`plan_semanal` ✅ | Lectura. |
| `apiFetchCombinedCalendarData` | 2 | `tasks` ✅ | Lectura. |
| `apiAddEmployee` | 1 | `DB_DIRECTORY` ✅ | Alta + creación de tabla/vista de tracker. |
| `apiDeleteEmployee` | 1 | `DB_DIRECTORY` ✅ | Baja. |
| `apiLogout` | 1 | `system_log` ✅ | Es un `console.log`. Sin registro `LOGOUT`. |

**Dato clave: en 13 de 16 casos la tabla ya existe y está mapeada** en
`api/services/sheets.py:362-378`. Lo que falta es la capa de endpoints, no el esquema. Son módulos
cortos, no reescrituras.

### 3.4 🚫 Código muerto en el real — **no migrar** (5)

Cero llamadas desde `index.html` en ambos repos:

`apiFetchAdminKPIs`, `apiFetchTeamKPIData`, `apiFetchTrackerProductivityMetrics`,
`apiFetchDistinctClients`, `apiCreateStandardStructure`.

### 3.5 ⛔ No aplica: propio de la plataforma GAS

`doGet`, `onOpen`, `cmdRealizarAlta`, `cmdActualizar` (menú del Spreadsheet),
`applyTrafficLightToSheet`, `setupConditionalFormatting`, `colIndexToLetter` (formato condicional de
celdas), `deduplicateAllSheets`, `debugSheetHeaders`, `forzarPermisos`, `instalarDisparador`,
`generarFolioAutomatico` (deuda legada, descartada a propósito), `transcribirConGemini`
(sustituido por Groq-Whisper en `api/ai_utils.py` — decisión válida, **ya documentada** aquí),
y los 12 `test_*` (su equivalente es `tests/` + `tests/gas/`).

---

## 4. Brechas por severidad

### 4.0 🔴 CRÍTICO — El botón de guardar de cada fila del tracker lanza `TypeError` y traba la app

`index.html:8417`, dentro de `saveRow` (`index.html:8345`), la función enlazada al **botón 💾 de
cada fila del staff tracker** (`index.html:2666`):

```js
}).withFailureHandler(...).internalUpdateTask(staffTracker.value.name, ..., currentUsername.value);
```

`internalUpdateTask` **no existe en `api_service.js`** (`grep` → 0). Como `google.script.run` es una
instancia de `GoogleScriptRunAdapter`, la llamada lanza
`TypeError: ...internalUpdateTask is not a function` de forma **sincrónica**, así que
`withFailureHandler` no la captura. Secuencia del fallo:

1. `saveRow` pone `row._isSaving = true` e `isSubmitting.value = true` (líneas 8364-8365).
2. `Swal.showLoading()` abre el spinner.
3. La llamada revienta. Los dos flags solo se reponen **dentro** de los handlers, que nunca corren.
4. El spinner queda girando y, como la guarda de entrada de `saveRow` es
   `if (row._isSaving || isSubmitting.value) return`, **todo guardado posterior en la aplicación
   queda bloqueado hasta recargar la página.**

Es la escritura más usada del sistema y arrastra al resto. El original expone `internalUpdateTask` en
el scope global de `CODIGO.js`, así que ahí sí funciona — su propio
`docs/ARQUITECTURA_Y_BASE_DE_DATOS.md` dice que las `internal*` "no las llama el FE directamente",
y esta es la excepción que la migración no vio.

**Arreglo:** un método `internalUpdateTask` en el adaptador apuntando a
`POST /api/legacy/updateTask` (mismos 3 argumentos que `apiUpdateTask`, que ya está conectado). Es
un alias de ~3 líneas. `apiUpdateTask` sí funciona en sus otros 3 puntos de uso (9311, 10011, 10131),
lo que explica por qué el fallo pasó desapercibido.

### 4.1 🔴 CRÍTICO — `STAFF_USER` recibe configuración de ADMIN

`api/main.py:111-187`. El original (`CODIGO.js:641-671`) tiene una rama explícita para
`STAFF_USER` que devuelve `departments: {}` y un solo módulo espejo con **su propio** tracker.
**En Python esa rama no existe**: `STAFF_USER` cae al `return` final de ADMIN y recibe

```
departments: ALL_DEPTS   ·   staff: full_directory   ·   accessProjects: True
```

Los ~34 usuarios con rol `STAFF_USER` (de las 42 cuentas de `USER_DB`) ven **todos los
departamentos, el directorio completo y el módulo de proyectos**. Es la brecha de permisos más
grave del sistema actual y hay que cerrarla antes de cualquier otra cosa.

### 4.2 🔴 ALTO — RBAC incompleto

| Brecha | Estado |
|---|---|
| **`/api/config` recibe solo `role`, no `username`** | Estructuralmente imposible implementar los casos por usuario. Bloquea las dos brechas siguientes. |
| Rama `JUANY_RODRIGUEZ` (COMPRAS + FACTURACION + FINANZAS) | Ausente. |
| Relabel `JESUS_CANTU` → módulo PPC = "INTERDICIPLINARIA" | Ausente. |
| `ALL_DEPTS`: **9 de 19 departamentos** | Faltan `CEO`, `PRESUPUESTOS`, `PRECIOS UNITARIOS`, `SEGURIDAD`, `LIMPIEZA`, `ALMACEN Y MAQUINARIA`, `FINANZAS`, `FACTURACION`, `RH`, `CALIDAD`. |
| `canSeeBancoJuntas` | **No aparece en ninguna** de las 5 respuestas de `/api/config`. El original lo devuelve en todas. |
| `USER_DB` (42 cuentas con `role`/`label`/`email`/`staffName`/`dept`/`seller`) | Sin migrar. `grep seller\|staffName` en `api/` y `backend/` → **0 resultados**. |
| Módulo `MY_SALES` para `seller: true` | Imposible sin el campo `seller`. Los 8 vendedores no ven su hoja `NOMBRE (VENTAS)`. |
| `TONITA`: módulo `MY_TRACKER` espejo a `ANTONIA PINEDA LOPEZ` | Ausente en la rama TONITA de Python. |
| `restrictedUsers` | No existe. |
| `isFieldEditable` server-side | Sigue solo en el cliente: un `POST` directo escribe cualquier campo. |

### 4.3 🔴 ALTO — Autenticación y superficie de datos

- **Contraseñas en texto plano.** `api/main.py:311` compara `row[pass_idx] == creds.password`.
  Sin `bcrypt`/`passlib`/`argon2` en `requirements.txt`.
  *(Nota: el original tiene el mismo defecto y su propio doc lo reconoce como limitación conocida —
  pero la migración es la oportunidad de cerrarlo, no de heredarlo.)*
- **`GET /api/data?sheet=USERS` sin autenticación** devuelve la tabla de usuarios completa,
  contraseñas incluidas. Cualquier nombre de tabla es legible por cualquiera. No hay sesión ni token.
- **Key de Gemini comprometida, aún versionada:** `CODIGO.js:3347`
  (`AIzaSyA7Lv551Quq7lMCynU7kRq9T1_MIaK6kkc`). La copia del GAS vive en la raíz del repo Python.
  Rotarla y sacarla del historial.

**Ya corregido (no confundir con la auditoría anterior):** la service key de Supabase salió del
fuente (`SupabaseManager` la resuelve de entorno, lazy), los mocks con contraseñas reales se
eliminaron, y el CORS ya no es permisivo (`allow_credentials=bool(_cors_origins)`).

### 4.4 🟠 MEDIO — Integridad de folios y datos

| # | Brecha | Detalle |
|---|---|---|
| 1 | **Carrera en los consecutivos** | Tracker (`tracker_store._secuencia_desde_la_base`) y WO (`work_order.get_next_sequence`) leen el máximo y suman. Sin candado ni secuencia de Postgres, dos peticiones simultáneas obtienen el mismo folio. El original usa `LockService` + Script Properties. Está documentado como Fase 2 en el propio código; **es la última pieza dura del núcleo.** |
| 2 | **`sequences.json` todavía en el camino** | `work_order.py:6,80`. Solo se usa sin base (desarrollo), pero en un despliegue mal configurado vuelve el reinicio a 1000 en cada arranque en frío. |
| 3 | **`ABBR_MAP` de folio WO: 24 de 27 entradas** | Faltan exactamente `FINANZAS→Finanzas`, `FACTURACION→Factura`, `FACTURACIÓN→Factura`. Una WO de Finanzas cae al truncado y genera un folio con formato distinto. Hallazgo de la auditoría anterior **todavía abierto**. |
| 4 | **3 bloques de WO sin tabla** | Viáticos, transporte e ingeniería: el endpoint avisa y el detalle solo queda en la nota de Obsidian. Honesto, pero incompleto. |
| 5 | **Sin migraciones versionadas** | No hay Alembic ni `.sql`. El esquema Supabase existe solo en la base; el repo no lo puede recrear ni revisar en PR. |

### 4.5 🟠 MEDIO — Automatizaciones ausentes

- **No hay scheduler.** `grep -iE 'apscheduler|celery|cron'` → 0; sin `.github/workflows`.
  Queda sin correr `autoUpdateQuoteMetrics` (trigger diario 07:00 → agente + correo).
- **No hay canal de correo.** `_sendAgentEmail` y `_sendTrackerProductivityEmail` no tienen
  equivalente. El webhook a Outlook (Make.com) sí funciona, pero es para asignación de tareas, no
  para los reportes.
- **`incrementarContadorDias`:** Python lo recalcula en el cliente (`calculateDiasCounter`). Es la
  solución correcta y más simple, pero **el valor nunca se persiste ni se expone server-side** →
  ningún consumidor externo (reporte, query SQL) puede usar el contador de días.
- **Archivado automático en Drive** (`archiveFile`, `processQuoteRow`, `runFullArchivingBatch`,
  `getBankRootFolder` → estructura `[Año]/[Mes]/[Cliente]`): sin equivalente. Depende de resolver
  primero el storage (§3.3).

### 4.6 🟡 BAJO — Higiene del repo

- **`HOLTMONT-PYTHON-main/`: 77 archivos, 4.6 MB — una copia completa del propio repo, versionada.**
  Contiene un `CODIGO.js` y un `api/` viejos. Cualquier `grep` da resultados duplicados y
  contradictorios; es una trampa para quien llegue nuevo.
- **24 scripts desechables en la raíz**: `modify_html*.py` (×6), `fix_*.py` (×5), `patch*.py`,
  `parse_*.py`, `finish_html*.py`, `rewrite_html.py`, `locate_and_extract.py`, `get_section.py`.
  Eran andamios de la migración del HTML.
- **`requirements.txt` no declara las dependencias de prueba.** `run_tests.sh` corre
  `python -m pytest`, pero `pytest`, `playwright` y `httpx` no están en el archivo → en un entorno
  limpio la suite Python **no arranca** (verificado: `No module named pytest`); solo corren los 85
  tests de Node, que pasan 85/85.
- Artefactos varios versionados: `commit_message.txt`, `recovered_blobs.txt`, `temp.html`,
  `temp2.html`, `index_backup.html`, `patch_ui.txt`, `*.patch`.

---

## 5. ¿Qué porcentaje de paridad funcional hay?

**Denominador:** de las 51 funciones server-side de `CODIGO.js`, **39 son superficie viva** — las que
`index.html` invoca de verdad. Las otras 12 son código muerto (§3.4), utilidades de la plataforma
GAS o pruebas (§3.5), y no cuentan porque migrarlas no aporta nada.

| Métrica | Cálculo | Resultado |
|---|---|---|
| **Por conteo de funciones** | 21 conectadas de 39 | **54%** |
| **Ponderado por puntos de invocación en la UI** | 26 de 55 llamadas | **47%** |
| **Solo lo fielmente equivalente** (descontando `getSystemConfig` y `runTrackerProductivityAgent`, conectadas pero degradadas) | 19 de 39 | **49%** |

### 5.1 Pero el promedio engaña: la distribución está muy polarizada

El número global (~50%) no describe bien el sistema, porque **el núcleo está casi terminado y la
periferia casi sin empezar**:

| Módulo | Funciones | Paridad | Comentario |
|---|---|---|---|
| Ventas / Papa Caliente / reverse sync | 3/3 | **~100%** | Lo más difícil del original, y está completo y con pruebas. |
| Cotizaciones + agente Gemini | 6/6 | **~95%** | Solo `runTrackerProductivityAgent` va simplificado. |
| Work Orders | 2/2 | **~85%** | Descuenta la carrera de folios y las 3 abreviaturas faltantes. |
| Tracker — lectura | 1/1 | **100%** | |
| Tracker — escritura | 2/3 | **~65%** | Conectadas las 2 grandes; roto el botón por fila (§4.0). |
| Directorio | 2/4 | **50%** | Falta alta/baja de empleados. |
| Autenticación / RBAC | 1.5/3 | **~50%** | `apiLogin` ✅; `apiLogout` no-op; `getSystemConfig` con el agujero de §4.1. |
| PPC | 2/6 | **33%** | Faltan lectura del maestro y los 3 de borradores. |
| Agenda / Hábitos | 1/3 | **33%** | Lectura sí, las 2 escrituras no. |
| Banco de Información | 1/2 | **~25%** | La mitad nominal, pero sin storage no sirve de nada. |
| Proyectos / Cascada | 0/5 | **0%** | Módulo entero sin empezar. |
| Archivos / adjuntos | 0/1 | **0%** | No hay storage. Bloquea 3 módulos. |
| Calendario combinado | 0/1 | **0%** | |
| Automatizaciones + correo | 0/2 | **0%** | Sin scheduler ni canal de correo. |
| KPI Dashboard / Productividad | — | **a la par** | Maqueta en los dos sistemas (§6). No es deuda de migración. |

**Lectura honesta:** si un usuario solo usa trackers, ventas, PPC básico, Work Orders y métricas de
cotizaciones — que es el uso diario del sistema — la paridad ronda el **85-90%**, con dos defectos
que hay que tapar (§4.0 y §4.1). Si además usa proyectos, adjuntos, borradores, banco o agenda, la
paridad cae a **~15%**.

### 5.2 Y el 50% restante no es 50% del esfuerzo

De las 18 funciones que faltan, **13 ya tienen su tabla creada y mapeada** en Supabase
(§3.3). Son endpoints CRUD contra un esquema que existe. El trabajo de fondo que queda es corto y
está acotado:

1. Storage de archivos (habilita 3 módulos de golpe).
2. La relación tarea↔proyecto de Proyectos/Cascada.
3. Secuencia de Postgres para los folios.
4. RBAC completo (`USER_DB` a la base + las ramas por usuario).
5. Scheduler y canal de correo.

Todo lo demás es cableado. Por eso el plan de §7 cabe en 5-6 semanas y no en un trimestre.

---

## 6. Dos correcciones a la auditoría del 5 de julio

Ambas cambian el plan de trabajo, por eso conviene dejarlas escritas:

1. **El KPI Dashboard ya está a la par — porque en el original también es una maqueta.**
   `loadKPIData()` en `REAL-HOLTMONT/index.html:7543` empieza con `// MOCK DATA GENERATION` y
   asigna literales (`{ name: 'JUDITH ECHAVARRIA', volumen: 15, eficiencia: 1.2 }`, …) dentro de un
   `setTimeout`. Nunca llama a `apiFetchAdminKPIs`. Python tiene **exactamente el mismo código**.
   El módulo 22.9 no es una deuda de migración: es una maqueta pendiente de construir en los dos
   sistemas. Igual pasa con `PRODUCTIVIDAD_ACTIVIDADES`, que solo renderiza
   `trackerProductivityData.geminiReport`.

2. **Los stubs ya no simulan éxito.** El `_noPortado`/`_lecturaVacia` de `api_service.js:121-135`
   devuelve error visible o vacío avisado. La regresión de "el usuario ve *Guardado* y el dato se
   pierde" está cerrada. `uploadFileToDrive` ya no inventa `fileUrl`.

---

## 7. Orden de ataque recomendado

**Fase 0 — Seguridad (1–2 días).** Cerrar el agujero: rama `STAFF_USER` en `/api/config`, y pasarle
`username` además de `role`. Blindar `GET /api/data` (lista negra de tablas sensibles + exigir
sesión). Rotar y purgar la key de Gemini de `CODIGO.js`. Hash de contraseñas.

**Fase 1 — RBAC completo (1 semana).** `USER_DB` a Supabase con `email`/`staffName`/`seller`/`dept`;
los 19 departamentos; `canSeeBancoJuntas`; ramas `JUANY_RODRIGUEZ` y `JESUS_CANTU` como
`role_overrides` (datos, no `if` por nombre); módulo `MY_SALES`; espejo `MY_TRACKER` de TONITA;
`isFieldEditable` validado en el backend.

**Fase 2 — Integridad (3–4 días).** Secuencia de Postgres para folios (mata la carrera del tracker y
la de WO de un golpe); eliminar `sequences.json`; completar `ABBR_MAP`; esquema versionado (Alembic)
incluyendo las 3 tablas WO faltantes.

**Fase 3 — Archivos (1 semana).** Supabase Storage para `uploadFileToDrive` + las 4 guardas de
35 MB. Desbloquea adjuntos en tracker, WO y banco, y habilita el archivado automático
`[Año]/[Mes]/[Cliente]`.

**Fase 4 — Los módulos cortos (1–2 semanas).** Con el esquema ya en la base, son endpoints CRUD:
Proyectos/Cascada (6 funciones, resolviendo el bug 🐛 de `apiFetchProjectTasks` por diseño),
Borradores (3), escrituras de Agenda/Hábitos (2), `apiFetchInfoBankData`, `apiFetchPPCData`,
`apiFetchCombinedCalendarData`, alta/baja de empleados (2), `apiLogout` con su registro.

**Fase 5 — Periferia (1 semana).** Scheduler (`autoUpdateQuoteMetrics` diario) y canal de correo
para los reportes de los agentes; las 3 reglas de productividad; persistir el contador de días.

**Transversal — Higiene.** Borrar `HOLTMONT-PYTHON-main/`, los 24 scripts de andamiaje y los
artefactos temporales; agregar `pytest`/`playwright`/`httpx` a `requirements.txt`.

**Y las 4 correcciones de UI de §2.1**, que son de minutos: el índice con coma (bug real), las
guardas de 35 MB, y una decisión sobre `defaultReqCotizacion` y el rediseño del paso 2 del PPC.
