# Pruebas unitarias e integración del backend GAS (`CODIGO.js`)

Suite automatizada que ejecuta el plan de pruebas de la migración contra el
código **real** de `CODIGO.js`, cargándolo en un contexto de Node con mocks en
memoria de los servicios de Google Apps Script (`SpreadsheetApp`, `LockService`,
`PropertiesService`, `CacheService`, `Utilities`, `UrlFetchApp`), tal como pide
`AGENTS.md` §6 ("Mocking Local").

## Ejecución

```bash
node tests/gas/run_tests.js
```

- Sin dependencias externas (solo Node ≥ 18, módulo `vm` de la librería estándar).
- Imprime una tabla por bloque y escribe el reporte en `tests/gas/RESULTADOS.md`.
- Código de salida `0` si todo pasa, `1` si hay fallos (apto para CI).

## Archivos

| Archivo | Contenido |
|---|---|
| `gas_mocks.js` | Hoja de cálculo en memoria + servicios GAS simulados y `createEnv()` |
| `formula_eval.js` | Evaluador de las fórmulas `whenFormulaSatisfied()` del semáforo |
| `run_tests.js` | Los 7 bloques de pruebas y el generador del reporte |
| `RESULTADOS.md` | Reporte generado en la última corrida (no editar a mano) |

## Bloques cubiertos

1. **Semáforo**: colores reales por `CLASIFICACION` (A / AA / AAA) evaluando las
   fórmulas condicionales que genera `applyTrafficLightToSheet`, más exclusión
   de hojas internas (`LOG_`, `DB_`, …).
2. **Ruteo (VENTAS)**: "La Ley de Antonia" — purga del sufijo `(VENTAS)` para
   usuarios que no son Toñita y protección del core de ventas.
3. **Folios y prefijos**: prefijos por usuario (`JO-`, `JC-`, `LC-`, `AV-`, …),
   fallback dinámico por iniciales y fallback seguro `PPC-`.
4. **Gatekeeper**: anti-duplicación por `_tempId`, recuperación de filas sin
   folio por `CONCEPTO`+`FECHA`+`RESPONSABLE` y auto-archivado a
   `TAREAS REALIZADAS`.
5. **Papa Caliente / Reverse Sync**: delegación de fases, sincronización inversa
   hacia `ANTONIA_VENTAS` y prevención de cierre prematuro de la venta.
6. **Métricas**: agente de KPIs de cotizaciones, integración Gemini y webhook a
   Make.com/Outlook (incluida la exigencia de `.toISOString()`).
7. **Contrato**: funciones que `index.html` invoca vía `google.script.run` y que
   deben existir en `CODIGO.js`, más el estado del adaptador de migración
   `api_service.js`.

## Cómo leer los fallos

Un fallo significa **una de dos cosas**, y el campo *Obtenido* del reporte lo
distingue:

- `undefined` / `0 ocurrencias` / `(función inexistente)` → **funcionalidad no
  migrada todavía** a `CODIGO.js` (existe en el frontend o en el plan, no en el
  backend).
- Un valor concreto distinto del esperado (p. ej. `ESTATUS = DONE` cuando se
  esperaba `EN PROCESO`) → **defecto de comportamiento** en código que sí existe.

## Paridad con el stack de Python

La misma lógica vive en `api/services/tracker_rules.py` (motor puro) y se
expone por FastAPI desde `api/main.py` a través de `api/services/tracker_store.py`.
Sus pruebas espejo no requieren Supabase ni credenciales:

```bash
python -m pytest tests/test_tracker_rules.py   # reglas de negocio (paridad con CODIGO.js)
python -m pytest tests/test_api_contract.py    # index.html -> api_service.js -> api/main.py
```

`test_api_contract.py` analiza estáticamente `api/main.py` y `api_service.js`,
por lo que detecta endpoints faltantes o métodos del adaptador que vuelvan a
convertirse en stubs sin necesidad de levantar el servidor.
