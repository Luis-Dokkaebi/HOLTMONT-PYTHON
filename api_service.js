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

    // Stubs for other methods to prevent crashes during partial migration
    apiLogout(username) {
        console.log("Logout:", username);
        // No callback usually needed for logout in this app flow
    }

    getSystemConfig(role) {
        fetch(`${API_BASE_URL}/api/config?role=${encodeURIComponent(role)}`)
            .then(res => res.json())
            .then(data => this._successHandler(data))
            .catch(err => this._failureHandler(err));
    }

    apiFetchPPCData() {
         console.warn("apiFetchPPCData not implemented");
         this._successHandler({ success: true, data: [] });
    }

    apiUpdateTask(sheet, data, user) {
        this._post('/api/legacy/updateTask', { sheetName: sheet, task: data, username: user });
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

    // --- Stubs to prevent crashes ---

    apiFetchCombinedCalendarData(target) {
        console.warn("apiFetchCombinedCalendarData stub called");
        this._successHandler({ success: true, data: [] });
    }

    apiFetchCascadeTree() {
        console.warn("apiFetchCascadeTree stub called");
        this._successHandler({ success: true, data: [] });
    }

    apiFetchDrafts() {
        console.warn("apiFetchDrafts stub called");
        this._successHandler({ success: true, data: [] });
    }

    apiFetchInfoBankData(year, month, company, folder) {
        console.warn("apiFetchInfoBankData stub called");
        this._successHandler({ success: true, data: [] });
    }

    uploadFileToDrive(data, type, name) {
        console.warn("uploadFileToDrive stub called");
        this._successHandler({ success: true, fileUrl: "http://mock.url/file" });
    }

    apiAddEmployee(employee) {
        console.warn("apiAddEmployee stub called");
        this._successHandler({ success: true });
    }

    apiDeleteEmployee(name) {
        console.warn("apiDeleteEmployee stub called");
        this._successHandler({ success: true });
    }

    apiFetchProjectTasks(projectName) {
        console.warn("apiFetchProjectTasks stub called");
        this._successHandler({ success: true, data: [], headers: [] });
    }

    apiSaveProjectTask(row, projectName, username) {
        console.warn("apiSaveProjectTask stub called");
        this._successHandler({ success: true });
    }

    apiSaveSubProject(data) {
        console.warn("apiSaveSubProject stub called");
        this._successHandler({ success: true });
    }

    apiSaveSite(data) {
        console.warn("apiSaveSite stub called");
        this._successHandler({ success: true });
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
        console.warn("apiSaveHabitLog stub called");
        this._successHandler({ success: true });
    }

    apiSavePersonalEvent(payload) {
        console.warn("apiSavePersonalEvent stub called");
        this._successHandler({ success: true });
    }

    apiSyncDrafts(drafts) {
        console.warn("apiSyncDrafts stub called");
        this._successHandler({ success: true });
    }

    apiClearDrafts() {
        console.warn("apiClearDrafts stub called");
        this._successHandler({ success: true });
    }
}

// Expose to window

// Expose to window
window.google = window.google || {};
window.google.script = window.google.script || {};
window.google.script.run = new GoogleScriptRunAdapter();
