const API_BASE_URL = (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://localhost:8000'
    : window.location.origin; // Configure this for production
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

    uploadFileToDrive(data, type, name) {
        // Devolver una fileUrl falsa era lo más dañino del adaptador: la URL
        // inventada se guardaba en la base como si el archivo existiera.
        this._noPortado('uploadFileToDrive');
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
