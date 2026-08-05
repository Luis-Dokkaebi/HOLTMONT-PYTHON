# RESTRICCIONES EXTREMAS

### Contrato de confianza para el código que escriben los agentes

> «Soy bastante mayor que tú. Empecé a programar a finales de los 60. Mi estrategia actual es
> **no leer el código que escriben mis agentes**. Es la única forma de aprovechar su productividad.
> En cambio, los someto a **restricciones extremas**: pruebas unitarias, pruebas Gherkin,
> procedimientos de control de calidad, métricas de calidad, pruebas de mutación, cobertura de
> pruebas y muchas otras. Al final, tengo mucha confianza en el código que producen porque han
> tenido que superar todas mis restricciones y pruebas.»
>
> — Robert C. Martin (*Uncle Bob*), [@unclebobmartin](https://x.com/unclebobmartin)

---

## 0. ⚠️ REGLA OBLIGATORIA PARA TODO AGENTE

> **Esta sección es vinculante para Claude, Codex, Cursor, Jules, Copilot, Gemini, cualquier otro
> agente de IA y cualquier desarrollador humano que trabaje en este repositorio.**
> No es una recomendación, no es una guía de estilo y no depende de que alguien te lo recuerde en
> el prompt. Si estás modificando este repositorio, esto aplica.

### Antes de reportar cualquier trabajo como terminado, DEBES ejecutar:

```bash
./run_tests.sh          # pytest (706 pruebas) + suite GAS de Node (87 pruebas)
ruff check api backend streamlit_cotizador tests
```

Y **pegar la salida real en tu respuesta y en el PR**.

### Las cinco obligaciones no negociables

1. **Ejecutar las pruebas.** Siempre. En cada tarea que toque código, por pequeña que parezca.
   "Es un cambio de una línea" no es una excepción: los cambios de una línea son los que rompen
   producción, precisamente porque nadie los prueba.

2. **Escribir la prueba que falta.** Comportamiento nuevo → prueba unitaria nueva. Bug corregido →
   prueba que fallaba antes del arreglo y pasa después. Regla de negocio → escenario Gherkin.
   Entregar código sin su prueba es entregar código en el que nadie puede confiar, incluido tú.

3. **No tocar las puertas.** Prohibido bajar un umbral, añadir `skip`, `noqa`, `pragma: no cover`,
   `--no-verify`, `continue-on-error` o borrar una prueba para que algo pase. Ver
   [Directiva Cero](#2-directiva-cero--la-regla-que-sostiene-todo-lo-demás). Esta es la
   prohibición más importante del documento.

4. **Reportar con honestidad.** Si una prueba falla y no la arreglaste, **dilo, con la salida
   literal del comando**. Si no pudiste correr la suite, **dilo y explica por qué**. Nunca afirmes
   "todas las pruebas pasan" sin haberlas corrido. Un reporte falso destruye más confianza que un
   bug: el bug se arregla, la desconfianza no.

5. **Responder las cinco preguntas de calidad** ([R6.1](#61--las-cinco-preguntas-obligatorias)) en
   todo PR, en español y con respuestas concretas.

### Por qué esto es obligatorio y no opcional

El dueño de este repositorio **no va a leer línea por línea el código que generas**. Esa es una
decisión deliberada, y es la única forma de aprovechar tu productividad.

Eso significa que **tú eres la última persona que ve ese código antes de que se ejecute contra
datos reales de la empresa.** Las pruebas no son un trámite burocrático que te pusieron encima:
son el único mecanismo por el que tu trabajo puede llegar a producción sin que alguien lo audite.

Si no las corres, no estás ahorrando tiempo. Estás gastando la confianza de alguien más.

---

## 1. La premisa

La productividad de un agente se pierde si un humano tiene que releer cada línea que produce. Si
vas a revisar todo a mano, no ganaste nada: cambiaste "escribir código" por "auditar código", que
es más lento y más aburrido.

La salida no es confiar a ciegas. Es **mover la confianza de sitio**: no confías en el código
porque lo leíste, confías en él porque **sobrevivió a un campo minado que tú diseñaste**.

Esto invierte la responsabilidad de la prueba:

| Modelo tradicional | Modelo de restricciones extremas |
| --- | --- |
| El humano lee el código y decide si sirve | Las puertas ejecutan el código y deciden si sirve |
| "Se ve bien" | "Pasó 793 pruebas, 82% de mutantes muertos y 0 regresiones" |
| La revisión escala con el tamaño del diff | La revisión escala con el número de puertas (constante) |
| Confianza subjetiva, no reproducible | Confianza medida, con número y fecha |

Y trae un corolario incómodo que hay que decir en voz alta:

> **Tu confianza vale exactamente lo que valen tus puertas.**
> Si las puertas son débiles, la confianza es falsa — y es peor que no tener ninguna, porque ahora
> no lees el código *y* además crees que está bien.

Por eso este documento no es una lista de buenos deseos. Es un contrato ejecutable.

---

## 2. Directiva Cero — la regla que sostiene todo lo demás

Cuando nadie lee el código, el mayor riesgo **no** es que el agente escriba un bug.
Es que el agente, al toparse con una puerta cerrada, **abra la puerta en vez de arreglar el código**.

Un bug lo atrapa la siguiente prueba. Una puerta debilitada no la atrapa nadie, nunca. Es un daño
permanente y silencioso al sistema de confianza completo.

### 🚫 Movimientos prohibidos

Está terminantemente prohibido, sin excepción y sin importar la urgencia:

1. **Bajar un umbral.** Cobertura, mutación, complejidad, lint. Ninguno baja. Nunca.
2. **Silenciar una prueba.** Nada de `@pytest.mark.skip`, `xfail`, `.skip()`, `.only()`,
   comentar un bloque de pruebas o borrarlo.
3. **Silenciar el análisis.** Nada de `# noqa` nuevo, `# type: ignore`, `# pragma: no cover`,
   `eslint-disable`, ni añadir rutas a las exclusiones de configuración.
4. **Saltarse la puerta.** Nada de `git commit --no-verify`, `continue-on-error: true`,
   `|| true` colgado de un comando de verificación, ni `if: always()` para tapar un fallo.
5. **Debilitar una aserción.** Cambiar `assertEqual(x, 42)` por `assertIsNotNone(x)` para que pase
   es falsificar evidencia.
6. **Simular lo que se está probando.** Si mockeas la función bajo prueba, la prueba mide el mock.
   Los mocks van en las **fronteras** (red, reloj, disco, GAS, Supabase), nunca en el núcleo.
7. **Reescribir la prueba para que acepte el bug.** Si el código y la prueba discrepan, el
   sospechoso por defecto es el código. Cambiar la prueba requiere justificación explícita en el PR.

### ✅ Qué hacer cuando una puerta se cierra

Solo hay dos salidas legítimas:

- **Arreglar el código** hasta que la puerta abra por mérito propio; o
- **Detenerse y reportar**: qué puerta falló, la salida literal del comando, qué intentaste y por
  qué crees que la puerta está mal calibrada.

Proponer cambiar un umbral es válido — **como propuesta explícita al humano, en el PR, discutida y
aprobada aparte**. Nunca como parte del cambio que necesita pasar esa puerta. Un agente que
modifica la puerta y el código en el mismo commit está corrompiendo la única cosa que hace posible
no leer su trabajo.

> **Regla mnemotécnica:** el agente juega el juego. El agente **no** escribe las reglas del juego.

---

## 3. Las restricciones

Diez restricciones. Cada una define *qué* mide, *por qué* existe, *cómo* se ejecuta y *cuándo*
bloquea.

---

### R1 · Pruebas unitarias

**Qué:** cada regla de negocio tiene una prueba automatizada que la ejerce directamente.

**Por qué:** es el piso. Sin esto, ninguna otra restricción significa nada — no puedes medir
cobertura de pruebas que no existen ni matar mutantes sin una suite que los detecte.

**Reglas:**

- Todo comportamiento nuevo llega **con** su prueba, en el mismo commit. Sin excepción.
- Todo bug corregido llega con una prueba que **falla antes del arreglo y pasa después**.
  Si no escribiste esa prueba, no puedes demostrar que arreglaste algo.
- Preferentemente **TDD**: prueba en rojo → código → verde → refactor. Un agente que escribe la
  prueba después tiende a escribir la prueba que su código ya pasa.
- Una prueba, una razón para fallar. Nombres que describen el comportamiento, no la función:
  `test_avance_uno_crudo_de_gas_cuenta_como_cien_por_ciento`, no `test_avance_2`.
- **Prohibido `assert True`, `assert x is not None` como única aserción, y pruebas sin aserción.**

**Comando:**
```bash
python -m pytest -v          # reglas de negocio, API, contratos
node tests/gas/run_tests.js  # backend Google Apps Script
```

**Bloquea si:** falla una sola prueba. No hay "fallos conocidos aceptables". Cero es cero.

---

### R2 · Pruebas Gherkin (BDD / aceptación)

**Qué:** las reglas de negocio críticas se escriben en lenguaje natural estructurado
(`Dado / Cuando / Entonces`) y se ejecutan como pruebas reales.

**Por qué:** una prueba unitaria demuestra que *el código hace lo que el código hace*. Un escenario
Gherkin demuestra que *el sistema hace lo que el negocio pidió*. Es la única capa que un no
programador puede leer y aprobar — y por lo tanto la única defensa contra un agente que implementa
perfectamente la cosa equivocada.

**Reglas:**

- Los `.feature` los aprueba el dueño del negocio y son la **fuente de verdad**. Si el código
  contradice un `.feature`, el código está mal.
- Escritos en español, en lenguaje del dominio: FOLIO, ESTATUS, AVANCE, INVOLUCRADOS, tracker,
  papa caliente. **Cero vocabulario técnico** — nada de "endpoint", "payload", "mock", "request".
- Un escenario describe **una** regla observable. Si tiene tres `Entonces` sin relación, son tres
  escenarios.
- Toda regla idiosincrática del negocio (las de `AGENTS.md`) **debe** tener escenario.

**Cobertura obligatoria de escenarios** — las reglas que más dinero cuestan si se rompen:

| Regla de negocio | Origen |
| --- | --- |
| La Ley de Antonia — ruteo y sufijo `(VENTAS)` | `AGENTS.md` §3 |
| Reverse Sync — tareas con prefijo `AV-` | `AGENTS.md` §3 |
| Gatekeeper — anti-duplicación por `_tempId` | `AGENTS.md` §2 |
| AVANCE: el `1` crudo de GAS es 100% | `AGENTS.md` §4 |
| Resolución de conflictos por `CONCEPTO` + `FECHA` | `AGENTS.md` §2 |
| Fechas ISO 8601 íntegras hacia Make.com | `AGENTS.md` §5 |
| Fallbacks de Data Validation (`PENDIENTE`, `NO`) | `AGENTS.md` §2 |

Ver el [Anexo A](#anexo-a--escenarios-gherkin-de-referencia) para los escenarios ya redactados.

**Comando:**
```bash
python -m pytest features/ -v      # pytest-bdd
# alternativa: behave features/
```

**Bloquea si:** falla un escenario, **o** existe un `.feature` sin implementación (`step` no
definido). Un escenario sin `steps` es documentación, no una restricción — y aquí no aceptamos
documentación disfrazada de garantía.

---

### R3 · Cobertura de pruebas

**Qué:** qué porcentaje del código ejecuta la suite.

**Por qué:** el código no cubierto es código que **nadie ha ejecutado nunca a propósito**. Cuando
no lees el código del agente, la cobertura es tu único mapa de qué territorio quedó inexplorado.

**Reglas — y una advertencia importante:**

- La cobertura es una métrica **negativa**: 40% prueba que hay un problema; 95% **no** prueba que
  esté bien. Un archivo con 100% de cobertura y cero aserciones tiene 100% de cobertura.
  Por eso la cobertura nunca va sola: va amarrada a R4 (mutación), que sí mide si las pruebas
  *verifican* algo.
- Se mide sobre **líneas y ramas** (`--cov-branch`). Solo líneas es engañarse.
- **Trinquete (§4): el número global nunca baja.**
- **Regla del diff:** el código nuevo o modificado exige **≥ 90%** de cobertura, sin importar el
  global. Deuda vieja se tolera; deuda nueva no se crea.

**Comando:**
```bash
python -m pytest --cov=api --cov=backend --cov=streamlit_cotizador \
                 --cov-branch --cov-report=term-missing \
                 --cov-fail-under=63
```

**Bloquea si:** el total baja del piso vigente (§4), o el diff cubre menos del 90%.

---

### R4 · Pruebas de mutación

**Qué:** la herramienta corrompe tu código a propósito (cambia `>` por `>=`, `True` por `False`,
borra una línea) y vuelve a correr la suite. Si las pruebas **siguen pasando** con el código roto,
esas pruebas no sirven.

**Por qué:** **esta es la restricción que hace honesto todo lo demás.** Es la única que prueba las
pruebas. Un agente puede generar 500 pruebas que suben la cobertura al 95% sin verificar nada — es
justo lo que un modelo optimizando por "cobertura alta" produce naturalmente. La mutación detecta
ese fraude en segundos: si los mutantes sobreviven, las pruebas son teatro.

Si solo puedes adoptar **una** restricción de este documento además de R1, que sea esta.

**Reglas:**

- No se corre sobre todo el repositorio: es carísimo (~5,500 sentencias aquí). Se corre sobre el
  **núcleo crítico**, donde una regresión silenciosa cuesta dinero real:
  - `api/services/tracker_rules.py` — motor de reglas (92% cubierto, es el corazón del sistema)
  - `backend/services/identity.py` — deduplicación y normalización de avance
  - `backend/repositories/tasks.py` — persistencia de tareas
- Un **mutante sobreviviente** es un hallazgo, no ruido: significa que existe una modificación real
  de la lógica que ninguna prueba nota. Se mata escribiendo la prueba que falta, no ignorándolo.
- Se corre en el PR solo sobre archivos tocados (rápido) y **completo cada noche** (lento).

**Comando:**
```bash
mutmut run --paths-to-mutate api/services/tracker_rules.py
mutmut results          # lista de sobrevivientes
mutmut show <id>        # el diff exacto que nadie detectó
```

**Umbral:** ≥ **80%** de mutantes muertos en los módulos del núcleo.
**Bloquea si:** el puntaje baja respecto de la corrida anterior.

---

### R5 · Métricas de calidad

**Qué:** propiedades estructurales medibles del código, independientes de si funciona.

**Por qué:** el código del agente puede pasar todas las pruebas y aun así ser inmantenible — una
función de 300 líneas con complejidad 53 que nadie podrá modificar sin romperla. Las pruebas miden
el comportamiento **de hoy**; estas métricas protegen tu capacidad de cambiarlo **mañana**.

| Métrica | Herramienta | Umbral |
| --- | --- | --- |
| Estilo y errores estáticos | `ruff check` | 0 nuevos (baseline: 51, §4) |
| Formato | `ruff format --check` | consistente, 0 diferencias |
| Complejidad ciclomática | `radon cc` | ≤ 10 en código nuevo; nunca subir la de una función existente |
| Índice de mantenibilidad | `radon mi` | ≥ B en archivos tocados |
| Tipado estático | `mypy` | 0 errores en `backend/` |
| Duplicación | `jscpd` | ≤ 3% |
| Secretos filtrados | `gitleaks` | **0, sin excepción** |
| Tamaño de función | revisión / `radon` | ≤ 50 líneas en código nuevo |
| Tamaño del diff del PR | — | ≤ 400 líneas útiles (ver R6) |

**Reglas:**

- Los umbrales aplican al **código que tocas**. No se exige refactorizar todo el repositorio para
  entregar un cambio de tres líneas.
- Pero la complejidad de una función existente **no puede subir**. Si tocas
  `apply_batch_update` (complejidad 53), sale igual o mejor. Nunca peor.
- La deuda estructural conocida está inventariada en §4 y se paga con un plan, no de golpe.

**Comando:**
```bash
ruff check api backend streamlit_cotizador tests
ruff format --check .
radon cc api backend -n C -s        # todo lo de complejidad ≥ 11
radon mi api backend -n B
mypy backend/
gitleaks detect --no-banner
```

---

### R6 · Procedimientos de control de calidad

**Qué:** el proceso humano alrededor del código. Lo que ninguna herramienta puede decidir.

**Por qué:** las herramientas verifican que el código es correcto. Nadie más que un humano puede
verificar que es el **código correcto** — que resuelve el problema que existía, que se puede
revertir, que alguien más lo podrá mantener.

#### 6.1 · Las cinco preguntas obligatorias

Vigentes en este repositorio (`AGENTS.md` §8) y en la plantilla de PR de `REAL-HOLTMONT`.
Todo PR las responde, **en español**, con respuestas concretas — no "sí":

1. **¿Tiene un feedback loop que verifique el código generado?**
   *Malo:* "Sí, hay pruebas." *Bueno:* "`tests/test_tracker_rules.py::test_ley_antonia` falla si
   se reintroduce el sufijo `(VENTAS)`; corre en CI en cada push."
2. **¿Cómo se hace el rollback si falla?**
   *Malo:* "Revertir el commit." *Bueno:* "`git revert abc1234`; no hay migración de datos, la
   columna nueva es nullable, el frontend tolera su ausencia."
3. **¿Tiene observabilidad en producción?**
   *Malo:* "Hay logs." *Bueno:* "`registrarLog(user, 'SAVE_BATCH', ...)` deja traza por usuario;
   un fallo de webhook queda en la hoja `AUDITORIA` con la fecha ISO."
4. **¿Escala si el equipo crece?**
5. **¿Tu equipo lo mantiene sin ti?**

Una respuesta vacía o genérica **invalida el PR**. Son el control de calidad, no un trámite.

#### 6.2 · Definición de Terminado (DoD)

Un cambio está terminado cuando **todo** esto es cierto:

- [ ] R1–R5 en verde, localmente y en CI
- [ ] Comportamiento nuevo con prueba unitaria propia
- [ ] Bug corregido con prueba que fallaba antes del arreglo
- [ ] Regla de negocio nueva o modificada con escenario Gherkin
- [ ] Cobertura del diff ≥ 90%; el global no bajó
- [ ] Las 5 preguntas respondidas con especificidad
- [ ] Documentación actualizada si cambió una regla (`AGENTS.md`, `docs/`)
- [ ] Sin secretos, credenciales ni URLs internas en el diff
- [ ] Ninguna puerta modificada (Directiva Cero)

#### 6.3 · Higiene de PR

- **Un PR, un propósito.** Refactor y feature no viajan juntos: hacen imposible saber cuál rompió qué.
- **≤ 400 líneas útiles** (sin lockfiles ni generados). Si no cabe, se parte.
- Título y descripción **en español** (`AGENTS.md` §8).
- La descripción dice **qué cambió y por qué**, no cómo — el cómo está en el diff.

---

### R7 · Seguridad y protección de datos de producción

**Qué:** ninguna prueba, script o agente toca datos reales.

**Por qué:** un agente que no supervisas ejecutando código contra la base de producción es la única
falla de este documento que **no se puede revertir con `git revert`**.

**Reglas — no negociables:**

- **Ninguna prueba escribe en la base de producción.** `tests/conftest.py` desconecta
  `SUPABASE_URL` / `SUPABASE_KEY` durante toda la sesión de pytest y fuerza `BACKEND_ENGINE=memoria`.
  **Esa protección no se toca.** Correr contra una base real es deliberado
  (`HOLTMONT_TEST_ALLOW_DB=1`) y **jamás en CI**.
- Cero credenciales en el repositorio. Todo por variables de entorno o Propiedades del Script de GAS.
- `gitleaks` en cada PR. Un secreto detectado **bloquea el merge y obliga a rotar la credencial** —
  borrar el commit no basta, ya está en el historial y hay que asumirlo comprometido.
- Dependencias nuevas: se justifican en el PR y pasan `pip-audit` / `npm audit`.

**Comando:**
```bash
gitleaks detect --no-banner
pip-audit
npm audit --audit-level=high
```

---

### R8 · Determinismo (política anti-flaky)

**Qué:** la misma entrada produce el mismo resultado, siempre.

**Por qué:** una prueba intermitente es **peor que ninguna prueba**. Entrena al equipo a re-correr
CI hasta que pase por casualidad — y el día que atrapa un bug real, nadie le cree. Una sola prueba
flaky degrada la confianza en las 793 restantes.

**Reglas:**

- Prohibido depender de reloj real, red, orden de ejecución, orden de diccionarios o aleatoriedad
  sin semilla. El tiempo se inyecta; `random` se siembra.
- Se corre con `-p no:randomly` desactivado a propósito: el **orden aleatorio es deseable**, expone
  acoplamiento oculto entre pruebas.
- Una prueba intermitente detectada se **arregla o se borra en 48 horas**. No se tolera "a veces
  falla". No existe `@flaky` ni reintentos automáticos.
- Fallo de CI por infraestructura (binario ausente, red caída) se distingue de fallo de código y
  se anota — pero no se usa como excusa genérica.

**Comando:**
```bash
python -m pytest -q -p no:cacheprovider   # repetir 3× seguidas: 3 verdes o hay flake
```

---

### R9 · Contratos entre capas

**Qué:** las fronteras del sistema (frontend ↔ backend ↔ API) tienen pruebas que verifican que
ambos lados siguen hablando el mismo idioma.

**Por qué:** aquí es donde el código generado falla de la forma más cara. Cada lado pasa sus
pruebas unitarias, y el sistema está roto igual porque uno manda `folio` y el otro espera `FOLIO`.
Es exactamente el tipo de fallo que un humano leyendo un solo archivo tampoco detecta.

**Reglas:**

- El contrato `index.html` → `api_service.js` → `api/main.py` está probado en
  `tests/test_api_contract.py`. Cambiar una firma sin actualizar la prueba rompe CI, **como debe ser**.
- Toda función que el frontend invoca por `google.script.run` debe existir en el scope global de
  `CODIGO.js` — verificado automáticamente.
- Cambios en el esquema de la API se reflejan en `docs/openapi.yaml` en el mismo PR.
- Los payloads hacia Make.com preservan ISO 8601 con milisegundos y `Z` (`AGENTS.md` §5), con prueba.

**Comando:**
```bash
python -m pytest tests/test_api_contract.py tests/test_paridad_appscript.py -v
node tests/gas/run_tests.js
```

---

### R10 · Reversibilidad y observabilidad

**Qué:** todo cambio se puede deshacer rápido, y en producción se nota si falló.

**Por qué:** las nueve restricciones anteriores reducen la probabilidad de un fallo. Ninguna la
lleva a cero. Esta es la red debajo del trapecio: cuando algo pase — y algo va a pasar — determina
si el costo son diez minutos o un día perdido.

**Reglas:**

- Todo PR declara su plan de rollback (pregunta 2 de R6.1). "Revertir el commit" solo es válido si
  es verdad: sin migración destructiva, sin estado nuevo incompatible.
- Migraciones de base: siempre compatibles hacia atrás. Columnas nuevas nullable. Nada de `DROP`
  en el mismo despliegue que introduce el reemplazo.
- Operaciones sensibles dejan traza: `registrarLog(user, action_type, description)` (`AGENTS.md` §2).
- Los cron y jobs fallan **ruidosamente**: `--fail-with-body`, como ya hace
  `.github/workflows/cron-metricas.yml`. Un cron que falla en silencio es peor que no tenerlo.

---

## 4. El trinquete (*ratchet*) — línea base medida

Un umbral inventado se ignora el primer día que estorba. Estos números **se midieron en este
repositorio**, no se estimaron:

<sub>Medición: 5 de agosto de 2026, rama `claude/uncle-bob-restrictions-doc-0zc7ld`, commit `5bdebf1`.</sub>

| Métrica | Valor medido hoy | Piso vigente | Meta |
| --- | --- | --- | --- |
| Pruebas Python (`pytest`) | **706 pasan** | 706 | crece con cada feature |
| Pruebas GAS (`node tests/gas/run_tests.js`) | **87 pasan, 0 fallan** | 87 | crece |
| Cobertura global (líneas) | **63%** | **63%** | 80% |
| Cobertura del diff | — | **90%** | 90% |
| Hallazgos de `ruff` (reglas por defecto) | **51** | **51** | 0 |
| Complejidad promedio (498 bloques) | **A (4.56)** | A | A |
| Funciones con complejidad ≥ 11 | **~25** | no aumentar | < 10 |
| Escenarios Gherkin | **0** | — | 7 reglas críticas (R2) |
| Puntaje de mutación (núcleo) | **no medido** | — | 80% |

### Regla del trinquete

> **Los umbrales solo se mueven en una dirección: hacia arriba.**

- Un PR que sube la cobertura global sube el piso, en el mismo PR.
- Un PR que baja cualquier métrica **no se mergea**. No se "arregla después": después no llega.
- Nadie baja un piso para desbloquear un cambio (Directiva Cero). Subir el piso es rutina; bajarlo
  es una decisión del dueño del repositorio, documentada, en un PR aparte que no contiene código.

### Deuda estructural inventariada

Estas funciones ya existen y están fuera de umbral. **No se exige arreglarlas para entregar otros
cambios** — se exige no empeorarlas, y se pagan con plan propio:

| Función | Complejidad | Archivo |
| --- | --- | --- |
| `apply_batch_update` | **F (53)** | `api/services/tracker_rules.py` |
| `render_pdf_quoter` | **F (47)** | `streamlit_cotizador/app.py` |
| `_build_pascal_scene` | **E (37)** | `api/paperclip_agents.py` |
| `compute_quote_metrics` | **E (34)** | `api/services/tracker_rules.py` |
| `process_and_save_work_order` | **E (32)** | `api/services/work_order.py` |
| `render_work_order_view` | **D (29)** | `streamlit_cotizador/work_order_view.py` |
| `apply_hot_potato` | **D (27)** | `api/services/tracker_rules.py` |

Módulos sin cobertura alguna (0%), candidatos prioritarios: `backend/core/engines/postgrest.py`,
`backend/core/engines/sqlalchemy_engine.py`, `streamlit_cotizador/app.py`,
`streamlit_cotizador/work_order_view.py`.

### Nota honesta sobre el entorno

Dos pruebas de UI (`test_catalogo_conceptos.py`, `test_cotizacion_preconstruccion.py`) fallan en
este contenedor por falta del binario `chrome-headless-shell` de Playwright — **es un fallo de
entorno, no de código**. En CI deben instalarse los navegadores (`playwright install chromium`) y
entonces cuentan como bloqueantes igual que todas las demás. Un fallo de entorno se documenta y se
arregla; nunca se convierte en una exclusión permanente.

---

## 5. Las cuatro puertas

El código del agente atraviesa cuatro filtros. Cada uno más caro y más lento que el anterior, así
que cada uno debe atrapar lo que el anterior dejó pasar.

```
   ┌──────────────────────────────────────────────────────────────────┐
   │  PUERTA 1 · Antes de escribir código        (segundos)          │
   │  Prueba en rojo primero. Sin prueba que falle, no hay código.   │
   └──────────────────────────────────────────────────────────────────┘
                                 ↓
   ┌──────────────────────────────────────────────────────────────────┐
   │  PUERTA 2 · Local, antes del commit         (< 1 minuto)        │
   │  ./run_tests.sh + ruff check + ruff format --check              │
   │  El agente NO hace commit sin esto en verde.                    │
   └──────────────────────────────────────────────────────────────────┘
                                 ↓
   ┌──────────────────────────────────────────────────────────────────┐
   │  PUERTA 3 · CI en el Pull Request           (minutos)           │
   │  R1–R5, R7–R9 completas. Bloqueante para el merge.              │
   │  ⚠️  Esta es la única puerta que el agente no puede evitar.      │
   └──────────────────────────────────────────────────────────────────┘
                                 ↓
   ┌──────────────────────────────────────────────────────────────────┐
   │  PUERTA 4 · Revisión humana                 (2 minutos)         │
   │  NO se lee el código. Se verifica el contrato:                  │
   │    · ¿Están las 5 preguntas respondidas con especificidad?      │
   │    · ¿El diff toca alguna puerta, umbral o configuración de CI? │
   │    · ¿El PR hace UNA cosa?                                      │
   │    · ¿Los escenarios Gherkin describen lo que pedí?             │
   └──────────────────────────────────────────────────────────────────┘
```

**La puerta 4 es la que hace realidad la idea de Uncle Bob.** El humano no audita implementación —
audita que el contrato se respetó. Dos minutos, no dos horas, y no escalan con el tamaño del diff.

Y su punto más importante: **revisar el diff en busca de manipulación de las puertas**. Es la única
lectura de código que sigue siendo obligatoria, porque es la única que ninguna herramienta puede
hacer por ti. En GitHub se automatiza parcialmente marcando como *protegidos* los archivos
`.github/workflows/**`, `pytest.ini`, `pyproject.toml` y este documento — que requieran aprobación
explícita mediante `CODEOWNERS`.

---

## 6. Comandos exactos

### Verificación completa local

```bash
./run_tests.sh                       # pytest + suite GAS de Node
```

### Por restricción

```bash
# R1 · unitarias
python -m pytest -v
node tests/gas/run_tests.js

# R2 · Gherkin
python -m pytest features/ -v

# R3 · cobertura (con piso del trinquete)
python -m pytest --cov=api --cov=backend --cov=streamlit_cotizador \
                 --cov-branch --cov-report=term-missing --cov-fail-under=63

# R4 · mutación (núcleo crítico)
mutmut run --paths-to-mutate api/services/tracker_rules.py
mutmut results

# R5 · métricas
ruff check api backend streamlit_cotizador tests
ruff format --check .
radon cc api backend -n C -s
mypy backend/

# R7 · seguridad
gitleaks detect --no-banner
pip-audit

# R8 · determinismo (3 corridas seguidas, 3 verdes)
for i in 1 2 3; do python -m pytest -q || echo "FLAKY en corrida $i"; done

# R9 · contratos
python -m pytest tests/test_api_contract.py tests/test_paridad_appscript.py -v
```

### Dependencias

```bash
pip install -r requirements.txt -r requirements-dev.txt
pip install ruff radon mypy mutmut pytest-cov pytest-bdd pip-audit
playwright install chromium      # necesario para las pruebas de UI
```

---

## 7. CI — lista para pegar

Guardar como `.github/workflows/restricciones-extremas.yml`. Es **la puerta 3**: la única que el
agente no puede saltarse.

```yaml
name: Restricciones Extremas

on:
  pull_request:
  push:
    branches: [main]

jobs:
  restricciones:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # gitleaks necesita el historial completo

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Instalar dependencias
        run: |
          pip install -r requirements.txt -r requirements-dev.txt
          pip install ruff radon mypy pytest-cov pytest-bdd pip-audit
          playwright install --with-deps chromium

      # ---- R5 · métricas (lo más rápido primero: falla barato) ----
      - name: R5 · Lint
        run: ruff check api backend streamlit_cotizador tests
      - name: R5 · Formato
        run: ruff format --check .
      - name: R5 · Complejidad
        run: radon cc api backend -n D -s   # D+ (>20) rompe el build

      # ---- R7 · seguridad ----
      - name: R7 · Secretos
        uses: gitleaks/gitleaks-action@v2
      - name: R7 · Vulnerabilidades
        run: pip-audit || true    # informativo mientras se sanea el baseline

      # ---- R1 + R3 · pruebas y cobertura ----
      - name: R1+R3 · Pytest con cobertura
        env:
          BACKEND_ENGINE: memoria     # R7: jamás contra base real
        run: |
          python -m pytest -v \
            --cov=api --cov=backend --cov=streamlit_cotizador \
            --cov-branch --cov-report=term-missing \
            --cov-fail-under=63

      # ---- R2 · Gherkin ----
      - name: R2 · Escenarios de aceptación
        run: python -m pytest features/ -v

      # ---- R1 + R9 · backend GAS y contratos ----
      - name: R1+R9 · Suite GAS (Node)
        run: node tests/gas/run_tests.js
      - name: R9 · Contratos entre capas
        run: python -m pytest tests/test_api_contract.py tests/test_paridad_appscript.py -v

  # ---- R4 · mutación: lenta, corre de noche, no bloquea el PR ----
  mutacion:
    if: github.event_name == 'schedule'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: |
          pip install -r requirements.txt -r requirements-dev.txt mutmut
          mutmut run --paths-to-mutate api/services/tracker_rules.py
          mutmut results
```

> ⚠️ **Importante:** `continue-on-error: true` está prohibido en este workflow salvo el caso
> marcado de `pip-audit`, que es informativo mientras se sanea la línea base y tiene fecha de
> caducidad. Una puerta que no bloquea no es una puerta: es un adorno que da falsa tranquilidad.

**Además, en la configuración del repositorio en GitHub:**

- Proteger `main`: prohibido el push directo.
- Marcar el job `restricciones` como **required status check**.
- `CODEOWNERS` sobre `.github/workflows/**`, `pytest.ini`, `pyproject.toml` y
  `RESTRICCIONES_EXTREMAS.md` — así, tocar una puerta exige aprobación humana explícita.

---

## 8. Plantilla de Pull Request

Guardar como `.github/PULL_REQUEST_TEMPLATE.md`.

```markdown
## Qué cambia y por qué

<!-- Una o dos frases. El "cómo" está en el diff. -->

## Control de calidad (obligatorio, en español y con especificidad)

1. **¿Tiene un feedback loop que verifique el código generado?**
2. **¿Cómo se hace el rollback si falla?**
3. **¿Tiene observabilidad en producción?**
4. **¿Escala si el equipo crece?**
5. **¿Tu equipo lo mantiene sin ti?**

## Restricciones extremas

- [ ] **R1** · `pytest` y `node tests/gas/run_tests.js` en verde
- [ ] **R2** · Escenario Gherkin para toda regla de negocio nueva o modificada
- [ ] **R3** · Cobertura del diff ≥ 90%; el global no bajó
- [ ] **R4** · Sin mutantes sobrevivientes nuevos en el núcleo
- [ ] **R5** · `ruff`, `radon`, `mypy` limpios en lo tocado; complejidad no subió
- [ ] **R6** · PR con un solo propósito, ≤ 400 líneas útiles
- [ ] **R7** · Sin secretos; ninguna prueba toca la base de producción
- [ ] **R8** · Suite corrida 3 veces seguidas sin intermitencias
- [ ] **R9** · Contratos entre capas verificados
- [ ] **R10** · Rollback declarado y viable

## Directiva Cero

- [ ] **Este PR no modifica ningún umbral, configuración de CI, `pytest.ini`,
      ni añade `skip` / `noqa` / `pragma: no cover` / `--no-verify`.**

<!-- Si tuviste que tocar una puerta, NO lo incluyas aquí: abre un PR aparte,
     sin código, explicando por qué la puerta está mal calibrada. -->

## Evidencia

<!-- Pega la salida real de ./run_tests.sh y del reporte de cobertura. -->
```

---

## 9. Cómo portar esto a otro proyecto

Este documento está escrito para Holtmont, pero la estructura es independiente del stack. Para
adoptarlo en otro repositorio:

1. **Copia este archivo** a la raíz del proyecto nuevo.
2. **Mide la línea base antes de fijar cualquier umbral.** Corre las pruebas, la cobertura y el
   lint tal como están hoy y anota los números reales en §4. *No inventes umbrales.* Un umbral
   aspiracional que falla desde el día uno enseña al equipo a ignorar CI — el daño exacto que
   este documento existe para evitar.
3. **Sustituye las herramientas por las de tu stack**, conservando la restricción:

   | Restricción | Python | Node / TypeScript | Go | Java |
   | --- | --- | --- | --- | --- |
   | R1 unitarias | pytest | vitest / jest | `go test` | JUnit |
   | R2 Gherkin | pytest-bdd / behave | cucumber-js | godog | Cucumber-JVM |
   | R3 cobertura | pytest-cov | c8 / istanbul | `go test -cover` | JaCoCo |
   | R4 mutación | mutmut | Stryker | go-mutesting | PIT |
   | R5 lint | ruff + mypy | eslint + tsc | golangci-lint | SpotBugs |
   | R5 complejidad | radon | eslint complexity | gocyclo | PMD |
   | R7 secretos | gitleaks | gitleaks | gitleaks | gitleaks |

4. **Reescribe §3-R2** con las reglas de negocio *de ese* dominio. Es la única sección que no se
   puede copiar: el Gherkin sin dominio real es plantilla vacía.
5. **Conecta la puerta 3** (§7) y márcala como *required status check*. **Sin este paso, el
   documento no hace nada** (§10).
6. **Adopta en este orden**, no todo de golpe: R1 → R3 → R5 → R7 → R2 → R4 → el resto.
   R1 y R3 dan el 70% del beneficio en un día. R4 es la que hace honesto todo lo demás; llega
   cuando la suite ya sea seria.

### Para `REAL-HOLTMONT` en particular

Ese repositorio comparte `CODIGO.js` con este, pero **hoy no tiene suite automatizada**: tiene
~40 scripts `test_*.js` sueltos en la raíz, que son diagnósticos manuales, no pruebas — nadie los
corre en conjunto y ninguno tiene código de salida verificado.

El camino más corto y de mayor rendimiento es **portar `tests/gas/` de este repositorio** (87
pruebas contra `CODIGO.js` con mocks de GAS, salida verificable y código de salida 0/1). Ya prueba
el mismo backend. Pasos:

1. Copiar `tests/gas/` completo a `REAL-HOLTMONT`.
2. Añadir `"scripts": { "test": "node tests/gas/run_tests.js" }` a su `package.json`.
3. Consolidar los `test_*.js` de la raíz que aún valgan como casos dentro de la suite; **borrar el
   resto** — un script de diagnóstico obsoleto en la raíz es ruido que se confunde con cobertura.
4. Conectar la puerta 3 con el job de Node únicamente.

---

## 10. Este documento no se hace cumplir solo

Hay que decirlo con claridad, porque es la diferencia entre que esto funcione y que sea decoración:

> **Un archivo `.md` no es una restricción. Es una intención.**

Un agente puede leer este documento y aun así no cumplirlo — por prisa, por una instrucción
contradictoria o simplemente por no haberlo cargado en su contexto. Lo que **sí** restringe a un
agente es un comando que devuelve código de salida distinto de cero y un merge que GitHub bloquea.

El valor de este archivo es ser **la especificación** de esas puertas: qué se mide, con qué umbral,
por qué, y qué hacer cuando una se cierra. Pero la restricción real vive en tres lugares:

1. `.github/workflows/restricciones-extremas.yml` — la puerta que ejecuta (§7)
2. La configuración de rama protegida con *required status checks* — lo que impide el merge
3. `CODEOWNERS` sobre los archivos de las puertas — lo que impide que se abran solas

Mientras esos tres no existan, este documento describe un campo minado sin minas.

**El orden correcto de adopción es:** conectar la puerta 3 primero (§7), aunque arranque solo con
R1 y R3 y con los umbrales flojos de §4. Una puerta modesta que bloquea de verdad vale
infinitamente más que diez restricciones perfectas que nadie ejecuta.

---

## Anexo A · Escenarios Gherkin de referencia

Escritos con las reglas reales de `AGENTS.md`. Sirven de plantilla para los `.feature` de R2.

```gherkin
# features/ley_de_antonia.feature
# language: es

Característica: Ruteo de tareas y la Ley de Antonia
  Para que la tabla maestra de ventas no se contamine con tareas del tracker general,
  el sistema debe enrutar según el origen de la tarea.

  Escenario: Un usuario cualquiera no puede enviar tareas a una hoja de ventas
    Dado que el usuario "RICARDO GARCIA" está en el tracker general
    Cuando envía una tarea a la hoja "JUAN PEREZ (VENTAS)"
    Entonces la tarea se guarda en la hoja "JUAN PEREZ"
    Y el sufijo "(VENTAS)" no aparece en la hoja destino

  Escenario: Las tareas de Antonia sí viven en la tabla de ventas
    Dado que la tarea tiene el folio "AV-00123"
    Cuando se actualiza su ESTATUS a "TERMINADO" desde otra hoja de personal
    Entonces el cambio se refleja también en la hoja "ANTONIA_VENTAS"
    Y la hoja maestra conserva el mismo FOLIO "AV-00123"

  Escenario: Una tarea del tracker general nunca genera reverse sync
    Dado que la tarea tiene el folio "TR-00456"
    Cuando se actualiza su ESTATUS a "TERMINADO"
    Entonces la hoja "ANTONIA_VENTAS" no se modifica
```

```gherkin
# features/anti_duplicacion.feature
# language: es

Característica: Prevención de tareas duplicadas
  Para que un doble clic o una red lenta no generen dos filas idénticas,
  el backend debe bloquear ejecuciones concurrentes de la misma tarea.

  Escenario: Doble envío del mismo formulario crea una sola fila
    Dado que el usuario crea una tarea nueva con el identificador temporal "tmp-abc-123"
    Cuando el formulario se envía dos veces seguidas antes de recibir respuesta
    Entonces existe exactamente una fila con esa tarea
    Y el frontend recibe el objeto guardado completo para poder fusionarlo

  Escenario: Si el FOLIO no se encuentra, se busca por CONCEPTO y FECHA
    Dado que existe una tarea con CONCEPTO "REVISION DE PLANOS" y FECHA "2026-08-05"
    Y que su FOLIO se perdió por un error de escritura
    Cuando llega una actualización para esa misma combinación
    Entonces se actualiza la fila existente
    Y no se genera un FOLIO nuevo
```

```gherkin
# features/avance.feature
# language: es

Característica: Interpretación del porcentaje de AVANCE
  Google Apps Script devuelve el valor numérico 1 para una celda con formato
  de porcentaje al 100%. Confundirlo con "1%" corrompe todos los indicadores.

  Esquema del escenario: Valores que significan tarea completada
    Dado que la celda AVANCE contiene <valor>
    Cuando el sistema evalúa si la tarea está completa
    Entonces el resultado es <completa>

    Ejemplos:
      | valor   | completa |
      | 1       | sí       |
      | "100"   | sí       |
      | "100%"  | sí       |
      | "1"     | no       |
      | "1.0"   | no       |
      | 0.5     | no       |
      | ""      | no       |
```

---

## Anexo B · Resumen de una página

Para pegar en el `AGENTS.md` de cualquier proyecto:

> **Las restricciones no se negocian.**
> Cuando una puerta se cierra, arregla el código o detente y reporta.
> Nunca bajes un umbral, silencies una prueba, añadas un `skip`, un `noqa`, un
> `pragma: no cover` ni un `--no-verify` para pasar. Modificar una puerta y el código en el mismo
> commit corrompe la única razón por la que nadie necesita leer tu trabajo.
>
> **Antes de cada commit:** `./run_tests.sh` y `ruff check` en verde.
> **En cada PR:** las 5 preguntas respondidas con especificidad, prueba para todo comportamiento
> nuevo, escenario Gherkin para toda regla de negocio, cobertura del diff ≥ 90%.
> **Siempre:** ninguna prueba toca la base de producción.

---

*Basado en la práctica descrita por Robert C. Martin (Uncle Bob). La cita es suya; los umbrales,
comandos y la línea base son de este repositorio y fueron medidos, no estimados.*
