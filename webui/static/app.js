"use strict";

/* ============================================================ util */

const $ = (sel) => document.querySelector(sel);
const view = $("#view");
const state = { es: null, timer: null, routeId: 0, routeController: null, sesi: null };
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
  trash: '<path d="M3 6h18M8 6V4.5A1.5 1.5 0 0 1 9.5 3h5A1.5 1.5 0 0 1 16 4.5V6M18.5 6l-.9 13.1A2 2 0 0 1 15.6 21H8.4a2 2 0 0 1-2-1.9L5.5 6"/><path d="M10 10.5v6M14 10.5v6"/>',
  eye: '<path d="M2 12s3.6-6.8 10-6.8S22 12 22 12s-3.6 6.8-10 6.8S2 12 2 12z"/><circle cx="12" cy="12" r="2.8"/>',
  x: '<path d="M18 6 6 18M6 6l12 12"/>',
  moon: '<path d="M20.8 13.4A8.6 8.6 0 1 1 10.6 3.2a6.7 6.7 0 0 0 10.2 10.2z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.5 1.5M17.6 17.6l1.5 1.5M2 12h2M20 12h2M4.9 19.1l1.5-1.5M17.6 6.4l1.5-1.5"/>',
  refresh: '<path d="M20.5 12a8.5 8.5 0 1 1-2.5-6"/><path d="M20.5 4v5h-5"/>',
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

/* ------------------------------------------------------------ tema */
// Seluruh warna datang dari variabel di app.css yang diganti di bawah
// `<html data-tema>`. Skrip di index.html sudah memasang atributnya sebelum
// CSS digambar; fungsi ini yang memutuskan perubahannya (sakelar di
// Pengaturan) dan menyimpannya per peramban.
const TEMA_KEY = "tuton-tema";

function temaSaatIni() {
  return document.documentElement.getAttribute("data-tema") === "gelap"
    ? "gelap" : "terang";
}

function terapkanTema(tema) {
  const nilai = tema === "gelap" ? "gelap" : "terang";
  document.documentElement.setAttribute("data-tema", nilai);
  try {
    localStorage.setItem(TEMA_KEY, nilai);
  } catch (e) {
    /* mode privat: tema tetap berlaku selama tab terbuka */
  }
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", nilai === "gelap" ? "#191919" : "#f7f6f3");
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
  list.innerHTML = '<div class="model-search"><input type="text" placeholder="Cari model..." autocomplete="off" spellcheck="false"></div><div class="model-results" role="listbox"></div>';
  const searchEl = list.querySelector(".model-search input");
  searchEl.value = query;
  const resultsEl = list.querySelector(".model-results");
  const render = (q) => {
    const term = q.trim().toLocaleLowerCase();
    const filtered = result.models.filter((model) => model.toLocaleLowerCase().includes(term));
    if (!filtered.length) {
      const message = result.error || (term ? "Model tidak ditemukan." : "Tidak ada model tersedia.");
      resultsEl.innerHTML = `<div class="model-empty">${esc(message)}</div>`;
      return;
    }
    resultsEl.innerHTML = filtered.map((model, index) => `
    <button class="model-option" type="button" role="option" aria-selected="${input.value === model}"
      id="${esc(list.id)}-${index}" data-model="${esc(model)}">${esc(model)}</button>`).join("");
  };
  render(searchEl.value);
  searchEl.addEventListener("input", () => render(searchEl.value));
  searchEl.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      event.stopPropagation();
      resultsEl.querySelector(".model-option")?.focus();
    } else if (event.key === "Enter") {
      event.preventDefault();
      resultsEl.querySelector(".model-option")?.click();
    } else if (event.key === "Escape") {
      event.stopPropagation();
      closeModelPicker(picker);
    }
  });
}

