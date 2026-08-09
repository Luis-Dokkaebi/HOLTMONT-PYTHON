# Flujo de Papa Caliente

Cómo se reparte una cotización por fases entre varias personas, qué escribe cada paso y
dónde está la evidencia de que funciona.

La traza ejecutable que respalda este documento es
[`verification/verify_papa_caliente.py`](../verification/verify_papa_caliente.py), y la
prueba que la vigila es `tests/test_flujo_papa_caliente_e2e.py`.

---

## 1. Qué resuelve

Una cotización de la tabla de ventas no la trabaja una sola persona. Pasa por siete fases
(`PROCESS_STEPS`) y en cada una Toñita delega el trabajo a quien toque:

| Id | Fase |
| --- | --- |
| `L` | Levantamiento |
| `CD` | Calculo y Diseño |
| `EP` | Elaboracion Presupuesto |
| `CI` | Cotizacion Interna |
| `EV` | Estrategia Ventas |
| `CEC` | Cotizacion Enviada al cliente |
| `RCC` | Revision de Cotizacion Cliente |

La cotización se queda en la tabla de ventas y en la tabla de cada trabajador aparece una
**microtarea** con la fase marcada en el CONCEPTO (`COTIZAR NAVE [Calculo y Diseño]`).

**La diferencia con una asignación normal**: asignar una actividad la delega entera, y el
100 % de quien la recibe la archiva en las dos tablas. La papa caliente delega **una fase**,
y el 100 % de una fase no cierra la venta — solo pinta esa fase de verde, y únicamente
cuando terminaron *todos* sus asignados.

---

## 2. El recorrido de un guardado

Entrada: `POST /api/legacy/saveTrackerBatch` → `tracker_store.save_tracker_batch`
(`api/services/tracker_store.py:537`).

1. **¿Se puede delegar?** `apply_hot_potato` consulta `bloqueo_de_fase`
   (`api/services/asignacion.py:419`). Si hay una fase anterior abierta, lanza `FaseEnCurso`
   y el guardado devuelve `{success: false, message}` **sin escribir nada** — guardar medio
   lote dejaría el proceso en un estado que el timeline no sabe pintar.
2. **Se abre el log.** Una entrada `IN_PROGRESS` por persona en `PROCESO_LOG`
   (`upsert_proceso_log_entry`), y el `MAP COT` se recalcula con `build_map_cot`.
3. **Se reparte.** Una fila por trabajador en su propia partición de `tasks`, con
   `ESTATUS = ASIGNADO`, avance vacío y la fase marcada en el CONCEPTO. Se escribe con
   `como_copia=True` para que cada copia tenga clave propia por hoja
   (`clave_de_copia` → `"<hoja>::<folio>"`).
4. **El trabajador cierra.** Al guardar su microtarea al 100 %, el reverse sync
   (`build_reverse_sync_payload`, `api/services/tracker_rules.py:702`) devuelve a la maestra
   **solo** `PROCESO_LOG` y `MAP COT`. `AVANCE`, `ESTATUS`, `CUMPLIMIENTO` y el CONCEPTO
   marcado quedan bloqueados (`FASE_BLOCKED_KEYS`).
5. **El verde.** `build_map_cot` pinta 🟢 una fase solo cuando **todas** sus entradas están
   en `DONE`. Hasta entonces, 🔴.

El disparo del reverse sync es por **prefijo de folio**, no por nombre de hoja: `AV-` vuelve
a `ANTONIA_VENTAS` y `AP-` al tracker personal de Antonia Pineda, desde cualquier hoja de
origen (`_hoja_maestra_de_folio`).

---

## 3. Los dos caminos no se pisan

La papa caliente y la asignación normal comparten tabla y folio, así que hay tres puertas
que las mantienen separadas. Las tres preguntan lo mismo —`es_delegacion_de_fase`,
`api/services/asignacion.py:139`— y todas responden por la marca de fase en el CONCEPTO:

