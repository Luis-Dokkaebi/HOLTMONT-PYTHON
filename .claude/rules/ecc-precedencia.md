# Precedencia entre ECC y este repositorio

> Regla puente. Se aplica siempre, sin importar el archivo que estés tocando.

Este repositorio importó agentes, comandos, reglas y skills del framework
[ECC](https://github.com/affaan-m/ECC) (MIT). ECC aporta el **método** — cómo
planear, a qué especialista delegar, cómo auditar. No aporta **umbrales**.

## La regla, en una línea

**Ante cualquier discrepancia entre un archivo importado de ECC y
`RESTRICCIONES_EXTREMAS.md`, gana `RESTRICCIONES_EXTREMAS.md`. Sin excepción.**

El motivo no es jerárquico sino epistemológico: los números de ECC son valores
por defecto plausibles para un proyecto cualquiera; los de este repositorio se
**midieron aquí** (§4, "el trinquete"). Un umbral medido siempre gana a uno
estimado, y sustituir el medido por el estimado es bajar una puerta — Directiva
Cero, §2.

## Conflictos conocidos, ya resueltos

No hace falta que los vuelvas a descubrir:

| Origen en ECC | Qué dice | Por qué no aplica aquí |
| --- | --- | --- |
| `rules/common/testing.md` | "Minimum Test Coverage: 80%" | **No se importó.** El piso real es el medido en §4, no 80%. |
| `contexts/dev.md` | "Write code first, explain after" | **No se importó.** R1 exige prueba en rojo primero. |
| `contexts/dev.md` | "Prefer working solutions over perfect" | **No se importó.** Invita justo a lo que Directiva Cero prohíbe. |
| `rules/common/code-review.md` | "coverage >= 80%" (2 líneas) | Importado con esas dos líneas **adaptadas** al trinquete. |
| `skills/tdd-workflow` | "80%+ coverage" en su descripción | El flujo rojo→verde→refactor sí aplica; el número, no. |

Si encuentras un conflicto nuevo: **no lo resuelvas bajando nada.** Aplica esta
regla, sigue adelante, y déjalo anotado en el PR para que se decida aparte.

## Lo que ECC sí manda aquí

- **Método de trabajo**: investigar antes de implementar (research-first),
  planear en fases, delegar al especialista, auditar el propio código antes de
  enseñarlo.
- **Estilo Python**: PEP 8, anotaciones de tipo en toda firma, estructuras
  inmutables, `ruff`.
- **Checklists de revisión y seguridad**: OWASP, secretos, validación de
  entrada, patrones de inyección.

## Lo que este repositorio manda siempre

- Umbrales, pisos y puertas (§4, §5).
- Directiva Cero (§2).
- Las 5 preguntas de calidad y la plantilla de PR (§6, §8).
- Idioma: PR, commits y comentarios en español (`AGENTS.md` §8).
- R7: ninguna prueba toca la base de producción.

## AgentShield

La skill `security-scan` invoca `npx ecc-agentshield scan`, un paquete npm de
terceros que **no** forma parte del repositorio ECC (vive en
`github.com/affaan-m/agentshield`).

Qué revisa: **solo el directorio `.claude/`** — `CLAUDE.md`, `settings.json`,
configuración MCP, `hooks/` y las definiciones de agentes. Busca secretos
embebidos, permisos demasiado abiertos, inyección de comandos en hooks y
superficie de inyección de prompt. No lee `CODIGO.js`, `index.html` ni `api/`.

Es especialmente pertinente aquí porque este repositorio importó 67
definiciones de agente de un tercero: son exactamente el tipo de archivo que
esta herramienta audita.

**Uso local y bajo demanda únicamente.** No se cablea en CI ni en ningún hook.
La decisión es deliberada: se descarga con `npx` desde npm en cada invocación,
y una dependencia de red no auditada no se convierte en puerta de calidad sin
decidirlo a propósito. Para secretos en el código, la puerta vigente sigue
siendo `gitleaks` en el workflow (R7).
