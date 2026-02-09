const API_BASE_URL = 'http://localhost:8000'; // Configure this for production

class ApiService {
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
        console.warn("apiUpdateTask not implemented");
        this._successHandler({ success: true });
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
        console.warn("apiFetchWeeklyPlanData stub called");
        this._successHandler({ success: true, data: [], headers: [] });
    }

    apiUpdatePPCV3(row, username) {
        console.warn("apiUpdatePPCV3 stub called");
        this._successHandler({ success: true });
    }

    apiFetchSalesHistory() {
        console.warn("apiFetchSalesHistory stub called");
        this._successHandler({ success: true, data: {} });
    }

    apiSaveTrackerBatch(sheetName, data, username) {
        console.warn("apiSaveTrackerBatch stub called");
        this._successHandler({ success: true });
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
// Use: google.script.run = new GoogleScriptRunAdapter();
