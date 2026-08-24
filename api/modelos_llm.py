"""
Los identificadores de modelo de los proveedores, en un solo sitio.

Un identificador de modelo es un dato que **caduca**. El proveedor retira el
modelo de su catálogo y, desde ese instante, cada llamada responde
`404 model_not_found` — no falla el código, falla un nombre que dejó de existir.

Ya pasó: `llama-3.3-70b-versatile` desapareció del catálogo de Groq y los
agentes empezaron a contestar

    The model llama-3.3-70b-versatile does not exist or you do not have
    access to it.

El identificador estaba copiado en cinco archivos, así que la retirada rompió
cinco funciones a la vez y repararlas dependía de que alguien recordara las
cinco. Por eso vive aquí una sola vez: la próxima vez que Groq mueva su
catálogo, se cambia un renglón y se cambia entero.

`GROQ_MODELO` permite fijarlo por entorno sin tocar código ni esperar un
despliegue, igual que `AGENTE_SQL_MODELO` en `api/services/agente_sql.py`.
"""

from __future__ import annotations

import os
from typing import List

# El modelo con el que se afinaron los prompts de los agentes de este
# repositorio. Se puede cambiar por entorno sin tocar código.
MODELO_GROQ = os.environ.get("GROQ_MODELO", "").strip() or "openai/gpt-oss-120b"


# --- Google Gemini --------------------------------------------------------
#
# El mismo problema, un proveedor más allá. Google retiró `gemini-1.5-flash` y
# `gemini-1.5-pro`: en `v1beta` responden 404 a las API keys emitidas después
# del retiro, y el síntoma que ve el usuario es "Error al consultar Gemini" con
# una key perfectamente válida.
#
# Es una LISTA y no una constante suelta porque
# `api/services/tracker_store.py` la recorre en orden y baja al siguiente solo
# cuando el error es del modelo (404); un 400 —key inválida— corta de inmediato.
# Esa degradación es lo que da un segundo intento cuando Google vuelva a mover
# el catálogo, sin esperar a un despliegue.
MODELOS_GEMINI: List[str] = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-latest",
]

# El de una sola oportunidad, para quien no puede degradar: `paperclip_agents`
# arma una cadena de LangChain de una vez y no ve el código HTTP de la
# respuesta. `GEMINI_MODEL` lo cambia por entorno, igual que `GROQ_MODELO`.
MODELO_GEMINI = os.environ.get("GEMINI_MODEL", "").strip() or MODELOS_GEMINI[0]