| Camino | Qué hace con una microtarea | Por qué |
| --- | --- | --- |
| `destinos_espejo` | devuelve `[]` | su reparto es el de `apply_hot_potato`, no el espejo |
| `campos_sincronizables` | devuelve `None` | las copias de una fase comparten folio: propagar el 100 % de uno lo pondría encima del trabajo del otro |
| `_retirar_copias_huerfanas` | la salta | cambiar el responsable de una cotización no puede borrar el trabajo ya repartido entre fases |

---

## 4. La evidencia

```bash
./venv/bin/python verification/verify_papa_caliente.py           # traza legible
./venv/bin/python verification/verify_papa_caliente.py --json    # traza en JSON
./venv/bin/python -m pytest tests/test_flujo_papa_caliente_e2e.py -q
```

El trazador encadena seis guardados reales contra `MemoryEngine` —cada uno leyendo el
estado que dejó el anterior— e imprime el estado de la base después de cada uno:

| Paso | Qué comprueba |
| --- | --- |
| 0 | la cotización existe sola, sin log ni microtareas |
| 1 | delegar CD a dos personas crea dos microtareas con clave propia |
| 2 | delegar EP con CD abierta se rechaza **y no escribe nada** |
| 3 | el cierre de uno no pinta la fase de verde |
| 4 | con los dos en DONE, 🟢 CD — y la cotización sigue al 0 % / EN PROCESO |
| 5 | cerrada CD, EP ya se delega |

Al final comprueba cinco invariantes contra el estado de la base: identidad propia por
copia, el 100 % de una fase no cierra la cotización, la maestra no hereda el concepto
marcado, las microtareas no se sincronizan entre sí, y la papa caliente no pasa por el
espejo de asignaciones.

---

## 5. Hallazgo abierto: la copia delegada y el guardado del trabajador usan claves distintas

**Estado: sin corregir.** Se documenta aquí porque arreglarlo cambia la regla de identidad
de fila y eso toca las 4.626 filas migradas — es una decisión del dueño, no un ajuste.

`TaskRepository.resolver_clave` (`backend/repositories/tasks.py:171`) decide la clave según
quién escribe:

```
resolver_clave("AV-3250", "MIGUEL GALLARDO", como_copia=True)   -> 'MIGUEL GALLARDO::AV-3250'
resolver_clave("AV-3250", "MIGUEL GALLARDO", como_copia=False)  -> 'AV-3250'
resolver_clave("AV-3250", "MIGUEL GALLARDO", como_copia=True)   -> 'AV-3250'   # tras la anterior
```

La delegación pide `como_copia=True` y obtiene la clave por hoja. Pero cuando el trabajador
guarda su propio avance, `save_tracker_batch` llama a `_persist_batch`
(`api/services/tracker_store.py:590`) **sin** `como_copia`, y como `AV-` es prefijo de
secuencia global sale el folio a secas. Resultado: dos filas para la misma microtarea en la
misma hoja.

Consecuencias visibles en la tabla del trabajador:

1. La fase que ya cerró le sigue apareciendo activa y al 0 %, porque su cierre se fue a otra
   fila.
2. Una segunda delegación a la misma persona cae sobre la fila suelta y **hereda su avance
   al 100 %**: la fase nueva nace archivada bajo TAREAS REALIZADAS y nunca aparece como
   pendiente.

El timeline de la cotización **no** se ve afectado: el reverse sync se resuelve por folio y
el `PROCESO_LOG` queda correcto en los seis pasos de la traza. Por eso el síntoma es
silencioso — el mapa de la cotización dice la verdad mientras la tabla del trabajador no.

Reproducción, en el paso 3 de la traza:

```
MIGUEL GALLARDO::AV-3250 | MIGUEL GALLARDO | COTIZAR NAVE [Calculo y Diseño] | avance: 0     | ASIGNADO
AV-3250                  | MIGUEL GALLARDO | COTIZAR NAVE [Calculo y Diseño] | avance: 100.0 | HECHO
```
