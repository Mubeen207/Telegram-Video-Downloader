import { 
    auth, 
    googleProvider, 
    signInWithPopup, 
    signOut, 
    onAuthStateChanged 
} from "/static/js/firebase-config.js";

// Global State
let currentUser = null;
let currentAnalyzedData = null;
let selectedQuality = "original";
let selectedPreset = "best";
let activeTasksPollingInterval = null;
let appSettings = {};

// Helper: Authenticated fetch wrapper that attaches Firebase ID token
async function authFetch(url, options = {}) {
    if (!currentUser) {
        throw new Error("User not authenticated.");
    }
    
    let token = await currentUser.getIdToken(false);
    const headers = options.headers ? { ...options.headers } : {};
    headers["Authorization"] = `Bearer ${token}`;

    let response = await fetch(url, {
        ...options,
        headers
    });

    if (response.status === 401) {
        // Try refreshing token once
        try {
            token = await currentUser.getIdToken(true);
            headers["Authorization"] = `Bearer ${token}`;
            response = await fetch(url, { ...options, headers });
            if (response.ok) return response;
        } catch (e) {}

        const errJson = await response.json().catch(() => ({}));
        showToast(errJson.detail || "Authentication error.", "error");
        throw new Error(errJson.detail || "Unauthorized");
    }

    return response;
}

// Authentication Listeners & State Machine
onAuthStateChanged(auth, async (user) => {
    const authScreen = document.getElementById("authScreen");
    const appDashboard = document.getElementById("appDashboard");
    const authSpinner = document.getElementById("authSpinner");
    const btnGoogle = document.getElementById("btnGoogleSignIn");

    if (user) {
        // Logged In
        currentUser = user;
        authScreen.style.display = "none";
        appDashboard.style.display = "flex";

        // Update User Profile Chip
        document.getElementById("userAvatarImg").src = user.photoURL || "https://www.gravatar.com/avatar/00000000000000000000000000000000?d=mp&f=y";
        document.getElementById("userDisplayName").textContent = user.displayName || "Google User";
        document.getElementById("userEmailText").textContent = user.email || "";
        document.getElementById("diagUserUid").textContent = user.uid;

        // Initialize dashboard data
        await loadSettings();
        await checkSystemStatus();
        startPollingTasks();
    } else {
        // Logged Out
        currentUser = null;
        if (activeTasksPollingInterval) {
            clearInterval(activeTasksPollingInterval);
            activeTasksPollingInterval = null;
        }
        appDashboard.style.display = "none";
        authScreen.style.display = "flex";
        resetDownloader();
    }

    if (btnGoogle) btnGoogle.disabled = false;
    if (authSpinner) authSpinner.style.display = "none";
});

// Google Sign-In Handler
window.handleGoogleSignIn = async function() {
    const btn = document.getElementById("btnGoogleSignIn");
    const spinner = document.getElementById("authSpinner");
    const errBanner = document.getElementById("authErrorBanner");

    errBanner.style.display = "none";
    btn.disabled = true;
    spinner.style.display = "inline-block";

    try {
        await signInWithPopup(auth, googleProvider);
        showToast("Signed in with Google successfully!", "success");
    } catch (error) {
        console.error("Google Auth error:", error);
        btn.disabled = false;
        spinner.style.display = "none";
        
        let message = "Failed to sign in with Google. Please try again.";
        if (error.code === "auth/unauthorized-domain") {
            message = "Domain not authorized. Please open http://localhost:8000 in your browser, or add '127.0.0.1' to Firebase Console > Authentication > Settings > Authorized domains.";
        } else if (error.code === "auth/popup-closed-by-user") {
            message = "Sign-in popup was closed before completing.";
        } else if (error.code === "auth/popup-blocked") {
            message = "Popup blocked by browser. Please allow popups for this site.";
        } else if (error.message) {
            message = error.message;
        }
        errBanner.textContent = message;
        errBanner.style.display = "block";
    }
};

// Sign-Out Handler
window.handleSignOut = async function() {
    try {
        await signOut(auth);
        showToast("Signed out successfully.", "info");
    } catch (e) {
        showToast("Error signing out.", "error");
    }
};

// Theme Management
window.initTheme = function() {
    const savedTheme = localStorage.getItem("tele_theme") || "dark";
    document.documentElement.setAttribute("data-theme", savedTheme);
};

window.toggleTheme = function() {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("tele_theme", next);
};

initTheme();