function bindModelPickers(root) {
  root.querySelectorAll("[data-model-picker]").forEach((picker) => {
    const input = picker.querySelector(".model-input");
    const list = picker.querySelector(".model-options");
    input.addEventListener("focus", () => {
      input.select();
      showModelOptions(picker, true);
    });
    input.addEventListener("input", () => {
      const searchEl = list.querySelector(".model-search input");
      if (searchEl) {
        searchEl.value = input.value;
        searchEl.dispatchEvent(new Event("input"));
      } else {
        showModelOptions(picker);
      }
    });
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
    state.sesi = false;
    showLogin("Sesi berakhir. Silakan masuk kembali.");
    throw new Error("auth");
  }
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (cacheMs && res.ok) apiCache.set(path, { data, expires: Date.now() + cacheMs });
  if (method !== "GET" && res.ok) apiCache.clear();
  // JSON error ({"error": ...}) dibuat gagal (throw) supaya semua pemanggil
  // yang pakai .catch/try-catch benar-benar tahu ada masalah -- mis. cookie
  // Moodle mati. Kalau tidak, pemanggil menerima objek {error} lalu salah
  // render (courses.map bukan fungsi, select matkul tidak terisi, kartu
  // dashboard menampilkan "undefined").
  if (!res.ok && data && typeof data === "object" && data.error) {
    throw new Error(data.error);
  }
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

/* `state.sesi` adalah penjaga rute: null = belum dicek, true/false =
   status autentikasi server. Semua rute memeriksanya sebelum merender. */
async function cekSesi() {
  try {
    const res = await fetch("/api/session", { cache: "no-store" });
    const s = await res.json();
    state.sesi = !!s.authenticated;
  } catch (e) {
    state.sesi = false;
  }
  return state.sesi;
}

function showLogin(message = "") {
  if (state.sesi === true) {
    // Sudah login: halaman login ditolak, kembali ke dashboard.
    $("#login").classList.add("hidden");
    $("#app").classList.remove("hidden");
    if (location.hash && location.hash !== "#dashboard") location.hash = "#dashboard";
    else route();
    return;
  }
  state.routeId += 1;
  state.routeController?.abort();
  state.routeController = null;
  if (state.es) { state.es.close(); state.es = null; }
  if (state.timer) { clearInterval(state.timer); state.timer = null; }
  const sebelumnyaTampil = !$("#login").classList.contains("hidden");
  $("#login").classList.remove("hidden");
  $("#app").classList.add("hidden");
  // Pesan hanya ditimpa kalau ada isinya, supaya pesan keluar tidak
  // hilang ketika route() ikut memanggil showLogin lewat guard rute.
  if (message || !sebelumnyaTampil) $("#login-err").textContent = message;
}

async function init() {
  const masuk = await cekSesi();
  if (!masuk) {
    // Datang langsung dengan rute aplikasi (mis. /#courses) sambil belum
    // masuk: pesan guard ikut ditampilkan, bukan halaman login yang hening.
    showLogin(location.hash ? "Silakan masuk terlebih dahulu." : "");
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
        remember: !!$("#login-remember")?.checked,
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
  state.sesi = true;
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
  // Middleware rute: tanpa sesi aktif tidak ada view yang boleh dibuka;
  // status sesi dipastikan ke server kalau belum pernah dicek.
  if (!(state.sesi === true || (state.sesi === null && await cekSesi()))) {
    // Pesan hanya untuk kunjungan rute langsung; kalau halaman login sudah
    // terbuka (mis. baru saja keluar), pesan lama tidak ditimpa.
    showLogin($("#login").classList.contains("hidden") ? "Silakan masuk terlebih dahulu." : "");
    return;
  }
  if (routeId !== state.routeId) return;
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

  // Grafik nilai diambil setelah render supaya dashboard tidak menunggu
  // scraping laporan nilai (bisa lambat saat pertama kali).
  view.insertAdjacentHTML("beforeend", `
    <div class="section-title">Nilai Diskusi &amp; Tugas per Sesi</div>
    <div class="card nilai-card" id="nilai-card">
      <p class="muted">Memuat nilai dari Moodle...</p>
    </div>`);
  api("/api/nilai").then((nilai) => {
    if (routeId !== state.routeId) return;
    const card = $("#nilai-card");
    if (!card) return;
    if (nilai && nilai.error) {
      card.innerHTML = `<p class="err">${esc(nilai.error)}</p>`;
      return;
    }
    const adaNilai = nilai && Array.isArray(nilai.courses) && nilai.courses.length;
    if (!adaNilai) {
      card.innerHTML = '<p class="muted">Belum ada nilai Diskusi/Tugas yang bisa diambil.</p>';
      return;
    }
    card.innerHTML = `
      <div class="tabs" id="nilai-filter">
        <button data-f="Semua" class="active">Semua</button>
        <button data-f="Diskusi">Diskusi</button>
        <button data-f="Tugas">Tugas</button>
      </div>
      <div class="nilai-body">
        <div class="nilai-legend" id="nilai-legend"></div>
        <div class="nilai-plot" id="nilai-plot"></div>
      </div>`;
    bindNilai(nilai);
  }).catch((e) => {
    const card = $("#nilai-card");
    if (card) card.innerHTML = `<p class="err">${esc(e.message || "Nilai tidak bisa dimuat.")}</p>`;
  });

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
    const daftar = Array.isArray(courses) ? courses : [];
    card.querySelector(".big").textContent = String(daftar.length);
    card.querySelector("p").textContent = "terdaftar";
  }).catch((e) => {
    if (routeId !== state.routeId || !masihDashboard()) return;
    const card = view.querySelector('[data-dashboard-card="Courses"]');
    if (!card) return;
    card.querySelector(".big").textContent = "—";
    card.querySelector("p").textContent = e.message || "gagal memuat";
  });
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
  const files = await api("/api/results").catch(() => []);
  if (routeId !== state.routeId) return;
  const list = Array.isArray(files) ? files : [];
  const groups = new Map();
  for (const f of list) {
    const matkul = String(f.slug || "Lainnya").replace(/-/g, " ");
    if (!groups.has(matkul)) groups.set(matkul, []);
    groups.get(matkul).push(f);
  }
  const total = list.length;
  setPills(`<span class="badge">${total} DOCX</span>`);
  if (!total) {
    view.innerHTML = '<div class="empty-state"><h2>Belum ada hasil</h2><p>Dokumen DOCX dari tugas yang selesai akan muncul di sini.</p></div>';
    return;
  }
  view.innerHTML = `
    <div id="res-msg" class="err"></div>
    <div class="result-grid">
      ${[...groups.entries()].map(([matkul, files]) => `
        <article class="result-card">
          <header class="result-card-head">
            <h2>${esc(matkul)}</h2>
            <span class="badge">${files.length} DOCX</span>
            <button type="button" class="icon-btn danger" data-hapus-matkul="${esc(files[0].slug)}"
              title="Hapus semua hasil ${esc(matkul)}">${icon("trash")}</button>
          </header>
          <ul class="result-files">
            ${files.map((f) => {
              const tanggal = f.waktu
                ? new Date(Number(f.waktu) * 1000).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" })
                : "";
              const mb = (Number(f.ukuran || 0) / 1048576).toFixed(2);
              const detail = [String(f.sesi || "").replace("sesi-", "Sesi "), `${mb} MB`, tanggal].filter(Boolean).join(" · ");
              const rel = `${f.slug}/${f.sesi}/${f.nama}`;
              const href = `/api/download-output/${rel.split("/").map(encodeURIComponent).join("/")}`;
              return `<li class="result-row">
                <button type="button" class="result-file" data-preview="${esc(rel)}"
                  title="Pratinjau ${esc(f.nama)}">
                  ${icon("file")}<span class="result-file-main"><strong>${esc(f.nama)}</strong><small>${esc(detail)}</small></span>${icon("eye")}
                </button>
                <span class="result-acts">
                  <a class="icon-btn" href="${href}" title="Unduh ${esc(f.nama)}">${icon("download")}</a>
                  <button type="button" class="icon-btn danger" data-hapus-file="${esc(rel)}"
                    title="Hapus ${esc(f.nama)}">${icon("trash")}</button>
                </span>
              </li>`;
            }).join("")}
          </ul>
        </article>`).join("")}
    </div>`;

  const pesan = (teks) => {
    const el = $("#res-msg");
    if (el) el.textContent = teks;
  };

  const hapusHasil = async (body, judul, pesanDialog) => {
    const ya = await konfirmasi({ judul, pesan: pesanDialog, labelYa: "Hapus", labelTidak: "Batal", nada: "danger" });
    if (!ya) return;
    const r = await api("/api/results/delete", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch((e) => ({ error: e.message }));
    if (routeId !== state.routeId) return;
    if (r && r.error) { pesan(r.error); return; }
    route();  // ambil ulang daftar; daftar berubah setiap penghapusan
  };

  view.querySelectorAll("[data-preview]").forEach((b) => {
    b.addEventListener("click", () => pratinjau(b.dataset.preview));
  });
  view.querySelectorAll("[data-hapus-file]").forEach((b) => {
    b.addEventListener("click", () => {
      const rel = b.dataset.hapusFile;
      const nama = rel.split("/").pop();
      const [slug, sesi] = rel.split("/");
      hapusHasil(
        { slug, sesi, nama },
        "Hapus berkas ini?",
        `${nama} akan dihapus permanen dari disk. Berkas lain di sesi ini tidak ikut terhapus.`,
      );
    });
  });
  view.querySelectorAll("[data-hapus-matkul]").forEach((b) => {
    b.addEventListener("click", () => {
      const slug = b.dataset.hapusMatkul;
      hapusHasil(
        { slug },
        "Hapus semua hasil mata kuliah ini?",
        `Seluruh folder output/${slug.replace(/-/g, " ")} beserta semua DOCX di dalamnya dihapus permanen. Tidak bisa dibatalkan.`,
      );
    });
  });
};

// Modal pratinjau DOCX. Isinya datang dari server sebagai HTML blok;
// peramban tidak bisa membaca .docx, jadi konversinya di server
// (webui/docxprev.py) dan hanya HTML polos yang dikirim ke sini.
function pratinjau(rel) {
  const enc = rel.split("/").map(encodeURIComponent).join("/");
  const nama = rel.split("/").pop();
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal modal-wide" role="dialog" aria-modal="true" aria-labelledby="prev-judul">
      <header class="modal-head">
        <h3 id="prev-judul">${esc(nama)}</h3>
        <button type="button" class="icon-btn" data-tutup title="Tutup pratinjau">${icon("x")}</button>
      </header>
      <div class="modal-body prev-body" id="prev-isi">
        <div class="prev-muat"><span class="spinner"></span> Membaca dokumen...</div>
      </div>
      <div class="modal-aksi">
        <a class="btn ghost" href="/api/download-output/${enc}">${icon("download")}<span>Unduh</span></a>
        <button type="button" class="btn" data-tutup>Tutup</button>
      </div>
    </div>`;
  const tutup = () => {
    document.removeEventListener("keydown", onKey);
    overlay.remove();
  };
  const onKey = (e) => { if (e.key === "Escape") tutup(); };
  overlay.addEventListener("click", (e) => { if (e.target === overlay) tutup(); });
  overlay.querySelectorAll("[data-tutup]").forEach((b) => b.addEventListener("click", tutup));
  document.addEventListener("keydown", onKey);
  document.body.appendChild(overlay);
  overlay.querySelector("[data-tutup]").focus();

  const isi = overlay.querySelector("#prev-isi");
  api(`/api/results/preview/${enc}`).then((d) => {
    if (isi.isConnected === false || overlay.isConnected === false) return;
    if (!d || typeof d !== "object" || typeof d.html !== "string") {
      throw new Error("Berkas tidak bisa dipratinjau.");
    }
    isi.innerHTML = d.html.trim()
      || '<p class="muted">Dokumen tidak memiliki teks yang bisa ditampilkan.</p>';
  }).catch((e) => {
    if (isi.isConnected === false) return;
    isi.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  });
}

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
        <div class="col"><label class="field" for="sc-jenis">Jenis soal</label>
          <select id="sc-jenis">
            <option value="">Otomatis (ikut sesi)</option>
            <option value="Tugas">Tugas saja</option>
            <option value="Diskusi">Diskusi saja</option>
          </select></div>
      </div>
      <div class="files-note">"Otomatis" mengerjakan semua soal yang ada di
      sesi itu. Memilih Tugas atau Diskusi menyaring soalnya -- sesi campuran
      hanya menghasilkan jenis yang dipilih, dan namanya ikut menyebut jenis
      (mis. <span class="kbd">Basis_Data_64_Tugas.1.docx</span>).</div>
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
          <select id="mn-matkul"><option value="">— memuat —</option></select></div>
        <div class="col"><label class="field">Sesi</label>
          <input id="mn-sesi" type="number" value="1" min="1"></div>
        <div class="col"><label class="field">Jenis</label>
          <select id="mn-jenis"><option>Tugas</option><option>Diskusi</option></select></div>
      </div>
      <div id="mn-matkul-info" class="files-note"></div>
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
  loadModelOptions();  // sama seperti halaman Settings: model sudah siap saat picker dibuka

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
  const hasilKursus = await api("/api/courses")
    .then((c) => (Array.isArray(c) ? c : []))
    .catch((e) => e);
  if (routeId !== state.routeId) return;
  const sel = $("#sc-matkul");
  if (!sel) return;
  // Cookie Moodle mati / server gagal: pilih `hasilKursus` berupa Error.
  // Tampilkan pesan di kedua pane tapi form tetap hidup (pane Input Manual
  // tidak butuh cookie dan tetap bisa dipakai).
  const galatMatkul = hasilKursus instanceof Error ? hasilKursus.message : "";
  const courses = galatMatkul ? [] : hasilKursus;
  const optKosong = galatMatkul
    ? `<option value="">${esc(galatMatkul)}</option>`
    : '<option value="">— pilih —</option>';
  sel.innerHTML = optKosong +
    courses.map((c) => `<option value="${esc(c.id)}">${esc(c.nama)}${c.kode ? " (" + esc(c.kode) + ")" : ""}</option>`).join("");
  const galatEl = $("#sc-msg");
  if (galatEl) galatEl.textContent = galatMatkul;

  const mnSel = $("#mn-matkul");
  if (mnSel) {
    mnSel.innerHTML = optKosong +
      courses.map((c) => `<option value="${esc(c.id)}" data-nama="${esc(c.nama)}" data-kode="${esc(c.kode)}" data-kelas="${esc(c.kelas)}">${esc(c.nama)}${c.kode ? " (" + esc(c.kode) + ")" : ""}</option>`).join("");
    const mnGalat = $("#mn-msg");
    if (mnGalat) mnGalat.textContent = galatMatkul;
    mnSel.addEventListener("change", () => {
      const opt = mnSel.selectedOptions[0];
      const info = $("#mn-matkul-info");
      if (info) info.textContent = opt && opt.value
        ? `Kode: ${opt.dataset.kode || "-"} · Kelas: ${opt.dataset.kelas || "-"}`
        : "";
    });
  }

  sel.addEventListener("change", async () => {
    const changeRouteId = state.routeId;
    const ses = $("#sc-sesi");
    const galat = $("#sc-msg");
    if (galat) galat.textContent = "";
    if (!sel.value) { ses.innerHTML = ""; return; }
    const list = await api(`/api/courses/${sel.value}/sessions`).catch((e) => e);
    if (changeRouteId !== state.routeId || !ses.isConnected) return;
    if (list instanceof Error) {
      ses.innerHTML = "";
      if (galat) galat.textContent = list.message;
      return;
    }
    ses.innerHTML = (Array.isArray(list) ? list : [])
      .map((s) => `<option value="${s.sesi}">Sesi ${s.sesi} (${s.jumlah} soal)</option>`).join("");
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
      jenis: $("#sc-jenis") ? $("#sc-jenis").value : "",
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
    const opt = $("#mn-matkul").selectedOptions[0];
    if (!opt || !opt.value) { $("#mn-msg").textContent = "Pilih mata kuliah."; return; }
    const fd = new FormData();
    fd.append("matkul_nama", opt.dataset.nama || "");
    fd.append("matkul_kode", opt.dataset.kode || "");
    fd.append("matkul_kelas", opt.dataset.kelas || "");
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
    ${(stoppable || selectedJob) ? `<div class="log-stop-row">
      ${stoppable ? `<button class="btn danger" id="log-stop">${icon("stop")}<span>Hentikan job</span></button>` : ""}
      ${selectedJob ? `<button class="btn ghost" id="log-hapus" type="button">${icon("trash")}<span>Hapus job</span></button>` : ""}
    </div>` : ""}
    <div id="log-msg" class="err"></div>
    <div class="console-bar">
      <span id="console-spinner" class="spinner hidden"></span>
      <span id="console-status" class="console-status">siap</span>
      <span class="spacer"></span>
      <span class="btns">
        <button class="btn sm" id="log-copy" type="button">Salin</button>
        <button class="btn sm" id="log-clear" type="button">Bersihkan</button>
        <button class="btn sm" id="log-follow" type="button" aria-pressed="true">Gulir otomatis</button>
      </span>
    </div>
    <div class="console" id="console"><span class="muted">Pilih job lalu tekan Tampilkan.</span></div>`;

  state.logFollow = state.logFollow !== false;
  const followBtn = $("#log-follow");
  followBtn.setAttribute("aria-pressed", String(state.logFollow));
  followBtn.addEventListener("click", () => {
    state.logFollow = !state.logFollow;
    followBtn.setAttribute("aria-pressed", String(state.logFollow));
    const c = $("#console");
    if (state.logFollow && c) c.scrollTop = c.scrollHeight;
  });
  $("#log-clear").addEventListener("click", () => {
    const c = $("#console");
    if (!c) return;
    c.innerHTML = '<span class="ln info">Log dibersihkan. Menunggu baris baru<span class="dots"></span></span>';
    // Bersihkan juga sumber replay-nya (buffer memori + events.jsonl).
    // Kalau DOM saja yang dikosongkan, log lama muncul lagi lewat replay
    // saat halaman dimuat ulang.
    if (id) {
      api(`/api/jobs/${encodeURIComponent(id)}/clear-log`, { method: "POST" })
        .catch(() => {});
    }
  });
  $("#log-copy").addEventListener("click", async () => {
    const c = $("#console");
    if (!c) return;
    try { await navigator.clipboard.writeText(c.innerText); }
    catch (e) { /* clipboard ditolak */ }
  });

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

  const hapusButton = $("#log-hapus");
  if (hapusButton) hapusButton.addEventListener("click", async () => {
    const ya = await konfirmasi({
      judul: `Hapus job ${id}?`,
      pesan: "Job beserta folder kerja dan lognya dihapus permanen. Hasil DOCX di tab Result tidak ikut terhapus.",
      labelYa: "Hapus",
      labelTidak: "Batal",
      nada: "danger",
    });
    if (!ya || routeId !== state.routeId || !hapusButton.isConnected) return;
    const r = await api(`/api/jobs/${encodeURIComponent(id)}/delete`, { method: "POST" })
      .catch((e) => ({ error: e.message }));
    if (routeId !== state.routeId) return;
    if (r && r.error) {
      const msg = $("#log-msg");
      if (msg) msg.textContent = r.error;
      return;
    }
    // Balik ke daftar tanpa id: job yang tadi dibuka sudah tidak ada, dan
    // menampilkan id mati di hash hanya membuat view mencari job hantu.
    if (location.hash.split(":")[1]) location.hash = "#log";
    else route();
  });

  if (id) attach(id, routeId);
};

async function attach(id, routeId = state.routeId) {
  if (routeId !== state.routeId) return;
  const consoleEl = $("#console");
  if (!consoleEl) return;
  consoleEl.innerHTML = "";
  consoleEl.classList.remove("live");
  const statusEl = $("#console-status");
  const spinEl = $("#console-spinner");
  if (statusEl) { statusEl.textContent = "menghubungkan"; statusEl.className = "console-status running"; }
  if (spinEl) spinEl.classList.remove("hidden");
  const evs = await api(`/api/jobs/${id}/events`).catch(() => []);
  if (routeId !== state.routeId || $("#console") !== consoleEl) return;
  evs.forEach((e) => appendLine(consoleEl, e));
  if (state.logFollow !== false) consoleEl.scrollTop = consoleEl.scrollHeight;

  if (state.es) state.es.close();
  if (routeId !== state.routeId) return;
  const es = new EventSource(`/api/jobs/${id}/stream`);
  state.es = es;
  consoleEl.classList.add("live");
  if (statusEl) { statusEl.textContent = "mengalir"; statusEl.className = "console-status running"; }
  es.onmessage = (ev) => {
    if (routeId !== state.routeId || $("#console") !== consoleEl) {
      es.close();
      if (state.es === es) state.es = null;
      return;
    }
    try { appendLine(consoleEl, JSON.parse(ev.data)); }
    catch (e) { /* abaikan */ }
    if (state.logFollow !== false) consoleEl.scrollTop = consoleEl.scrollHeight;
  };
  es.addEventListener("done", (event) => {
    if (routeId !== state.routeId || $("#console") !== consoleEl) {
      es.close();
      if (state.es === es) state.es = null;
      return;
    }
    consoleEl.classList.remove("live");
    const d = document.createElement("span");
    d.className = "ln info";
    let status = "done";
    try { status = JSON.parse(event.data).status || status; }
    catch (e) { /* abaikan */ }
    d.textContent = status === "stopped" ? "\n=== job dihentikan ==="
      : status === "error" ? "\n=== job gagal ===" : "\n=== job selesai ===";
    consoleEl.appendChild(d);
    if (state.logFollow !== false) consoleEl.scrollTop = consoleEl.scrollHeight;
    es.close();
    if (state.es === es) state.es = null;
    if (statusEl) {
      statusEl.textContent = status === "error" ? "gagal"
        : status === "stopped" ? "dihentikan" : "selesai";
      statusEl.className = "console-status " + (status === "error" ? "error"
        : status === "stopped" ? "stopped" : "done");
    }
    if (spinEl) spinEl.classList.add("hidden");
  });
  es.onerror = () => {
    if (routeId !== state.routeId) {
      es.close();
      return;
    }
    if (consoleEl.isConnected && state.es === es) {
      if (statusEl) statusEl.textContent = "mencoba ulang";
      if (spinEl) spinEl.classList.remove("hidden");
    }
  };
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

function bindNilai(data) {
  // Warna garis & titik. Palet gelap lebih terang dari palet terang supaya
  // tidak ada seri yang tenggelam di latar #191919; pemilihan dibaca saat
  // grafik digambar, jadi menyalakan mode gelap lalu buka Dashboard
  // menghasilkan palet yang sesuai.
  const PALETTE = temaSaatIni() === "gelap"
    ? ["#6fb2df", "#dcb45c", "#8bc894", "#e07c78", "#a894e8", "#5fc9bd", "#e79a63", "#93aef5"]
    : ["#1f6c9f", "#956400", "#346538", "#9f2f2d", "#5b3d9e", "#0f766e", "#b5541d", "#3a5fcd"];
  const hidden = new Set();
  let filter = "Semua";

  const legendEl = $("#nilai-legend");
  legendEl.innerHTML = data.courses.map((c, i) => `
    <button class="nilai-leg" data-c="${esc(c.id)}" title="Klik untuk menampilkan/menyembunyikan">
      <span class="nilai-dot" style="background:${PALETTE[i % PALETTE.length]}"></span>${esc(c.nama)}
    </button>`).join("") + `
    <div class="nilai-keys">
      <span class="nilai-key"><span class="k full"></span>Diskusi</span>
      <span class="nilai-key"><span class="k ring"></span>Tugas</span>
    </div>`;

  let VW = 720, VH = 320;   // ukuran viewBox aktif (dipakai posisi tooltip)
  let lebarTerakhir = 0;     // lebar plot saat terakhir digambar

  function render() {
    const plot = $("#nilai-plot");
    if (!plot) return;
    const sesi = data.sesi;
    // Layar sempit (ponsel): viewBox dibuat lebih kecil DAN lebih tinggi.
    // SVG-nya `width:100%; height:auto`, jadi tinggi render = lebar x (H/W).
    // Dengan rasio 720x320, plot selebar 340px cuma setinggi ~150px dan teks
    // sumbunya ikut menyusut jadi ~5px. Rasio mendekati 1:1 menjaga tinggi
    // di kisaran 340px; skala pembesarnya juga lebih besar, jadi huruf, grid,
    // dan titik ikut terbaca.
    // kalau plot belum punya lebar (belum dilayout / isinya masih kosong),
    // pakai lebar induknya sebagai cadangan, bukan langsung 720.
    const lebar = plot.clientWidth || (plot.parentElement && plot.parentElement.clientWidth) || 720;
    const sempit = lebar < 620;
    const W = sempit ? 400 : 720;
    const H = sempit ? 400 : 320;
    const PL = sempit ? 32 : 42, PB = sempit ? 26 : 30;
    const PT = sempit ? 14 : 16, PR = sempit ? 12 : 16;
    const KS = sempit ? 3 : 2.2;    // ketebalan garis
    const KC = sempit ? 2.6 : 2;    // ketebalan tepi titik
    const RT = sempit ? 5 : 3.6;    // radius titik
    VW = W; VH = H;
    lebarTerakhir = lebar;
    const x = (i) => PL + (sesi.length > 1 ? i * (W - PL - PR) / (sesi.length - 1) : (W - PL - PR) / 2);
    const y = (v) => PT + (100 - v) / 100 * (H - PT - PB);
    const visible = data.courses.filter((c) => !hidden.has(c.id));
    let g = "";
    // grid y setiap 20
    for (let v = 0; v <= 100; v += 20) {
      g += `<line x1="${PL}" y1="${y(v)}" x2="${W - PR}" y2="${y(v)}" class="grid"/>`;
      g += `<text x="${PL - 6}" y="${y(v) + 3}" class="axis" text-anchor="end">${v}</text>`;
    }
    // label x -- di layar sempit dilewati tiap label kedua supaya "S10"
    // tidak bertabrakan dengan tetangganya saat daftar sesinya panjang
    const langkah = sempit && sesi.length > 8 ? 2 : 1;
    sesi.forEach((s, i) => {
      if (i % langkah !== 0) return;
      g += `<text x="${x(i)}" y="${H - PB + 16}" class="axis" text-anchor="middle">S${s}</text>`;
    });
    // Satu garis per matkul: Diskusi dan Tugas digabung jadi satu
    // garis yang menyambung; jenisnya dibedakan lewat titik & hover.
    for (const c of visible) {
      const color = PALETTE[data.courses.indexOf(c) % PALETTE.length];
      const pts = [];
      for (const t of c.titik) {
        let v = null;
        let jenis = null;
        if (filter !== "Tugas" && t.Diskusi !== null && t.Diskusi !== undefined) {
          v = t.Diskusi;
          jenis = "Diskusi";
        } else if (filter !== "Diskusi" && t.Tugas !== null && t.Tugas !== undefined) {
          v = t.Tugas;
          jenis = "Tugas";
        }
        if (v === null) continue;
        const i = sesi.indexOf(t.sesi);
        if (i < 0) continue;
        pts.push({ x: x(i), y: y(v), v, s: t.sesi, jenis, i });
      }
      if (pts.length >= 2) {
        let d = `M ${pts[0].x} ${pts[0].y}`;
        for (let k = 1; k < pts.length; k++) {
          const a = pts[k - 1];
          const b = pts[k];
          const mx = (a.x + b.x) / 2;
          d += ` C ${mx} ${a.y}, ${mx} ${b.y}, ${b.x} ${b.y}`;
        }
        g += `<path d="${d}" fill="none" stroke="${color}" stroke-width="${KS}" class="line"/>`;
      }
      for (const p of pts) {
        // Diskusi: bulat penuh warna mata kuliah. Tugas: ring -- pusatnya
        // warna permukaan (sama seperti kunci legenda .k.ring) dan pinggirnya
        // warna mata kuliah. `fill` ditaruh di style karena atribut
        // presentasi SVG tidak memahani var().
        const isi = p.jenis === "Diskusi" ? color : "var(--surface-2)";
        g += `<circle cx="${p.x}" cy="${p.y}" r="${RT}" stroke="${color}" stroke-width="${KC}" data-nama="${esc(c.nama)}" data-s="${p.s}" data-jenis="${p.jenis}" data-v="${p.v}" data-color="${color}" class="nilai-pt" style="fill:${isi};animation:ptin .35s ${p.i * 60}ms both"/>`;
      }
    }
    plot.innerHTML = `<svg viewBox="0 0 ${W} ${H}" class="nilai-svg${sempit ? " sempit" : ""}">${g}</svg><div class="nilai-tip hidden" id="nilai-tip"></div>`;
    legendEl.querySelectorAll(".nilai-leg").forEach((b) =>
      b.classList.toggle("off", hidden.has(b.dataset.c)));
  }

  $("#nilai-filter").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    filter = b.dataset.f;
    document.querySelectorAll("#nilai-filter button").forEach((x) => x.classList.toggle("active", x === b));
    render();
  });
  legendEl.addEventListener("click", (e) => {
    const b = e.target.closest(".nilai-leg");
    if (!b) return;
    if (hidden.has(b.dataset.c)) hidden.delete(b.dataset.c);
    else hidden.add(b.dataset.c);
    render();
  });
  $("#nilai-plot").addEventListener("mouseover", (e) => {
    const c = e.target.closest(".nilai-pt");
    const tip = $("#nilai-tip");
    const plot = $("#nilai-plot");
    if (!c || !tip || !plot) return;
    const s = Number(c.dataset.s);
    const jenis = c.dataset.jenis;
    const nomor = jenis === "Tugas" ? (s - 1) / 2 : s;
    const item = Number.isInteger(nomor) ? `${jenis} ${nomor}` : jenis;
    tip.innerHTML = `
      <div class="tip-top">
        <span class="tip-dot" style="background:${esc(c.dataset.color)}"></span>
        <span>${esc(c.dataset.nama)}</span>
      </div>
      <div class="tip-mid">Sesi ${s} <span class="tip-sep">·</span> ${esc(item)}</div>
      <div class="tip-val">${esc(c.dataset.v)}<small> / 100</small></div>`;
    tip.classList.remove("hidden");
    const rect = plot.getBoundingClientRect();
    const cx = Number(c.getAttribute("cx")) * (rect.width / VW);
    const cy = Number(c.getAttribute("cy")) * (rect.height / VH);
    const tw = tip.offsetWidth;
    const th = tip.offsetHeight;
    let left = cx - tw / 2;
    left = Math.max(4, Math.min(left, rect.width - tw - 4));
    let top = cy - th - 10;
    if (top < 0) top = cy + 12;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  });
  $("#nilai-plot").addEventListener("mouseout", (e) => {
    if (e.target.closest(".nilai-pt")) {
      const tip = $("#nilai-tip");
      if (tip) tip.classList.add("hidden");
    }
  });

  // Gambar ulang kalau lebar plot benar-benar berubah (rotate, jendela
  // dipindah, bilah alamat URL bar mobile yang mengubah tata letak).
  // Cuma ketika lebar bergeser > 6px supaya animasi titik tidak berulang
  // tiap kali layar berdenyut. Listener lama ikut dilepas supaya bolak-balik
  // Dashboard tidak menumpuk.
  let timerRender = 0;
  const renderUlang = () => {
    clearTimeout(timerRender);
    timerRender = setTimeout(() => {
      const p = document.querySelector("#nilai-plot");
      if (!p) {
        window.removeEventListener("resize", renderUlang);
        return;
      }
      if (Math.abs((p.clientWidth || 0) - lebarTerakhir) < 6) return;
      render();
    }, 160);
  };
  if (state.nilaiResize) window.removeEventListener("resize", state.nilaiResize);
  state.nilaiResize = renderUlang;
  window.addEventListener("resize", renderUlang);

  render();
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
    <p class="muted">Klik satu baris untuk melihat sesi dan jadwal Diskusi/Tugas-nya.</p>
    <table id="course-table">
      <thead><tr><th>Mata kuliah</th><th>Kode</th><th>Kelas</th><th></th></tr></thead>
      <tbody>
        ${courses.map((c) => `
          <tr class="bisa-klik" data-cid="${esc(c.id)}" onclick="loadSessions('${esc(c.id)}', this)">
            <td>${esc(c.nama)}</td>
            <td>${esc(c.kode)}</td>
            <td>${esc(c.kelas)}</td>
            <td><span class="link lihat-sesi">${icon("calendar")}<span>lihat sesi</span></span></td>
          </tr>`).join("")}
      </tbody>
    </table>
    <div id="course-detail"></div>`;
};

window.loadSessions = async function (cid, tr) {
  const routeId = state.routeId;
  const detail = $("#course-detail");
  if (!detail) return;
  document.querySelectorAll("#course-table tbody tr").forEach((row) => row.classList.remove("aktif"));
  const baris = tr || document.querySelector(`#course-table tr[data-cid="${cid}"]`);
  if (baris) baris.classList.add("aktif");
  detail.innerHTML = '<p class="muted">Memuat sesi dan jadwal dari Moodle...</p>';
  const [hasilList, hasilJadwal] = await Promise.all([
    api(`/api/courses/${cid}/sessions`).catch((e) => e),
    api(`/api/jadwal/${cid}`).catch((e) => ({ items: [], error: e.message })),
  ]);
  if (routeId !== state.routeId || $("#course-detail") !== detail) return;
  // Cookie mati: tampilkan pesan dari server, jangan diam-diam kosong.
  const galatSesi = hasilList instanceof Error ? hasilList.message : "";
  const list = galatSesi || !Array.isArray(hasilList) ? [] : hasilList;
  const jadwal = hasilJadwal || { items: [] };
  const items = jadwal.items || [];
  detail.innerHTML = `
    ${galatSesi ? `<p class="err">${esc(galatSesi)}</p>` : `
    <div class="section-title">Sesi dengan soal</div>
    <div class="row">
      ${list.map((s) => `<span class="badge blue">Sesi ${s.sesi} — ${s.jumlah} soal</span>`).join("") || '<span class="muted">tidak ada</span>'}
    </div>`}
    <div class="section-title">Jadwal Diskusi &amp; Tugas</div>
    <div class="card jadwal-card" id="jadwal-card"></div>`;
  pasangJadwal(items, jadwal.error);
};

// Kalender besar: tiap bar adalah rentang Diskusi/Tugas dari tanggal
// dibuka sampai tenggatnya, memanjang melewati kolom hari.
function pasangJadwal(items, galat) {
  const card = $("#jadwal-card");
  if (!card) return;
  if (galat) {
    card.innerHTML = `<p class="muted">Jadwal tidak bisa dimuat: ${esc(galat)}</p>`;
    return;
  }
  if (!items.length) {
    card.innerHTML = '<p class="muted">Belum ada Diskusi/Tugas dengan tenggat di course ini.</p>';
    return;
  }

  const D = (s) => new Date(s + "T00:00:00");
  const rentang = items.map((it) => ({ ...it, s: D(it.mulai), e: D(it.tenggat) }));
  const hariIni = new Date();
  hariIni.setHours(0, 0, 0, 0);
  const awalBulan = (d) => new Date(d.getFullYear(), d.getMonth(), 1);
  const akhirBulan = (d) => new Date(d.getFullYear(), d.getMonth() + 1, 0);
  const kunci = (d) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;

  // Mulai dari bulan berjalan; kalau tidak ada jadwal di sana, pindah ke
  // tenggat terdekat supaya user langsung melihat bar-nya.
  const diBulanIni = rentang.some((r) => r.s <= akhirBulan(hariIni) && r.e >= awalBulan(hariIni));
  const berikut = rentang.filter((r) => r.e >= hariIni).sort((a, b) => a.e - b.e)[0];
  const rujuk = diBulanIni ? hariIni : ((berikut && berikut.e) || rentang[rentang.length - 1].e);
  let tampil = awalBulan(rujuk);

  const NAMA_HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"];
  const NAMA_BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
  const LANE_H = 20;

  function gambar() {
    const y = tampil.getFullYear();
    const m = tampil.getMonth();
    const pertama = new Date(y, m, 1);
    const offset = (pertama.getDay() + 6) % 7;   // Senin = kolom 0
    const gridMulai = new Date(y, m, 1 - offset);
    const bulanAkhir = new Date(y, m + 1, 0);
    const jumlahMinggu = Math.ceil((offset + bulanAkhir.getDate()) / 7);
    const gridAkhir = new Date(gridMulai);
    gridAkhir.setDate(gridMulai.getDate() + jumlahMinggu * 7 - 1);

    const nampak = rentang
      .filter((r) => r.s <= gridAkhir && r.e >= gridMulai)
      .sort((a, b) => a.s - b.s || a.e - b.e);
    // lane = baris agar bar yang tumpang tindih tidak saling menutupi
    const akhirLane = [];
    for (const r of nampak) {
      let lane = akhirLane.findIndex((t) => t < r.s);
      if (lane === -1) { lane = akhirLane.length; akhirLane.push(r.e); }
      else { akhirLane[lane] = r.e; }
      r.lane = lane;
    }
    const tinggiBaris = Math.max(76, 24 + akhirLane.length * LANE_H + 6);

    let rows = "";
    for (let w = 0; w < jumlahMinggu; w++) {
      const awal = new Date(gridMulai);
      awal.setDate(gridMulai.getDate() + w * 7);
      const akhir = new Date(awal);
      akhir.setDate(awal.getDate() + 6);
      // Tenggat di minggu ini: satu Map per tanggal supaya garisnya
      // tidak dobel kalau dua activity jatuh tempo pada hari yang sama.
      const tenggatMinggu = new Map();
      for (const r of nampak) {
        if (r.e >= awal && r.e <= akhir && !tenggatMinggu.has(kunci(r.e))) {
          tenggatMinggu.set(kunci(r.e), r.jenis.toLowerCase());
        }
      }
      let cells = "";
      const garis = [];
      for (let d = 0; d < 7; d++) {
        const tgl = new Date(awal);
        tgl.setDate(awal.getDate() + d);
        const cls = ["jad-hari"];
        if (tgl.getMonth() !== m) cls.push("luar");
        if (kunci(tgl) === kunci(hariIni)) cls.push("ini");
        const jenisTenggat = tenggatMinggu.get(kunci(tgl));
        if (jenisTenggat) {
          cls.push("tenggat");
          garis.push({ col: d, jenis: jenisTenggat });
        }
        cells += `<div class="${cls.join(" ")}"><span>${tgl.getDate()}</span></div>`;
      }
      let bars = "";
      for (const r of nampak) {
        if (r.e < awal || r.s > akhir) continue;
        const cs = r.s < awal ? 0 : Math.round((r.s - awal) / 86400000);
        const ce = r.e > akhir ? 6 : Math.round((r.e - awal) / 86400000);
        // label hanya di minggu pertama bar ini tampil di bulan ini,
        // walau bar-nya sudah dimulai di bulan sebelumnya
        const hari0 = Math.max(0, Math.round((r.s - gridMulai) / 86400000));
        const awalSeg = w === Math.floor(hari0 / 7);
        const left = (cs / 7) * 100;
        const width = ((ce - cs + 1) / 7) * 100;
        const label = awalSeg ? `<span>${esc(r.jenis)} ${r.nomor}</span>` : "";
        const ket = `${r.nama} — Sesi ${r.sesi} · ${r.mulai} → ${r.tenggat}`
          + (r.mulai_turunan ? " (awal dihitung dari tenggat sebelumnya)" : "");
        bars += `<a class="jad-bar ${r.jenis.toLowerCase()}" href="${esc(r.url)}" target="_blank" rel="noopener"
          title="${esc(ket)}"
          style="left:calc(${left}% + 3px); width:calc(${width}% - 3px); top:${24 + r.lane * LANE_H}px">${label}</a>`;
      }
      const garisHtml = garis.map((g) =>
        `<i class="jad-tenggat ${g.jenis}" style="left:calc(${((g.col + 1) / 7) * 100}% - 1px)"></i>`).join("");
      rows += `<div class="jad-row" style="height:${tinggiBaris}px">${cells}${bars}${garisHtml}</div>`;
    }

    card.innerHTML = `
      <div class="jad-head">
        <div class="jad-nav">
          <button class="jad-btn" data-nav="-1" aria-label="Bulan sebelumnya">${icon("chevron")}</button>
          <strong class="jad-judul">${NAMA_BULAN[m]} ${y}</strong>
          <button class="jad-btn jad-btn-kanan" data-nav="1" aria-label="Bulan berikutnya">${icon("chevron")}</button>
        </div>
        <div class="jad-leg">
          <span class="jad-leg-item"><i class="diskusi"></i>Diskusi</span>
          <span class="jad-leg-item"><i class="tugas"></i>Tugas</span>
          <span class="jad-leg-item"><i class="garis"></i>Garis tenggat</span>
          <span class="jad-leg-item"><i class="hari-ini"></i>Hari ini</span>
        </div>
      </div>
      <div class="jad-grid">
        <div class="jad-row jad-head-hari">${NAMA_HARI.map((h) => `<div class="jad-hari">${h}</div>`).join("")}</div>
        ${rows}
      </div>`;
    card.querySelectorAll("[data-nav]").forEach((b) => {
      b.addEventListener("click", () => {
        tampil = new Date(tampil.getFullYear(), tampil.getMonth() + Number(b.dataset.nav), 1);
        gambar();
      });
    });
  }
  gambar();
}

VIEWS.settings = async (routeId) => {
  const items = await api("/api/settings");
  if (routeId !== state.routeId) return;
  setPills("");
  const rahasia = new Set(["COOKIE_MOODLE", "APP_PASSWORD"]);
  view.innerHTML = `
    <p class="muted">Pengaturan disimpan ke <span class="kbd">.env</span>.
    COOKIE_MOODLE hanya untuk koneksi Moodle, bukan untuk login dashboard.
    Masukkan cookie Moodle di sini. Kolom rahasia yang kosong tidak mengubah nilai tersimpan.</p>
    <div class="set-tema">
      <div class="set-tema-teks">
        <strong>Mode gelap</strong>
        <p>Dipakai di seluruh aplikasi -- kartu, tabel, grafik, dan modal.
        Tersimpan di peramban ini, bukan di <span class="kbd">.env</span>, jadi tidak ikut terkirim ke mana pun.</p>
      </div>
      <button type="button" class="switch" id="set-tema" role="switch" aria-checked="false">
        ${icon("moon")}
        <span class="switch-track"><span class="switch-thumb"></span></span>
        <span class="switch-label">Terang</span>
      </button>
    </div>
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
  // Sakelar tema hidup di luar #set-list: ia bukan nilai .env, jadi tidak
  // boleh ikut terbaca oleh loop simpan di bawah.
  const sakelarTema = $("#set-tema");
  const sinkronSakelar = () => {
    const gelap = temaSaatIni() === "gelap";
    sakelarTema.classList.toggle("on", gelap);
    sakelarTema.setAttribute("aria-checked", String(gelap));
    sakelarTema.querySelector(".switch-label").textContent = gelap ? "Gelap" : "Terang";
    sakelarTema.querySelector(".icon").outerHTML = icon(gelap ? "moon" : "sun");
  };
  sakelarTema.addEventListener("click", () => {
    terapkanTema(temaSaatIni() === "gelap" ? "terang" : "gelap");
    sinkronSakelar();
  });
  sinkronSakelar();
  // Pra-muat daftar model sekarang, bukan saat picker diklik. Di Linux
  // `opencode models` butuh ±1,5 detik; kalau dimulai dari klik, picker
  // terlihat kosong/memuat lama. Hasilnya di-cache 5 menit di kedua sisi.
  loadModelOptions();
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
    message.textContent = r && r.ok
      ? (r.moodle_disegarkan
        ? `Tersimpan. Cache Moodle dibersihkan (${r.cache_dibersihkan || 0} halaman) -- memuat ulang...`
        : "Tersimpan.")
      : (r && r.error) || "Gagal.";
    if (r && r.ok) setTimeout(() => {
      if (saveRouteId === state.routeId) location.reload();
    }, r.moodle_disegarkan ? 900 : 600);
  });
};

/* ============================================================ modal */

// Dialog konfirmasi kecil. Mengembalikan Promise<boolean>; Esc, klik area
// gelap, dan tombol batal semuanya dianggap "tidak".
function konfirmasi({ judul, pesan, labelYa = "Ya", labelTidak = "Batal", nada = "" }) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal" role="alertdialog" aria-modal="true" aria-labelledby="modal-judul">
        <h3 id="modal-judul">${esc(judul)}</h3>
        <p>${esc(pesan)}</p>
        <div class="modal-aksi">
          <button type="button" class="btn ghost" data-tidak>${esc(labelTidak)}</button>
          <button type="button" class="btn ${esc(nada)}" data-ya>${esc(labelYa)}</button>
        </div>
      </div>`;
    const selesai = (hasil) => {
      document.removeEventListener("keydown", onKey);
      overlay.remove();
      resolve(hasil);
    };
    const onKey = (e) => { if (e.key === "Escape") selesai(false); };
    overlay.addEventListener("click", (e) => { if (e.target === overlay) selesai(false); });
    overlay.querySelector("[data-tidak]").addEventListener("click", () => selesai(false));
    overlay.querySelector("[data-ya]").addEventListener("click", () => selesai(true));
    document.addEventListener("keydown", onKey);
    document.body.appendChild(overlay);
    overlay.querySelector("[data-ya]").focus();
  });
}

/* ============================================================ boot */

$("#login-form").addEventListener("submit", doLogin);
$("#logout").addEventListener("click", async () => {
  const ya = await konfirmasi({
    judul: "Keluar dari sesi?",
    pesan: "Halaman masuk akan terbuka dan kamu perlu login lagi. Job yang sedang berjalan tetap berlanjut di server.",
    labelYa: "Keluar",
    labelTidak: "Batal",
    nada: "danger",
  });
  if (!ya) return;
  state.sesi = false;
  await api("/api/logout", { method: "POST" }).catch(() => {});
  location.hash = "#dashboard";
  showLogin();
});
window.addEventListener("hashchange", route);
init();
