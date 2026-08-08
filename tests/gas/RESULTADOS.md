# Resultados de pruebas — Migración Holtmont

> Generado automáticamente por `node tests/gas/run_tests.js` contra `CODIGO.js` con mocks de Google Apps Script.

**Total:** 87 · **Pasan:** 87 · **Fallan:** 0


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
| 1.4 | AA a los 15 días (límite del plan = 14) | ROJO | ROJO | ✅ PASA |

## 2. Ruteo y tablas (VENTAS)

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 2.1 | La tarea llega a la hoja del vendedor con sufijo (VENTAS) | 1 fila | 1 fila(s) | ✅ PASA |
| 2.1b | Antonia genera folio para la nueva cotización | folio no vacío | FOLIO="AV-1001" | ✅ PASA |
| 2.1c | El vendedor conserva su hoja (VENTAS) al guardar | 1 fila | 1 fila(s) | ✅ PASA |
| 2.2a | El sufijo (VENTAS) se purga: escribe en el tracker general | 1 fila en "EDUARDO MANZANARES" | 1 fila(s) | ✅ PASA |
| 2.2b | NO se escribe en la tabla de ventas del vendedor | 0 filas en "(VENTAS)" | 0 fila(s) | ✅ PASA |
| 2.2c | NO contamina la maestra de Antonia (reverse sync indebido) | 0 filas en ANTONIA_VENTAS | 0 fila(s) | ✅ PASA |
| 2.2d | internalUpdateTask también purga el sufijo (VENTAS) | general=1 / ventas=0 | general=1 / ventas=0 | ✅ PASA |
| 2.3a | Se redirige al tracker personal ANTONIA PINEDA LOPEZ | 1 fila en tracker personal | 1 fila(s) | ✅ PASA |
| 2.3b | NO se escribe en el core de ventas ANTONIA_VENTAS | 0 filas en ANTONIA_VENTAS | 0 fila(s) | ✅ PASA |
| 2.3c | El folio usa prefijo AP- (no AV-) | empieza con "AP-" | "AP-1001" | ✅ PASA |

## 3. Folios y prefijos

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 3.0 | La función generatePrefix está definida en CODIGO.js | function | function | ✅ PASA |
| 3.1 | Folio de JAIME_OLIVO inicia con JO- | JO-… | "JO-1001" | ✅ PASA |
| 3.1 | Folio de JESUS_CANTU inicia con JC- | JC-… | "JC-1001" | ✅ PASA |
| 3.1 | Folio de LUIS_CARLOS inicia con LC- | LC-… | "LC-1001" | ✅ PASA |
| 3.1 | Folio de ADMINISTRADOR inicia con LC- | LC-… | "LC-1001" | ✅ PASA |
| 3.1 | Folio de ANTONIA_VENTAS inicia con AV- | AV-… | "AV-1001" | ✅ PASA |
| 3.1 | Folio de RAMIRO_RODRIGUEZ inicia con RR- | RR-… | "RR-1001" | ✅ PASA |
| 3.1 | Folio de SEBASTIAN_PADILLA inicia con SP- | SP-… | "SP-1001" | ✅ PASA |
| 3.1 | Folio de TERESA_GARZA inicia con TG- | TG-… | "TG-1001" | ✅ PASA |
| 3.1 | Folio de MIGUEL_GALLARDO inicia con MG- | MG-… | "MG-1001" | ✅ PASA |
| 3.2 | generatePrefix("") retorna "PPC-" | PPC- | PPC- | ✅ PASA |

