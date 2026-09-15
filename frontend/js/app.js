/**
 * Tuton Agent - Main Application Module
 * Orchestrates all components and handles business logic.
 */

const appStore = window.store;
const appAuthAPI = window.AuthAPI;
const appCoursesAPI = window.CoursesAPI;
const appStatusAPI = window.StatusAPI;
const appResultsAPI = window.ResultsAPI;
const appRunAPI = window.RunAPI;
const appScheduleAPI = window.ScheduleAPI;
const appToast = window.Toast;
const appSpinner = window.Spinner;
const appTerminal = window.Terminal;
const appNavigation = window.Navigation;
const appTableRenderer = window.TableRenderer;
const appCardRenderer = window.CardRenderer;

// === DOM Elements ===
const elements = {
    loginView: null,
    appView: null,
    loginForm: null,
    usernameInput: null,
    passwordInput: null,
    loginBtn: null,
    terminalOutput: null,
    runBtn: null,
    runCourseId: null,
    runSesi: null,
    runForce: null,
    cronToggle: null,
    cronDay: null,
    cronTime: null,
    saveScheduleBtn: null,
    saveEnvBtn: null,
    clearTerminalBtn: null,
    statusTableBody: null,
    resultsGrid: null,
    statsCards: null,
};

function populateConfigForm(config) {
    const values = {
        nama: config.nama || "",
        nim: config.nim || "",
        prodi: config.prodi || "",
        moodle_url: config.base_url || "",
        moodle_session: "",
        opencode_model: config.model === "(default)" ? "" : (config.model || ""),
    };

    Object.entries(values).forEach(([name, value]) => {
        const input = document.querySelector(`[name="${name}"]`);
        if (input && value) input.value = value;
    });
}

// === Initialize DOM References ===
function initElements() {
    elements.loginView = document.getElementById("loginView");
    elements.appView = document.getElementById("appView");
    elements.loginForm = document.getElementById("loginForm");
    elements.usernameInput = document.getElementById("username");
    elements.passwordInput = document.getElementById("password");
    elements.loginBtn = document.getElementById("loginBtn");
    elements.terminalOutput = document.getElementById("terminal-output");
    elements.runBtn = document.getElementById("btnRun");
    elements.runCourseId = document.getElementById("runCourseId");
    elements.runSesi = document.getElementById("runSesi");
    elements.runForce = document.getElementById("runForce");
    elements.cronToggle = document.getElementById("cronToggle");
    elements.cronDay = document.getElementById("cronDay");
    elements.cronTime = document.getElementById("cronTime");
    elements.saveScheduleBtn = document.getElementById("btnSaveSchedule");
    elements.saveEnvBtn = document.getElementById("btnSaveEnv");
    elements.clearTerminalBtn = document.getElementById("clearTerminal");
    elements.statusTableBody = document.getElementById("statusTableBody");
    elements.resultsGrid = document.getElementById("resultsGrid");
    elements.statsCards = document.getElementById("statsCards");
}

// === Event Handlers ===
async function handleLogin(e) {
    e.preventDefault();

    const username = elements.usernameInput.value.trim();
    const password = elements.passwordInput.value.trim();

    if (!username || !password) {
        appToast.show("Username dan password wajib diisi", "error");
        return;
    }

    elements.loginBtn.innerHTML = `${appSpinner.create("sm")} Memverifikasi...`;
    elements.loginBtn.disabled = true;

    try {
        const result = await appAuthAPI.login(username, password);

        if (!result.success) {
            appToast.show(result.error || "Login gagal", "error");
            return;
        }

        const config = await appAuthAPI.getConfig();
        if (!config.has_session) {
            appToast.show("Session Moodle belum dikonfigurasi di Settings", "warning");
        }

        appStore.set("isLoggedIn", true);
        elements.loginView.classList.add("opacity-0");

        setTimeout(() => {
            elements.loginView.classList.add("hidden");
            elements.appView.classList.remove("hidden");
            appNavigation.switchTo("status", appStore);
            appToast.show("Berhasil login ke sistem");
            loadInitialData();
        }, 300);
    } catch (error) {
        appToast.show("Login gagal: " + error.message, "error");
    } finally {
        elements.loginBtn.innerHTML = `<span>Akses Sistem</span><i data-lucide="arrow-right" class="w-4 h-4"></i>`;
        elements.loginBtn.disabled = false;
        if (window.lucide) lucide.createIcons();
    }
}

