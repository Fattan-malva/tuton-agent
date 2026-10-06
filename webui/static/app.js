"use strict";

/* ============================================================ util */

const $ = (sel) => document.querySelector(sel);
const view = $("#view");
const state = { es: null, timer: null, routeId: 0, routeController: null };
const ICONS = {
  login: '<path d="M10 17l5-5-5-5M15 12H3"/><path d="M12 3h6a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-6"/>',
  logout: '<path d="M14 17l5-5-5-5M19 12H9"/><path d="M12 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h6"/>',
  dashboard: '<rect x="3" y="3" width="8" height="8" rx="1.5"/><rect x="13" y="3" width="8" height="5" rx="1.5"/><rect x="13" y="10" width="8" height="11" rx="1.5"/><rect x="3" y="13" width="8" height="8" rx="1.5"/>',
  task: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/>',
  bot: '<rect x="4" y="7" width="16" height="13" rx="3"/><path d="M12 3v4M8 12h.01M16 12h.01M9 16h6M2 12v3M22 12v3"/>',
  history: '<path d="M3 12a9 9 0 1 0 2.64-6.36L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>',
  book: '<path d="M12 7v14M3 18V5a2 2 0 0 1 2-2h3a4 4 0 0 1 4 4 4 4 0 0 1 4-4h3a2 2 0 0 1 2 2v13h-5a4 4 0 0 0-4 3 4 4 0 0 0-4-3z"/>',
  settings: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M2 14h4M10 8h4M18 16h4"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  play: '<path d="m8 5 12 7-12 7z"/>',
  stop: '<rect x="5" y="5" width="14" height="14" rx="2"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5M12 15V3"/>',
  chevron: '<path d="m6 9 6 6 6-6"/>',
  calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 11h18"/>',
};

function icon(name) {
  return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
}

document.querySelectorAll("[data-icon]").forEach((el) => {
  el.innerHTML = icon(el.dataset.icon);
});

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

let modelOptionsPromise;

function modelPickerMarkup(id, value = "", key = "") {
  const listId = `${id}-options`;
  const keyAttr = key ? ` data-key="${esc(key)}"` : "";
  return `<div class="model-picker" data-model-picker>
    <div class="model-picker-control">
      <input id="${esc(id)}" class="model-input" type="text"${keyAttr} role="combobox"
        aria-autocomplete="list" aria-expanded="false" aria-controls="${esc(listId)}"
        value="${esc(value)}" placeholder="Klik untuk melihat model, ketik untuk mencari" autocomplete="off" spellcheck="false">
      <button class="model-picker-toggle" type="button" aria-label="Tampilkan semua model" title="Tampilkan semua model">${icon("chevron")}</button>
    </div>
    <div id="${esc(listId)}" class="model-options hidden" role="listbox"></div>
  </div>`;
}

async function loadModelOptions() {
  if (!modelOptionsPromise) {
    modelOptionsPromise = api("/api/models")
      .then((data) => ({ models: data.models || [], error: data.error || "" }))
      .catch((error) => ({ models: [], error: error.message || "Gagal memuat model." }));
  }
  const result = await modelOptionsPromise;
  if (!result.models.length) modelOptionsPromise = null;
  return result;
}

function closeModelPicker(picker) {
  picker.classList.remove("open");
  picker.querySelector(".model-input").setAttribute("aria-expanded", "false");
  picker.querySelector(".model-picker-toggle").setAttribute("aria-expanded", "false");
  picker.querySelector(".model-options").classList.add("hidden");
}

