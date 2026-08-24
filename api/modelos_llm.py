"""
El identificador del modelo de Groq, en un solo sitio.

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

# El modelo con el que se afinaron los prompts de los agentes de este
# repositorio. Se puede cambiar por entorno sin tocar código.
MODELO_GROQ = os.environ.get("GROQ_MODELO", "").strip() or "openai/gpt-oss-120b"

