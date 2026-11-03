# Dashboard de la Pre Work Order

Adaptación de `gs3.py` (actualizada a `gsai.py`) a la plataforma: cada vez que
alguien sube un documento con datos (xlsx, xls, csv, pdf, docx) a la PWO, o
ANTONIO_SALAZAR pulsa **Procesar** en el apartado **Dashboard Streamlit**, tres
agentes de Gemini convierten ese documento en una app de Streamlit, se valida y
se publica en **una liga corta que siempre enseña el último dashboard bueno**.

```
PWO / Dashboard Streamlit (HOLTMONT) ──sube documento──▶ Supabase Storage
   └─▶ POST /api/pwo/dashboard o /api/dashboard/procesar
          ──repository_dispatch──▶ .github/workflows/dashboard-pwo.yml (este repositorio)
          Agente 1 (extrae JSON) ▶ Agente 2 (diseña) ▶ Agente 3 (programa)
          (cada llamada a Gemini: hasta 4 reintentos con espera 1 s, 2 s, 4 s)
          ▶ sintaxis + AppTest + Playwright, hasta 3 intentos
          ▶ commit de app.py + requirements.txt en la rama dashboard-pwo
   Streamlit Cloud redespliega ▶ https://agentefull-mhytzkjfr38ukzqxnuxbkf.streamlit.app/
   El apartado pregunta cada 10 s (GET /api/dashboard/estado) hasta que la
   corrida termina y entonces enseña "¡Procesamiento Exitoso!" con la liga.
```

Si el dashboard nuevo falla las pruebas 3 veces, **no se publica**: el Action
termina en rojo y la liga sigue mostrando el anterior.

## Dónde vive cada cosa

Todo corre en **este repositorio** (HOLTMONT-PYTHON, privado). Antes el Action
vivía en `Agente_Full`, que es **público**: el dashboard lleva incrustados los
datos del cliente (costos, cotizaciones) y cualquiera los habría leído.

| Archivo | Para qué |
| --- | --- |
| `.github/workflows/dashboard-pwo.yml` | el Action; lo dispara el `repository_dispatch` de la API |
| `agente_full/pipeline_dashboard.py` | los tres agentes y las pruebas del dashboard |
| `agente_full/requirements-pipeline.txt` | dependencias del pipeline (no las de la API) |
| rama `dashboard-pwo` | `app.py` + `requirements.txt` que escribe el Action; Streamlit Cloud la sirve |

El Action **nunca toca `main`**: publica en la rama `dashboard-pwo`, que nace
huérfana (sin el código de la API). Así no choca con la protección de `main`,
no redespliega Vercel con cada dashboard y no pisa el `requirements.txt` de la
API. Además baja solo `agente_full/` (checkout parcial) y cierra el checkout al
usuario `pwo-sandbox`, para que el código generado no pueda leer el resto del
repositorio. Las pruebas de ese contrato están en `tests/test_dashboard_pwo.py`;
las del pipeline, en `tests/test_agente_full_pipeline.py` y
`tests/test_agente_full_navegador.py`.

## Configuración, una sola vez

### 1. Rotar las credenciales que venían en `gs3.py`

`gs3.py` traía en claro un token de GitHub (`ghp_…`) y tres API keys de Gemini,
y circuló por WhatsApp. **Asúmelas comprometidas:**

- GitHub → Settings → Developer settings → Personal access tokens: revocar el `ghp_…`.
- Google AI Studio / Cloud Console: borrar las tres keys y crear nuevas.

El pipeline ya no necesita ningún token de GitHub: el commit lo hace el
`GITHUB_TOKEN` del propio Action.

### 2. Secretos y variables en HOLTMONT-PYTHON

Settings → Secrets and variables → Actions:

| Tipo | Nombre | Valor |
| --- | --- | --- |
| Secret | `GEMINI_API_KEY_AGENT_1` | key nueva del Agente 1 |
| Secret | `GEMINI_API_KEY_AGENT_2` | key nueva del Agente 2 |
| Secret | `GEMINI_API_KEY_AGENT_3` | key nueva del Agente 3 |
| Variable | `ORIGEN_PERMITIDO` | `https://<proyecto>.supabase.co/storage/v1/object/public/` |
| Variable (opcional) | `GEMINI_MODEL` | por defecto `gemini-3.5-flash`, el de `gs3.py` |

`ORIGEN_PERMITIDO` es el único sitio del que el pipeline acepta descargar: la
URL pública del Storage de Holtmont (la misma `SUPABASE_URL` del despliegue).

### 3. Streamlit Community Cloud

La rama `dashboard-pwo` no existe hasta la primera corrida del Action: corre
primero la prueba manual (abajo) y después crea la app.

