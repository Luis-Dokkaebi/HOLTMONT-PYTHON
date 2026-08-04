# Mapa de arquitectura

Dos entregables generados a partir de la lectura del código de los dos repositorios:

| Archivo | Para qué sirve |
| --- | --- |
| `arquitectura.html` | Diagrama interactivo. Un solo archivo, sin CDN ni dependencias: se abre con doble clic o se sirve como estático. |
| `arquitectura.json` | El mismo modelo en `{nodes, edges, flows}`, pensado para que lo consuma un agente de IA. |

Ambos salen del mismo modelo, así que no pueden desincronizarse: `generar.py` los escribe en la misma corrida.

## Qué contiene

**82 componentes · 124 relaciones · 24 flujos**, repartidos en dos sistemas independientes:

- **Holtmont Workspace** (`HOLTMONT-PYTHON`) — ERP operativo. Monolito Vue 3 sin build step sobre
  FastAPI, con motor de reglas gemelo de `CODIGO.js`, persistencia en Supabase y tres agentes de
  LangGraph. Desplegado en Vercel.
- **Oficina Eficiencia** (`MLCLAUDE`) — visión por computadora on-premise. YOLOv8 + ByteTrack +
  reconocimiento facial sobre SQLite cifrado, con licenciamiento DRM offline y aislamiento
  multi-tenant. Se distribuye como ejecutable ofuscado.

No hay aristas entre ambos: son productos separados y el mapa lo refleja.

## El HTML

- **Diagrama por capas.** Cada sistema se dibuja en columnas — de los clientes a los servicios
  externos. Rueda para acercar, arrastre para mover, `⤢` para reencuadrar.
- **Panel de flujos a la derecha.** Al elegir un flujo se resalta la ruta completa: los nodos se
  numeran en orden, las aristas del camino se marcan y el resto se atenúa. El encuadre se ajusta
  solo a la ruta.
- **Tooltips.** El cursor sobre cualquier nodo muestra qué es, con qué está hecho y en qué archivos
  vive.
- **Detalle por componente.** Al hacer clic: descripción, tecnología, archivos, de qué depende,
  quién lo usa y en qué flujos participa — todo navegable.
- **Buscador** (`/` para enfocarlo) sobre nombre, descripción, tecnología y rutas de archivo.
- Responsive, con tema claro y oscuro según el sistema. `Esc` restablece la vista.

### Rutas punteadas

Un tramo punteado en rojo es un salto del relato —el retorno de una respuesta, o un intermediario
que el flujo no menciona— y **no** una dependencia del código. Sólo aparece mientras ese flujo está
seleccionado; nunca se agrega al grafo. El detalle del flujo dice cuántos tramos son de cada tipo.

## El JSON

```jsonc
{
  "meta":  { "systems": [...], "tipos_de_nodo": {...}, "tipos_de_arista": {...}, "conteos": {...} },
  "nodes": [ { "id", "label", "type", "system", "layer", "desc", "tech", "files": [], "tags": [] } ],
  "edges": [ { "id", "source", "target", "label", "kind" } ],
  "flows": [ {
      "id", "name", "system", "category", "desc",
      "steps":       [ { "node", "action" } ],
      "transitions": [ { "from", "to", "edge": "id|null", "tipo": "arista|derivada" } ]
  } ]
}
```

Tres garantías que el generador verifica en cada corrida y que un agente puede dar por hechas:

1. Los `id` de nodo son únicos.
2. Toda arista tiene sus dos extremos en `nodes`.
3. Todo paso de un flujo existe como nodo, y `transitions` ya trae resuelto —contra el grafo real—
   qué tramos son aristas y cuáles son saltos del relato.

Los `files` apuntan a rutas reales del repositorio: sirven como punto de entrada para leer el código
de un componente sin buscarlo.

## Regenerar

```bash
python3 generar.py .        # reescribe arquitectura.json y arquitectura.html
```

`generar.py` contiene el modelo (nodos, aristas y flujos) y `plantilla.html` la interfaz; el
generador inyecta el JSON en la plantilla. Para corregir el mapa cuando el código cambie, se edita
el modelo en `generar.py` — nunca los archivos de salida, que se sobrescriben.