async function showModelOptions(picker, showAll = false) {
  const input = picker.querySelector(".model-input");
  const list = picker.querySelector(".model-options");
  const sequence = Number(picker.dataset.requestSequence || 0) + 1;
  picker.dataset.requestSequence = String(sequence);
  picker.classList.add("open");
  input.setAttribute("aria-expanded", "true");
  picker.querySelector(".model-picker-toggle").setAttribute("aria-expanded", "true");
  list.classList.remove("hidden");
  list.innerHTML = '<div class="model-empty">Memuat daftar model...</div>';
  const result = await loadModelOptions();
  if (picker.dataset.requestSequence !== String(sequence) || !picker.classList.contains("open")) return;
  const query = showAll ? "" : input.value.trim().toLocaleLowerCase();
  const filtered = result.models.filter((model) => model.toLocaleLowerCase().includes(query));
  if (!filtered.length) {
    const message = result.error || (query ? "Model tidak ditemukan." : "Tidak ada model tersedia.");
    list.innerHTML = `<div class="model-empty">${esc(message)}</div>`;
    return;
  }
  list.innerHTML = filtered.map((model, index) => `
    <button class="model-option" type="button" role="option" aria-selected="${input.value === model}"
      id="${esc(list.id)}-${index}" data-model="${esc(model)}">${esc(model)}</button>`).join("");
}

function bindModelPickers(root) {
  root.querySelectorAll("[data-model-picker]").forEach((picker) => {
    const input = picker.querySelector(".model-input");
    const list = picker.querySelector(".model-options");
    input.addEventListener("focus", () => {
      input.select();
      showModelOptions(picker, true);
    });
    input.addEventListener("input", () => showModelOptions(picker));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") closeModelPicker(picker);
      if (event.key === "ArrowDown" && !list.classList.contains("hidden")) {
        event.preventDefault();
        list.querySelector(".model-option")?.focus();
      }
    });
    picker.querySelector(".model-picker-toggle").addEventListener("click", () => {
      if (picker.classList.contains("open")) closeModelPicker(picker);
      else input.focus();
    });
    list.addEventListener("click", (event) => {
      const option = event.target.closest(".model-option");
      if (!option) return;
      input.value = option.dataset.model;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      closeModelPicker(picker);
    });
    list.addEventListener("keydown", (event) => {
      const options = [...list.querySelectorAll(".model-option")];
      const index = options.indexOf(document.activeElement);
      if (event.key === "ArrowDown" && options[index + 1]) {
        event.preventDefault();
        options[index + 1].focus();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        (options[index - 1] || input).focus();
      } else if (event.key === "Escape") {
        closeModelPicker(picker);
        input.focus();
      }
    });
  });
}

document.addEventListener("pointerdown", (event) => {
  document.querySelectorAll(".model-picker.open").forEach((picker) => {
    if (!picker.contains(event.target)) closeModelPicker(picker);
  });
});

async function api(path, opts = {}) {
  const options = { ...opts };
  const method = (options.method || "GET").toUpperCase();
  const cacheMs = method === "GET" ? apiCacheLifetime(path) : 0;
  const cached = cacheMs ? apiCache.get(path) : null;
  if (cached && cached.expires > Date.now()) return cached.data;
  if ((options.method || "GET").toUpperCase() === "GET" && !options.signal) {
    options.signal = state.routeController?.signal;
  }
  const res = await fetch(path, options);
  if (res.status === 401) {
    showLogin("Sesi berakhir. Silakan masuk kembali.");
    throw new Error("auth");
  }
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (cacheMs && res.ok) apiCache.set(path, { data, expires: Date.now() + cacheMs });
  if (method !== "GET" && res.ok) apiCache.clear();
  return data;
}

const apiCache = new Map();

function apiCacheLifetime(path) {
  if (path === "/api/courses" || path.startsWith("/api/courses/") || path === "/api/models") return 5 * 60 * 1000;
  if (path === "/api/moodle-status") return 60 * 1000;
  if (path === "/api/status" || path === "/api/agents") return 30 * 1000;
  return 0;
}

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString("id-ID", { hour12: false });
}

function badge(status) {
  if (status === "done") return '<span class="badge green">selesai</span>';
  if (status === "stopped") return '<span class="badge red">dihentikan</span>';
  if (status === "stopping") return '<span class="badge yellow">menghentikan</span>';
  if (status === "error") return '<span class="badge red">gagal</span>';
  if (status === "running") return '<span class="badge blue">berjalan</span>';
  return '<span class="badge">antre</span>';
}

function setPills(html) { $("#pills").innerHTML = html || ""; }