function handleLogout() {
    appStore.set("isLoggedIn", false);
    elements.appView.classList.add("hidden");
    elements.loginView.classList.remove("hidden");
    elements.loginView.classList.remove("opacity-0");
    appToast.show("Sesi diakhiri");
}

async function loadInitialData() {
    appStore.set("isLoading", true);
    
    try {
        // Load config
        const config = await appAuthAPI.getConfig();
        appStore.set("config", config);
        populateConfigForm(config);
        
        // Load status
        await loadStatus();
        
        // Load results
        await loadResults();
        
        // Load courses for dropdown
        await loadCourses();
    } catch (error) {
        console.error("Failed to load initial data:", error);
        appToast.show("Gagal memuat data awal: " + error.message, "error");
    } finally {
        appStore.set("isLoading", false);
    }
}

async function loadCourses() {
    const select = elements.runCourseId;
    if (!select) return;

    try {
        const response = await appCoursesAPI.getAll();
        appStore.set("courses", response.courses || []);
        
        // Populate course dropdown
        select.disabled = false;
        select.innerHTML = '<option value="">Semua mata kuliah</option>';
        (response.courses || []).forEach((course) => {
            const option = document.createElement("option");
            option.value = course.id;
            option.textContent = `${course.name} (ID: ${course.id})`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error("Failed to load courses:", error);
        select.innerHTML = '<option value="">Course tidak tersedia - perbarui session Moodle</option>';
        select.disabled = true;
    }
}

async function loadStatus() {
    try {
        const response = await appStatusAPI.getAll();
        appStore.set("status", response);
        
        // Update stats cards
        updateStatsCards(response.stats);
        
        // Update table
        if (elements.statusTableBody) {
            elements.statusTableBody.innerHTML = appTableRenderer.renderStatusTable(response.items);
            if (window.lucide) lucide.createIcons();
        }
    } catch (error) {
        console.error("Failed to load status:", error);
    }
}

function updateStatsCards(stats) {
    if (!elements.statsCards) return;
    
    elements.statsCards.innerHTML = `
        <div class="bg-white p-6 rounded-2xl border border-gray-100 shadow-soft">
            <div class="w-12 h-12 rounded-full bg-green-50 text-green-600 flex items-center justify-center mb-4">
                <i data-lucide="check-circle-2" class="w-6 h-6"></i>
            </div>
            <p class="text-sm text-gray-500 font-medium mb-1">Pekerjaan Selesai</p>
            <p class="text-3xl font-bold text-gray-900">${stats.done}</p>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-gray-100 shadow-soft">
            <div class="w-12 h-12 rounded-full bg-red-50 text-red-600 flex items-center justify-center mb-4">
                <i data-lucide="x-circle" class="w-6 h-6"></i>
            </div>
            <p class="text-sm text-gray-500 font-medium mb-1">Pekerjaan Gagal</p>
            <p class="text-3xl font-bold text-gray-900">${stats.failed}</p>
        </div>
        <div class="bg-white p-6 rounded-2xl border border-gray-100 shadow-soft">
            <div class="w-12 h-12 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center mb-4">
                <i data-lucide="clock" class="w-6 h-6"></i>
            </div>
            <p class="text-sm text-gray-500 font-medium mb-1">Dalam Antrean</p>
            <p class="text-3xl font-bold text-gray-900">${stats.pending}</p>
        </div>
    `;
    
    if (window.lucide) lucide.createIcons();
}

async function loadResults() {
    try {
        const response = await appResultsAPI.getAll();
        appStore.set("results", response);
        
        if (elements.resultsGrid) {
            elements.resultsGrid.innerHTML = response.courses
                .map((course) => appCardRenderer.renderResultCard(course))
                .join("");
            
            if (window.lucide) lucide.createIcons();
        }
    } catch (error) {
        console.error("Failed to load results:", error);
    }
}

async function handleRun(e) {
    e.preventDefault();
    
    if (appStore.get("isRunning")) return;
    
    const courseId = elements.runCourseId.value ? parseInt(elements.runCourseId.value) : null;
    const sesi = elements.runSesi.value ? parseInt(elements.runSesi.value) : null;
    const force = elements.runForce.checked;
    
    // Build command string for display
    let cmdStr = "python main.py run";
    if (courseId) cmdStr += ` --course ${courseId}`;
    if (sesi) cmdStr += ` --sesi ${sesi}`;
    if (force) cmdStr += ` --force`;
    
    appTerminal.append(`user@tuton:~$ ${cmdStr}`, "cmd");
    
    // Disable button
    elements.runBtn.disabled = true;
    elements.runBtn.classList.add("opacity-75", "cursor-not-allowed");
    elements.runBtn.innerHTML = `${appSpinner.create("sm")} Mengeksekusi...`;
    if (window.lucide) lucide.createIcons();
    
    appStore.set("isRunning", true);
    appStore.set("runOutput", []);
    
    try {
        const response = await appRunAPI.start({ course_id: courseId, sesi, force });
        
        if (!response.success) {
            appTerminal.append(`Error: ${response.error}`, "error");
            appToast.show("Gagal memulai: " + response.error, "error");
            return;
        }
        
        // Start polling for output
        pollRunOutput();
    } catch (error) {
        appTerminal.append(`Error: ${error.message}`, "error");
        appToast.show("Gagal menjalankan agent: " + error.message, "error");
    }
}

let pollInterval = null;

function pollRunOutput() {
    pollInterval = setInterval(async () => {
        try {
            const response = await appRunAPI.getOutput();
            const newOutput = response.output || [];
            
            // Only append new lines
            const currentOutput = appStore.get("runOutput") || [];
            const newLines = newOutput.slice(currentOutput.length);
            
            newLines.forEach((line) => {
                let type = "info";
                if (line.includes("ERROR") || line.includes("Gagal") || line.includes("✗")) {
                    type = "error";
                } else if (line.includes("✓") || line.includes("Selesai") || line.includes("siap")) {
                    type = "success";
                } else if (line.includes("dilewati") || line.includes("timeout")) {
                    type = "warning";
                } else if (line.startsWith("user@tuton")) {
                    type = "cmd";
                }
                appTerminal.append(line, type);
            });
            
            appStore.set("runOutput", newOutput);
            
            // Check if process finished
            if (newOutput.length > 0) {
                const lastLine = newOutput[newOutput.length - 1];
                if (lastLine.includes("Selesai") || lastLine.includes("Gagal") || lastLine.includes("exit")) {
                    stopPolling();
                    onRunComplete();
                }
            }
        } catch (error) {
            console.error("Polling error:", error);
        }
    }, 1000);
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

async function onRunComplete() {
    appStore.set("isRunning", false);
    
    // Re-enable button
    elements.runBtn.disabled = false;
    elements.runBtn.classList.remove("opacity-75", "cursor-not-allowed");
    elements.runBtn.innerHTML = `<i data-lucide="play" class="w-5 h-5"></i> Jalankan Sekarang`;
    if (window.lucide) lucide.createIcons();
    
    // Refresh data
    await loadStatus();
    await loadResults();
    
    appToast.show("Run selesai dieksekusi");
}

async function handleStopRun() {
    try {
        await appRunAPI.stop();
        stopPolling();
        appTerminal.append("user@tuton:~$ Proses dihentikan oleh pengguna", "warning");
        appToast.show("Proses dihentikan");
    } catch (error) {
        appToast.show("Gagal menghentikan: " + error.message, "error");
    }
}

function handleClearTerminal() {
    appTerminal.clear();
}

async function handleSaveSchedule(e) {
    e.preventDefault();
    
    const enabled = elements.cronToggle.checked;
    const day = elements.cronDay.value;
    const time = elements.cronTime.value;
    
    elements.saveScheduleBtn.innerHTML = `${appSpinner.create("sm")} Menyimpan...`;
    elements.saveScheduleBtn.disabled = true;
    
    try {
        const response = await appScheduleAPI.save({ enabled, day, time });
        appToast.show(response.message);
        
        if (enabled) {
            appTerminal.append(`user@tuton:~$ Konfigurasi cron berhasil diperbarui. Agent akan berjalan ${day === "*" ? "setiap hari" : `hari ${day}`} pukul ${time} WIB.`, "success");
        } else {
            appTerminal.append(`user@tuton:~$ Konfigurasi cron dinonaktifkan.`, "warning");
        }
    } catch (error) {
        appToast.show("Gagal menyimpan jadwal: " + error.message, "error");
    } finally {
        elements.saveScheduleBtn.innerHTML = `<i data-lucide="save" class="w-4 h-4"></i> Simpan Jadwal`;
        elements.saveScheduleBtn.disabled = false;
        if (window.lucide) lucide.createIcons();
    }
}

async function handleSaveEnv(e) {
    e.preventDefault();
    
    const formData = new FormData(e.target);
    const data = {
        nama: formData.get("nama") || document.querySelector('[name="nama"]').value,
        nim: formData.get("nim") || document.querySelector('[name="nim"]').value,
        prodi: formData.get("prodi") || document.querySelector('[name="prodi"]').value,
        moodle_url: formData.get("moodle_url") || document.querySelector('[name="moodle_url"]').value,
        moodle_session: formData.get("moodle_session") || document.querySelector('[name="moodle_session"]').value,
        opencode_model: formData.get("opencode_model") || document.querySelector('[name="opencode_model"]').value,
    };
    
    elements.saveEnvBtn.innerHTML = `${appSpinner.create("sm")} Menyimpan...`;
    elements.saveEnvBtn.disabled = true;
    
    try {
        const response = await appAuthAPI.saveConfig(data);
        appToast.show("Settings berhasil disimpan");
        
        // Reload config
        const config = await appAuthAPI.getConfig();
        appStore.set("config", config);
        populateConfigForm(config);
    } catch (error) {
        appToast.show("Gagal menyimpan settings: " + error.message, "error");
    } finally {
        elements.saveEnvBtn.innerHTML = `<i data-lucide="save" class="w-5 h-5"></i> Simpan Settings`;
        elements.saveEnvBtn.disabled = false;
        if (window.lucide) lucide.createIcons();
    }
}

// === Tab Switching ===
function setupTabNavigation() {
    document.querySelectorAll(".nav-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
            const tabId = btn.id.replace("nav-", "");
            appNavigation.switchTo(tabId, appStore);
            
            // Load data for specific tabs
            if (tabId === "status") {
                loadStatus();
            } else if (tabId === "result") {
                loadResults();
            } else if (tabId === "run") {
                loadCourses();
            }
        });
    });
}

