/* ═══════════════════════════════════════════════════
   ClawdBot Recruiter – App Logic
   ═══════════════════════════════════════════════════ */

const API = '';  // same origin

// ── State ──────────────────────────────────────────
let currentJobId = null;
let pollTimer = null;
let startTime = null;
let candidates = [];

// ── DOM refs ───────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const searchPanel = $('#searchPanel');
const statusPanel = $('#statusPanel');
const resultsPanel = $('#resultsPanel');
const historyPanel = $('#historyPanel');

// ── Init ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    loadHistory();

    // Search form
    $('#searchForm').addEventListener('submit', handleSearch);

    // New search button
    $('#btnNewSearch').addEventListener('click', resetToSearch);

    // Export
    $('#btnExport').addEventListener('click', handleExport);

    // Filter
    $('#filterInput').addEventListener('input', handleFilter);

    // View toggle
    $('#viewTable').addEventListener('click', () => setView('table'));
    $('#viewCards').addEventListener('click', () => setView('cards'));
});


// ═══ Search ════════════════════════════════════════
async function handleSearch(e) {
    e.preventDefault();

    const keywordsRaw = $('#keywords').value.trim();
    if (!keywordsRaw) return;

    const keywords = keywordsRaw.split(',').map(k => k.trim()).filter(Boolean);
    const location = $('#location').value.trim();
    const maxItems = parseInt($('#maxItems').value) || 10;

    const platforms = [];
    $$('input[name="platforms"]:checked').forEach(cb => platforms.push(cb.value));
    if (platforms.length === 0) {
        toast('Vui lòng chọn ít nhất 1 nền tảng', 'error');
        return;
    }

    const payload = {
        keywords,
        platforms,
        location: location || undefined,
        max_items_per_platform: maxItems,
    };

    // Disable button
    const btn = $('#btnSearch');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Đang tạo job...';

    try {
        const resp = await fetch(`${API}/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();

        if (!resp.ok) {
            toast(data.detail || 'Lỗi tạo job', 'error');
            btn.disabled = false;
            btn.innerHTML = '<span class="btn-icon">🚀</span> Bắt đầu quét';
            return;
        }

        currentJobId = data.job_id;
        startTime = Date.now();

        // Auto-generate tab name
        const tabName = `${keywords[0]} ${location || ''} ${new Date().toLocaleDateString('vi')}`.trim();
        $('#tabName').value = tabName;

        // Show status panel
        showStatusPanel(platforms.length);
        startPolling();

        toast('Job đã được tạo! Đang quét...', 'info');

    } catch (err) {
        toast(`Lỗi kết nối server: ${err.message}`, 'error');
    }

    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">🚀</span> Bắt đầu quét';
}


// ═══ Polling ═══════════════════════════════════════
function startPolling() {
    pollTimer = setInterval(pollStatus, 3000);
}

function stopPolling() {
    if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

async function pollStatus() {
    if (!currentJobId) return;

    try {
        const resp = await fetch(`${API}/jobs/${currentJobId}`);
        const data = await resp.json();

        const elapsed = Math.round((Date.now() - startTime) / 1000);
        $('#statTime').textContent = elapsed < 60 ? `${elapsed}s` : `${Math.floor(elapsed / 60)}m ${elapsed % 60}s`;
        $('#statCandidates').textContent = data.candidate_count || 0;

        if (data.status === 'running') {
            const progress = Math.min(90, (elapsed / 180) * 90);
            $('#progressFill').style.width = `${progress}%`;
            $('#progressText').textContent = `Đang quét... đã tìm thấy ${data.candidate_count} ứng viên`;
        }
        else if (data.status === 'succeeded') {
            stopPolling();
            $('#progressFill').style.width = '100%';
            $('#progressText').textContent = `Hoàn thành! ${data.candidate_count} ứng viên`;
            $('#statusIcon').textContent = '✅';
            $('#statusTitle').textContent = 'Quét hoàn tất!';
            $('#statusSubtitle').textContent = `Tìm thấy ${data.candidate_count} ứng viên trên các nền tảng`;

            toast(`Tìm thấy ${data.candidate_count} ứng viên!`, 'success');

            // Load results
            await loadResults();
            loadHistory();
        }
        else if (data.status === 'failed') {
            stopPolling();
            $('#progressFill').style.width = '100%';
            $('#progressFill').style.background = 'var(--danger)';
            $('#progressText').textContent = `Lỗi: ${data.error || 'Unknown error'}`;
            $('#statusIcon').textContent = '❌';
            $('#statusTitle').textContent = 'Quét thất bại';
            $('#statusSubtitle').textContent = data.error || 'Đã xảy ra lỗi';
            toast('Job thất bại: ' + (data.error || '').substring(0, 80), 'error');
            loadHistory();
        }

    } catch (err) {
        console.error('Poll error:', err);
    }
}


// ═══ Results ═══════════════════════════════════════
async function loadResults() {
    if (!currentJobId) return;

    try {
        const resp = await fetch(`${API}/jobs/${currentJobId}/results`);
        const data = await resp.json();
        candidates = data.candidates || [];

        $('#resultCount').textContent = candidates.length;

        renderTable(candidates);
        renderCards(candidates);

        // Show results panel
        resultsPanel.classList.remove('hidden');

    } catch (err) {
        toast('Không thể tải kết quả', 'error');
    }
}

function renderTable(items) {
    const tbody = $('#resultsBody');
    tbody.innerHTML = '';

    items.forEach((c, i) => {
        const links = [];
        if (c.linkedin_url) links.push(`<a href="${c.linkedin_url}" target="_blank" class="link-pill">LinkedIn</a>`);
        if (c.artstation_url) links.push(`<a href="${c.artstation_url}" target="_blank" class="link-pill">ArtStation</a>`);
        if (c.instagram_url) links.push(`<a href="${c.instagram_url}" target="_blank" class="link-pill">Instagram</a>`);
        if (c.portfolio_url) links.push(`<a href="${c.portfolio_url}" target="_blank" class="link-pill">Portfolio</a>`);
        if (c.source_url && !links.some(l => l.includes(c.source_url))) {
            links.push(`<a href="${c.source_url}" target="_blank" class="link-pill">Profile</a>`);
        }

        const platformClass = (c.source_platform || '').toLowerCase();
        const isTwitter = platformClass === 'x';

        const tr = document.createElement('tr');
        tr.innerHTML = `
      <td style="color:var(--text-muted)">${i + 1}</td>
      <td><strong>${esc(c.full_name || 'N/A')}</strong></td>
      <td style="max-width:200px;color:var(--text-secondary)">${esc((c.title || '').substring(0, 60))}</td>
      <td style="color:var(--text-secondary)">${esc(c.location || '')}</td>
      <td>
        <span class="platform-badge ${platformClass}">${esc(c.source_platform || '')}</span>
      </td>
      <td>${c.email ? `<span class="email-text">${esc(c.email)}</span>` : '<span style="color:var(--text-muted)">—</span>'}</td>
      <td>
        <div class="link-pills">
          ${links.join('')}
          ${isTwitter ? `<button onclick="handleDeepScan('${esc(c.raw?.user?.screen_name || '')}')" class="link-pill deep-scan-pill">🔍 Connects</button>` : ''}
        </div>
      </td>
    `;
        tbody.appendChild(tr);
    });
}

function renderCards(items) {
    const container = $('#cardsView');
    container.innerHTML = '';

    items.forEach(c => {
        const links = [];
        if (c.linkedin_url) links.push(`<a href="${c.linkedin_url}" target="_blank" class="link-pill">💼 LinkedIn</a>`);
        if (c.artstation_url) links.push(`<a href="${c.artstation_url}" target="_blank" class="link-pill">🎨 ArtStation</a>`);
        if (c.instagram_url) links.push(`<a href="${c.instagram_url}" target="_blank" class="link-pill">📸 Instagram</a>`);
        if (c.portfolio_url) links.push(`<a href="${c.portfolio_url}" target="_blank" class="link-pill">🌐 Portfolio</a>`);

        const platformClass = (c.source_platform || '').toLowerCase();
        const isTwitter = platformClass === 'x';

        const card = document.createElement('div');
        card.className = 'candidate-card';
        card.innerHTML = `
      <div class="candidate-card-header">
        <div>
          <div class="candidate-name">${esc(c.full_name || 'N/A')}</div>
          <div class="candidate-title">${esc(c.title || c.bio || '')}</div>
          ${c.location ? `<div class="candidate-location">${esc(c.location)}</div>` : ''}
        </div>
        <span class="platform-badge ${platformClass}">${esc(c.source_platform || '')}</span>
      </div>
      ${c.email ? `<div class="email-text" style="margin-bottom:8px">📧 ${esc(c.email)}</div>` : ''}
      <div class="candidate-meta">
        ${links.join('')}
        ${isTwitter ? `<button onclick="handleDeepScan('${esc(c.raw?.user?.screen_name || '')}')" class="link-pill deep-scan-pill">🔍 Connects</button>` : ''}
      </div>
    `;
        container.appendChild(card);
    });
}


// ═══ Filter ════════════════════════════════════════
function handleFilter() {
    const query = $('#filterInput').value.toLowerCase();
    if (!query) {
        renderTable(candidates);
        renderCards(candidates);
        return;
    }

    const filtered = candidates.filter(c => {
        const text = [c.full_name, c.title, c.location, c.email, c.source_platform, c.bio, ...(c.skills || [])].join(' ').toLowerCase();
        return text.includes(query);
    });

    renderTable(filtered);
    renderCards(filtered);
}


// ═══ Export ════════════════════════════════════════
async function handleExport() {
    if (!currentJobId) return;

    const sheetId = $('#sheetId').value.trim();
    const tabName = $('#tabName').value.trim() || 'Candidates';

    if (!sheetId) {
        toast('Vui lòng nhập Google Sheet ID', 'error');
        return;
    }

    const btn = $('#btnExport');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Đang export...';

    try {
        const resp = await fetch(`${API}/jobs/${currentJobId}/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sheet_id: sheetId, tab_name: tabName }),
        });
        const data = await resp.json();

        const resultEl = $('#exportResult');
        resultEl.classList.remove('hidden');

        if (resp.ok) {
            resultEl.className = 'export-result success';
            resultEl.innerHTML = `✅ Đã export <strong>${data.exported_count}</strong> ứng viên! <a href="${data.sheet_url}" target="_blank" style="color:var(--success)">Mở Google Sheet →</a>`;
            toast('Export thành công!', 'success');
        } else {
            resultEl.className = 'export-result error';
            resultEl.textContent = `❌ Lỗi: ${data.detail || 'Unknown error'}`;
            toast('Export thất bại', 'error');
        }

    } catch (err) {
        toast(`Lỗi kết nối: ${err.message}`, 'error');
    }

    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">📊</span> Export Google Sheet';
}


