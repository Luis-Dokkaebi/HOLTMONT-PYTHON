#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Hook Stop — R1 (RESTRICCIONES_EXTREMAS.md seccion 0, obligacion 1)
#
# Corre la suite cuando el agente intenta terminar. Si algo falla, lo BLOQUEA
# y le devuelve la salida real para que la arregle. El agente no puede
# reportar "listo" sobre codigo roto: no es que no deba, es que no puede.
#
# Solo corre si hubo cambios en codigo, para no penalizar sesiones de lectura.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO" || exit 0

# Sin cambios en codigo -> nada que verificar.
if git diff --quiet HEAD -- '*.py' '*.js' '*.html' 2>/dev/null \
   && git diff --cached --quiet HEAD -- '*.py' '*.js' '*.html' 2>/dev/null; then
    exit 0
fi

fallos=""

salida_py=$(python3 -m pytest -q 2>&1)
if [ $? -ne 0 ]; then
    fallos+="=== PYTEST FALLO ===
$(printf '%s' "$salida_py" | tail -25)

"
fi

if command -v node >/dev/null 2>&1 && [ -f tests/gas/run_tests.js ]; then
    salida_gas=$(node tests/gas/run_tests.js 2>&1)
    if [ $? -ne 0 ]; then
        fallos+="=== SUITE GAS FALLO ===
$(printf '%s' "$salida_gas" | tail -20)
"
    fi
fi

if [ -n "$fallos" ]; then
    razon="R1 BLOQUEA: la suite no esta en verde y modificaste codigo. No puedes terminar aqui.

${fallos}
Tus dos salidas legitimas (RESTRICCIONES_EXTREMAS.md seccion 2):
  1. Arreglar el codigo hasta que la suite pase por merito propio.
  2. Detenerte y reportar al humano la salida literal de arriba.

PROHIBIDO: silenciar la prueba, marcarla skip/xfail, debilitar su asercion
o borrarla. Modificar la puerta y el codigo en el mismo cambio corrompe la
unica razon por la que nadie necesita leer tu trabajo."

    jq -nc --arg r "$razon" '{decision:"block", reason:$r}'
    exit 0
fi

exit 0
