// El origen de la pagina es siempre el de la API: `vercel.json` sirve
// `index.html`, este archivo y `api/main.py` bajo el mismo dominio, y en local
// FastAPI publica los tres. No hay ningun despliegue donde diverjan.
//
// Antes se fijaba `http://localhost:8000` a mano cuando el host era `localhost`
// o `127.0.0.1`, ignorando el puerto real. Arrancar en cualquier otro puerto
// dejaba el login roto de forma dificil de diagnosticar: el `fetch` salia hacia
// un puerto vacio, no se registraba ninguna peticion a `/api/` y la pantalla
// solo decia "Connection Error: TypeError: Failed to fetch".
const API_BASE_URL = window.location.origin;
window.API_BASE_URL = API_BASE_URL; // Ensure global visibility

// Ensure window.google structure exists for localhost
if (!window.google) window.google = {};
if (!window.google.script) window.google.script = {};

class ApiService {
    static async runPaperclipAgents(requestText) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/run_paperclip_agency`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: requestText })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Error en Paperclip Agency');
            return data;
        } catch (error) {
            console.error('Error running Paperclip Agency:', error);
            throw error;
        }
    }

    // Plano 2D y escena 3D de la Descripción del Trabajo a Realizar. Antes esto
    // lo resolvía el navegador llamando a `image.pollinations.ai`, que devolvía
    // una ilustración sin escala ni cotas; ahora lo calcula el backend y las dos
    // vistas salen de la misma geometría.
    static async generarPlano2D(descripcion) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/plano_2d`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ descripcion: descripcion })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Error generando el plano');
            return data;
        } catch (error) {
            console.error('Error generando plano 2D:', error);
            throw error;
        }
    }

    // --- Prospección geoespacial (DENUE) -------------------------------
    //
    // Van aquí y NO en `GoogleScriptRunAdapter` a propósito. El adaptador imita
    // `google.script.run`, y todo lo que el frontend invoca por ese puente debe
    // existir como función en `CODIGO.js` — lo verifica la prueba 7.1 de
    // `tests/gas/run_tests.js`. Estas dos lecturas no tienen equivalente en
    // Apps Script y no pueden tenerlo: el catálogo es un SQLite dentro del
    // bundle de Vercel. Ponerlas en el adaptador habría roto ese contrato; es
    // el mismo motivo por el que `generarPlano2D` vive en esta clase.

    /** Alcaldías y giros del catálogo, para los combos del mapa. */
    static async geoCatalogo() {
        try {
            const response = await fetch(`${API_BASE_URL}/api/geo/catalogo`);
            return await response.json();
        } catch (e) {
            return { success: false, message: "Connection Error: " + e.toString() };
        }
    }

    /**
     * Establecimientos que pasan los filtros del mapa.
     *
     * Recibe un objeto y no argumentos posicionales porque son siete filtros y
     * casi todos opcionales: posicionalmente, agregar el octavo obligaría a
     * tocar todas las llamadas.
     *
     * Tres detalles del contrato que se resuelven aquí y no en el componente:
     *
     *  - `giros` viaja como el MISMO parámetro repetido (`?giros=A&giros=B`),
     *    que es lo que FastAPI lee como lista. Un `giros=A,B` llegaría como una
     *    sola cadena y no emparejaría con ningún giro del DENUE.
     *  - Los valores vacíos NO se mandan. `alcaldia=` es una alcaldía llamada
     *    cadena vacía y devolvería cero establecimientos; omitir el parámetro
     *    es lo que significa "sin filtrar".
     *  - `bbox` es `lat_min,lon_min,lat_max,lon_max` — el orden del INEGI y de
     *    Leaflet, no el de GeoJSON, que pone la longitud primero.
     */
    static async geoEstablecimientos(filtros) {
        const f = filtros || {};
        const params = new URLSearchParams();
        if (f.alcaldia) params.append('alcaldia', f.alcaldia);
        (f.giros || []).forEach(giro => { if (giro) params.append('giros', giro); });
        if (f.personal_min) params.append('personal_min', String(f.personal_min));
        if (f.solo_con_contacto) params.append('solo_con_contacto', 'true');
        if (f.bbox) params.append('bbox', f.bbox);
        if (f.limite) params.append('limite', String(f.limite));
        if (f.desplazamiento) params.append('desplazamiento', String(f.desplazamiento));
        try {
            const response = await fetch(
                `${API_BASE_URL}/api/geo/establecimientos?${params.toString()}`);
            return await response.json();
        } catch (e) {
            return { success: false, message: "Connection Error: " + e.toString() };
        }
    }

    /** Marca el estado comercial de un establecimiento (`geo_prospectos`). */
    static async geoProspecto(payload) {
        return ApiService._geoPost('/api/geo/prospecto', payload);
    }

    /** El agente: analiza el sitio del negocio o redacta el correo de contacto. */
    static async geoAgente(payload) {
        return ApiService._geoPost('/api/geo/agente', payload);
    }

    // --- Agente de Consultas (/api/agente) -------------------------------
    // Reutilizan `_geoPost`: es un POST con JSON y una respuesta con `success`,
    // exactamente la misma forma. Duplicarlo con otro nombre solo daría dos
    // sitios donde arreglar el manejo de error de red.

    /** Pregunta en lenguaje natural sobre `tasks` o `quotes`. */
    static async agenteConsulta(payload) {
        return ApiService._geoPost('/api/agente/consulta', payload);
    }

    /** Los departamentos que menciona una respuesta del agente. */
    static async agenteAreas(payload) {
        return ApiService._geoPost('/api/agente/areas', payload);
    }

    /** Un borrador de correo por área, para revisarlos antes de mandarlos. */
    static async agenteBorradores(payload) {
        return ApiService._geoPost('/api/agente/borradores', payload);
    }

    /**
     * Qué le falta al agente para funcionar: modelo, base, función RPC y tablas.
     *
     * Es GET y no POST —no cambia nada— y por eso no puede reutilizar
     * `_geoPost`. Existe en el navegador, y no solo como ruta que alguien abre
     * a mano, porque el aviso de error no distingue "falta ejecutar el DDL" de
     * "la SUPABASE_URL apunta a otro sitio": esta llamada sí, y quien ve el
     * error es justo quien necesita esa respuesta.
     */
    static async agenteDiagnostico() {
        try {
            const response = await fetch(`${API_BASE_URL}/api/agente/diagnostico`);
            return await response.json();
        } catch (e) {
            return { success: false, message: "Connection Error: " + e.toString() };
        }
    }

    /** Aplica un cambio a UN borrador; los demás no se tocan. */
    static async agenteCambioBorrador(payload) {
        return ApiService._geoPost('/api/agente/borrador', payload);
    }

    /** Manda los correos ya aprobados por una persona. */
    static async agenteEnviar(payload) {
        return ApiService._geoPost('/api/agente/enviar', payload);
    }

    /** La solicitud de cotización. Hoy vuelve bloqueada: falta el aviso legal. */
    static async geoSolicitarCotizacion(payload) {
        return ApiService._geoPost('/api/geo/solicitar_cotizacion', payload);
    }

    static async _geoPost(ruta, payload) {
        try {
            const response = await fetch(`${API_BASE_URL}${ruta}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload || {})
            });
            return await response.json();
        } catch (e) {
            return { success: false, message: "Connection Error: " + e.toString() };
        }
    }

    /**
     * Descarga la selección del polígono como CSV o XLSX.
     *
     * El archivo lo arma el servidor y baja como binario, así que aquí NO se
     * puede hacer `res.json()`: hay que mirar el `content-type` para distinguir
     * el archivo del error. Un `{success:false}` interpretado como archivo se
     * descargaría como un CSV con el mensaje de error dentro, y eso parece un
     * archivo bueno hasta que alguien lo abre.
     */
    static async geoExportarSeleccion(payload, formato) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/geo/seleccion`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(Object.assign({}, payload, { formato: formato }))
            });
            if ((response.headers.get('content-type') || '').includes('application/json')) {
                return await response.json();
            }
            ApiService._descargar(await response.blob(), `prospectos.${formato}`);
            return { success: true };
        } catch (e) {
            return { success: false, message: "Connection Error: " + e.toString() };
        }
    }

    static _descargar(blob, nombre) {
        const url = URL.createObjectURL(blob);
        const enlace = document.createElement('a');
        enlace.href = url;
        enlace.download = nombre;
        document.body.appendChild(enlace);
        enlace.click();
        enlace.remove();
        // Sin revocar, cada exportación deja el archivo entero retenido en
        // memoria hasta que se recargue la pestaña.
        URL.revokeObjectURL(url);
    }

    /**
     * Sube un archivo DIRECTO a Storage con una URL firmada.
     *
     * Por qué no basta `uploadFileToDrive`: ahí el archivo viaja en base64
     * dentro del JSON de la petición, y ese JSON es el cuerpo de una función
     * serverless de Vercel, que la plataforma corta en 4.5 MB. Base64 infla
     * 4/3, así que por esa vía no pasa un adjunto de más de ~3.3 MB — el 413
     * lo emite la plataforma antes de ejecutar nada, y su respuesta ni
     * siquiera es JSON. Ese es el "no me deja cargar archivos pesados" de
     * BUG-0009.
     *
     * Aquí el servidor solo firma la ruta y los bytes van del navegador a
     * Storage, sin pasar por la función. Devuelve `{success, fileUrl}`, la
     * misma forma que `uploadFileToDrive`, para que quien la llame no tenga
     * que distinguir.
     */
    static async subirArchivoDirecto(file, client) {
        if (!file) return { success: false, message: 'No se eligió ningún archivo.' };
        let firma;
        try {
            const response = await fetch(`${API_BASE_URL}/api/legacy/uploadUrl`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: file.name, client: client || null })
            });
            firma = await response.json();
        } catch (e) {
            return { success: false, message: 'No se pudo preparar la subida: ' + e.toString() };
        }
        if (!firma || !firma.success || !firma.uploadUrl) {
            return { success: false, message: (firma && firma.message) || 'No se pudo preparar la subida.' };
        }
        if (firma.maxBytes && file.size > firma.maxBytes) {
            return { success: false, message: `El archivo pesa ${file.size} bytes y el máximo es ${firma.maxBytes}.` };
        }
        try {
            const subida = await fetch(firma.uploadUrl, {
                method: 'PUT',
                headers: { 'Content-Type': file.type || 'application/octet-stream' },
                body: file
            });
            if (!subida.ok) {
                // El cuerpo de Storage puede no ser JSON; el estado sí dice algo.
                return { success: false, message: `Storage rechazó el archivo (HTTP ${subida.status}).` };
            }
        } catch (e) {
            return { success: false, message: 'No se pudo subir el archivo: ' + e.toString() };
        }
        return { success: true, fileUrl: firma.fileUrl, path: firma.path };
    }

    static async login(username, password) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
            if (!response.ok) throw new Error("Network response was not ok");
            return await response.json();
        } catch (e) {
            return { success: false, message: "Connection Error: " + e.toString() };
        }
    }

    static async fetchSheetData(sheetName) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/data?sheet=${encodeURIComponent(sheetName)}`);
            if (!response.ok) throw new Error("Network response was not ok");
            return await response.json();
        } catch (e) {
            return { success: false, message: "Connection Error: " + e.toString() };
        }
    }
}

/**
 * Adapter to mimic google.script.run for easy migration.
 * Allows using the new Python backend without rewriting all Vue components.
 */
class GoogleScriptRunAdapter {
    constructor() {
        this._successHandler = (res) => console.log("Success:", res);
        this._failureHandler = (err) => console.error("Failure:", err);
    }

    withSuccessHandler(fn) {
        const newAdapter = new GoogleScriptRunAdapter();
        newAdapter._successHandler = fn;
        newAdapter._failureHandler = this._failureHandler;
        return newAdapter;
    }

    withFailureHandler(fn) {
        const newAdapter = new GoogleScriptRunAdapter();
        newAdapter._successHandler = this._successHandler;
        newAdapter._failureHandler = fn;
        return newAdapter;
    }

    // --- Mapped Methods ---

    apiLogin(username, password) {
        ApiService.login(username, password)
            .then(res => this._successHandler(res))
            .catch(err => this._failureHandler(err));
    }

    apiFetchStaffTrackerData(sheetName) {
        ApiService.fetchSheetData(sheetName)
            .then(res => this._successHandler(res))
            .catch(err => this._failureHandler(err));
    }

    /**
     * Helper interno: llama a un endpoint y enruta la respuesta a los
     * handlers de éxito/fallo, igual que google.script.run.
     */
    _call(path, options) {
        fetch(`${API_BASE_URL}${path}`, options)
            .then(res => res.json())
            .then(data => this._successHandler(data))
            .catch(err => this._failureHandler(err));
    }

    _post(path, body) {
        this._call(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
    }

    /**
     * Operación de ESCRITURA todavía no portada a FastAPI.
     *
     * Antes estos métodos respondían `{success: true}` sin persistir nada: el
     * frontend marcaba la fila como guardada (`_isNew = false`), limpiaba el
     * borrador local y el usuario se quedaba con la impresión de haber guardado.
     * Se perdía el dato en silencio.
     *
     * Ahora devuelven la envoltura de error estándar, que el frontend ya sabe
     * mostrar, para que la pérdida sea visible mientras se completa la
     * migración (ver docs/PLAN_BACKEND_PYTHON.md, Fase 5).
     */
    _noPortado(nombre) {
        const message = `"${nombre}" aún no está disponible en el backend Python. ` +
            `El cambio NO se guardó; usa la versión de Google Apps Script para esta operación.`;
        console.error(`[api_service] ${nombre}: operación de escritura no portada.`);
        this._successHandler({ success: false, message: message, _notImplemented: true });
    }

    /** Operación de LECTURA no portada: se responde vacío, pero avisando. */
    _lecturaVacia(nombre, extra) {
        console.warn(`[api_service] ${nombre}: lectura no portada, se devuelve vacío.`);
        this._successHandler(Object.assign(
            { success: true, data: [], _notImplemented: true },
            extra || {}
        ));
    }

    apiLogout(username) {
        // El original registra LOGOUT en LOG_SISTEMA. `system_log` guarda 16.196
        // accesos historicos y sin esto solo se anotaba la mitad del par.
        this._post('/api/legacy/logout', { username: username || '' });
    }

    /**
     * `username` no es opcional en la práctica.
     *
     * El frontend siempre lo manda —`loadConfig(r, u)` llama a
     * `getSystemConfig(r, u)`—, pero este método lo declaraba con un solo
     * parámetro y el segundo argumento se perdía en silencio. Sin él el backend
     * no puede resolver el tracker propio de un STAFF_USER ni las ramas que el
     * original cablea por cuenta (JUANY_RODRIGUEZ, JESUS_CANTU).
     */
    getSystemConfig(role, username) {
        const params = new URLSearchParams({ role: role || '', username: username || '' });
        fetch(`${API_BASE_URL}/api/config?${params}`)
            .then(res => res.json())
            .then(data => this._successHandler(data))
            .catch(err => this._failureHandler(err));
    }

    apiFetchPPCData() {
        this._call('/api/legacy/ppcData');
    }

    /**
     * Transcripción de audio. Conserva el nombre de la función de Apps Script
     * porque es el que invoca `index.html` en sus dos rutas de voz (el selector
     * de archivo de audio y la grabadora de micrófono), pero por debajo usa el
     * endpoint propio de Python: Groq-Whisper, no Gemini.
     *
     * Dos diferencias de contrato que hay que salvar aquí y no en el frontend:
     *
     *  - GAS recibía `(base64, mimeType)` como argumentos posicionales; el
     *    endpoint espera `multipart/form-data` con un archivo. Se reconstruye
     *    el binario desde el base64.
     *  - GAS devolvía **el texto pelado**, y el handler del frontend lo
     *    concatena directo en el textarea (`textoActual + textoTranscrito`).
     *    El endpoint responde `{success, transcription, data}`, así que se
     *    entrega solo `transcription`. Devolver el objeto escribiría
     *    "[object Object]" en el campo CONCEPTO.
     */
    transcribirConGemini(base64Data, mimeType) {
        try {
            const binario = atob(base64Data);
            const bytes = new Uint8Array(binario.length);
            for (let i = 0; i < binario.length; i++) bytes[i] = binario.charCodeAt(i);

            const tipo = mimeType || 'audio/webm';
            // Solo es el respaldo: si el servidor tiene ffmpeg, normaliza el
            // audio y renombra el archivo. Cuando no lo tiene, Whisper decide
            // por la extensión, así que conviene que sea coherente.
            const extension = (tipo.split('/')[1] || 'webm').split(';')[0];
            const cuerpo = new FormData();
            cuerpo.append('file', new Blob([bytes], { type: tipo }), `audio.${extension}`);

            fetch(`${API_BASE_URL}/api/transcribe_and_analyze`, { method: 'POST', body: cuerpo })
                .then(res => res.json())
                .then(data => {
                    if (data && data.success) {
                        this._successHandler(data.transcription || '');
                    } else {
                        this._failureHandler(new Error((data && (data.message || data.detail)) || 'No se pudo transcribir el audio.'));
                    }
                })
                .catch(err => this._failureHandler(err));
        } catch (err) {
            this._failureHandler(err);
        }
    }

    apiUpdateTask(sheet, data, user) {
        this._post('/api/legacy/updateTask', { sheetName: sheet, task: data, username: user });
    }

    /**
     * Mismo endpoint que `apiUpdateTask`, con el nombre que usa `saveRow()`.
     *
     * `saveRow` (index.html) es el botón de guardar de cada fila del tracker y
     * llama a `internalUpdateTask`, no a `apiUpdateTask`. En Apps Script eso
     * funciona porque todas las funciones de `CODIGO.js` viven en el scope
     * global; aquí el adaptador es una clase, y un método que no existe no es
     * `undefined`: la llamada lanza `TypeError` de forma **sincrónica**, así que
     * `withFailureHandler` no lo captura.
     *
     * El daño no era solo que no guardaba: `saveRow` pone `row._isSaving` e
     * `isSubmitting` en `true` antes de llamar, y solo los repone dentro de los
     * handlers. Al reventar antes, ambos quedaban en `true` para siempre — el
     * spinner no cerraba y su propia guarda de entrada
     * (`if (row._isSaving || isSubmitting.value) return`) bloqueaba **todo**
     * guardado posterior de la aplicación hasta recargar la página.
     */
    internalUpdateTask(sheet, data, user) {
        this.apiUpdateTask(sheet, data, user);
    }

    apiSavePPCData(payload, activeUser) {
        fetch(`${API_BASE_URL}/api/savePPC`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ payload, activeUser })
        })
        .then(res => res.json())
        .then(data => this._successHandler(data))
        .catch(err => this._failureHandler(err));
    }

    apiGetNextWorkOrderSeq() {
        fetch(`${API_BASE_URL}/api/nextSeq`)
        .then(res => res.json())
        .then(seq => this._successHandler(seq))
        .catch(err => this._failureHandler(err));
    }

    // --- Pendientes de portar (Fase 5 de docs/PLAN_BACKEND_PYTHON.md) ---

    apiFetchCombinedCalendarData(target) {
        this._call(`/api/legacy/combinedCalendar?sheet=${encodeURIComponent(target || '')}`);
    }

    apiFetchCascadeTree() {
        this._call('/api/legacy/cascadeTree');
    }

    apiFetchDrafts() {
        this._call('/api/legacy/drafts');
    }

    apiFetchInfoBankData(year, month, company, folder) {
        const params = new URLSearchParams({
            year: year || '', month: month || '',
            company: company || '', folder: folder || ''
        });
        this._call(`/api/legacy/infoBankData?${params}`);
    }

    apiFetchProjectTasks(projectName) {
        this._call(`/api/legacy/projectTasks?projectName=${encodeURIComponent(projectName || '')}`);
    }

    // Escrituras: fallan de forma visible en vez de fingir éxito.

    /**
     * Subida de archivos, ahora contra Supabase Storage.
     *
     * Era el último stub del adaptador. Antes de la Fase 0 devolvía una
     * `fileUrl` inventada que se guardaba en la base como si el archivo
     * existiera; después pasó a fallar de forma visible. Ahora sube de verdad.
     *
     * El cuarto argumento (`client`) no lo manda el frontend todavía: cuando se
     * pasa, el archivo cae en la estructura del banco de información
     * (AÑO/MES/CLIENTE) en vez de en AÑO/MES.
     */
    uploadFileToDrive(data, type, name, client) {
        this._post('/api/legacy/upload', {
            data: data, type: type || null, name: name || null, client: client || null
        });
    }

    /** archiveFile + processQuoteRow: reubica un archivo ya subido. */
    apiArchiveQuoteFile(fileUrl, client, date) {
        this._post('/api/legacy/archiveQuote', {
            fileUrl: fileUrl, client: client, date: date || null
        });
    }

    /** apiFetchTrackerProductivityMetrics: métricas sin disparar el correo. */
    apiFetchTrackerProductivityMetrics(params) {
        const p = params || {};
        this._call(`/api/legacy/trackerProductivityMetrics?month=${p.month || ''}&year=${p.year || ''}`);
    }

    apiAddEmployee(employee) {
        const e = employee || {};
        this._post('/api/legacy/addEmployee', {
            name: e.name || '', dept: e.dept || '', type: e.type || 'ESTANDAR'
        });
    }

    apiDeleteEmployee(name) {
        this._post('/api/legacy/deleteEmployee', { name: name || '' });
    }

    apiSaveProjectTask(row, projectName, username) {
        this._post('/api/legacy/saveProjectTask', { task: row, projectName: projectName, username: username });
    }

    apiSaveSubProject(data) {
        const d = data || {};
        this._post('/api/legacy/saveSubProject', {
            parentId: d.parentId || d.siteId || '',
            name: d.name || '',
            type: d.type || null,
            createdBy: d.createdBy || null
        });
    }

    apiSaveSite(data) {
        const d = data || {};
        this._post('/api/legacy/saveSite', {
            name: d.name || '',
            client: d.client || '',
            type: d.type || null,
            createdBy: d.createdBy || null
        });
    }

    apiFetchWeeklyPlanData(username) {
        this._call(`/api/legacy/weeklyPlan?username=${encodeURIComponent(username || '')}`);
    }

    apiUpdatePPCV3(row, username) {
        this._post('/api/legacy/updatePPCV3', { task: row, username: username });
    }

    apiFetchUnifiedAgenda(username) {
        this._call(`/api/legacy/unifiedAgenda?username=${encodeURIComponent(username || '')}`);
    }

    apiFetchSalesHistory() {
        this._call('/api/legacy/salesHistory');
    }

    apiSaveTrackerBatch(sheetName, data, username) {
        this._post('/api/legacy/saveTrackerBatch', {
            sheetName: sheetName,
            tasks: Array.isArray(data) ? data : [data],
            username: username
        });
    }

    // --- Agente de métricas de cotizaciones ---

    apiFetchQuoteAgentMetrics(params) {
        const p = params || {};
        this._call(`/api/legacy/quoteMetrics?month=${p.month || ''}&year=${p.year || ''}`);
    }

    runQuoteMetricsAgent(params) {
        this._post('/api/legacy/runQuoteAgent', params || {});
    }

    apiGetLastAgentReport() {
        this._call('/api/legacy/lastAgentReport');
    }

    apiWriteQuoteMetricsToSheet(params) {
        this._post('/api/legacy/writeQuoteMetrics', params || {});
    }

    apiCheckGeminiKey() {
        this._call('/api/legacy/geminiKey');
    }

    apiSaveGeminiKey(key) {
        this._post('/api/legacy/geminiKey', { key: key });
    }

    runTrackerProductivityAgent(params) {
        this._post('/api/legacy/trackerProductivity', params || {});
    }

    // --- Directorio, auditoría y banco de información ---

    apiResyncDirectory() {
        this._post('/api/legacy/resyncDirectory', {});
    }

    apiLogDateChange(payload, username) {
        this._post('/api/legacy/logDateChange', { payload: payload, username: username });
    }

    apiFetchInfoBankCompanies(year, month) {
        this._call(`/api/legacy/infoBankCompanies?year=${encodeURIComponent(year)}&month=${encodeURIComponent(month)}`);
    }

    runPaperclipAgents(text) {
        this._post('/api/run_paperclip_agency', { text: text });
    }

    apiSaveHabitLog(payload) {
        const p = payload || {};
        this._post('/api/legacy/habitLog', { payload: p, username: p.USUARIO || p.usuario || '' });
    }

    apiSavePersonalEvent(payload) {
        const p = payload || {};
        this._post('/api/legacy/personalEvent', { payload: p, username: p.USUARIO || p.usuario || '' });
    }

    apiSyncDrafts(drafts) {
        this._post('/api/legacy/syncDrafts', { drafts: drafts || [] });
    }

    apiClearDrafts() {
        this._post('/api/legacy/clearDrafts', {});
    }
}

// Expose to window

// Expose to window
window.google = window.google || {};
window.google.script = window.google.script || {};
window.google.script.run = new GoogleScriptRunAdapter();
