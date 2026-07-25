# Resultados de pruebas — Migración Holtmont

> Generado automáticamente por `node tests/gas/run_tests.js` contra `CODIGO.js` con mocks de Google Apps Script.

**Total:** 69 · **Pasan:** 20 · **Fallan:** 49


## 1. Semáforo / Formato condicional

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 1.0 | Formato condicional aplicado a hoja habilitada | true + reglas > 0 | true + 9 reglas | ✅ PASA |
| 1.0b | LOG_SISTEMA excluida del semáforo | false | false | ✅ PASA |
| 1.1 | Clasificación A — hoy (0 días) | VERDE | VERDE | ✅ PASA |
| 1.1 | Clasificación A — 1 día | VERDE | VERDE | ✅ PASA |
| 1.1 | Clasificación A — 2 días | AMARILLO | AMARILLO | ✅ PASA |
| 1.1 | Clasificación A — 4 días | ROJO | ROJO | ✅ PASA |
| 1.2 | Clasificación AA — 11 días | VERDE | VERDE | ✅ PASA |
| 1.2 | Clasificación AA — 13 días | AMARILLO | AMARILLO | ✅ PASA |
| 1.2 | Clasificación AA — 16 días | ROJO | ROJO | ✅ PASA |
| 1.3 | Clasificación AAA — 24 días | VERDE | VERDE | ✅ PASA |
| 1.3 | Clasificación AAA — 27 días | AMARILLO | AMARILLO | ✅ PASA |
| 1.3 | Clasificación AAA — 32 días | ROJO | ROJO | ✅ PASA |
| 1.4 | AA a los 15 días (límite del plan = 14) | ROJO | AMARILLO | ❌ FALLA |
| | _CODIGO.js usa límite 15 (addRulePair("AA", 15, 3)), el plan documenta 14_ | | | |

## 2. Ruteo y tablas (VENTAS)

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 2.1 | La tarea llega a la hoja del vendedor con sufijo (VENTAS) | 1 fila | 1 fila(s) | ✅ PASA |
| 2.1b | Antonia genera folio para la nueva cotización | folio no vacío | FOLIO="1001" | ✅ PASA |
| 2.2a | El sufijo (VENTAS) se purga: escribe en el tracker general | 1 fila en "EDUARDO MANZANARES" | 0 fila(s) | ❌ FALLA |
| 2.2b | NO se escribe en la tabla de ventas del vendedor | 0 filas en "(VENTAS)" | 1 fila(s) | ❌ FALLA |
| 2.2c | NO contamina la maestra de Antonia (reverse sync indebido) | 0 filas en ANTONIA_VENTAS | 1 fila(s) | ❌ FALLA |
| 2.2d | internalUpdateTask también purga el sufijo (VENTAS) | general=1 / ventas=0 | general=0 / ventas=1 | ❌ FALLA |
| 2.3a | Se redirige al tracker personal ANTONIA PINEDA LOPEZ | 1 fila en tracker personal | 0 fila(s) | ❌ FALLA |
| 2.3b | NO se escribe en el core de ventas ANTONIA_VENTAS | 0 filas en ANTONIA_VENTAS | 1 fila(s) | ❌ FALLA |
| 2.3c | El folio usa prefijo AP- (no AV-) | empieza con "AP-" | "1001" | ❌ FALLA |

## 3. Folios y prefijos

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 3.0 | La función generatePrefix está definida en CODIGO.js | function | undefined | ❌ FALLA |
| 3.1 | Folio de JAIME_OLIVO inicia con JO- | JO-… | (folio vacío) | ❌ FALLA |
| 3.1 | Folio de JESUS_CANTU inicia con JC- | JC-… | (folio vacío) | ❌ FALLA |
| 3.1 | Folio de LUIS_CARLOS inicia con LC- | LC-… | (folio vacío) | ❌ FALLA |
| 3.1 | Folio de ADMINISTRADOR inicia con LC- | LC-… | (folio vacío) | ❌ FALLA |
| 3.1 | Folio de ANTONIA_VENTAS inicia con AV- | AV-… | "1001" | ❌ FALLA |
| 3.1 | Folio de RAMIRO_RODRIGUEZ inicia con RR- | RR-… | (folio vacío) | ❌ FALLA |
| 3.1 | Folio de SEBASTIAN_PADILLA inicia con SP- | SP-… | (folio vacío) | ❌ FALLA |
| 3.1 | Folio de TERESA_GARZA inicia con TG- | TG-… | (folio vacío) | ❌ FALLA |
| 3.1 | Folio de MIGUEL_GALLARDO inicia con MG- | MG-… | (folio vacío) | ❌ FALLA |
| 3.2 | generatePrefix("") retorna "PPC-" | PPC- | (función inexistente) | ❌ FALLA |