// ═══ History ═══════════════════════════════════════
async function loadHistory() {
    try {
        const resp = await fetch(`${API}/jobs`);
        const jobs = await resp.json();

        const list = $('#historyList');

        if (!jobs.length) {
            list.innerHTML = '<p class="empty-state">Chưa có lịch sử quét nào</p>';
            return;
        }

        // Sort by most recent
        jobs.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));

        list.innerHTML = jobs.slice(0, 10).map(job => {
            const req = job.request || {};
            const keywords = (req.keywords || []).join(', ') || 'N/A';
            const location = req.location || '';
            const platforms = (req.platforms || []).join(', ');
            const count = job.candidate_count || 0;
            const status = job.status || 'unknown';

            return `
        <div class="history-item" onclick="loadJob('${job.job_id}')">
          <div class="history-item-left">
            <div class="history-status ${status}"></div>
            <div class="history-info">
              <span class="history-keywords">${esc(keywords)}${location ? ` • ${esc(location)}` : ''}</span>
              <span class="history-detail">${esc(platforms)} • ${status}</span>
            </div>
          </div>
          <span class="history-count">${count} 👤</span>
        </div>
      `;
        }).join('');

    } catch (err) {
        console.error('History error:', err);
    }
}

async function loadJob(jobId) {
    currentJobId = jobId;

    try {
        const resp = await fetch(`${API}/jobs/${jobId}`);
        const data = await resp.json();

        if (data.status === 'succeeded') {
            await loadResults();
            searchPanel.classList.add('hidden');
            statusPanel.classList.add('hidden');
            resultsPanel.classList.remove('hidden');
        } else if (data.status === 'running') {
            startTime = Date.now();
            showStatusPanel(0);
            startPolling();
        }

    } catch (err) {
        toast('Không thể tải job', 'error');
    }
}


