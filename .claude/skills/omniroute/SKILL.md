---
name: omniroute
description: "Enrutador/pasarela de IA OmniRoute expuesto como REST compatible con OpenAI. Úsala cuando haya que llamar a un LLM desde este repositorio (api/ai_utils.py, api/paperclip_agents.py, api/engineering_agent.py, streamlit_cotizador), cuando falle o se agote la cuota de un proveedor y haga falta fallback automático, cuando se quiera cambiar de modelo sin tocar código, o cuando el usuario mencione OmniRoute, combos de routing, MCP de OmniRoute o el comando omniroute."
metadata:
  origin: OmniRoute (github.com/diegosouzapw/OmniRoute, MIT)
  upstream: skills/omni-auth/SKILL.md (bloque curado) + catálogo skills/README.md
---

# OmniRoute

Pasarela de IA (local o remota) que expone **una sola API compatible con OpenAI** delante de
356 proveedores. Una única clave y un único endpoint; OmniRoute elige el proveedor, reintenta
y hace *fallback* solo cuando uno falla o agota su cuota.

Repositorio de referencia en esta máquina: `/home/user/OmniRoute` (upstream:
`github.com/diegosouzapw/OmniRoute`, MIT).

## Cuándo activarla

- Vas a escribir o modificar código que llama a un LLM (hoy este repo usa `groq` y
  `langchain-groq` directo; OmniRoute es la alternativa cuando se quiere fallback o cambiar
  de modelo sin tocar el código).
- Un proveedor devuelve `429`/`503` y hace falta seguir trabajando con otro.
- Quieres comparar modelos o abaratar tokens sin reescribir los agentes.
- El usuario nombra OmniRoute, "combos", "routing", el MCP de OmniRoute o el binario
  `omniroute`.

## Configuración

```bash
export OMNIROUTE_URL="http://localhost:20128"   # o la URL del VPS / túnel
export OMNIROUTE_KEY="sk-..."                    # Dashboard → API Keys
```

Puerto por defecto: **20128** (API y dashboard comparten puerto).

Todas las peticiones van a `${OMNIROUTE_URL}/v1/...` con
`Authorization: Bearer ${OMNIROUTE_KEY}`. El prefijo `/v1/*` se reescribe internamente a
`/api/v1/*` (`next.config.mjs`), así que ambos funcionan.

**Nunca escribas la clave en el código ni en un test.** Va por variable de entorno, igual que
`SUPABASE_KEY` (ver `RESTRICCIONES_EXTREMAS.md` y `.claude/rules/ecc-seguridad-comun.md`).

### Verificar que está viva

```bash
curl $OMNIROUTE_URL/api/health
# {"status":"ok","timestamp":"2026-..."}   ← sin auth, sonda de liveness
```

`/api/health/ping` además confirma que la base responde. Métricas y estado detallado están
detrás de auth en `/api/monitoring/health`.

## Descubrir modelos

```bash
curl $OMNIROUTE_URL/v1/models -H "Authorization: Bearer $OMNIROUTE_KEY"
curl $OMNIROUTE_URL/api/models/catalog -H "Authorization: Bearer $OMNIROUTE_KEY"  # catálogo completo
```

El `data[].id` es lo que se manda en el campo `model`. Los combos aparecen con
`owned_by: "combo"`.

## Inferencia

Endpoints compatibles con OpenAI (todos bajo `${OMNIROUTE_URL}/v1`):

| Endpoint                 | Para qué                                     |
| ------------------------ | -------------------------------------------- |
| `POST /chat/completions` | chat / generación de texto (el más usado)    |
| `POST /responses`        | Responses API                                |
| `POST /messages`         | formato Anthropic                            |
| `POST /embeddings`       | embeddings                                   |
| `POST /images/generations` | generación de imágenes                     |
| `POST /audio/speech`     | texto → voz                                  |
| `POST /audio/transcriptions` | voz → texto                              |
| `POST /moderations`      | moderación de contenido                      |
| `POST /rerank`           | reordenado de resultados                     |

### curl

```bash
curl -X POST $OMNIROUTE_URL/v1/chat/completions \
  -H "Authorization: Bearer $OMNIROUTE_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"<id de /v1/models>","messages":[{"role":"user","content":"Hola"}]}'
```

### Python (sin dependencias nuevas)

Este repositorio **no** tiene el SDK `openai` en `requirements.txt`; con la biblioteca
estándar o `requests` basta:

```python
import os, json, urllib.request

def omniroute_chat(mensajes: list[dict], modelo: str) -> str:
    url = f"{os.environ['OMNIROUTE_URL']}/v1/chat/completions"
    cuerpo = json.dumps({"model": modelo, "messages": mensajes}).encode()
    peticion = urllib.request.Request(
        url,
        data=cuerpo,
        headers={
            "Authorization": f"Bearer {os.environ['OMNIROUTE_KEY']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(peticion, timeout=60) as respuesta:
        datos = json.load(respuesta)
    return datos["choices"][0]["message"]["content"]
```

