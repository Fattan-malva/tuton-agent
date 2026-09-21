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
    cronNextRun: null,
    saveEnvBtn: null,
    clearTerminalBtn: null,
    statusTableBody: null,
    resultsGrid: null,
    statsCards: null,
    btnStopRun: null,
    runStatusBar: null,
    runStatusLabel: null,
    runStatusMeta: null,
    runProgressBar: null,
    runElapsed: null,
    runStep: null,
    runBadge: null,
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
    elements.cronNextRun = document.getElementById("cronNextRun");
    elements.saveEnvBtn = document.getElementById("btnSaveEnv");
    elements.clearTerminalBtn = document.getElementById("clearTerminal");
    elements.statusTableBody = document.getElementById("statusTableBody");
    elements.resultsGrid = document.getElementById("resultsGrid");
    elements.statsCards = document.getElementById("statsCards");
    elements.btnStopRun = document.getElementById("btnStopRun");
    elements.runStatusBar = document.getElementById("runStatusBar");
    elements.runStatusLabel = document.getElementById("runStatusLabel");
    elements.runStatusMeta = document.getElementById("runStatusMeta");
    elements.runProgressBar = document.getElementById("runProgressBar");
    elements.runElapsed = document.getElementById("runElapsed");
    elements.runStep = document.getElementById("runStep");
    elements.runBadge = document.getElementById("runBadge");
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
        
        // Load cron schedule config
        await loadSchedule();
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

async function loadSchedule() {
    try {
        const response = await appScheduleAPI.get();
        appStore.set("schedule", response);
        
        if (elements.cronToggle) elements.cronToggle.checked = !!response.enabled;
        if (elements.cronDay) elements.cronDay.value = response.day || "*";
        if (elements.cronTime) elements.cronTime.value = response.time || "02:00";
        updateCronNextRun(response);
    } catch (error) {
        console.error("Failed to load schedule:", error);
    }
}

