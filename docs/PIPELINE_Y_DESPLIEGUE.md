# Pipeline, QA y Despliegue

Cómo se prueba (QA) y cómo se despliega Holtmont Workspace en su estado actual.

---

## 1. Estrategia de QA

El proyecto **no** tiene un framework de testing formal (Jest, Mocha) ni CI automatizado en GitHub
Actions. La verificación se hace en **dos planos complementarios**:

1. **Pruebas locales con Node** (`test_*.js`, `check_*.js` en la raíz): ejecutan la lógica de
   `CODIGO.js`/`index.html` fuera de GAS, usando `vm` + *stubs* de los servicios de Google.
2. **Pruebas dentro de Apps Script** (`test_*` en `CODIGO.js`): funciones ejecutables desde el editor
   de GAS que validan flujos end-to-end contra el entorno real (Sheets de prueba).

### 1.1 Pruebas locales obligatorias (antes de commitear)

Según `AGENTS.md`, tras cualquier modificación:

```bash
node test_departments.js   # Organigrama: USER_DB + INITIAL_DIRECTORY == organigrama oficial
node check_html2.js        # Sintaxis del frontend (index.html). Respaldo de check_html.js
```

`test_departments.js` extrae los bloques `INITIAL_DIRECTORY` y `USER_DB` de `CODIGO.js` con un
parser de balanceo de brackets, los evalúa en un sandbox `vm` y los compara contra el organigrama
oficial transcrito. Sale con código ≠ 0 si algo no coincide (apto para usarse como gate).

### 1.2 Catálogo de pruebas locales (Node)

| Grupo | Archivos | Qué valida |
|---|---|---|
| **Organigrama** | `test_departments.js` | `USER_DB`/`INITIAL_DIRECTORY` vs. organigrama oficial. |
| **Sintaxis FE** | `check_html.js`, `check_html2.js`, `check_html_fix.js` | Parseo/estructura de `index.html` (usa `acorn`/`jsdom`). |
| **Anti-duplicación** | `check_duplication.js`, `test_deduplication*.js`, `test_duplication_issue*.js` | Deduplicación de filas y Gatekeeper. |
| **Parseo de AVANCE / 100%** | `test_avance_logic*.js`, `test_parse_*`, `test_is_complete*.js`, `test_empty_string*` | Interpretación de `AVANCE`/`CUMPLIMIENTO` (incluye el caso `1`=100% y strings vacíos). |
| **Distribución/enrutamiento** | `test_distribution*.js`, `test_distribution_subagent*.js`, `test_subagent.js` | Reparto de tareas a hojas destino. |
| **Reverse Sync / Papa Caliente** | `test_reverse_sync.js`, `test_reverse_is_complete.js`, `test_remove_worker.js` | Sincronización bidireccional `AV-` y delegación lateral. |
| **Ventas / estatus** | `test_parse_estatus.js`, `test_parse_cpl_si.js`, `test_case.js` | Normalización de estatus/cumplimiento. |
| **Internos** | `check_internal.js`, `test_script.js` | Utilidades varias. |

Ejecución individual: `node <archivo>.js`. No hay runner agregado; se corren los relevantes al cambio.

### 1.3 Pruebas dentro de Apps Script (end-to-end)

Ejecutables desde el editor de GAS (menú **Ejecutar**). Cubren flujos completos contra Sheets:

| Función | Cubre |
|---|---|
| `test_DataIntegrity` | Integridad de lectura/escritura de hojas. |
| `test_Generacion_MAP_COT` | Generación de columna `MAP COT` en ventas. |
| `test_Security_Filter_AllowedBase` | Filtro de enrutamiento / seguridad de destino. |
| `test_Flujo_Completo_Delegacion_y_Sincronizacion` | Delegación + sincronización completa. |
| `test_Cierre_Terminal_RCC` | Cierre de etapa RCC (Revisión Cotización Cliente). |
| `test_SavePPCV3_Flow` | Alta y distribución PPC. |
| `test_WorkOrder_Generation` | Generación de folios de Work Order. |
| `test_Directory_CRUD` | Alta/baja en el directorio. |
| `test_ReverseSync_Flow` | Reverse Sync de tareas `AV-`. |
| `test_NumericSequence_Generation` | Secuencias numéricas por prefijo. |
| `test_Antonia_Distribution_Manual` | Ley de Antonia (no mezclar ventas). |
| `test_SystemConfig_Label` | Etiquetas de módulos por rol/usuario. |
| `test_avance_100_bug` | Regresión del bug de `AVANCE`=100%. |
| `testIntegracionOutlook` | Envío real de un evento de prueba a Outlook vía Make.com. |

### 1.4 Feedback loop recomendado

```
editar CODIGO.js / index.html
   │
   ├─ node test_departments.js         (si tocaste USER_DB/INITIAL_DIRECTORY)
   ├─ node check_html2.js              (si tocaste index.html)
   ├─ node test_<área afectada>.js     (deduplicación, avance, distribución, reverse sync…)
   │
   ├─ clasp push  → editor GAS
   ├─ ejecutar test_* relevante en GAS (Sheets de prueba)
   └─ validar en la Web App de staging
```

