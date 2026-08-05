#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Hook PreToolUse — Directiva Cero (RESTRICCIONES_EXTREMAS.md §2)
#
# Bloquea que un agente edite los archivos que DEFINEN las puertas de calidad.
# Lo ejecuta el harness de Claude Code, no el modelo: el agente no puede
# saltarselo ni "decidir" ignorarlo.
#
# Entrada: JSON por stdin con .tool_input.file_path
# Salida:  JSON con permissionDecision=deny cuando el archivo esta protegido
# ---------------------------------------------------------------------------
set -uo pipefail

payload=$(cat)
archivo=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null)

[ -z "$archivo" ] && exit 0

case "$archivo" in
    */.github/workflows/*|\
    */pytest.ini|\
    */pyproject.toml|\
    */setup.cfg|\
    */.github/CODEOWNERS|\
    */RESTRICCIONES_EXTREMAS.md|\
    */.claude/settings.json|\
    */.claude/hooks/*|\
    */run_tests.sh|\
    */tests/conftest.py)
        razon="DIRECTIVA CERO — '${archivo##*/}' define una puerta de calidad y no se modifica dentro del mismo cambio que necesita pasarla. Ver RESTRICCIONES_EXTREMAS.md seccion 2. Si una puerta se cierra tienes dos salidas legitimas: arreglar el codigo, o detenerte y reportar. Si crees que la puerta esta mal calibrada, proponlo al humano en un PR aparte que no contenga codigo."
        jq -nc --arg r "$razon" '{
            hookSpecificOutput: {
                hookEventName: "PreToolUse",
                permissionDecision: "deny",
                permissionDecisionReason: $r
            }
        }'
        exit 0
        ;;
esac

exit 0
