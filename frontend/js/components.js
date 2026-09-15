/**
 * Tuton Agent - UI Components Module
 * Reusable UI component renderers.
 */

// === Toast ===
const Toast = {
    show(message, type = "info", duration = 3000) {
        const toast = document.getElementById("toast");
        const icon = toast.querySelector("[data-lucide]");
        const text = document.getElementById("toast-message");
        
        // Set icon based on type
        const iconMap = {
            info: "check-circle",
            success: "check-circle",
            error: "alert-circle",
            warning: "alert-triangle",
        };
        
        const colorMap = {
            info: "text-green-400",
            success: "text-green-400",
            error: "text-red-400",
            warning: "text-yellow-400",
        };
        
        icon.setAttribute("data-lucide", iconMap[type] || iconMap.info);
        icon.className = `w-5 h-5 ${colorMap[type] || colorMap.info} shrink-0`;
        text.innerText = message;
        
        // Re-render icons
        if (window.lucide) {
            lucide.createIcons();
        }
        
        // Show
        toast.classList.remove("translate-x-full");
        toast.classList.add("translate-x-0");
        
        setTimeout(() => {
            toast.classList.remove("translate-x-0");
            toast.classList.add("translate-x-full");
        }, duration);
    },
};

// === Loading Spinner ===
const Spinner = {
    create(size = "sm") {
        const sizeClasses = {
            xs: "w-3 h-3",
            sm: "w-4 h-4",
            md: "w-5 h-5",
            lg: "w-6 h-6",
        };
        return `<span class="inline-flex items-center justify-center ${sizeClasses[size]} animate-spin">
            <svg class="w-full h-full text-current" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
        </span>`;
    },
};

// === Status Badge ===
const StatusBadge = {
    render(status) {
        const classes = {
            done: "bg-green-100 text-green-700",
            failed: "bg-red-100 text-red-700",
            pending: "bg-gray-100 text-gray-600",
        };
        
        const icons = {
            done: "check",
            failed: "x",
            pending: "clock",
        };
        
        const labels = {
            done: "DONE",
            failed: "FAIL",
            pending: "PENDING",
        };
        
        const cls = classes[status] || classes.pending;
        const icon = icons[status] || icons.pending;
        const label = labels[status] || status.toUpperCase();
        
        return `<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md ${cls} text-xs font-bold">
            <i data-lucide="${icon}" class="w-3 h-3"></i> ${label}
        </span>`;
    },
};

