/**
 * Tuton Agent - API Client Module
 * Handles all communication with the Flask backend server.
 */

const API_BASE = "";  // Same origin, served by Flask

class ApiError extends Error {
    constructor(message, status = 500, data = null) {
        super(message);
        this.name = "ApiError";
        this.status = status;
        this.data = data;
    }
}

async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: {
            "Content-Type": "application/json",
            ...options.headers,
        },
        ...options,
    };

    try {
        const response = await fetch(url, config);
        const data = await response.json();

        if (!response.ok) {
            throw new ApiError(
                data.error || `HTTP ${response.status}`,
                response.status,
                data
            );
        }

        return data;
    } catch (error) {
        if (error instanceof ApiError) throw error;
        throw new ApiError("Network error: " + error.message, 0, error);
    }
}

// === Auth ===
const AuthAPI = {
    async login(username, password) {
        return apiRequest("/api/login", {
            method: "POST",
            body: JSON.stringify({ username, password }),
        });
    },

    async getConfig() {
        return apiRequest("/api/config");
    },

    async saveConfig(data) {
        return apiRequest("/api/config", {
            method: "POST",
            body: JSON.stringify(data),
        });
    },
};

// === Courses ===
const CoursesAPI = {
    async getAll() {
        return apiRequest("/api/courses");
    },

    async getSections(courseId) {
        return apiRequest(`/api/courses/${courseId}/sections`);
    },

    async getActivities(courseId) {
        return apiRequest(`/api/courses/${courseId}/activities`);
    },

    async deleteCourse(folder) {
        return apiRequest(`/api/courses/${encodeURI(folder)}`, {
            method: "DELETE",
        });
    },
};

// === Status ===
const StatusAPI = {
    async getAll() {
        return apiRequest("/api/status");
    },
};

// === Results ===
const ResultsAPI = {
    async getAll() {
        return apiRequest("/api/results");
    },

    async download(filepath) {
        const url = `/api/download/${encodeURI(filepath)}`;
        window.open(url, "_blank");
    },

    async delete(filepath) {
        return apiRequest(`/api/results/${encodeURI(filepath)}`, {
            method: "DELETE",
        });
    },
};

// === Run ===
const RunAPI = {
    async start(data) {
        return apiRequest("/api/run", {
            method: "POST",
            body: JSON.stringify(data),
        });
    },

    async getOutput() {
        return apiRequest("/api/run/output");
    },

    async getStatus() {
        return apiRequest("/api/run/status");
    },

    async stop() {
        return apiRequest("/api/run/stop", { method: "POST" });
    },
};

// === Schedule ===
const ScheduleAPI = {
    async get() {
        return apiRequest("/api/schedule");
    },

    async save(data) {
        return apiRequest("/api/schedule", {
            method: "POST",
            body: JSON.stringify(data),
        });
    },
};

// === Export to browser globals ===
window.ApiError = ApiError;
window.apiRequest = apiRequest;
window.AuthAPI = AuthAPI;
window.CoursesAPI = CoursesAPI;
window.StatusAPI = StatusAPI;
window.ResultsAPI = ResultsAPI;
window.RunAPI = RunAPI;
window.ScheduleAPI = ScheduleAPI;