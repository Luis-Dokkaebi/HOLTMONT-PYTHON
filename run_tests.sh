#!/bin/bash
# Corre la suite completa del repositorio: reglas de negocio en Python, contrato
# de la API, pruebas de extremo a extremo (Playwright) y el backend GAS en Node.
#
# No hace falta levantar el servidor a mano: la fixture `live_server` de
# tests/conftest.py arranca FastAPI si el puerto 8000 esta libre y reutiliza el
# que ya este escuchando.
set -u

cd "$(dirname "$0")" || exit 1

if [ -f venv/bin/activate ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

STATUS=0

echo "== Pruebas Python (pytest) =="
python -m pytest -v || STATUS=1

echo
echo "== Pruebas del backend GAS (Node) =="
if command -v node >/dev/null 2>&1; then
    node tests/gas/run_tests.js || STATUS=1
else
    echo "node no esta instalado: se omite tests/gas/run_tests.js" >&2
    STATUS=1
fi

echo
if [ "$STATUS" -eq 0 ]; then
    echo "TODAS LAS PRUEBAS PASARON"
else
    echo "HAY PRUEBAS FALLANDO" >&2
fi
exit "$STATUS"