/* ============================================================ auth */

function showLogin(message = "") {
  state.routeId += 1;
  state.routeController?.abort();
  state.routeController = null;
  if (state.es) { state.es.close(); state.es = null; }
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  $("#login").classList.remove("hidden");
  $("#app").classList.add("hidden");
  $("#login-err").textContent = message;
}

async function init() {
  let session;
  try {
    const res = await fetch("/api/session");
    session = await res.json();
  }
  catch (e) { return; }
  if (!session.authenticated) {
    showLogin();
    return;
  }
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  route();
}

async function doLogin(e) {
  e.preventDefault();
  let r;
  try {
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: $("#login-user").value,
        password: $("#login-pass").value,
      }),
    });
    r = await res.json();
  } catch (e) {
    r = { ok: false, error: "Server tidak dapat dihubungi." };
  }
  if (r && r.ok) { showApp(); }
  else { $("#login-err").textContent = (r && r.error) || "Gagal masuk."; }
}

function showApp() {
  $("#login").classList.add("hidden");
  $("#app").classList.remove("hidden");
  $("#side-user").textContent = "sesi aktif";
  route();
}

/* ============================================================ router */

const TITLES = {
  dashboard: "Dashboard", buat: "Kerjakan Tugas", agents: "Agent Worker",
  results: "Result", log: "Log Live", courses: "Courses", settings: "Pengaturan",
};

async function route() {
  const routeId = ++state.routeId;
  state.routeController?.abort();
  state.routeController = new AbortController();
  if (state.es) { state.es.close(); state.es = null; }
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  const name = (location.hash || "#dashboard").slice(1).split(":", 1)[0];
  document.querySelectorAll("#nav a").forEach((a) =>
    a.classList.toggle("active", a.dataset.view === name));
  $("#page-title").textContent = TITLES[name] || "Dashboard";
  view.innerHTML = '<div class="muted">Memuat...</div>';
  const fn = VIEWS[name] || VIEWS.dashboard;
  try { await fn(routeId); }
  catch (e) {
    if (routeId !== state.routeId || e.name === "AbortError") return;
    view.innerHTML = `<div class="err">${esc(e.message || e)}</div>`;
  }
}

/* ============================================================ views */

const VIEWS = {};

VIEWS.dashboard = async (routeId) => {
  const [status, jobs] = await Promise.all([api("/api/status"), api("/api/jobs")]);
  if (routeId !== state.routeId) return;
  const last = jobs[0];
  setPills('<span class="badge blue">Moodle: memeriksa</span>');
  const cards = [
    ["Moodle", "Memeriksa...", "Koneksi Moodle diperiksa di latar belakang."],
    ["OpenCode", status.opencode || "—", "v2"],
    ["Python", status.python, status.platform],
    ["Courses", "—", "Memuat daftar mata kuliah..."],
    ["Job terakhir", last ? (last.status) : "—", last ? last.matkul : "belum ada"],
  ];
  view.innerHTML = `
    <div class="grid dashboard-grid">
      ${cards.map((c) => `
        <div class="card" data-dashboard-card="${esc(c[0])}">
          <h3>${esc(c[0])}</h3>
          <div class="big">${esc(c[1])}</div>
          <p>${esc(c[2])}</p>
        </div>`).join("")}
    </div>
    <div class="section-title">Aksi cepat</div>
    <div class="row">
      <button class="btn" onclick="location.hash='#buat'">${icon("plus")}<span>Kerjakan Tugas Baru</span></button>
      <button class="btn ghost" onclick="location.hash='#log'">${icon("terminal")}<span>Buka Log Live</span></button>
      <button class="btn ghost" onclick="location.hash='#results'">${icon("file")}<span>Lihat Result</span></button>
    </div>`;

  const masihDashboard = () => (location.hash || "#dashboard") === "#dashboard";
  api("/api/moodle-status").then((ml) => {
    if (routeId !== state.routeId || !masihDashboard()) return;
    const card = view.querySelector('[data-dashboard-card="Moodle"]');
    if (!card) return;
    card.querySelector(".big").textContent = ml.masuk ? "Masuk" : "Belum";
    card.querySelector("p").textContent = ml.pesan || "";
    setPills(ml.masuk
      ? '<span class="badge green">Moodle: masuk</span>'
      : '<span class="badge red">Moodle: tidak masuk</span>');
  }).catch(() => {});
  api("/api/courses").then((courses) => {
    if (routeId !== state.routeId || !masihDashboard()) return;
    const card = view.querySelector('[data-dashboard-card="Courses"]');
    if (!card) return;
    card.querySelector(".big").textContent = String(courses.length);
    card.querySelector("p").textContent = "terdaftar";
  }).catch(() => {});
};