1. New app → repositorio `HOLTMONT-PYTHON`, rama **`dashboard-pwo`**, archivo
   `app.py`. Streamlit Cloud necesita permiso sobre repositorios privados
   (Settings → Linked accounts → GitHub).
2. Settings → General → **Custom subdomain** (p. ej. `holtmont-pwo`): esa es la
   liga corta, `https://holtmont-pwo.streamlit.app`. No cambia entre despliegues.
3. **Los datos de la PWO son de clientes** (costos, cotizaciones). El
   repositorio ya es privado, pero la liga de Streamlit es pública por defecto:
   en Settings → Sharing, limita quién puede ver la app.
4. Si la liga nueva no es la de siempre, ponla en `DASHBOARD_PWO_URL` (paso 4).
   La app vieja de `Agente_Full` se puede borrar para liberar su subdominio.

### 4. Variables en HOLTMONT (Vercel)

| Variable | Valor |
| --- | --- |
| `DASHBOARD_PWO_TOKEN` | **obligatoria.** Token *fine-grained* con *Resource owner* `Luis-Dokkaebi`, solo para `HOLTMONT-PYTHON`, permisos **Contents: Read and write** (lo pide el `repository_dispatch`) y **Actions: Read** (con él el apartado Dashboard Streamlit sabe cuándo terminó) |
| `DASHBOARD_PWO_REPO` | opcional; si no está, `Luis-Dokkaebi/HOLTMONT-PYTHON` |
| `DASHBOARD_PWO_URL` | opcional; si no está, la liga corta del paso 3: `https://agentefull-mhytzkjfr38ukzqxnuxbkf.streamlit.app/` |

Sin el token, la PWO no dispara nada, el botón DASHBOARD queda desactivado y el
apartado Dashboard Streamlit responde "Falta configurar DASHBOARD_PWO_TOKEN".
Vercel solo lee las variables al desplegar: después de agregarla (entorno
**Production**), **Redeploy**.

## Prueba manual

Actions → **Dashboard PWO** → Run workflow → pega la URL pública de un `.xlsx`
del Storage. En 5–10 min la liga corta enseña el dashboard nuevo. Si falla, el
log del paso "Generar y validar el dashboard" trae el historial de los 3 intentos.

A mano, sin Action:

```bash
pip install -r agente_full/requirements-pipeline.txt && playwright install chromium
export GEMINI_API_KEY=...            # una para los tres agentes
python agente_full/pipeline_dashboard.py --archivo junta.xlsx --salida /tmp/dashboard
streamlit run /tmp/dashboard/app.py
```

## Qué cambió frente a `gs3.py`

- Credenciales por secretos del Action, nunca en el código.
- El código que escribe el modelo se ejecuta **sin** las claves en el entorno
  (AppTest y `streamlit run` en un subproceso con entorno mínimo) y, en el
  Action, como el usuario `pwo-sandbox`, sin sudo. Lo segundo es necesario: con
  el mismo usuario, el código podía leer las claves en `/proc/<pid>/environ`
  del proceso padre (comprobado), y en los runners de GitHub `sudo` no pide
  contraseña. Si `USUARIO_AISLADO` no sirve, el pipeline no arranca.
- El documento solo se descarga del Storage de Holtmont, con tope de 20 MB y
  sin seguir redirecciones.
- Un documento ilegible detiene el pipeline en vez de publicar un dashboard
  sobre el mensaje de error.
- La auditoría en navegador usa los selectores de error de la versión actual
  de Streamlit; los de `gs3.py` ya no existían y un `st.error` pasaba sin verse.
- `requirements.txt` se publica con las versiones exactas que se validaron.
- `st.dataframe`/`st.plotly_chart` con `width="stretch"`
  (`use_container_width` está deprecado).

## Qué se tomó de `gsai.py` (2026-10-19)

- Cada llamada a Gemini pasa por `invocar_con_reintentos`: hasta 4 intentos con
  espera exponencial; una respuesta vacía (la de un filtro) cuenta como fallo.
  Si los 4 fallan, el Action termina en rojo sin tocar `app.py`.
- El Agente 3 se repara como máximo **3** veces (antes 4).
- El workflow lleva `run-name: Dashboard PWO <solicitud>`; sin esa línea el
  apartado Dashboard Streamlit no encuentra la corrida y, a los 3 minutos,
  avisa que GitHub no arrancó el procesamiento.
- Lo que `gsai.py` hacía distinto y **no** se tomó: el token de GitHub y las
  claves de Gemini en el código (siguen en secretos), el commit con la API de
  Git Data y un token personal (lo hace el `GITHUB_TOKEN` del Action), y los
  selectores de error de Playwright de una versión vieja de Streamlit.
