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
        this._successHandler = fn;
        return this; // Chainable
    }

    withFailureHandler(fn) {
        this._failureHandler = fn;
        return this; // Chainable
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
        // This is complex logic in GAS. For now, we might need to implement it in backend too.
        // Or return a mock config.
        console.warn("getSystemConfig not fully implemented in backend yet.");
        // Mock response for testing UI
        this._successHandler({
            departments: { "TEST": { label: "Test Dept", icon: "fa-cogs", color: "blue" } },
            staff: [],
            directory: [],
            specialModules: []
        });
    }

    apiFetchPPCData() {
         console.warn("apiFetchPPCData not implemented");
         this._successHandler({ success: true, data: [] });
    }

    apiUpdateTask(sheet, data, user) {
        console.warn("apiUpdateTask not implemented");
        this._successHandler({ success: true });
    }
}

// Expose to window
// Use: google.script.run = new GoogleScriptRunAdapter();