VIEWS.agents = async (routeId) => {
  const [agents, jobs] = await Promise.all([api("/api/agents"), api("/api/jobs")]);
  if (routeId !== state.routeId) return;
  const running = jobs.find((j) => j.status === "running" || j.status === "queued");
  const stat = running
    ? `<span class="badge blue">Aktif: ${esc(running.id)}</span>`
    : '<span class="badge green">Idle</span>';
  setPills(stat);
  view.innerHTML = `
    <p class="muted">Empat agent yang dipanggil pipeline per sesi. Aktivitas
    per langkah bisa dipantau secara langsung di <a href="#log">Log Live</a>.</p>
    <div class="grid">
      ${agents.map((a) => `
        <div class="card">
          <h3>${esc(a.name)}</h3>
          <div class="big" style="font-size:18px">${esc(a.model || "—")}</div>
          <p>agent ${esc(a.name)}</p>
        </div>`).join("")}
    </div>`;
};

VIEWS.results = async (routeId) => {
  const jobs = await api("/api/jobs");
  if (routeId !== state.routeId) return;
  const groups = new Map();
  for (const job of jobs) {
    if (job.status !== "done" || !job.hasil || !job.hasil.docx) continue;
    const matkul = String(job.matkul || "Mata kuliah").trim() || "Mata kuliah";
    if (!groups.has(matkul)) groups.set(matkul, []);
    groups.get(matkul).push(job);
  }
  const total = [...groups.values()].reduce((count, files) => count + files.length, 0);
  setPills(`<span class="badge">${total} DOCX</span>`);
  if (!total) {
    view.innerHTML = '<div class="empty-state"><h2>Belum ada hasil</h2><p>Dokumen DOCX dari tugas yang selesai akan muncul di sini.</p></div>';
    return;
  }
  view.innerHTML = `
    <div class="result-grid">
      ${[...groups.entries()].map(([matkul, files]) => `
        <article class="result-card">
          <header class="result-card-head">
            <h2>${esc(matkul)}</h2>
            <span class="badge">${files.length} DOCX</span>
          </header>
          <ul class="result-files">
            ${files.map((job) => {
              const filename = String(job.hasil.docx).split(/[\\/]/).pop();
              const tanggal = job.dibuat
                ? new Date(Number(job.dibuat) * 1000).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" })
                : "";
              const detail = [`Sesi ${job.sesi || "—"}`, job.jenis || (job.kind === "manual" ? "Input manual" : "Tugas"), tanggal].filter(Boolean).join(" · ");
              return `<li><a class="result-file" href="/api/download/${encodeURIComponent(job.id)}" title="Unduh ${esc(filename)}">
                ${icon("file")}<span class="result-file-main"><strong>${esc(filename)}</strong><small>${esc(detail)}</small></span>${icon("download")}
              </a></li>`;
            }).join("")}
          </ul>
        </article>`).join("")}
    </div>`;
};

function downloadJob(id) {
  window.location.href = `/api/download/${id}`;
}