// Navigation Tabs
window.switchTab = function(tabId) {
    document.querySelectorAll(".nav-tab").forEach(tab => tab.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(pane => pane.classList.remove("active"));

    const tabBtnMap = {
        downloader: "tabBtnDownloader",
        queue: "tabBtnQueue",
        history: "tabBtnHistory",
        settings: "tabBtnSettings"
    };

    const paneMap = {
        downloader: "paneDownloader",
        queue: "paneQueue",
        history: "paneHistory",
        settings: "paneSettings"
    };

    if (tabBtnMap[tabId]) document.getElementById(tabBtnMap[tabId])?.classList.add("active");
    if (paneMap[tabId]) document.getElementById(paneMap[tabId])?.classList.add("active");

    if (tabId === "history") loadHistory();
    if (tabId === "settings") loadSettings();
    if (tabId === "queue") fetchTasks();
};

// Clipboard Paste
window.pasteFromClipboard = async function() {
    try {
        const text = await navigator.clipboard.readText();
        if (text) {
            document.getElementById("telegramUrlInput").value = text.trim();
            handleAnalyze();
        }
    } catch (e) {
        showToast("Clipboard access denied. Please paste manually.", "error");
    }
};

// Alert handling
window.showAlert = function(message) {
    const alertEl = document.getElementById("alertContainer");
    const msgEl = document.getElementById("alertMessage");
    msgEl.textContent = message;
    alertEl.style.display = "flex";
};

window.hideAlert = function() {
    document.getElementById("alertContainer").style.display = "none";
};

// Toast notification
window.showToast = function(message, type = "info") {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = "0";
        setTimeout(() => toast.remove(), 300);
    }, 3500);
};

// Analyze Telegram URL
window.handleAnalyze = async function() {
    hideAlert();
    const urlInput = document.getElementById("telegramUrlInput");
    const rawUrl = urlInput.value.trim();

    if (!rawUrl) {
        showAlert("Please enter a Telegram video link.");
        return;
    }

    const btnAnalyze = document.getElementById("btnAnalyze");
    const btnText = btnAnalyze.querySelector(".btn-text");
    const btnSpinner = btnAnalyze.querySelector(".btn-spinner");
    const btnArrow = btnAnalyze.querySelector(".btn-arrow");

    btnText.textContent = "Analyzing...";
    btnSpinner.style.display = "inline-block";
    btnArrow.style.display = "none";
    btnAnalyze.disabled = true;

    try {
        const response = await authFetch("/api/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ url: rawUrl })
        });

        const res = await response.json();

        if (!response.ok || !res.success) {
            throw new Error(res.detail || res.error || "Failed to analyze video.");
        }

        renderVideoPreview(res.data);

        // Check if auto-start download is turned on
        if (appSettings.auto_start_download === "true") {
            startDownload();
        }
    } catch (err) {
        showAlert(err.message || "Could not retrieve public media from this Telegram URL.");
        document.getElementById("videoPreviewCard").style.display = "none";
    } finally {
        btnText.textContent = "Analyze Video";
        btnSpinner.style.display = "none";
        btnArrow.style.display = "inline-block";
        btnAnalyze.disabled = false;
    }
};

