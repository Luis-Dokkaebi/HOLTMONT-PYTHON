# CLAUDE.md — Reglas de trabajo en este repositorio

Este archivo se carga automáticamente al iniciar una sesión. Es vinculante.

## ⚠️ Regla 0 — Restricciones extremas (OBLIGATORIA)

**Debes cumplir [`RESTRICCIONES_EXTREMAS.md`](RESTRICCIONES_EXTREMAS.md) en toda tarea que toque
código de este repositorio.** Léelo antes de tu primer cambio.

**Antes de reportar cualquier trabajo como terminado, ejecuta y pega la salida real:**

```bash
./run_tests.sh                                      # 706 pruebas Python + 87 pruebas GAS
ruff check api backend streamlit_cotizador tests
```

### Las cinco obligaciones no negociables

1. **Ejecuta las pruebas siempre.** En toda tarea que toque código. "Es un cambio de una línea" no
   es excepción.
2. **Escribe la prueba que falta.** Comportamiento nuevo → prueba unitaria. Bug corregido → prueba
   que fallaba antes del arreglo. Regla de negocio → escenario Gherkin.
3. **No toques las puertas** (*Directiva Cero*). Prohibido bajar umbrales o añadir `skip`, `noqa`,
   `pragma: no cover`, `--no-verify`, `continue-on-error` o borrar pruebas para que algo pase. Si
   una puerta se cierra: arregla el código, o detente y reporta.
4. **Reporta con honestidad.** Si una prueba falla, dilo con la salida literal del comando. Si no
   pudiste correr la suite, dilo y explica por qué. Nunca afirmes que las pruebas pasan sin
   haberlas corrido.
5. **Responde las 5 preguntas de calidad** en todo PR, en español y con respuestas concretas
   (`AGENTS.md` §8).

**Por qué:** el dueño de este repositorio no lee línea por línea el código que generas. Eso te
convierte en la última revisión antes de que corra contra datos reales de la empresa.

## Contexto del proyecto

Las reglas de negocio, el stack y las skills específicas están en [`AGENTS.md`](AGENTS.md).
Léelo antes de tocar `CODIGO.js`, `index.html` o `api/`.

## Regla de seguridad crítica

**Ninguna prueba escribe en la base de producción.** `tests/conftest.py` desconecta
`SUPABASE_URL`/`SUPABASE_KEY` y fuerza `BACKEND_ENGINE=memoria`. Esa protección no se toca.

## Idioma

Los PR, commits y comentarios se redactan **en español** (`AGENTS.md` §8).