VIEWS.buat = async (routeId) => {
  setPills("");
  view.innerHTML = `
    <div class="tabs">
      <button data-tab="scrape" class="active">${icon("book")}<span>Dari Moodle</span></button>
      <button data-tab="manual">${icon("task")}<span>Input Manual</span></button>
    </div>
    <div id="pane-scrape">
      <p class="muted">Pilih mata kuliah & sesi yang sudah di-scrape dari akun
      Moodle Anda (memakai cookie di .env).</p>
      <div class="row">
        <div class="col"><label class="field">Mata kuliah</label>
          <select id="sc-matkul"><option value="">— memuat —</option></select></div>
        <div class="col"><label class="field">Sesi</label>
          <select id="sc-sesi"></select></div>
      </div>
      <label class="field"><input type="checkbox" id="sc-semua" style="width:auto;vertical-align:middle"> Proses semua mata kuliah (satu sesi)</label>
      <label class="field"><input type="checkbox" id="sc-tanpa-docx" style="width:auto;vertical-align:middle"> Tanpa buat DOCX (hanya .md)</label>
      <label class="field"><input type="checkbox" id="sc-tanpa-gambar" style="width:auto;vertical-align:middle"> Lewati transkripsi gambar</label>
      <div class="row">
        <div class="col"><label class="field" for="sc-model">Model utama (opsional)</label>
          ${modelPickerMarkup("sc-model")}</div>
        <div class="col"><label class="field" for="sc-model-mata">Model vision (opsional)</label>
          ${modelPickerMarkup("sc-model-mata")}</div>
      </div>
      <button class="btn" id="sc-submit" style="margin-top:16px">${icon("play")}<span>Mulai dari Moodle</span></button>
      <div id="sc-msg" class="err"></div>
    </div>

    <div id="pane-manual" class="hidden">
      <div class="row">
        <div class="col"><label class="field">Mata kuliah</label>
          <input id="mn-matkul" placeholder="nama mata kuliah"></div>
        <div class="col"><label class="field">Kode</label>
          <input id="mn-kode" placeholder="ALEA4213"></div>
        <div class="col"><label class="field">Kelas</label>
          <input id="mn-kelas" placeholder="95"></div>
        <div class="col"><label class="field">Sesi</label>
          <input id="mn-sesi" type="number" value="1" min="1"></div>
        <div class="col"><label class="field">Jenis</label>
          <select id="mn-jenis"><option>Tugas</option><option>Diskusi</option></select></div>
      </div>
      <label class="field">Soal (tempel teks)</label>
      <textarea id="mn-soal" placeholder="Tempel rumusan soal di sini..."></textarea>
      <label class="field">Unggah berkas soal (doc, pdf, gambar, dll) — bisa banyak</label>
      <input id="mn-files" type="file" multiple>
      <div class="files-note" id="mn-files-note"></div>
      <label class="field"><input type="checkbox" id="mn-dengan-gambar" checked style="width:auto;vertical-align:middle"> Transkripsi gambar dengan vision</label>
      <label class="field"><input type="checkbox" id="mn-dengan-ref" checked style="width:auto;vertical-align:middle"> Cari daftar pustaka (research)</label>
      <label class="field"><input type="checkbox" id="mn-tanpa-docx" style="width:auto;vertical-align:middle"> Tanpa buat DOCX</label>
      <div class="row">
        <div class="col"><label class="field" for="mn-model">Model utama (opsional)</label>
          ${modelPickerMarkup("mn-model")}</div>
        <div class="col"><label class="field" for="mn-model-mata">Model vision (opsional)</label>
          ${modelPickerMarkup("mn-model-mata")}</div>
      </div>
      <button class="btn" id="mn-submit" style="margin-top:16px">${icon("play")}<span>Mulai Manual</span></button>
      <div id="mn-msg" class="err"></div>
    </div>`;

  bindModelPickers(view);

  // tab switch
  document.querySelectorAll(".tabs button").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll(".tabs button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      const t = b.dataset.tab;
      $("#pane-scrape").classList.toggle("hidden", t !== "scrape");
      $("#pane-manual").classList.toggle("hidden", t !== "manual");
    }));

  // populate courses
  const courses = await api("/api/courses").catch(() => []);
  if (routeId !== state.routeId) return;
  const sel = $("#sc-matkul");
  if (!sel) return;
  sel.innerHTML = '<option value="">— pilih —</option>' +
    courses.map((c) => `<option value="${esc(c.id)}">${esc(c.nama)}${c.kode ? " (" + esc(c.kode) + ")" : ""}</option>`).join("");

  sel.addEventListener("change", async () => {
    const changeRouteId = state.routeId;
    const ses = $("#sc-sesi");
    if (!sel.value) { ses.innerHTML = ""; return; }
    const list = await api(`/api/courses/${sel.value}/sessions`).catch(() => []);
    if (changeRouteId !== state.routeId || !ses.isConnected) return;
    ses.innerHTML = list.map((s) => `<option value="${s.sesi}">Sesi ${s.sesi} (${s.jumlah} soal)</option>`).join("");
  });

  $("#sc-semua").addEventListener("change", (e) => {
    $("#sc-matkul").disabled = e.target.checked;
    $("#sc-sesi").disabled = e.target.checked;
  });

  $("#mn-files").addEventListener("change", (e) => {
    const n = e.target.files.length;
    $("#mn-files-note").textContent = n ? `${n} berkas dipilih` : "";
  });

  $("#sc-submit").addEventListener("click", async () => {
    const submitRouteId = state.routeId;
    const semua = $("#sc-semua").checked;
    const body = {
      matkul_id: semua ? "semua" : $("#sc-matkul").value,
      sesi: parseInt($("#sc-sesi").value || "0", 10),
      tanpa_docx: $("#sc-tanpa-docx").checked,
      tanpa_gambar: $("#sc-tanpa-gambar").checked,
      model: $("#sc-model").value,
      model_mata: $("#sc-model-mata").value,
    };
    if (!semua && !body.matkul_id) { $("#sc-msg").textContent = "Pilih mata kuliah."; return; }
    const r = await api("/api/jobs/scrape", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch((e) => ({ error: e.message }));
    if (submitRouteId !== state.routeId) return;
    if (r.error) { $("#sc-msg").textContent = r.error; return; }
    const id = r.jobs[0];
    location.hash = "#log:" + id;
    if (r.jobs.length > 1)
      setTimeout(() => alert(`${r.jobs.length} job diantrekan (semua mata kuliah).`), 200);
  });

  $("#mn-submit").addEventListener("click", async () => {
    const submitRouteId = state.routeId;
    const fd = new FormData();
    fd.append("matkul_nama", $("#mn-matkul").value);
    fd.append("matkul_kode", $("#mn-kode").value);
    fd.append("matkul_kelas", $("#mn-kelas").value);
    fd.append("sesi", $("#mn-sesi").value);
    fd.append("jenis", $("#mn-jenis").value);
    fd.append("question", $("#mn-soal").value);
    fd.append("dengan_gambar", $("#mn-dengan-gambar").checked ? "on" : "off");
    fd.append("dengan_referensi", $("#mn-dengan-ref").checked ? "on" : "off");
    fd.append("tanpa_docx", $("#mn-tanpa-docx").checked ? "on" : "off");
    fd.append("model", $("#mn-model").value);
    fd.append("model_mata", $("#mn-model-mata").value);
    for (const f of $("#mn-files").files) fd.append("file", f, f.name);
    const r = await api("/api/jobs/manual", { method: "POST", body: fd })
      .catch((e) => ({ error: e.message }));
    if (submitRouteId !== state.routeId) return;
    if (r.error) { $("#mn-msg").textContent = r.error; return; }
    location.hash = "#log:" + r.jobs[0];
  });
};