---

## 2. Control de calidad en Pull Requests

El repositorio incluye una plantilla obligatoria en
[`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md). **Todo PR** debe responder,
**en español**, las 5 preguntas de control de calidad:

1. ¿Tiene un feedback loop que verifique el código generado?
2. ¿Cómo se hace el rollback si falla?
3. ¿Tiene observabilidad en producción?
4. ¿Escala si el equipo crece?
5. ¿Tu equipo lo mantiene sin ti?

Estas preguntas son un gate cualitativo definido en `AGENTS.md §8`. La descripción y comentarios del
PR deben redactarse siempre en español.

---

## 3. Flujo de despliegue

No hay pipeline de CI/CD automatizado. El despliegue es **manual**, con dos caminos equivalentes.

### 3.1 Despliegue con `clasp` (recomendado)

```bash
# Prerrequisitos: clasp instalado y autenticado (clasp login), proyecto vinculado (.clasp.json)

# 1. Verificación local
node test_departments.js
node check_html2.js

# 2. Empujar código al proyecto de Apps Script
clasp push

# 3. Crear/actualizar la implementación de Web App
clasp deploy --description "vXYZ: descripción del cambio"
#    o gestionar versiones desde el editor de GAS
```

> Recuerda el mapeo: `CODIGO.js` = archivo de servidor; `index.html` debe existir como **`Index`**
> en el editor (lo referencia `HtmlService.createTemplateFromFile('Index')`).

### 3.2 Despliegue desde el editor de Apps Script

1. **Extensiones → Apps Script** en el Spreadsheet contenedor.
2. Pegar cambios y guardar.
3. **Implementar → Administrar implementaciones → Editar (lápiz) → Nueva versión**.
4. Confirmar. La URL `/exec` de la Web App sirve la nueva versión.

### 3.3 Configuración post-despliegue (una vez)

- Definir `GEMINI_API_KEY` en Propiedades del script.
- Actualizar `WEBHOOK_OUTLOOK_URL` con el escenario real de Make.com.
- Instalar triggers: `setupDailyQuoteMetricsTrigger()` (07:00) e `instalarDisparador()` (01:00).
- Ejecutar `apiResyncDirectory()` como ADMIN para materializar `DB_DIRECTORY` y trackers faltantes.

---

## 4. Observabilidad en producción

| Señal | Fuente |
|---|---|
| Errores de ejecución | **Stackdriver / Cloud Logging** (`exceptionLogging: "STACKDRIVER"` en `appsscript.json`). |
| Logs de ejecución | `console.log`/`console.error` en el backend → panel **Ejecuciones** del editor GAS. |
| Auditoría de negocio | Hoja `LOG_SISTEMA` (`registrarLog(user, action, details)`): login, altas, actualizaciones, `ERROR_CRITICO_PPC`. |
| Reportes programados | Correos de `_sendAgentEmail` / `_sendTrackerProductivityEmail`; último estado en Script Property `LAST_AGENT_RUN`. |
| Integraciones | Códigos HTTP de `NotifierService.sendToOutlook` (200/202 OK) registrados en consola. |

---

## 5. Rollback

| Escenario | Acción |
|---|---|
| Regresión en la Web App | Editor GAS → **Administrar implementaciones** → seleccionar versión anterior. |
| Cambio de código | `git revert <commit>` y `clasp push` (o restaurar desde `CODIGO.js.bak`/`.orig` si aplica). |
| Datos corruptos en una hoja | Restaurar desde el **historial de versiones de Google Sheets** (Archivo → Historial). |
| Directorio inconsistente | Re-ejecutar `apiResyncDirectory()`. |

---

## 6. Escalabilidad y mantenimiento (consideraciones)

- **Escala:** Google Sheets impone límites prácticos (celdas por hoja, cuotas de ejecución de GAS,
  tiempo máximo por ejecución ~6 min). El sistema mitiga con lectura/escritura en lote (`setValues`)
  y candados. Para equipos mucho mayores, considerar migrar la capa de datos a una base real.
- **Mantenibilidad:** el organigrama y credenciales viven en código (`USER_DB`, `INITIAL_DIRECTORY`)
  y se validan con `test_departments.js`; el contrato de API está en
  [`openapi.yaml`](openapi.yaml) y [`API_CONTRACT.md`](API_CONTRACT.md). `AGENTS.md` fija las reglas
  de negocio que no deben romperse.

### Riesgos conocidos / deuda técnica

- Contraseñas en texto plano dentro de `CODIGO.js` (`USER_DB`). Rotarlas o migrarlas a
  `PropertiesService`/hashing es una mejora pendiente.
- `WEBHOOK_OUTLOOK_URL` hardcodeado; conviene moverlo a Script Properties.
- Ausencia de CI: las pruebas locales existen pero no corren automáticamente en cada PR. Un
  workflow de GitHub Actions que ejecute `node test_departments.js && node check_html2.js` cerraría
  esta brecha.