Si en algún momento se añade `openai` o `langchain-openai` al `requirements.txt`, apunta
`base_url` a `f"{OMNIROUTE_URL}/v1"` y `api_key` a `OMNIROUTE_KEY`: el resto del código no
cambia.

## Combos y routing

Un *combo* es una lista ordenada de destinos con una estrategia de reparto (19 disponibles:
`priority`, `weighted`, `round-robin`, `cost-optimized`, `auto`, `fusion`, …). Se usa como si
fuera un modelo: `"model": "<nombre-del-combo>"`. Sirve para que una caída de Groq no pare el
cotizador.

Se administran desde el dashboard, por `/api/combos`, o con `omniroute combo list` / `combo create` / `combo switch` en la CLI.

## MCP y A2A

OmniRoute trae servidor MCP propio (110 herramientas, 33 scopes) en tres transportes:

- SSE — `GET $OMNIROUTE_URL/api/mcp/sse`
- Streamable HTTP — `POST $OMNIROUTE_URL/api/mcp/stream`
- stdio — vía el binario `omniroute`

Catálogo en vivo: `GET $OMNIROUTE_URL/api/mcp/tools`. Estado: `/api/mcp/status`.

También expone un servidor A2A (JSON-RPC 2.0) con 6 skills: `smart-routing`,
`quota-management`, `provider-discovery`, `cost-analysis`, `health-report`,
`list-capabilities`.

## CLI

```bash
npm install -g omniroute      # o npx omniroute
omniroute --version
omniroute serve               # arrancar el servidor
omniroute health              # estado y métricas
omniroute models              # catálogo
omniroute chat "pregunta" -m <modelo> [--combo <nombre>] [--stream]
omniroute repl                # sesión interactiva
```

## Errores frecuentes

| Código | Qué significa                | Qué hacer                                              |
| ------ | ---------------------------- | ------------------------------------------------------ |
| `401`  | clave inválida o ausente     | revisa `OMNIROUTE_KEY` (Dashboard → API Keys)          |
| `400`  | formato de modelo inválido   | confirma que el `id` existe en `/v1/models`            |
| `429`  | límite de tasa               | respeta la cabecera `Retry-After`                      |
| `503`  | circuito del proveedor abierto | el upstream está caído; reintenta tras `Retry-After` |

## Reglas de este repositorio que aplican aquí

1. **Ninguna prueba llama a OmniRoute de verdad.** `tests/conftest.py` desconecta las
   credenciales reales y fuerza `BACKEND_ENGINE=memoria`; una llamada de red en la suite
   rompe esa garantía (R7 de `RESTRICCIONES_EXTREMAS.md`). Simula la respuesta HTTP.
2. **Comportamiento nuevo → prueba nueva.** Si integras OmniRoute en un agente, la prueba
   unitaria acompaña al cambio en el mismo PR.
3. **Ejecuta `./run_tests.sh` y `ruff check api backend streamlit_cotizador tests`** antes de
   dar por terminado, y pega la salida real.
4. La clave nunca se registra en logs ni se sube al repositorio.

## Catálogo completo (45 skills)

Esta skill es el punto de entrada. Para un área concreta, el manifiesto original está en
`/home/user/OmniRoute/skills/<id>/SKILL.md` o en
`https://raw.githubusercontent.com/diegosouzapw/OmniRoute/main/skills/<id>/SKILL.md`:

| Necesitas                         | `<id>`                |
| --------------------------------- | --------------------- |
| Autenticación y sesiones          | `omni-auth`           |
| Inferencia completa (referencia)  | `omni-inference`      |
| Modelos y alias                   | `omni-models`         |
| Proveedores y conexiones          | `omni-providers`      |
| Combos y estrategias de routing   | `omni-combos-routing` |
| Claves de API y scopes            | `omni-api-keys`       |
| Uso, coste y logs                 | `omni-usage-logs`     |
| Presupuesto y límites             | `omni-budget`         |
| Caché de respuestas               | `omni-cache`          |
| Compresión de prompts (RTK)       | `omni-compression`    |
| Resiliencia y monitorización      | `omni-resilience`     |
| Servidor MCP                      | `omni-mcp`            |
| Protocolo A2A                     | `omni-agents-a2a`     |
| Webhooks                          | `omni-webhooks`       |
| Túneles                           | `omni-tunnels`        |
| CLI: arrancar/parar el servidor   | `cli-serve`           |
| CLI: chat y REPL                  | `cli-chat`            |
| CLI: proveedores                  | `cli-providers`       |
| CLI: coste y uso                  | `cli-cost-usage`      |

El listado íntegro (23 skills de API + 21 de CLI + 1 de configuración) está en
`/home/user/OmniRoute/skills/README.md`.