VIEWS.log = async (routeId) => {
  let id = (location.hash.split(":")[1] || "").trim();
  const jobs = await api("/api/jobs").catch(() => []);
  if (routeId !== state.routeId) return;
  if (!id) id = jobs[0] ? jobs[0].id : "";
  const selectedJob = jobs.find((job) => job.id === id);
  const stoppable = selectedJob && ["queued", "running", "stopping"].includes(selectedJob.status);
  setPills(id ? `<span class="badge blue">job ${esc(id)}</span>` : "");
  view.innerHTML = `
    <div class="row log-controls">
      <div class="col log-select"><label class="field" for="log-sel">Job</label>
        <select id="log-sel"><option value="">— pilih job —</option></select></div>
      <div class="col log-action"><button class="btn" id="log-go">${icon("play")}<span>Tampilkan</span></button></div>
    </div>
    ${stoppable ? `<div class="log-stop-row"><button class="btn danger" id="log-stop">${icon("stop")}<span>Hentikan job</span></button></div>` : ""}
    <div class="console" id="console" style="margin-top:16px"><span class="muted">Pilih job lalu tekan Tampilkan.</span></div>`;

  $("#log-sel").innerHTML = '<option value="">— pilih job —</option>' +
    jobs.map((j) => `<option value="${esc(j.id)}">${esc(j.id)} · ${esc(j.matkul)} · ${esc(j.status)}</option>`).join("");
  if (id) $("#log-sel").value = id;

  $("#log-go").addEventListener("click", () => {
    const v = $("#log-sel").value;
    if (v) location.hash = "#log:" + v;
    else attach(id);
  });

  const stopButton = $("#log-stop");
  if (stopButton) stopButton.addEventListener("click", async () => {
    stopButton.disabled = true;
    stopButton.querySelector("span").textContent = "Menghentikan...";
    const result = await api(`/api/jobs/${encodeURIComponent(id)}/stop`, { method: "POST" })
      .catch((error) => ({ error: error.message }));
    if (routeId !== state.routeId || !stopButton.isConnected) return;
    if (result.error) {
      stopButton.disabled = false;
      stopButton.querySelector("span").textContent = "Hentikan job";
      return;
    }
    stopButton.querySelector("span").textContent = "Membersihkan sesi...";
  });

  if (id) attach(id, routeId);
};