## 4. Gatekeeper / duplicidad / archivado

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 4.1a | 5 peticiones idénticas con el mismo _tempId insertan 1 sola fila | 1 fila | 1 fila(s) | ✅ PASA |
| 4.1b | El backend usa CacheService como Gatekeeper del _tempId (AGENTS.md §2) | al menos 1 llamada a CacheService | 10 llamadas | ✅ PASA |
| 4.1c | CODIGO.js referencia _tempId | sí | sí | ✅ PASA |
| 4.1d | index.html implementa el flag reactivo isSubmitting | > 0 ocurrencias | 45 ocurrencias | ✅ PASA |
| 4.2a | No se duplica la tarea: se sobrescribe la fila existente | 1 fila | 1 fila(s) | ✅ PASA |
| 4.2b | El comentario se escribe en la fila original (no en una copia) | COMENTARIO NUEVO DEL FRONTEND | COMENTARIO NUEVO DEL FRONTEND | ✅ PASA |
| 4.3a | AVANCE nativo 1 (celda porcentaje) se archiva | archivada | archivada | ✅ PASA |
| 4.3b | AVANCE "100%" (string del frontend) se archiva | archivada | archivada | ✅ PASA |
| 4.3c | ESTATUS = HECHO archiva la tarea | archivada | archivada | ✅ PASA |
| 4.3d | CUMPLIMIENTO = SI archiva la tarea | archivada | archivada | ✅ PASA |
| 4.3e | AVANCE "1" (1 %) NO debe interpretarse como 100 % (AGENTS.md §4) | activa | activa | ✅ PASA |
| 4.3f | Tarea con 40 % permanece activa (control) | activa | activa | ✅ PASA |

## 5. Papa Caliente y Reverse Sync

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 5.1a | Aparece la fase delegada en la hoja de ANGEL SALINAS | 1 fila (tracker o ventas) | tracker=1 / ventas=0 | ✅ PASA |
| 5.1b | El CONCEPTO delegado lleva la marca [Calculo y Diseño] | CONCEPTO … [Calculo y Diseño] | COTIZACION PLANTA [Calculo y Diseño] | ✅ PASA |
| 5.1c | MAP COT de la etapa CD pasa de ⚪ a 🔴 | 🔴 CD | 🟢 L \| 🔴 CD \| ⚪ EP \| ⚪ CI \| ⚪ EV \| ⚪ CEC \| ⚪ RCC | ✅ PASA |
| 5.1d | CODIGO.js implementa la lógica PROCESO_LOG / MAP COT | sí | sí | ✅ PASA |
| 5.2a | La tarea se archiva en la hoja de ANGEL SALINAS | archivada | archivada | ✅ PASA |
| 5.2b | La COTIZACION se inserta en la celda correcta de ANTONIA_VENTAS | URL del archivo | https://drive.google.com/cot_2025.pdf | ✅ PASA |
| 5.2c | PROCESO_LOG de Antonia marca la etapa como DONE | contiene DONE | [{"step":"CD","status":"DONE","assignee":"ANGEL SALINAS","timestamp":<ts>,"dateStr":"<fecha>"}] | ✅ PASA |
| 5.2d | MAP COT de CD cambia a 🟢 | 🟢 CD | 🟢 L \| 🟢 CD \| ⚪ EP \| ⚪ CI \| ⚪ EV \| ⚪ CEC \| ⚪ RCC | ✅ PASA |
| 5.3a | El ESTATUS de Antonia NO se sobrescribe con el del trabajador | EN PROCESO | EN PROCESO | ✅ PASA |
| 5.3b | El AVANCE de Antonia NO se sobrescribe con 100 | 40 | 40 | ✅ PASA |
| 5.3c | La cotización de Antonia NO se auto-archiva por el avance del trabajador | activa | activa | ✅ PASA |

## 6. Métricas, Gemini y Webhook

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 6.1a | runQuoteMetricsAgent está definida en CODIGO.js | function | function | ✅ PASA |
| 6.1b | autoUpdateQuoteMetrics está definida en CODIGO.js | function | function | ✅ PASA |
| 6.1c | apiFetchQuoteAgentMetrics está definida en CODIGO.js | function | function | ✅ PASA |
| 6.2a | API de configuración de GEMINI_API_KEY (apiSaveGeminiKey/apiCheckGeminiKey) | function | function | ✅ PASA |
| 6.2b | Prompt de métricas con "recomendación operativa" | presente en CODIGO.js | presente | ✅ PASA |
| 6.2c | apiGetLastAgentReport (resumen de ~180 palabras al dashboard) | function | function | ✅ PASA |
| 6.3a | Se dispara el webhook al asignar un nuevo RESPONSABLE | ≥ 1 llamada UrlFetchApp | 1 llamadas | ✅ PASA |
| 6.3b | CODIGO.js contiene el NotifierService / endpoint de Make.com | presente | presente | ✅ PASA |
| 6.3c | La fecha del payload usa .toISOString() (AGENTS.md §5) | presente | presente | ✅ PASA |
| 6.3d | USER_DB mapea correos corporativos @holtmont.com | > 0 correos | 13 correos | ✅ PASA |

