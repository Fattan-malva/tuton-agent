/**
 * Tuton Agent - State Management Module
 * Centralized state store with reactive updates.
 */

class Store {
    constructor() {
        this.listeners = new Map();
        this.state = {
            // Auth
            isLoggedIn: localStorage.getItem("tuton_logged_in") === "true",
            config: {
                nama: "",
                nim: "",
                prodi: "",
                model: "",
                base_url: "",
                has_session: false,
            },
            
            // Data
            courses: [],
            status: null,
            results: null,
            activities: null,
            
            // UI
            currentTab: "status",
            isLoading: false,
            error: null,
            
            // Run
            isRunning: false,
            runOutput: [],
        };
    }

    get(key) {
        return this.state[key];
    }

    set(key, value) {
        const oldValue = this.state[key];
        this.state[key] = value;
        
        // Notify listeners
        const listeners = this.listeners.get(key) || [];
        listeners.forEach((fn) => fn(value, oldValue));
    }

    update(updates) {
        Object.entries(updates).forEach(([key, value]) => {
            this.set(key, value);
        });
    }

    on(key, fn) {
        if (!this.listeners.has(key)) {
            this.listeners.set(key, []);
        }
        this.listeners.get(key).push(fn);
    }

    off(key, fn) {
        const listeners = this.listeners.get(key) || [];
        const index = listeners.indexOf(fn);
        if (index > -1) {
            listeners.splice(index, 1);
        }
    }
}

// Create singleton store
const store = new Store();

// Persistence
store.on("isLoggedIn", (value) => {
    localStorage.setItem("tuton_logged_in", value.toString());
});

window.store = store;