## 4. Gatekeeper / duplicidad / archivado

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 4.1a | 5 peticiones idénticas con el mismo _tempId insertan 1 sola fila | 1 fila | 5 fila(s) | ❌ FALLA |
| 4.1b | El backend usa CacheService como Gatekeeper del _tempId (AGENTS.md §2) | al menos 1 llamada a CacheService | 0 llamadas | ❌ FALLA |
| 4.1c | CODIGO.js referencia _tempId | sí | no (0 ocurrencias) | ❌ FALLA |
| 4.1d | index.html implementa el flag reactivo isSubmitting | > 0 ocurrencias | 45 ocurrencias | ✅ PASA |
| 4.2a | No se duplica la tarea: se sobrescribe la fila existente | 1 fila | 2 fila(s) | ❌ FALLA |
| 4.2b | El comentario se escribe en la fila original (no en una copia) | COMENTARIO NUEVO DEL FRONTEND | (vacío) | ❌ FALLA |
| 4.3a | AVANCE nativo 1 (celda porcentaje) se archiva | archivada | archivada | ✅ PASA |
| 4.3b | AVANCE "100%" (string del frontend) se archiva | archivada | archivada | ✅ PASA |
| 4.3c | ESTATUS = HECHO archiva la tarea | archivada | activa | ❌ FALLA |
| 4.3d | CUMPLIMIENTO = SI archiva la tarea | archivada | activa | ❌ FALLA |
| 4.3e | AVANCE "1" (1 %) NO debe interpretarse como 100 % (AGENTS.md §4) | activa | archivada | ❌ FALLA |
| 4.3f | Tarea con 40 % permanece activa (control) | activa | activa | ✅ PASA |

## 5. Papa Caliente y Reverse Sync

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 5.1a | Aparece la fase delegada en la hoja de ANGEL SALINAS | 1 fila (tracker o ventas) | tracker=0 / ventas=0 | ❌ FALLA |
| 5.1b | El CONCEPTO delegado lleva la marca [Calculo y Diseño] | CONCEPTO … [Calculo y Diseño] | (sin fila) | ❌ FALLA |
| 5.1c | MAP COT de la etapa CD pasa de ⚪ a 🔴 | 🔴 CD | ⚪ CD | ❌ FALLA |
| 5.1d | CODIGO.js implementa la lógica PROCESO_LOG / MAP COT | sí | no (0 ocurrencias en CODIGO.js) | ❌ FALLA |
| 5.2a | La tarea se archiva en la hoja de ANGEL SALINAS | archivada | archivada | ✅ PASA |
| 5.2b | La COTIZACION se inserta en la celda correcta de ANTONIA_VENTAS | URL del archivo | https://drive.google.com/cot_2025.pdf | ✅ PASA |
| 5.2c | PROCESO_LOG de Antonia marca la etapa como DONE | contiene DONE | [] | ❌ FALLA |
| 5.2d | MAP COT de CD cambia a 🟢 | 🟢 CD | 🔴 CD | ❌ FALLA |
| 5.3a | El ESTATUS de Antonia NO se sobrescribe con el del trabajador | EN PROCESO | DONE | ❌ FALLA |
| 5.3b | El AVANCE de Antonia NO se sobrescribe con 100 | 40 | 100 | ❌ FALLA |
| 5.3c | La cotización de Antonia NO se auto-archiva por el avance del trabajador | activa | archivada (venta cerrada) | ❌ FALLA |

## 6. Métricas, Gemini y Webhook

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 6.1a | runQuoteMetricsAgent está definida en CODIGO.js | function | undefined | ❌ FALLA |
| 6.1b | autoUpdateQuoteMetrics está definida en CODIGO.js | function | undefined | ❌ FALLA |
| 6.1c | apiFetchQuoteAgentMetrics está definida en CODIGO.js | function | undefined | ❌ FALLA |
| 6.2a | API de configuración de GEMINI_API_KEY (apiSaveGeminiKey/apiCheckGeminiKey) | function | undefined | ❌ FALLA |
| 6.2b | Prompt de métricas con "recomendación operativa" | presente en CODIGO.js | ausente | ❌ FALLA |
| 6.2c | apiGetLastAgentReport (resumen de ~180 palabras al dashboard) | function | undefined | ❌ FALLA |
| 6.3a | Se dispara el webhook al asignar un nuevo RESPONSABLE | ≥ 1 llamada UrlFetchApp | 0 llamadas | ❌ FALLA |
| 6.3b | CODIGO.js contiene el NotifierService / endpoint de Make.com | presente | ausente | ❌ FALLA |
| 6.3c | La fecha del payload usa .toISOString() (AGENTS.md §5) | presente | ausente (0 ocurrencias) | ❌ FALLA |
| 6.3d | USER_DB mapea correos corporativos @holtmont.com | > 0 correos | 0 correos | ❌ FALLA |

## 7. Contrato index.html ↔ CODIGO.js

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 7.1 | Funciones google.script.run sin implementación en CODIGO.js | 0 faltantes | 11: apiCheckGeminiKey, apiFetchInfoBankCompanies, apiFetchQuoteAgentMetrics, apiGetLastAgentReport, apiLogDateChange, apiResyncDirectory, apiSaveGeminiKey, apiWriteQuoteMetricsToSheet, runPaperclipAgents, runQuoteMetricsAgent, runTrackerProductivityAgent | ❌ FALLA |
| 7.1b | Métodos de guardado del adaptador FastAPI que siguen siendo stubs | 0 stubs | 5: apiSaveTrackerBatch, apiUpdateTask, apiUpdatePPCV3, apiFetchWeeklyPlanData, apiFetchSalesHistory | ❌ FALLA |
| | _Un stub responde {success:true} sin persistir nada en Supabase/FastAPI_ | | | |
| 7.2 | La respuesta incluye res.data con la tarea actualizada | res.data presente | ausente ({"success":true,"message":"Guardado exitoso"}) | ❌ FALLA |