function updateCronNextRun(schedule) {
    if (!elements.cronNextRun) return;
    const next = schedule && schedule.next_run ? schedule.next_run.replace("T", " ") : null;
    const lastStatus = schedule && schedule.last_status ? schedule.last_status : null;
    let text = "";
    if (next) {
        text = `Jadwal berikutnya: ${next} WIB`;
        if (lastStatus === "skipped_busy") text += " (terakhir: dilewati)";
    } else {
        text = "Cronjob nonaktif.";
    }
    elements.cronNextRun.textContent = text;
    elements.cronNextRun.classList.remove("hidden");
    if (elements.cronNextRun) {
        elements.cronNextRun.classList.toggle("text-success", !!next);
        elements.cronNextRun.classList.toggle("text-gray-500", !next);
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
        <div class="bg-surface/50 backdrop-blur-sm p-6 rounded-2xl border border-white/5 transition-all hover:border-success/30 hover:shadow-lg hover:shadow-success/5">
            <div class="w-12 h-12 rounded-xl bg-success/20 text-success flex items-center justify-center mb-4">
                <i data-lucide="check-circle-2" class="w-6 h-6"></i>
            </div>
            <p class="text-sm text-gray-400 font-medium mb-1">Pekerjaan Selesai</p>
            <p class="text-3xl font-bold text-white">${stats.done}</p>
        </div>
        <div class="bg-surface/50 backdrop-blur-sm p-6 rounded-2xl border border-white/5 transition-all hover:border-danger/30 hover:shadow-lg hover:shadow-danger/5">
            <div class="w-12 h-12 rounded-xl bg-danger/20 text-danger flex items-center justify-center mb-4">
                <i data-lucide="x-circle" class="w-6 h-6"></i>
            </div>
            <p class="text-sm text-gray-400 font-medium mb-1">Pekerjaan Gagal</p>
            <p class="text-3xl font-bold text-white">${stats.failed}</p>
        </div>
        <div class="bg-surface/50 backdrop-blur-sm p-6 rounded-2xl border border-white/5 transition-all hover:border-accent/30 hover:shadow-lg hover:shadow-accent/5">
            <div class="w-12 h-12 rounded-xl bg-accent/20 text-accent flex items-center justify-center mb-4">
                <i data-lucide="clock" class="w-6 h-6"></i>
            </div>
            <p class="text-sm text-gray-400 font-medium mb-1">Dalam Antrean</p>
            <p class="text-3xl font-bold text-white">${stats.pending}</p>
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
    appStore.set("stoppedByUser", false);
    resetRunProgress();
    showRunStatus(true);
    elements.runStatusLabel.textContent = "Menyiapkan…";
    elements.runElapsed.textContent = "00:00";
    
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
            const [statusRes, outputRes] = await Promise.all([
                appRunAPI.getStatus(),
                appRunAPI.getOutput(),
            ]);

            const newOutput = outputRes.output || [];
            const currentOutput = appStore.get("runOutput") || [];

            // Jika output server direset (mis. proses selesai/mulai ulang),
            // jangan potong buta — reset tampilan ke state baru.
            if (newOutput.length < currentOutput.length) {
                appTerminal.clear();
                appStore.set("runOutput", []);
                resetRunProgress();
            }

            const tail = appStore.get("runOutput") || [];
            const newLines = newOutput.slice(tail.length);

            newLines.forEach((line) => {
                let type = "info";
                if (line.includes("ERROR") || line.includes("Gagal") || line.includes("✗")) {
                    type = "error";
                } else if (line.includes("✓") || line.includes("Selesai") || line.includes("siap")) {
                    type = "success";
                } else if (line.includes("dilewati") || line.includes("timeout") || line.includes("BERHENTI")) {
                    type = "warning";
                } else if (line.startsWith("user@tuton")) {
                    type = "cmd";
                }
                appTerminal.append(line, type);
                updateRunProgress(line);
            });

            appStore.set("runOutput", newOutput);

            // Update elapsed dari server (lebih akurat dari timer lokal)
            if (statusRes.elapsed != null && elements.runElapsed) {
                elements.runElapsed.textContent = formatElapsedMs(statusRes.elapsed * 1000);
            }

            // Selesai hanya jika server bilang proses tidak running lagi
            if (!statusRes.running) {
                stopPolling();
                onRunComplete(statusRes.returncode || 0);
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

async function onRunComplete(returnCode) {
    appStore.set("isRunning", false);
    const stoppedByUser = !!appStore.get("stoppedByUser");
    appStore.set("stoppedByUser", false);
    
    // Re-enable button
    elements.runBtn.disabled = false;
    elements.runBtn.classList.remove("opacity-75", "cursor-not-allowed");
    elements.runBtn.innerHTML = `<i data-lucide="play" class="w-5 h-5"></i> Jalankan Sekarang`;
    if (window.lucide) lucide.createIcons();
    
    // Sembunyikan status bar
    showRunStatus(false);
    
    // Refresh data
    await loadStatus();
    await loadResults();
    
    if (stoppedByUser) {
        appTerminal.append("user@tuton:~$ Run dihentikan oleh pengguna", "warning");
        appToast.show("Run dihentikan oleh pengguna");
    } else if (returnCode !== 0) {
        appTerminal.append(`user@tuton:~$ Run selesai dengan exit code ${returnCode}`, "error");
        appToast.show(`Proses selesai dengan error (exit ${returnCode})`, "error");
    } else {
        appTerminal.append("user@tuton:~$ Run selesai dieksekusi", "success");
        appToast.show("Run selesai dieksekusi");
    }
}

async function handleStopRun() {
    try {
        const res = await appRunAPI.stop();
        if (res && res.success) {
            appStore.set("stoppedByUser", true);
            elements.btnStopRun?.classList.add("hidden");
        } else {
            appToast.show((res && res.error) || "Proses sudah berhenti", "warning");
        }
    } catch (error) {
        appToast.show("Gagal menghentikan: " + error.message, "error");
    }
}

function handleClearTerminal() {
    appTerminal.clear();
}

// === Run Progress (progress bar + status strip) ===
const runProgress = {
    matkul: "",
    kind: "diskusi",
    itemLabel: "",
    itemsTotal: 0,
    itemsDone: 0,
    partial: 0,
    step: "idle",
};

function resetRunProgress() {
    runProgress.matkul = "";
    runProgress.kind = "diskusi";
    runProgress.itemLabel = "";
    runProgress.itemsTotal = 0;
    runProgress.itemsDone = 0;
    runProgress.partial = 0;
    runProgress.step = "idle";
}

function updateRunProgress(line) {
    if (!line) return;

    const mCourse = line.match(/^=== (.+) ===$/);
    if (mCourse) {
        runProgress.matkul = mCourse[1];
        runProgress.itemsTotal = 0;
        runProgress.itemsDone = 0;
        runProgress.step = "scraping";
    }

    if (/^\s*· TOTAL:\s*(\d+)\s*item/.test(line)) {
        runProgress.itemsTotal = parseInt(line.match(/^\s*· TOTAL:\s*(\d+)\s*item/)[1], 10);
    }

    if (/^\s*· (DISKUSI|TUGAS)\s*:/.test(line)) {
        runProgress.itemsTotal += 1;
    }

    // Marker progres dari main.py: "· [3/5] [diskusi] Judul → transkripsi ..."
    const mItem = line.match(/^\s*· \[(\d+)\/(\d+)\]\s+\[(diskusi|tugas)\]\s+(.+?)\s+→/);
    if (mItem) {
        runProgress.itemsTotal = parseInt(mItem[2], 10);
        runProgress.itemsDone = parseInt(mItem[1], 10) - 1;
        runProgress.kind = mItem[3];
        runProgress.itemLabel = mItem[4];
        // Sub-progres dalam satu item supaya bar ikut bergerak realtime:
        // parse → transkripsi → opencode → docx.
        if (/→ transkripsi/.test(line)) {
            runProgress.partial = 0.35;
            runProgress.step = "transkripsi";
        } else if (/→ opencode/.test(line)) {
            runProgress.partial = 0.7;
            runProgress.step = "opencode";
        } else if (/→ membuat docx/.test(line)) {
            runProgress.partial = 0.92;
            runProgress.step = "membuat docx";
        } else {
            runProgress.partial = 0;
            runProgress.step = "mengerjakan";
        }
    } else {
        const mItemOld = line.match(/^\s*· \[(diskusi|tugas)\]\s+(.+?)\s+→/);
        if (mItemOld) {
            runProgress.kind = mItemOld[1];
            runProgress.itemLabel = mItemOld[2];
            runProgress.step = "mengerjakan";
        }
    }

    // Item yang dilewati (sudah dikerjakan) juga dihitung sebagai selesai.
    if (/→ sudah dikerjakan, dilewati/.test(line)) {
        runProgress.itemsDone += 1;
        runProgress.step = "mengerjakan";
    }

    if (/^\s*· Transkripsi /.test(line)) runProgress.step = "transkripsi";
    if (/→ .*? run \.\.\./.test(line)) runProgress.step = "opencode";
    if (/✓ .+? siap\.$/.test(line)) {
        runProgress.itemsDone += 1;
        runProgress.partial = 0;
        runProgress.step = "membuat docx";
    }
    if (/Selesai\. (\d+) item diproses/.test(line)) {
        runProgress.itemsDone = parseInt(line.match(/Selesai\. (\d+) item diproses/)[1], 10);
        runProgress.step = "selesai";
    }
    if (/✗ Gagal|ERROR|timeout|BERHENTI/.test(line)) runProgress.step = "error";

    renderRunStatus();
}

function stepLabel() {
    const map = {
        idle: "Idle",
        scraping: "Membaca struktur",
        mengerjakan: runProgress.kind === "tugas" ? "Mengerjakan: " + (runProgress.itemLabel || "tugas") : "Mengerjakan: " + (runProgress.itemLabel || "diskusi"),
        transkripsi: "Transkripsi lampiran",
        opencode: "Menjalankan opencode",
        "membuat docx": "Generate DOCX",
        selesai: "Selesai",
        error: "Error",
    };
    return map[runProgress.step] || runProgress.step;
}

function formatElapsedMs(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const s = total % 60;
    const m = Math.floor(total / 60) % 60;
    const h = Math.floor(total / 3600);
    const pad = (v) => String(v).padStart(2, "0");
    return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function renderRunStatus() {
    if (!elements.runStatusBar || !elements.runProgressBar) return;

    const total = runProgress.itemsTotal;
    const done = runProgress.itemsDone;
    let pct = 0;
    if (runProgress.step === "selesai") {
        pct = 100;
    } else if (total > 0) {
        const partial = runProgress.partial || 0;
        pct = Math.min(100, Math.round(((done + partial) / total) * 100));
    }

    elements.runProgressBar.style.width = pct + "%";
    elements.runStatusLabel.textContent = runProgress.matkul || "Menyiapkan…";
    elements.runStatusMeta.textContent = `${done}/${total || "?"} item`;
    elements.runStep.textContent = stepLabel();

    // Strip beranimasi selama masih ada proses berjalan (bar mengikuti item
    // yang selesai, background bergerak sebagai indikator "sedang kerja").
    const active = ["scraping", "mengerjakan", "transkripsi", "opencode", "membuat docx"]
        .includes(runProgress.step);
    elements.runProgressBar.classList.toggle("progress-active", active);
}

function showRunStatus(show) {
    if (elements.runStatusBar) {
        if (show) elements.runStatusBar.classList.remove("hidden");
        else elements.runStatusBar.classList.add("hidden");
    }
    if (elements.runBadge) {
        if (show) elements.runBadge.classList.remove("hidden");
        else elements.runBadge.classList.add("hidden");
    }
    if (elements.btnStopRun) {
        if (show) elements.btnStopRun.classList.remove("hidden");
        else elements.btnStopRun.classList.add("hidden");
    }
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
        appStore.set("schedule", response);
        updateCronNextRun(response);
        
        if (enabled) {
            const next = response.next_run ? ` (berikutnya: ${response.next_run.replace("T", " ")} WIB)` : "";
            appTerminal.append(`user@tuton:~$ Konfigurasi cron diperbarui. Agent akan berjalan ${day === "*" ? "setiap hari" : `hari ${day}`} pukul ${time} WIB${next}.`, "success");
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
    elements.btnStopRun?.addEventListener("click", handleStopRun);
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