async function attach(id, routeId = state.routeId) {
  if (routeId !== state.routeId) return;
  const consoleEl = $("#console");
  if (!consoleEl) return;
  consoleEl.innerHTML = "";
  const evs = await api(`/api/jobs/${id}/events`).catch(() => []);
  if (routeId !== state.routeId || $("#console") !== consoleEl) return;
  evs.forEach((e) => appendLine(consoleEl, e));
  consoleEl.scrollTop = consoleEl.scrollHeight;

  if (state.es) state.es.close();
  if (routeId !== state.routeId) return;
  const es = new EventSource(`/api/jobs/${id}/stream`);
  state.es = es;
  es.onmessage = (ev) => {
    if (routeId !== state.routeId || $("#console") !== consoleEl) {
      es.close();
      if (state.es === es) state.es = null;
      return;
    }
    try { appendLine(consoleEl, JSON.parse(ev.data)); }
    catch (e) { /* abaikan */ }
    consoleEl.scrollTop = consoleEl.scrollHeight;
  };
  es.addEventListener("done", (event) => {
    if (routeId !== state.routeId || $("#console") !== consoleEl) {
      es.close();
      if (state.es === es) state.es = null;
      return;
    }
    const d = document.createElement("span");
    d.className = "ln info";
    let status = "done";
    try { status = JSON.parse(event.data).status || status; }
    catch (e) { /* abaikan */ }
    d.textContent = status === "stopped" ? "\n=== job dihentikan ===" : "\n=== job selesai ===";
    consoleEl.appendChild(d);
    consoleEl.scrollTop = consoleEl.scrollHeight;
    es.close();
    if (state.es === es) state.es = null;
  });
  es.onerror = () => { if (routeId !== state.routeId) es.close(); };
}

function appendLine(consoleEl, e) {
  const ln = document.createElement("span");
  ln.className = "ln " + (e.level || "info");
  const ts = e.ts ? `<span class="ts">${fmtTime(e.ts)}</span>` : "";
  const stage = e.stage ? `[${esc(e.stage)}] ` : "";
  const agent = e.agent ? `<${esc(e.agent)}> ` : "";
  ln.innerHTML = ts + stage + agent + esc(e.msg);
  consoleEl.appendChild(ln);
}