// ═══ UI Helpers ════════════════════════════════════
function showStatusPanel(platformCount) {
    searchPanel.classList.add('hidden');
    statusPanel.classList.remove('hidden');
    resultsPanel.classList.add('hidden');

    // Reset
    $('#progressFill').style.width = '5%';
    $('#progressFill').style.background = '';
    $('#progressText').textContent = 'Đang khởi tạo...';
    $('#statusIcon').textContent = '⏳';
    $('#statusTitle').textContent = 'Đang quét...';
    $('#statusSubtitle').textContent = 'Hệ thống đang tìm kiếm ứng viên trên các nền tảng';
    $('#statCandidates').textContent = '0';
    $('#statPlatforms').textContent = platformCount;
    $('#statTime').textContent = '0s';
}

function resetToSearch() {
    stopPolling();
    currentJobId = null;
    candidates = [];

    searchPanel.classList.remove('hidden');
    statusPanel.classList.add('hidden');
    resultsPanel.classList.add('hidden');

    $('#exportResult').classList.add('hidden');
    loadHistory();
}

function setView(view) {
    if (view === 'table') {
        $('#tableView').classList.remove('hidden');
        $('#cardsView').classList.add('hidden');
        $('#viewTable').classList.add('active');
        $('#viewCards').classList.remove('active');
    } else {
        $('#tableView').classList.add('hidden');
        $('#cardsView').classList.remove('hidden');
        $('#viewTable').classList.remove('active');
        $('#viewCards').classList.add('active');
    }
}

