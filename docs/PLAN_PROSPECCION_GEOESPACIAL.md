# Plan: integrar el modelo geoespacial (DENUE) como módulo de la plataforma

Documento de arranque para incorporar [`ModeloGeo`](https://github.com/Luis-Dokkaebi/ModeloGeo)
—prospección de proveedores y clientes de construcción sobre el DENUE del INEGI— a
`index.html` como un módulo más del menú lateral, con su backend en `api/`.

**Estado: propuesta. No se ha escrito código de implementación.**

Todo número de este documento **se midió** en la sesión del 18 de agosto de 2026 contra
`ModeloGeo@0174561` y `HOLTMONT-PYTHON@929295f`. Los comandos exactos están en §2 para que
cualquiera los reproduzca. Lo que no se midió se dice que no se midió.

---

## 1. Qué se integra, qué se reescribe y qué se tira

`ModeloGeo` son tres capas mezcladas dentro de un notebook de Colab
(`modelo_analisis_geoespacial (2).ipynb`, 4 celdas). No las tres sirven igual:

| Capa | Qué es hoy | Destino |
| --- | --- | --- |
| **Dato** | `data/denue_cdmx.parquet` (462,732 filas), `data/denue_construccion.parquet` (20,957), ETL probado en `scripts/convertir_denue_a_parquet.py` | ✅ **Se reusa tal cual.** Se le agrega un paso `parquet → sqlite` |
| **Agente** | Celda 4: grafo LangGraph de 3 nodos (`check_website` → `search` → `analyze`, o `draft`) sobre Groq | ✅ **Se porta casi 1:1** a `api/services/prospeccion_agente.py` |
| **Interfaz** | `ipyleaflet` + `ipywidgets` | ❌ **Se reescribe.** `ipywidgets` solo existe dentro de un kernel de Jupyter; no se puede embeber en la plataforma |

La reescritura de la interfaz es la parte barata: `ipyleaflet` **es** Leaflet, y la plataforma
ya carga sus librerías por CDN (*Skill: Monolithic Frontend Mastery*, `AGENTS.md`).

| Notebook | Plataforma |
| --- | --- |
| `Map(basemap=CartoDB.Positron)` | `L.map` + tiles CartoDB |
| `MarkerCluster` | `Leaflet.markercluster` |
| `DrawControl` (polígono / rectángulo) | `Leaflet.draw` |
| `gdf.geometry.within(poligono)` | `turf.booleanPointInPolygon` en el navegador |
| `Dropdown` / `SelectMultiple` | Controles Vue, como el resto de `index.html` |
| `widgets.Password` para la Groq API | `GROQ_API_KEY` del servidor. **La clave nunca baja al navegador** |
| `crawl4ai` + Playwright | Caché precalculada + `urllib` + Tavily (§4, D3) |

---

## 2. Evidencia medida

### 2.1 Por qué pandas no puede vivir en la función serverless

```bash
pip3 download --no-deps --dest /tmp/whl pandas pyarrow numpy
# desempaquetadas:
#   pandas 3.0.5   →  42 MB
#   numpy  2.4.6   →  58 MB
#   pyarrow 25.0.1 → 152 MB
#                    ──────
#                    251 MB
```

El límite de una serverless function de Vercel es **250 MB descomprimidos**. Esas tres
solas ya lo rebasan, antes de `fastapi`, `supabase`, `sqlalchemy`, `psycopg` y `langchain`,
que ya están en `api/requirements.txt`. **Leer el Parquet desde la API queda descartado.**

### 2.2 El SQLite del catálogo: peso y tiempos reales

Construido desde `data/denue_construccion.parquet` con 14 de las 42 columnas y 3 índices
(`municipio`, `codigo_act`, `latitud+longitud`):

```
20,957 filas  →  5,255,168 bytes (5.0 MB)
```

Consultado con `sqlite3` de la **biblioteca estándar** (sin pandas, sin dependencias nuevas):

| Consulta | Filas | Tiempo |
| --- | ---: | ---: |
| `SELECT DISTINCT municipio` (catálogo de alcaldías) | 16 | 2.9 ms |
| `SELECT DISTINCT nombre_act` (catálogo de giros) | 99 | 13.8 ms |
| Filtro alcaldía + giro (`Miguel Hidalgo` + `%ferreter%`) | 207 | 3.8 ms |
| Bbox del mapa (`lat/lon BETWEEN`, `LIMIT 3000`) | 3,000 | 10.7 ms |
| Conteo de 11+ personas con algún contacto | 1,972 | 4.9 ms |

Ese **1,972** es exactamente la cifra que publica el README de `ModeloGeo`, recalculada
desde el archivo: el dato cuadra con su documentación.

### 2.3 El scraper sin navegador: qué cubre y qué no

Prueba contra sitios reales del DENUE con `urllib.request` + `html.parser` (biblioteca
estándar, techo de 400 KB, timeout de 8 s):

```
[OK]    WWW.GRUPOLAFE.COM        777 ms      443 chars
[OK]    NORSK.MX                 430 ms    2,484 chars
[OK]    WWW.ADTEC.COM.MX         662 ms       16 chars   ← arma su contenido con JS
[FALLA] WWW.2MARQUITECTOS.COM               404          ← sitio muerto
```

La lectura honesta: la biblioteca estándar resuelve la mayoría en menos de un segundo, y
queda un residuo real —páginas que dependen de JS y sitios caídos— que necesita otra ruta.

### 2.4 Cifras del universo de datos

| | Valor | Fuente |
| --- | ---: | --- |
| Establecimientos de construcción (CDMX) | 20,957 | medido |
| Con teléfono | 8,170 | medido |
| Con correo | 7,324 | medido |
| **Con sitio web** | **2,848** | medido |
| URLs que traen esquema `http(s)` | **10** de 2,848 | medido |
| Proveedores de 11+ personas con contacto | 1,972 | medido |

Las dos últimas filas mandan sobre el diseño: hay que anteponer el esquema a casi todas
las URLs, y **el scraping aplica solo al 13.6% de los registros**.

---

## 3. Arquitectura: el reparto de responsabilidades

La idea que sortea los dos obstáculos es una sola: **sacar el trabajo pesado del runtime**.

```
   FUERA DE LÍNEA (local / CI)                EN VERCEL                    NAVEGADOR
   ───────────────────────────                ─────────                    ─────────
   CSV del INEGI (248 MB)
        │ pandas + pyarrow
        ▼
   denue_construccion.parquet ──┐
        │                       │
        │ (paso nuevo)          │
        ▼                       │
   denue.sqlite (5 MB) ─────────┼──► api/services/prospeccion.py ──► GET /api/geo/*
        ▲                       │        (sqlite3 estándar)              │
        │                       │                                        ▼
   enriquecimiento web ─────────┘                                   Leaflet + Vue
   (crawl4ai + Playwright,                api/services/                  │
    2,848 sitios)                         prospeccion_agente.py ◄────────┘
        │                                   (langgraph + groq)      POST /api/geo/agente
        ▼                                          │
   caché de texto ──────────────────────────────────┤
                                                    ▼
                                            Supabase (PostgrestEngine)
                                            tabla geo_prospectos
                                            = lo que la empresa genera
```

| Componente | Dónde corre | Dependencias |
| --- | --- | --- |
| ETL `csv → parquet → sqlite` | Local / CI | pandas, pyarrow |
| Enriquecimiento web (2,848 sitios) | Local / CI / GitHub Action | crawl4ai, playwright |
| API de lectura del catálogo | Vercel | `sqlite3` (estándar) |
| Estado del prospecto | Vercel → Supabase | `PostgrestEngine` (ya existe) |
| Agente | Vercel | `langgraph`, `langchain-groq` (ya están) + `urllib` |
| Mapa | Navegador | Leaflet + markercluster + draw + turf, por CDN |

> **Dependencias nuevas en `api/requirements.txt`: ninguna.** Es el criterio de aceptación
> arquitectónico de todo este plan. Si una fase lo rompe, la fase está mal diseñada.

---

## 4. Decisiones de diseño

### D1 · El catálogo del DENUE viaja como SQLite de solo lectura en el bundle

**Alternativas:** (a) Parquet + pandas en la API — descartada por §2.1; (b) tabla en
Supabase — viable pero paga red y carga inicial para leer un dato que nunca cambia entre
publicaciones del INEGI; (c) SQLite en el bundle.

**Elegida: (c).** 5.0 MB, consultas de 3–14 ms con la biblioteca estándar (§2.2), cero
infraestructura, cold start plano. El costo real —"actualizar el dato exige desplegar"— es
irrelevante: **el INEGI publica el DENUE cada semestre.**

**Cuándo se revisa:** si se quiere el DENUE nacional o varias entidades. Extrapolando el
CDMX completo (462,732 filas) el archivo rondaría los **110 MB** —cifra estimada, no
medida—: todavía bajo el límite, pero ya incómodo en un repositorio. Ese es el disparador
para mover el catálogo a Supabase. Como el acceso queda detrás de un repositorio con
interfaz (§6.3), migrar es cambiar una implementación, no la vista.

### D2 · El dato que genera la empresa sí va a Supabase

El DENUE es de terceros, público e inmutable. Lo que la empresa produce encima —prospecto
contactado, asignado a un vendedor, cotización ligada, notas— es nuestro y mutable. **Se
separan.** Así el dato del INEGI no entra a los respaldos de la empresa, y no se suben
21,000 filas a Supabase solo para leerlas.

No hay que inventar la maquinaria: `backend/core/engine.py` ya define el protocolo
`DataEngine`; `backend/core/engines/postgrest.py` habla con Supabase por `urllib` estándar
—elegido justamente porque respeta el proxy HTTPS de este entorno, ver su docstring—; y
`backend/core/engines/memoria.py` es el doble de pruebas que `tests/conftest.py` fuerza con
`BACKEND_ENGINE=memoria`. **R7 se cumple sin escribir nada nuevo.**

### D3 · El scraping se precalcula fuera de línea; en vivo es la excepción

Los sitios son un conjunto finito y conocido: **2,848** (§2.4). Scrapear en tiempo real
significa el vendedor esperando 5–30 s y el agente colgado de que un sitio ajeno responda.
Tres capas, en orden de costo:

1. **Caché precalculada.** Un job corre *fuera de Vercel* —local, `ModeloGeo` o un GitHub
   Action, donde crawl4ai y Playwright funcionan sin límite de bundle— y guarda el texto
   extraído. La plataforma lee caché → LLM. Se re-corre cuando el INEGI publique.
2. **Fetch en vivo con biblioteca estándar** para "no está en caché" o "refréscalo".
   Medido en §2.3.
3. **Tavily** cuando 1 y 2 no dan texto. Ya es dependencia declarada, `TAVILY_API_KEY` ya
   está en `.env.example` y hay precedente de uso en `api/engineering_agent.py:107`
   (`research_node`). Resuelve justamente el caso de las páginas con JS.

El grafo apenas cambia: `check_website` pasa de dos ramas a tres estados —caché / fetch /
sin dato— y `analyze_node` y `draft_node` quedan idénticos.

### D4 · Sin PostGIS y sin GeoPandas

A esta escala no hacen falta. El bbox con índice B-tree sobre `latitud, longitud` responde
en 10.7 ms (§2.2) y el punto-en-polígono lo resuelve el navegador con `turf.js`, sin viaje
al servidor. Si algún día hiciera falta, SQLite trae R*Tree y Supabase trae PostGIS; no se
paga hoy.

### D5 · La clave de Groq es del servidor

El notebook la pide en un `widgets.Password` y —peor— tiene una clave real escrita en un
comentario al final de la celda 4. En la plataforma sale de `GROQ_API_KEY`, igual que en
`api/ai_utils.py`. Ver Fase 0.

---

## 5. Los dos obstáculos, resueltos

| Obstáculo | Cómo se sortea | Evidencia |
| --- | --- | --- |
| **crawl4ai + Playwright no caben en Vercel** (250 MB, sin binario de Chromium) | Se saca el scraping del runtime: caché precalculada fuera de línea (2,848 sitios, conjunto finito) + `urllib` estándar en vivo + Tavily de respaldo | §2.3, D3 |
| **Dónde vive el dato** (pandas+pyarrow+numpy = 251 MB) | pandas y pyarrow se quedan en el ETL. Al runtime llega un SQLite de 5 MB consultado con la biblioteca estándar; lo mutable va a Supabase por el motor que ya existe | §2.1, §2.2, D1, D2 |

---

## 6. Contratos

### 6.1 API (`api/main.py` + `api/services/prospeccion.py`)

| Método y ruta | Entrada | Salida |
| --- | --- | --- |
| `GET /api/geo/catalogo` | — | `{ alcaldias: [16], giros: [99] }` |
| `GET /api/geo/establecimientos` | `alcaldia`, `giros[]`, `personal_min`, `solo_con_contacto`, `bbox`, `limite` | `{ total, mostrados, items: [...] }` |
| `POST /api/geo/seleccion` | GeoJSON del polígono dibujado | Los establecimientos dentro, para exportar |
| `POST /api/geo/agente` | `{ establecimiento_id, consulta }` | `{ tipo: "analisis"\|"correo", texto, fuente: "cache"\|"web"\|"tavily"\|"sin_web" }` |
| `POST /api/geo/prospecto` | `{ establecimiento_id, estado, vendedor, nota }` | Escribe en `geo_prospectos` (Supabase) |

`items` lleva solo lo que pinta el mapa: `id`, `nom_estab`, `nombre_act`, `per_ocu`,
`telefono`, `correoelec`, `www`, `municipio`, `latitud`, `longitud`. Nunca las 42 columnas.

La envoltura de respuesta sigue la del resto de la plataforma (`docs/API_CONTRACT.md` §1) y
los endpoints nuevos se documentan también en `docs/openapi.yaml` (R9).

### 6.2 Datos

**SQLite en el bundle** (`api/data/denue.sqlite`, generado, versionado):

```sql
CREATE TABLE denue (
  id TEXT PRIMARY KEY, nom_estab TEXT, nombre_act TEXT, codigo_act TEXT,
  per_ocu TEXT, telefono TEXT, correoelec TEXT, www TEXT,
  municipio TEXT, nom_vial TEXT, numero_ext TEXT, cod_postal TEXT,
  latitud REAL, longitud REAL
);
CREATE INDEX idx_mun ON denue(municipio);
CREATE INDEX idx_act ON denue(codigo_act);
CREATE INDEX idx_geo ON denue(latitud, longitud);
```

`cod_postal` va como **TEXT** a propósito: el README de `data/` de `ModeloGeo` documenta que
los ceros a la izquierda del INEGI (`"09"`, `"017"`, `"15700"`) son la trampa clásica de
estos datos, y el ETL ya los preserva. No se rompe aquí.

**Supabase** (DDL nuevo, va a `docs/DDL_PENDIENTE.sql` para que lo aplique el dueño):

```sql
CREATE TABLE geo_prospectos (
  denue_id      TEXT PRIMARY KEY,   -- id del DENUE; no hay FK, viven en bases distintas
  estado        TEXT NOT NULL,      -- NUEVO | CONTACTADO | COTIZANDO | DESCARTADO
  vendedor      TEXT,
  nota          TEXT,
  web_cache     TEXT,               -- texto extraído del sitio (D3, capa 1)
  web_cache_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 6.3 Capas internas (R9)

```
api/main.py              ← rutas, validación, HTTP
  └─ api/services/prospeccion.py         ← reglas y consultas (recibe el repositorio)
       ├─ api/services/denue_repo.py     ← única que sabe que hay un SQLite
       └─ backend/... (DataEngine)       ← única que sabe que hay un Supabase
  └─ api/services/prospeccion_agente.py  ← el grafo; recibe llm y extractor inyectados
```

Ninguna capa de arriba conoce a `sqlite3` ni a `urllib`. Es lo que hace que D1 sea
reversible y que las pruebas no necesiten red ni base.

---

## 7. Frontend: los puntos de sutura exactos

La plataforma ya tiene el hueco hecho; son tres cortes y ninguno toca lo existente.

| # | Archivo | Punto | Cambio |
| --- | --- | --- | --- |
| 1 | `api/main.py:145` (`api_get_system_config`) | Junto a `kpi_module`, `wo_module` | Declarar el módulo y agregarlo a las ramas de rol que corresponda |
| 2 | `index.html:8285` (`openModule`) | Cadena de `else if` | `else if (m.type === 'geo_prospect_view') { currentView.value = 'PROSPECCION_GEO'; cargarCatalogoGeo(); }` |
| 3 | `index.html` | Junto a `v-if="currentView === 'KPI_DASHBOARD'"` (línea 1405) | El panel del mapa |
| 4 | `api_service.js` | Adaptador `GoogleScriptRunAdapter` | Métodos `apiGeoCatalogo`, `apiGeoEstablecimientos`, `apiGeoAgente` |
| 5 | `index.html` `<head>` | CDN | `leaflet`, `leaflet.markercluster`, `leaflet-draw`, `turf` |

```python
# api/main.py — el módulo
geo_module = { "id": "PROSPECCION_GEO", "label": "Prospección", "icon": "fa-map-marked-alt",
               "color": "#20c997", "type": "geo_prospect_view" }
```

Las CDN nuevas hay que sumarlas al caché de `tests/conftest.py` (intercepta las peticiones
externas del navegador para que la suite corra sin red); si no, las pruebas de UI fallan por
una razón ajena al código.

**Decisión pendiente del dueño (§11):** qué roles ven el módulo. La propuesta es `ADMIN`,
`ADMIN_CONTROL` y las cuentas de compras/ventas; no `STAFF_USER` genérico.

---

## 8. Plan por fases

Cada fase entrega algo que funciona y se puede mergear sola. Ninguna deja el repositorio en
un estado peor que el anterior (§4 del documento de restricciones, la regla del trinquete).

### Fase 0 — Rotar la clave expuesta 🔴 *bloqueante*

La celda 4 de `modelo_analisis_geoespacial (2).ipynb` termina con una API key de Groq real
escrita en un comentario (`gsk_kWd297…`, dos ocurrencias en el archivo). Está en el archivo
y en el historial de git de `ModeloGeo`.

1. Revocarla y emitir una nueva en la consola de Groq. **Esto lo hace el dueño, no un agente.**
2. Borrar las dos ocurrencias del notebook.
3. Purgar el historial de `ModeloGeo` o, si el repositorio es privado y el dueño lo acepta,
   dejar constancia de la revocación en el PR. Con la clave ya revocada, la exposición
   histórica deja de ser explotable.
4. Verificar con `gitleaks` (la puerta vigente por R7).

**No se empieza la Fase 1 antes de que la clave esté revocada.** Ninguna otra fase toca esa
clave, así que el riesgo no baja solo con el tiempo.

**Esfuerzo: 0.5 día.** Repositorio: `ModeloGeo`.

### Fase 1 — El dato: `parquet → sqlite`

**Repositorio: `ModeloGeo`.** Entregables:

- `scripts/construir_sqlite.py`: lee el Parquet, escribe `denue.sqlite` con el esquema de
  §6.2. Determinista: dos corridas sobre el mismo Parquet producen el mismo archivo (R8).
- Pruebas en `tests/test_construir_sqlite.py`, en el estilo del ETL que ya existe:
  - las 20,957 filas llegan completas;
  - `cod_postal` conserva los ceros a la izquierda (`"15700"`, no `15700`);
  - los índices existen y una consulta por alcaldía los usa (`EXPLAIN QUERY PLAN`);
  - el conteo de 11+ personas con contacto da 1,972 — el número de §2.2 fijado como prueba.
- El artefacto se copia a `HOLTMONT-PYTHON/api/data/denue.sqlite`.

**Criterio de aceptación:** `python -m pytest tests/ -v` verde en `ModeloGeo`, y el SQLite
pesa < 8 MB.

**Esfuerzo: 1 día.**

### Fase 2 — Backend de lectura

**Repositorio: `HOLTMONT-PYTHON`.** Entregables:

- `api/services/denue_repo.py`: abre el SQLite en modo solo lectura
  (`file:…?mode=ro`, `uri=True`), conexión cacheada por proceso.
- `api/services/prospeccion.py`: catálogo, filtros, bbox, selección por polígono.
- Rutas `GET /api/geo/catalogo` y `GET /api/geo/establecimientos` en `api/main.py`.
- `docs/openapi.yaml` y `docs/API_CONTRACT.md` actualizados (R9).
- Pruebas `tests/test_prospeccion_geo.py` contra un SQLite de **fixture** de ~20 filas
  construido en el `tmp_path` de la prueba —no contra el archivo de 5 MB—: filtros,
  paginación, límites, bbox, y qué pasa con parámetros basura.

**Criterio de aceptación:** `./run_tests.sh` verde; sin dependencias nuevas en
`api/requirements.txt`; ningún endpoint devuelve las 42 columnas.

**Esfuerzo: 1.5 días.**

### Fase 3 — El mapa en `index.html`

**Repositorio: `HOLTMONT-PYTHON`.** Entregables: los 5 cortes de §7 — módulo en `/api/config`,
rama en `openModule`, panel con Leaflet + cluster + draw, métodos en `api_service.js`, CDN
en el `<head>` y en el caché de `conftest.py`.

Paridad funcional con el notebook: filtro por alcaldía y por giro, clustering, dibujo de
polígono con conteo, ficha del negocio al hacer clic. El techo de 2,000 marcadores del
notebook se sustituye por carga por bbox: se pide lo que cabe en la vista actual.

- Prueba de UI con Playwright, como las que ya existen: el módulo aparece para el rol
  correcto, el mapa monta, un filtro reduce el conteo.
- Escenario Gherkin en `tests/features/` para la regla de negocio: *"solo se ofrecen como
  prospecto los establecimientos con al menos un dato de contacto"* (R2).

**Criterio de aceptación:** `./run_tests.sh` verde, incluidas las pruebas de UI. Si fallan
por falta del binario de Playwright, es fallo de entorno y se reporta como tal — no se
excluye la prueba (Directiva Cero).

**Esfuerzo: 2.5 días.**

### Fase 4 — El agente

**Repositorio: `HOLTMONT-PYTHON`.** Entregables:

- `api/services/prospeccion_agente.py`: el grafo portado, con `llm` y `extractor`
  **inyectados** (mismo patrón que `api/services/plano.py` con `llm_disponible()`), para que
  las pruebas corran sin red y sin clave.
- `api/services/extractor_web.py`: `urllib` + `html.parser` con la lista de defensas de §9.
- Ruta `POST /api/geo/agente`; caché de texto leída de `geo_prospectos.web_cache` (D2).
- Job de enriquecimiento en `ModeloGeo` (`scripts/enriquecer_sitios.py`) que llena la caché
  con crawl4ai fuera de línea.
- Pruebas con dobles: sitio con caché, sitio sin web (rama `draft`), sitio que responde 404,
  sitio que devuelve 16 caracteres → cae a Tavily. Los cuatro casos salen de §2.3: son
  comportamientos observados, no imaginados.

**Criterio de aceptación:** ninguna prueba abre una conexión de red; el endpoint degrada con
`success: false` y un motivo accionable en vez de lanzar 500 (mismo criterio que
`/api/plano_2d`).

**Esfuerzo: 2 días.**

### Fase 5 — El puente con el negocio

Sin esto el módulo es un mapa bonito. Entregables:

- `POST /api/geo/prospecto` sobre `geo_prospectos` (D2), con `MemoryEngine` en pruebas.
- Exportar la selección del polígono a CSV/XLSX.
- Botón "solicitar cotización" que lleva el correo redactado por el agente al circuito que
  ya existe (`api/services/correo.py`).

**Esfuerzo: 1.5–2 días.**

### Resumen

| Fase | Repositorio | Esfuerzo | Bloquea a |
| --- | --- | ---: | --- |
| 0 · Rotar la clave | ModeloGeo | 0.5 d | **todo** |
| 1 · `parquet → sqlite` | ModeloGeo | 1 d | 2 |
| 2 · Backend de lectura | HOLTMONT | 1.5 d | 3, 4 |
| 3 · Mapa en `index.html` | HOLTMONT | 2.5 d | 5 |
| 4 · Agente | HOLTMONT | 2 d | 5 |
| 5 · Puente con el negocio | HOLTMONT | 1.5–2 d | — |
| | | **9–9.5 d** | |

Las fases 3 y 4 son paralelizables una vez cerrada la 2.

---

## 9. Seguridad

### SSRF — obligatorio antes de mergear la Fase 4

`api/services/extractor_web.py` recibe una URL que viene del dato del INEGI y, en el peor
caso, del usuario. Es SSRF de manual. La prueba de §2.3 ya usa techo de bytes y timeout;
falta el resto:

- [ ] Lista blanca de esquemas: solo `http` y `https`.
- [ ] Resolver el DNS y **rechazar** IP privadas, loopback, link-local y metadata (`169.254.169.254`).
- [ ] No seguir redirecciones hacia destinos internos (revalidar en cada salto).
- [ ] Timeout corto (8 s) y tope de lectura (400 KB) — ya probados.
- [ ] `User-Agent` identificable y respeto de `robots.txt`.
- [ ] Revisión con el agente `security-reviewer` antes del merge.

### Secretos

- Fase 0 (clave de Groq del notebook) es bloqueante.
- `GROQ_API_KEY` y `TAVILY_API_KEY` salen del entorno. Nada de claves en el navegador (D5).
- El SQLite del catálogo es dato público del INEGI: no lleva nada de la empresa.

### Datos personales

El DENUE es público y abierto, y el `data/README.md` de `ModeloGeo` deja constancia de que
no contiene datos de particulares. Aun así, usar esos correos para contacto comercial cae
bajo la LFPDPPP: los correos redactados por el agente deben identificar a la empresa y
ofrecer una vía de baja. **Es una decisión del dueño, no del código** (§11).

---

## 10. Cómo se cumple el trinquete

`RESTRICCIONES_EXTREMAS.md` §4 fija los pisos vigentes: **708 pruebas Python** y **87 GAS**
(`CLAUDE.md` menciona 706; se toma la medición real al abrir la rama, con el comando exacto
del workflow — nunca uno parecido), cobertura con ramas **≥ 60%**, **≥ 90% sobre el diff**,
`ruff` **≤ 51** hallazgos.

Qué implica para este trabajo:

- Cada fase **suma** pruebas; ninguna las resta. El conteo sube en cada PR.
- El código nuevo nace con cobertura alta por diseño: la lógica vive en servicios puros con
  el repositorio y el LLM inyectados, así que se prueba sin red, sin base y sin clave.
- Dos módulos que hoy están en 0% —`backend/core/engines/postgrest.py` y el resto de la
  lista de §4— se rozan en la Fase 5. Si el diff los toca, se cubren; si no, no se tocan.
- Ninguna función nueva pasa de complejidad B. `apply_batch_update` (F, 53) es deuda
  inventariada, no un permiso.
- **Directiva Cero:** si una puerta se cierra, se arregla el código o se detiene y se
  reporta. Ni `skip`, ni `noqa`, ni bajar un umbral, ni `continue-on-error`.

Antes de reportar cualquier fase como terminada:

```bash
./run_tests.sh
ruff check api backend streamlit_cotizador tests
```

con la salida real pegada en el PR, y las 5 preguntas de calidad respondidas en español
(`AGENTS.md` §8).

---

## 11. Decisiones que necesitan al dueño

| # | Decisión | Propuesta | Bloquea |
| --- | --- | --- | --- |
| 1 | Revocar la clave de Groq expuesta | Hacerlo hoy | Todo |
| 2 | ¿Qué roles ven el módulo? | `ADMIN`, `ADMIN_CONTROL` y cuentas de compras/ventas | Fase 3 |
| 3 | ¿Se purga el historial de `ModeloGeo` o basta la revocación? | Revocar + constancia si el repo es privado | Fase 0 |
| 4 | Alcance: ¿solo construcción CDMX o todo el DENUE? | Empezar con construcción CDMX (D1) | Fase 1 |
| 5 | Texto legal de baja en los correos del agente | Definirlo antes de que salga el primer correo | Fase 5 |
| 6 | ¿`ModeloGeo` sigue como repositorio aparte? | Sí: es el laboratorio del dato y del ETL; la plataforma consume su artefacto | Fase 1 |

---

## 12. Riesgos

| Riesgo | Probabilidad | Qué haríamos |
| --- | --- | --- |
| El bundle de Vercel se acerca al límite por otra causa | Media | El SQLite son 5 MB y no hay dependencias nuevas; el margen lo consumen las que ya están. Se mide antes de la Fase 2 con un despliegue de prueba |
| Muchos sitios con JS que `urllib` no puede leer | **Alta** (medida: 1 de 4) | Ya está previsto: Tavily es la tercera capa (D3) |
| Sitios caídos en el DENUE | **Alta** (medida: 1 de 4) | La caché guarda también el fallo, con fecha, para no reintentar en cada consulta |
| La suite de UI falla por el binario de Playwright | Alta en este contenedor | Es fallo de entorno documentado en §4; se instala en CI, no se excluye la prueba |
| El INEGI cambia el formato del CSV | Baja (semestral) | El ETL de `ModeloGeo` ya tiene pruebas que lo detectan al regenerar |

---

## 13. Definición de "hecho"

Una fase está terminada cuando, y solo cuando:

- [ ] `./run_tests.sh` corre completo y su salida real está pegada en el PR.
- [ ] `ruff check api backend streamlit_cotizador tests` no sube de 51 hallazgos.
- [ ] El conteo de pruebas subió respecto al piso vigente.
- [ ] Hay prueba unitaria por comportamiento nuevo y escenario Gherkin por regla de negocio.
- [ ] `api/requirements.txt` no creció.
- [ ] Las 5 preguntas de calidad están respondidas en español y con especificidad.
- [ ] La declaración de Directiva Cero está firmada en el PR.

---

## Anexo · Reproducir las mediciones

```bash
# §2.1 — peso de las ruedas
pip3 download --no-deps --dest /tmp/whl pandas pyarrow numpy
cd /tmp/whl && for w in *.whl; do python3 -m zipfile -e "$w" "/tmp/unz/${w%%-*}"; done
du -sh /tmp/unz/*

# §2.2 — SQLite: se construye desde el Parquet de ModeloGeo y se cronometra
#          con sqlite3 de la biblioteca estándar (ver Fase 1)

# §2.3 — extracción sin navegador
#          urllib.request + html.parser, techo de 400 KB, timeout de 8 s

# §2.4 — cifras del universo
python -c "import pandas as pd; d=pd.read_parquet('data/denue_construccion.parquet'); \
print(d.shape, d.www.notna().sum(), d.telefono.notna().sum(), d.correoelec.notna().sum())"
```
