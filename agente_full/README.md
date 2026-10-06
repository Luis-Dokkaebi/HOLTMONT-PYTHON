# Dashboard de la Pre Work Order (`Agente_Full`)

Adaptación de `gs3.py` a la Pre Work Order: cada vez que alguien sube un
documento con datos (xlsx, xls, csv, pdf, docx) a la PWO, tres agentes de
Gemini convierten ese documento en una app de Streamlit, se valida y se publica
en **una liga corta que siempre enseña el último dashboard bueno**.

```
PWO (HOLTMONT) ──sube documento──▶ Supabase Storage
   └─▶ POST /api/pwo/dashboard ──repository_dispatch──▶ Action de Agente_Full
          Agente 1 (extrae JSON) ▶ Agente 2 (diseña) ▶ Agente 3 (programa)
          ▶ sintaxis + AppTest + Playwright, hasta 4 intentos
          ▶ commit de app.py + requirements.txt
   Streamlit Cloud redespliega ▶ https://<subdominio>.streamlit.app (la liga corta)
```

Si el dashboard nuevo falla las pruebas 4 veces, **no se publica**: el Action
termina en rojo y la liga sigue mostrando el anterior.

## Archivos (esta carpeta → raíz de `Agente_Full`)

| Aquí | En `Agente_Full` |
| --- | --- |
| `pipeline_dashboard.py` | `pipeline_dashboard.py` |
| `requirements-pipeline.txt` | `requirements-pipeline.txt` |
| `workflow_dashboard_pwo.yml` | `.github/workflows/dashboard-pwo.yml` |

`app.py` y `requirements.txt` de `Agente_Full` los escribe el Action; no se
editan a mano. Las pruebas del pipeline viven en HOLTMONT-PYTHON
(`tests/test_agente_full_pipeline.py`, `tests/test_agente_full_navegador.py`):
si cambias el pipeline, cámbialo aquí, corre `./run_tests.sh` y vuelve a copiarlo.

## Configuración, una sola vez

### 1. Rotar las credenciales que venían en `gs3.py`

`gs3.py` traía en claro un token de GitHub (`ghp_…`) y tres API keys de Gemini,
y circuló por WhatsApp. **Asúmelas comprometidas:**

- GitHub → Settings → Developer settings → Personal access tokens: revocar el `ghp_…`.
- Google AI Studio / Cloud Console: borrar las tres keys y crear nuevas.

El pipeline ya no necesita ningún token de GitHub: el commit lo hace el
`GITHUB_TOKEN` del propio Action.

### 2. Secretos y variables en `Agente_Full`

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

1. New app → repositorio `Agente_Full`, rama principal, archivo `app.py`.
2. Settings → General → **Custom subdomain** (p. ej. `holtmont-pwo`): esa es la
   liga corta, `https://holtmont-pwo.streamlit.app`. No cambia entre despliegues.
3. **Los datos de la PWO son de clientes** (costos, cotizaciones). El dashboard
   los lleva incrustados en `app.py`. Si el repositorio es público, cualquiera
   los lee en GitHub y en la liga. Recomendado: repositorio privado y, en
   Settings → Sharing, limitar quién puede ver la app.

### 4. Variables en HOLTMONT (Vercel)

| Variable | Valor |
| --- | --- |
| `DASHBOARD_PWO_REPO` | `Luis-py-stack/Agente_Full` |
| `DASHBOARD_PWO_TOKEN` | token *fine-grained* solo para `Agente_Full`, permiso **Contents: Read and write** (lo pide el `repository_dispatch`) |
| `DASHBOARD_PWO_URL` | la liga corta del paso 3 |

Sin las tres, la PWO no dispara nada y el botón DASHBOARD queda desactivado.

## Prueba manual

Actions → **Dashboard PWO** → Run workflow → pega la URL pública de un `.xlsx`
del Storage. En 5–10 min la liga corta enseña el dashboard nuevo. Si falla, el
log del paso "Generar y validar el dashboard" trae el historial de los 4 intentos.

A mano, sin Action:

```bash
pip install -r requirements-pipeline.txt && playwright install chromium
export GEMINI_API_KEY=...            # una para los tres agentes
python pipeline_dashboard.py --archivo junta.xlsx --salida /tmp/dashboard
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
