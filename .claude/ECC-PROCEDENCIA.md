# Procedencia de lo importado desde ECC

Este directorio contiene material tomado del framework
[ECC — Everything Claude Code](https://github.com/affaan-m/ECC), licencia **MIT
© 2026 Affaan Mustafa**.

- **Commit de origen:** `68e926bf77dd8ac15ea67b1aa551cba5b8b17e53` (2026-06-15)
- **Manifiesto verificable:** [`ecc-import.json`](ecc-import.json) — 86 archivos
  con su `sha256`, su ruta de origen y si fue adaptado.
- **Regla de precedencia:** [`rules/ecc-precedencia.md`](rules/ecc-precedencia.md)

## Qué se importó

| Qué | Cuántos | Dónde | Adaptado |
| --- | --- | --- | --- |
| Agentes especializados | 67 | `.claude/agents/` | No — verbatim |
| Comandos | 6 | `.claude/commands/` | No — verbatim |
| Reglas | 8 | `.claude/rules/ecc-*.md` | 5 sí (ver abajo) |
| Skills | 5 | `.claude/skills/` | No — verbatim |

Comandos: `/python-review`, `/code-review`, `/test-coverage`, `/quality-gate`,
`/refactor-clean`, `/security-scan`.

Skills: `tdd-workflow`, `security-review`, `architecture-decision-records`,
`hexagonal-architecture`, `security-scan`.

## Qué NO se importó, y por qué

Estos archivos de ECC **contradicen** `RESTRICCIONES_EXTREMAS.md`. Como
`.claude/rules/*.md` se carga como instrucción vinculante en cada sesión,
importarlos habría dado a un agente futuro material para justificar bajar una
puerta — el daño silencioso que la Directiva Cero existe para prevenir.

- **`rules/common/testing.md`** — fija "Minimum Test Coverage: 80%". El piso de
  este repositorio es un número **medido** (§4), no uno elegido. Un umbral
  estimado no sustituye a uno medido.
- **`contexts/dev.md`** — dice "Write code first, explain after" y "Prefer
  working solutions over perfect solutions". Lo primero invierte R1 (prueba en
  rojo primero); lo segundo invita exactamente a lo que §2 prohíbe. Nota: esto
  también contradice al propio `SOUL.md` de ECC, que declara Test-Driven como
  principio.

## Qué se adaptó al importar

| Archivo | Cambio |
| --- | --- |
| `ecc-revision-codigo.md` | Dos líneas con "coverage >= 80%" ahora apuntan al trinquete de §4. Enlaces muertos reescritos. |
| `ecc-fastapi.md` | `paths:` cambiado de `**/app/**/*.py` a `api/**/*.py` y `backend/**/*.py`: los globs originales no coincidían con este repositorio, así que la regla nunca se habría activado. |
| `ecc-python-{estilo,patrones,pruebas,seguridad}.md` | La línea "extends common/…" apuntaba a archivos no importados. Reemplazada por una nota de procedencia. |

## AgentShield

`AgentShield` **no** forma parte del repositorio ECC: es un paquete npm
independiente (`ecc-agentshield`, repo `github.com/affaan-m/agentshield`). La
skill `security-scan` solo lo invoca.

Alcance real: revisa **solo `.claude/`** — `CLAUDE.md`, `settings.json`, config
MCP, `hooks/` y definiciones de agentes, buscando secretos, permisos abiertos,
inyección de comandos y superficie de inyección de prompt. No toca `CODIGO.js`,
`index.html` ni `api/`. Es pertinente justo porque aquí entraron 67 agentes de
un tercero.

**Uso local y bajo demanda.** No está cableado en CI ni en ningún hook, por
decisión explícita: `npx` lo descarga de npm en cada invocación, y una
dependencia de red no auditada no se vuelve puerta de calidad sin decidirlo a
propósito. La puerta vigente para secretos en el código sigue siendo `gitleaks`
en `.github/workflows/restricciones-extremas.yml` (R7).

## Cómo re-sincronizar con ECC

1. Clonar ECC y anotar el nuevo commit.
2. Copiar de nuevo solo los archivos listados en `ecc-import.json` con
   `"adaptado": false`.
3. Para los que tienen `"adaptado": true`, comparar contra el original y
   **volver a aplicar la adaptación**; nunca aceptar el original tal cual, o
   los umbrales de ECC vuelven a entrar.
4. Revisar si aparecieron nuevos conflictos con `RESTRICCIONES_EXTREMAS.md` y
   anotarlos en `rules/ecc-precedencia.md`.
5. Regenerar los `sha256` del manifiesto.

Comprobar que nada se alteró después de importar:

```bash
python3 - <<'PY'
import hashlib, json, pathlib
m = json.load(open(".claude/ecc-import.json"))
for ruta, meta in m["archivos"].items():
    p = pathlib.Path(ruta)
    real = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else "AUSENTE"
    if real != meta["sha256"]:
        print(f"CAMBIADO: {ruta}")
print("verificados:", len(m["archivos"]))
PY
```