function toast(message, type = 'info') {
    const container = $('#toastContainer');
    const el = document.createElement('div');
    el.className = `toast ${type}`;
    el.textContent = message;
    container.appendChild(el);

    setTimeout(() => {
        el.style.opacity = '0';
        el.style.transform = 'translateX(40px)';
        el.style.transition = 'all 0.3s';
        setTimeout(() => el.remove(), 300);
    }, 4000);
}

async function handleDeepScan(screenName) {
    if (!screenName) {
        toast('Không tìm thấy username để quét chuyên sâu', 'error');
        return;
    }

    if (!confirm(`Bạn có muốn quét danh sách Follower của @${screenName} để tìm thêm ứng viên không?`)) {
        return;
    }

    const payload = {
        screen_name: screenName,
        connection_type: "followers",
        max_items: 20
    };

    try {
        toast('Bắt đầu quét chuyên sâu...', 'info');
        const resp = await fetch(`${API}/jobs/deep-scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();

        if (!resp.ok) {
            toast(data.detail || 'Lỗi tạo job chuyên sâu', 'error');
            return;
        }

        currentJobId = data.job_id;
        startTime = Date.now();

        // Show status panel
        showStatusPanel(1);
        $('#statusTitle').textContent = `Đang đào sâu kết nối của @${screenName}`;
        startPolling();

    } catch (err) {
        toast(`Lỗi: ${err.message}`, 'error');
    }
}

function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