// Render Video Information & Quality Controls
function renderVideoPreview(data) {
    currentAnalyzedData = data;
    const card = document.getElementById("videoPreviewCard");

    // Title
    document.getElementById("videoTitle").textContent = data.title || `Telegram Video (${data.channel})`;

    // Meta chips
    document.getElementById("metaResText").textContent = data.resolution || "Original";
    document.getElementById("metaDurationText").textContent = data.formatted_duration || "00:00";
    document.getElementById("metaSizeText").textContent = data.formatted_filesize || "Unknown size";
    document.getElementById("metaFormatText").textContent = data.format || "MP4";

    // Duration tag on thumb
    document.getElementById("videoDurationTag").textContent = data.formatted_duration || "00:00";

    // Thumbnail
    const imgEl = document.getElementById("videoThumbImg");
    if (data.thumbnail) {
        imgEl.src = data.thumbnail;
        imgEl.style.display = "block";
    } else {
        imgEl.src = "";
        imgEl.style.display = "none";
    }

    // Populate Dynamic Quality Options
    const qualityGroup = document.getElementById("qualitySelectorGroup");
    qualityGroup.innerHTML = "";

    selectedQuality = "original";
    if (data.available_qualities && data.available_qualities.length > 0) {
        data.available_qualities.forEach((q, idx) => {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = `quality-btn ${idx === 0 ? 'active' : ''}`;
            btn.textContent = q.name;
            btn.dataset.quality = q.id;
            btn.onclick = () => selectQuality(q.id);
            qualityGroup.appendChild(btn);
        });
    }

    // Update Presets Estimated Sizes
    if (data.compression_presets) {
        const best = data.compression_presets.find(p => p.id === "best");
        const bal = data.compression_presets.find(p => p.id === "balanced");
        const small = data.compression_presets.find(p => p.id === "smallest");

        if (best) document.getElementById("estSizeBest").textContent = best.estimated_size;
        if (bal) document.getElementById("estSizeBalanced").textContent = bal.estimated_size;
        if (small) document.getElementById("estSizeSmallest").textContent = small.estimated_size;
    }

    // Reset Filename Input
    document.getElementById("customFilenameInput").value = data.filename || "";

    card.style.display = "block";
    card.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

window.handleThumbError = function(img) {
    img.style.display = "none";
};

window.selectQuality = function(qId) {
    selectedQuality = qId;
    document.querySelectorAll(".quality-btn").forEach(btn => {
        if (btn.dataset.quality === qId) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });
};

window.selectPreset = function(presetId) {
    selectedPreset = presetId;
    document.querySelectorAll(".preset-btn").forEach(btn => {
        if (btn.dataset.preset === presetId) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });

    const summaryText = {
        best: "Direct original stream (Fastest & best quality)",
        balanced: "H.264 balanced compression (Saves ~45% space)",
        smallest: "H.264 high compression (Smallest file size)"
    };
    document.getElementById("presetSummaryText").textContent = summaryText[presetId] || "";
};

window.toggleAdvancedSettings = function() {
    const drawer = document.getElementById("advancedDrawer");
    const btn = document.querySelector(".btn-accordion");
    if (drawer.style.display === "none") {
        drawer.style.display = "block";
        btn.classList.add("open");
    } else {
        drawer.style.display = "none";
        btn.classList.remove("open");
    }
};

window.togglePlayPreview = function() {
    if (!currentAnalyzedData || !currentAnalyzedData.direct_url) return;
    const player = document.getElementById("html5VideoPlayer");
    const wrapper = document.getElementById("thumbWrapper");
    if (player.style.display === "none") {
        player.src = currentAnalyzedData.direct_url;
        player.style.display = "block";
        wrapper.style.display = "none";
        player.play().catch(() => {});
    }
};

window.resetDownloader = function() {
    currentAnalyzedData = null;
    const card = document.getElementById("videoPreviewCard");
    if (card) card.style.display = "none";
    const inp = document.getElementById("telegramUrlInput");
    if (inp) inp.value = "";
    const player = document.getElementById("html5VideoPlayer");
    if (player) {
        player.pause();
        player.src = "";
        player.style.display = "none";
    }
    const wrapper = document.getElementById("thumbWrapper");
    if (wrapper) wrapper.style.display = "flex";
};

// Start Download
window.startDownload = async function() {
    if (!currentAnalyzedData) return;

    const customFilename = document.getElementById("customFilenameInput").value.trim() || currentAnalyzedData.filename;
    const crfVal = document.getElementById("customCrfInput").value;
    const fpsVal = document.getElementById("customFpsSelect").value;
    const formatVal = document.getElementById("customFormatSelect").value || "mp4";

    const payload = {
        source_url: currentAnalyzedData.source_url,
        direct_url: currentAnalyzedData.direct_url,
        title: currentAnalyzedData.title,
        filename: customFilename.endsWith(`.${formatVal}`) ? customFilename : `${customFilename.replace(/\.[^/.]+$/, "")}.${formatVal}`,
        quality: selectedQuality,
        preset: selectedPreset,
        total_bytes: currentAnalyzedData.filesize,
        duration: currentAnalyzedData.duration,
        resolution: currentAnalyzedData.resolution,
        custom_settings: {
            crf: crfVal ? parseInt(crfVal) : null,
            fps: fpsVal ? parseInt(fpsVal) : null,
            format: formatVal
        }
    };

    try {
        const res = await authFetch("/api/download", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const data = await res.json();
        if (data.success) {
            showToast("Download started!", "success");
            switchTab("queue");
            fetchTasks();
        }
    } catch (err) {
        showToast(`Failed to start download: ${err.message}`, "error");
    }
};

// Download Tasks & Queue Polling
function startPollingTasks() {
    fetchTasks();
    if (!activeTasksPollingInterval) {
        activeTasksPollingInterval = setInterval(fetchTasks, 1000);
    }
}

async function fetchTasks() {
    if (!currentUser) return;
    try {
        const res = await authFetch("/api/downloads");
        if (!res.ok) return;
        const data = await res.json();
        renderTasks(data.tasks || []);
    } catch (e) {}
}

function renderTasks(tasks) {
    const list = document.getElementById("tasksList");
    const empty = document.getElementById("emptyQueueState");
    const badge = document.getElementById("activeTasksBadge");

    const activeCount = tasks.filter(t => ["downloading", "queued", "processing"].includes(t.status)).length;
    if (activeCount > 0) {
        badge.textContent = activeCount;
        badge.style.display = "inline-block";
    } else {
        badge.style.display = "none";
    }

    if (!tasks || tasks.length === 0) {
        list.innerHTML = "";
        empty.style.display = "flex";
        return;
    }

    empty.style.display = "none";
    list.innerHTML = tasks.map(task => {
        const isDownloading = task.status === "downloading";
        const isProcessing = task.status === "processing";
        const isCompleted = task.status === "completed";
        const isPaused = task.status === "paused";
        const isFailed = task.status === "failed";

        let statusBadgeClass = "badge-subtle";
        let statusLabel = task.status.toUpperCase();
        if (isDownloading) {
            statusBadgeClass = "badge-warning";
            statusLabel = "DOWNLOADING";
        } else if (isProcessing) {
            statusBadgeClass = "badge-warning";
            statusLabel = "PROCESSING (FFMPEG)";
        } else if (isCompleted) {
            statusBadgeClass = "badge-success";
            statusLabel = "COMPLETED";
        } else if (isFailed) {
            statusBadgeClass = "badge-danger";
            statusLabel = "FAILED";
        }

        return `
        <div class="task-card" id="task-${task.id}">
            <div class="task-top">
                <div class="task-info-main">
                    <h4>${escapeHtml(task.filename)}</h4>
                    <div class="task-tags">
                        <span class="badge ${statusBadgeClass}">${statusLabel}</span>
                        <span>${task.quality.toUpperCase()}</span>
                        <span>${task.preset.toUpperCase()}</span>
                    </div>
                </div>
                <div class="task-actions">
                    ${isDownloading ? `
                        <button class="task-btn-action" onclick="pauseTask('${task.id}')" title="Pause">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                        </button>
                    ` : ''}
                    ${isPaused ? `
                        <button class="task-btn-action" onclick="resumeTask('${task.id}')" title="Resume">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                        </button>
                    ` : ''}
                    ${isFailed ? `
                        <button class="task-btn-action" onclick="retryTask('${task.id}')" title="Retry">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
                        </button>
                    ` : ''}
                    ${(isDownloading || isPaused || isProcessing) ? `
                        <button class="task-btn-action" onclick="cancelTask('${task.id}')" title="Cancel">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    ` : ''}
                    ${isCompleted ? `
                        <button class="task-btn-action" onclick="openDownloadFolder()" title="Open Folder">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                        </button>
                    ` : ''}
                    <button class="task-btn-action" onclick="deleteTask('${task.id}')" title="Remove from list">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                </div>
            </div>

            <div class="progress-track">
                <div class="progress-fill ${isProcessing ? 'processing' : (isCompleted ? 'completed' : (isFailed ? 'failed' : ''))}" style="width: ${task.progress_percent}%;"></div>
            </div>

            <div class="task-bottom">
                <div>
                    <span>${task.formatted_downloaded} / ${task.formatted_total}</span>
                    <span>(${task.progress_percent}%)</span>
                </div>
                <div>
                    ${isDownloading ? `<span>Speed: ${task.formatted_speed}</span> • <span>ETA: ${task.formatted_eta}</span>` : ''}
                    ${isProcessing ? `<span>Optimizing video with FFmpeg...</span>` : ''}
                    ${isCompleted ? `<span>Completed</span>` : ''}
                    ${isFailed ? `<span style="color:var(--color-danger);">${escapeHtml(task.error_message || 'Failed')}</span>` : ''}
                </div>
            </div>
        </div>
        `;
    }).join("");
}

window.pauseTask = async function(id) { await authFetch(`/api/downloads/${id}/pause`, { method: "POST" }); fetchTasks(); };
window.resumeTask = async function(id) { await authFetch(`/api/downloads/${id}/resume`, { method: "POST" }); fetchTasks(); };
window.retryTask = async function(id) { await authFetch(`/api/downloads/${id}/retry`, { method: "POST" }); fetchTasks(); };
window.cancelTask = async function(id) { await authFetch(`/api/downloads/${id}/cancel`, { method: "POST" }); fetchTasks(); };
window.deleteTask = async function(id) { await authFetch(`/api/downloads/${id}`, { method: "DELETE" }); fetchTasks(); };

// History
async function loadHistory() {
    if (!currentUser) return;
    try {
        const res = await authFetch("/api/history");
        const data = await res.json();
        renderHistory(data.history || []);
    } catch (e) {}
}

function renderHistory(items) {
    const tbody = document.getElementById("historyTableBody");
    const empty = document.getElementById("emptyHistoryState");
    const table = document.getElementById("historyTable");

    if (!items || items.length === 0) {
        tbody.innerHTML = "";
        table.style.display = "none";
        empty.style.display = "flex";
        return;
    }

    table.style.display = "table";
    empty.style.display = "none";

    tbody.innerHTML = items.map(item => `
        <tr>
            <td class="history-title">${escapeHtml(item.filename)}</td>
            <td><code>${escapeHtml(item.resolution || 'Original')}</code></td>
            <td>${escapeHtml(item.formatted_size || 'Unknown')}</td>
            <td>${new Date(item.created_at).toLocaleString()}</td>
            <td><span class="badge badge-success">Saved</span></td>
            <td style="text-align: right;">
                <button class="btn-ghost" onclick="openDownloadFolder()" title="Open Folder">
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                </button>
                <button class="btn-ghost" onclick="removeHistoryItem('${item.id}')" title="Delete">
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
            </td>
        </tr>
    `).join("");
}

window.removeHistoryItem = async function(id) {
    await authFetch(`/api/history/${id}`, { method: "DELETE" });
    loadHistory();
};

window.clearHistory = async function() {
    if (!confirm("Are you sure you want to clear all your download history?")) return;
    await authFetch("/api/history", { method: "DELETE" });
    loadHistory();
    showToast("History cleared.", "info");
};

// Settings
async function loadSettings() {
    if (!currentUser) return;
    try {
        const res = await authFetch("/api/settings");
        const data = await res.json();
        appSettings = data.settings || {};

        document.getElementById("settingDownloadDir").value = appSettings.download_dir || "";
        document.getElementById("settingDefaultQuality").value = appSettings.default_quality || "original";
        document.getElementById("settingDefaultPreset").value = appSettings.default_preset || "best";
        document.getElementById("settingMaxDownloads").value = appSettings.max_concurrent_downloads || "3";
    } catch (e) {}
}

window.saveSettings = async function() {
    const updated = {
        download_dir: document.getElementById("settingDownloadDir").value.trim(),
        default_quality: document.getElementById("settingDefaultQuality").value,
        default_preset: document.getElementById("settingDefaultPreset").value,
        max_concurrent_downloads: document.getElementById("settingMaxDownloads").value
    };

    try {
        const res = await authFetch("/api/settings", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ settings: updated })
        });
        const data = await res.json();
        if (data.success) {
            appSettings = data.settings;
            showToast("Settings saved successfully!", "success");
        }
    } catch (e) {
        showToast("Failed to save settings.", "error");
    }
};

// System Diagnostics & FFmpeg
async function checkSystemStatus() {
    try {
        const res = await fetch("/api/system/status");
        const data = await res.json();
        const diagFfmpeg = document.getElementById("diagFfmpeg");

        if (data.ffmpeg && data.ffmpeg.available) {
            diagFfmpeg.textContent = "Detected & Ready (Hardware Transcoding Enabled)";
            diagFfmpeg.style.color = "var(--color-success)";
        } else {
            diagFfmpeg.textContent = "Not Found (Original Stream mode active)";
            diagFfmpeg.style.color = "var(--color-warning)";
        }
    } catch (e) {}
}

// Open folder
window.openDownloadFolder = async function() {
    try {
        const res = await authFetch("/api/open-folder", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ path: appSettings.download_dir || null })
        });
        if (res.ok) {
            showToast("Opened download folder in Windows Explorer.", "success");
        } else {
            showToast("Could not open folder automatically.", "error");
        }
    } catch (e) {
        showToast("Could not open folder.", "error");
    }
};

function escapeHtml(str) {
    if (!str) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