## 7. Contrato index.html ↔ CODIGO.js

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 7.1 | Funciones google.script.run sin implementación en CODIGO.js | 0 faltantes | 0 faltantes | ✅ PASA |
| 7.1c | Métodos que el frontend llama y el adaptador no define | 0 ausentes | 0 ausentes (41 verificados) | ✅ PASA |
| | _Un método ausente lanza TypeError SINCRONICO: withFailureHandler no lo captura, los flags _isSaving/isSubmitting quedan en true y se bloquea todo guardado posterior_ | | | |
| 7.1b | Métodos de guardado del adaptador FastAPI que siguen siendo stubs | 0 stubs | 0 stubs | ✅ PASA |
| | _Un stub responde {success:true} sin persistir nada en Supabase/FastAPI_ | | | |
| 7.1d | Métodos del adaptador que descartan argumentos del frontend | 0 | 0 | ✅ PASA |
| | _Un parámetro no declarado se pierde en silencio: el backend nunca recibe el dato_ | | | |
| 7.2 | La respuesta incluye res.data con la tarea actualizada | res.data presente | presente | ✅ PASA |

## 8. Supabase Sync (escritura doble)

| # | Prueba | Esperado | Obtenido | Resultado |
|---|--------|----------|----------|-----------|
| 8.1 | Clave de identidad de fila para los 10 casos reales | 0 fallos | 0 fallos | ✅ PASA |
| | _JO-0009 vive en 10 trackers: cada copia necesita su propia clave_ | | | |
| 8.2 | Papa Caliente: JO-0009 no se colapsa en una sola fila | 3 claves distintas | 3 distintas | ✅ PASA |
| 8.3 | AVANCE normalizado a escala 0-100 sin confundir 1 con "1" | 0 fallos | 0 fallos | ✅ PASA |
| | _Colapsar ambos casos archivaria como terminadas las tareas al 1%_ | | | |
| 8.4 | El espejo queda inerte mientras no se configure | cero peticiones | 0 peticiones, skipped=true | ✅ PASA |
| 8.5 | Upsert a tasks con la clave y el AVANCE correctos | on_conflict=dedupe_key, avance=100 | envios=1, key=JAIME OLIVO::JO-0009, avance=100 | ✅ PASA |
| 8.6 | Ruteo por tipo de hoja y monto limpiado | quotes, folio, monto=1500.5 | quotes=1, tasks=0, monto=1500.5 | ✅ PASA |
| 8.7 | Se resuelve la primera persona y se conserva el texto completo | uuid-ramiro | assignee_id=uuid-ramiro | ✅ PASA |
| | _Nunca guardar el string compuesto como si fuera una persona_ | | | |
| 8.8 | Con la red caída la tarea se guarda igual | success=true y 1 fila en la hoja | success=true, filas=1 | ✅ PASA |
| | _INVARIANTE: mejor perder una réplica que una tarea_ | | | |
| 8.9 | Auditoría espejada con fecha ISO | 1 envío con usuario y accion | envios=1, usuario=LUIS_CARLOS, fecha=2026-08-08T21:56:35.395Z | ✅ PASA |
| 8.11 | Estatus canónico en la escritura | 0 fallos | 0 fallos | ✅ PASA |
| | _Sin esto la columna vuelve a acumular variantes en cada captura_ | | | |
| 8.12 | Un valor no reconocido pasa tal cual | se conserva | 'EN LICITACION'->"EN LICITACION", 'RAM'->"RAM" | ✅ PASA |
| | _Si el equipo empieza a usar un estatus nuevo, tirarlo perderia el dato_ | | | |
| 8.13 | El estado terminal se conserva tras normalizar | 0 cambios | 0 cambios | ✅ PASA |
| | _Un alias mal mapeado archivaria o desarchivaria tareas_ | | | |
| 8.14 | La errata ASIGANDA llega como ASIGNADO | ASIGNADO | "ASIGNADO" | ✅ PASA |
| 8.15 | Sin estatus se envía cadena vacía, no null | "" | "" | ✅ PASA |
| | _tasks.status tiene NOT NULL: un null aborta el upsert entero_ | | | |
| 8.10 | SUPABASE_URL/KEY solo por Propiedades del Script | sin credenciales en CODIGO.js | sin credenciales | ✅ PASA |