// === Initialize ===
function init() {
    initElements();
    
    // Check if already logged in
    if (appStore.get("isLoggedIn")) {
        elements.loginView.classList.add("hidden");
        elements.appView.classList.remove("hidden");
        loadInitialData();
    }
    
    // Event listeners
    elements.loginForm?.addEventListener("submit", handleLogin);
    elements.loginForm?.setAttribute("onsubmit", "return false;");
    elements.runBtn?.addEventListener("click", handleRun);
    elements.clearTerminalBtn?.addEventListener("click", handleClearTerminal);
    document.getElementById("envForm")?.addEventListener("submit", handleSaveEnv);
    
    // Tab navigation
    setupTabNavigation();
    
    // Logout button
    document.getElementById("logoutBtn")?.addEventListener("click", handleLogout);
    
    // Initialize Lucide icons
    if (window.lucide) {
        lucide.createIcons();
    }
    
    console.log("Tuton Agent initialized");
}

// Start when DOM is ready
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
} else {
    init();
}

// Export for global access (for inline onclick handlers)
window.Results = {
    download: (path) => appResultsAPI.download(path),
    async delete(path) {
        if (!window.confirm("Hapus file DOCX ini?")) return;
        try {
            await appResultsAPI.delete(path);
            appToast.show("File DOCX berhasil dihapus", "success");
            await loadResults();
        } catch (error) {
            appToast.show("Gagal menghapus file: " + error.message, "error");
        }
    },
    async deleteCourse(folder) {
        if (!window.confirm(`Hapus seluruh folder matkul "${folder}" beserta semua filenya?\nFolder ini akan dihapus permanen dari output/.`)) return;
        try {
            await appCoursesAPI.deleteCourse(folder);
            appToast.show("Matkul berhasil dihapus", "success");
            await loadResults();
        } catch (error) {
            appToast.show("Gagal menghapus matkul: " + error.message, "error");
        }
    },
};
window.handleLogin = handleLogin;
window.handleLogout = handleLogout;
window.handleRun = handleRun;
window.handleSaveSchedule = handleSaveSchedule;
window.handleEnvSave = handleSaveEnv;
window.clearTerminal = handleClearTerminal;
window.switchTab = (tabId) => appNavigation.switchTo(tabId, appStore);