// === File Size Format ===
const FileUtils = {
    formatSize(bytes) {
        if (bytes === 0) return "0 B";
        const k = 1024;
        const sizes = ["B", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
    },
};

// === Terminal Output ===
const Terminal = {
    append(text, type = "info") {
        const terminal = document.getElementById("terminal-output");
        if (!terminal) return;
        
        const div = document.createElement("div");
        div.className = `terminal-line ${type}`;
        div.textContent = text;
        terminal.appendChild(div);
        terminal.scrollTop = terminal.scrollHeight;
    },
    
    appendHtml(html, type = "info") {
        const terminal = document.getElementById("terminal-output");
        if (!terminal) return;
        
        const div = document.createElement("div");
        div.className = `terminal-line ${type}`;
        div.innerHTML = html;
        terminal.appendChild(div);
        terminal.scrollTop = terminal.scrollHeight;
    },
    
    clear() {
        const terminal = document.getElementById("terminal-output");
        if (terminal) {
            terminal.innerHTML = `<div class="terminal-line cmd">user@tuton:~$ Terminal dibersihkan.</div>`;
        }
    },
};

// === Navigation ===
const Navigation = {
    switchTo(tabId, state) {
        // Hide all tabs
        document.querySelectorAll(".tab-content").forEach((tab) => {
            tab.classList.add("hidden");
            tab.classList.remove("flex");
        });
        
        // Show selected tab
        const activeTab = document.getElementById(`tab-${tabId}`);
        if (activeTab) {
            activeTab.classList.remove("hidden");
            activeTab.classList.add("flex");
        }
        
        // Update nav buttons
        document.querySelectorAll(".nav-btn").forEach((btn) => {
            btn.classList.remove("active", "bg-white/10", "text-white");
            btn.classList.add("text-slate-400");
        });
        
        // Highlight active nav
        const activeNav = document.getElementById(`nav-${tabId}`);
        if (activeNav) {
            activeNav.classList.add("active", "bg-white/10", "text-white");
            activeNav.classList.remove("text-slate-400");
        }
        
        state.set("currentTab", tabId);
    },
};

// === Table Rendering ===
const TableRenderer = {
    renderStatusTable(items) {
        if (!items || items.length === 0) {
            return `<tr><td colspan="4" class="px-6 py-8 text-center text-gray-500">Tidak ada data</td></tr>`;
        }
        
        return items.map((item) => `
            <tr class="hover:bg-gray-50 transition-colors">
                <td class="px-6 py-4">
                    ${StatusBadge.render(item.status)}
                </td>
                <td class="px-6 py-4 font-medium text-gray-900">${item.matkul}</td>
                <td class="px-6 py-4 text-gray-600">${item.sesi ? `Sesi ${item.sesi}` : "-"}</td>
                <td class="px-6 py-4 text-gray-600">${item.desc}</td>
            </tr>
        `).join("");
    },
};

// === Card Rendering ===
const CardRenderer = {
    renderResultCard(course) {
        const fileCount = course.files.length;
        if (fileCount === 0) {
            return `
                <div class="bg-white rounded-2xl border border-gray-100 shadow-soft overflow-hidden flex flex-col border-dashed opacity-70">
                    <div class="p-6 border-b border-gray-50 bg-gray-50/30 flex items-start justify-between">
                        <div>
                            <div class="text-xs font-bold text-gray-400 mb-1 uppercase tracking-wider">${course.name}</div>
                            <h3 class="text-lg font-bold text-gray-600">${course.name}</h3>
                            <p class="text-xs text-gray-400 mt-1">Belum ada file selesai</p>
                        </div>
                        ${course.folder ? `
                        <button class="text-gray-400 hover:text-red-600 transition-colors p-2" 
                                onclick="Results.deleteCourse('${course.folder.replace(/\\/g, "\\\\")}')" title="Hapus matkul">
                            <i data-lucide="trash-2" class="w-5 h-5"></i>
                        </button>` : ""}
                    </div>
                </div>
            `;
        }
        
        const fileItems = course.files.map((file) => `
            <li class="flex items-center justify-between p-3 rounded-xl hover:bg-gray-50 border border-transparent hover:border-gray-100 transition-colors group">
                <div class="flex items-center gap-3 overflow-hidden">
                    <i data-lucide="file-text" class="w-4 h-4 text-blue-500 shrink-0"></i>
                    <div class="truncate">
                        <p class="text-sm font-medium text-gray-900 truncate">${file.name}</p>
                        <p class="text-[10px] text-gray-400">Sesi ${file.sesi || "?"} • ${FileUtils.formatSize(file.size)}</p>
                    </div>
                </div>
                <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button class="text-gray-400 hover:text-accent transition-colors p-2" 
                            onclick="Results.download('${file.path.replace(/\\/g, "\\\\")}')" title="Download DOCX">
                        <i data-lucide="download" class="w-4 h-4"></i>
                    </button>
                    <button class="text-gray-400 hover:text-red-600 transition-colors p-2" 
                            onclick="Results.delete('${file.path.replace(/\\/g, "\\\\")}')" title="Hapus DOCX">
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                </div>
            </li>
        `).join("");
        
        return `
            <div class="bg-white rounded-2xl border border-gray-100 shadow-soft overflow-hidden flex flex-col transition-transform hover:-translate-y-1 duration-200">
                <div class="p-6 border-b border-gray-50 bg-gray-50/30 flex items-start justify-between">
                    <div>
                        <div class="text-xs font-bold text-accent mb-1 uppercase tracking-wider">${course.name}</div>
                        <h3 class="text-lg font-bold text-gray-900">${course.name}</h3>
                        <p class="text-xs text-gray-500 mt-1">${fileCount} file berhasil dibuat</p>
                    </div>
                    <div class="flex items-center gap-1">
                        ${course.folder ? `
                        <button class="text-gray-400 hover:text-red-600 transition-colors p-2" 
                                onclick="Results.deleteCourse('${course.folder.replace(/\\/g, "\\\\")}')" title="Hapus matkul">
                            <i data-lucide="trash-2" class="w-5 h-5"></i>
                        </button>` : ""}
                        <div class="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center text-accent">
                            <i data-lucide="book-open" class="w-5 h-5"></i>
                        </div>
                    </div>
                </div>
                <div class="p-4 flex-1">
                    <ul class="space-y-2">${fileItems}</ul>
                </div>
            </div>
        `;
    },
};

window.Toast = Toast;
window.Spinner = Spinner;
window.StatusBadge = StatusBadge;
window.FileUtils = FileUtils;
window.Terminal = Terminal;
window.Navigation = Navigation;
window.TableRenderer = TableRenderer;
window.CardRenderer = CardRenderer;