VIEWS.courses = async (routeId) => {
  let courses;
  try { courses = await api("/api/courses"); }
  catch (e) {
    if (routeId !== state.routeId) return;
    view.innerHTML = `<div class="err">${esc(e.message)}</div>`;
    return;
  }
  if (routeId !== state.routeId) return;
  if (!courses) return;
  setPills(`<span class="badge">${courses.length} courses</span>`);
  if (!courses.length) { view.innerHTML = '<p class="muted">Tidak ada mata kuliah (cek cookie Moodle).</p>'; return; }
  view.innerHTML = `
    <table>
      <thead><tr><th>Mata kuliah</th><th>Kode</th><th>Kelas</th><th></th></tr></thead>
      <tbody>
        ${courses.map((c) => `
          <tr>
            <td>${esc(c.nama)}</td>
            <td>${esc(c.kode)}</td>
            <td>${esc(c.kelas)}</td>
            <td><button class="link icon-link" onclick="loadSessions('${esc(c.id)}', this)">${icon("calendar")}<span>lihat sesi</span></button></td>
          </tr>`).join("")}
      </tbody>
    </table>
    <div id="course-detail"></div>`;
};

window.loadSessions = async function (cid, btn) {
  const routeId = state.routeId;
  const detail = $("#course-detail");
  if (!detail) return;
  const list = await api(`/api/courses/${cid}/sessions`).catch(() => []);
  if (routeId !== state.routeId || $("#course-detail") !== detail) return;
  detail.innerHTML = `
    <div class="section-title">Sesi dengan soal</div>
    <div class="row">
      ${list.map((s) => `<span class="badge blue">Sesi ${s.sesi} — ${s.jumlah} soal</span>`).join("") || '<span class="muted">tidak ada</span>'}
    </div>`;
};

VIEWS.settings = async (routeId) => {
  const items = await api("/api/settings");
  if (routeId !== state.routeId) return;
  setPills("");
  const rahasia = new Set(["COOKIE_MOODLE", "APP_PASSWORD"]);
  view.innerHTML = `
    <p class="muted">Pengaturan disimpan ke <span class="kbd">.env</span>.
    COOKIE_MOODLE hanya untuk koneksi Moodle, bukan untuk login dashboard.
    Masukkan cookie Moodle di sini. Kolom rahasia yang kosong tidak mengubah nilai tersimpan.</p>
    <div id="set-list">
      ${items.map((it) => `
        <div class="settings-field">
          <label class="field" for="set-${esc(it.key)}">${esc(it.key)}${it.rahasia ? " (rahasia)" : ""}</label>
          ${["PRIMARY_MODEL", "VISION_MODEL"].includes(it.key)
            ? modelPickerMarkup(`set-${it.key}`, it.value, it.key)
            : `<input id="set-${esc(it.key)}" data-key="${esc(it.key)}" type="${it.rahasia ? "password" : "text"}"
                value="${esc(it.rahasia ? "" : it.value)}"
                placeholder="${it.rahasia ? (it.ada ? "biarkan kosong = tetap" : "isi baru") : ""}">`}
        </div>`).join("")}
    </div>
    <button class="btn" id="set-save" style="margin-top:18px">Simpan</button>
    <div id="set-msg" class="err"></div>`;
  bindModelPickers(view);
  $("#set-save").addEventListener("click", async () => {
    const saveRouteId = state.routeId;
    const payload = {};
    document.querySelectorAll("#set-list input").forEach((inp) => {
      payload[inp.dataset.key] = inp.value;
    });
    const r = await api("/api/settings", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).catch((e) => ({ error: e.message }));
    if (saveRouteId !== state.routeId) return;
    const message = $("#set-msg");
    if (!message) return;
    message.textContent = r && r.ok ? "Tersimpan." : (r && r.error) || "Gagal.";
    if (r && r.ok) setTimeout(() => {
      if (saveRouteId === state.routeId) location.reload();
    }, 600);
  });
};

/* ============================================================ boot */

$("#login-form").addEventListener("submit", doLogin);
$("#logout").addEventListener("click", async () => {
  await api("/api/logout").catch(() => {});
  location.reload();
});
window.addEventListener("hashchange", route);
init();
