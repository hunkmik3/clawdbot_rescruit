/* ═══════════════════════════════════════════════════
   Otsulabs Recruiter – App Logic
   ═══════════════════════════════════════════════════ */

const API = '';  // same origin

// ── State ──────────────────────────────────────────
let currentJobId = null;
let pollTimer = null;
let startTime = null;
let candidates = [];
const EMAIL_REGEX = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig;
const EMAIL_BLOCKLIST_PREFIXES = ['noreply@', 'no-reply@', 'donotreply@', 'example@', 'test@'];
const CROSS_PLATFORM_LABELS = {
    artstation: 'ArtStation',
    x: 'X/Twitter',
    twitter: 'X/Twitter',
    linkedin: 'LinkedIn',
    instagram: 'Instagram',
    behance: 'Behance',
};
const COUNTRY_LIST = [
    "Afghanistan",
    "Albania",
    "Algeria",
    "Andorra",
    "Angola",
    "Antigua and Barbuda",
    "Argentina",
    "Armenia",
    "Australia",
    "Austria",
    "Azerbaijan",
    "Bahamas",
    "Bahrain",
    "Bangladesh",
    "Barbados",
    "Belarus",
    "Belgium",
    "Belize",
    "Benin",
    "Bhutan",
    "Bolivia",
    "Bosnia and Herzegovina",
    "Botswana",
    "Brazil",
    "Brunei",
    "Bulgaria",
    "Burkina Faso",
    "Burundi",
    "Cabo Verde",
    "Cambodia",
    "Cameroon",
    "Canada",
    "Central African Republic",
    "Chad",
    "Chile",
    "China",
    "Colombia",
    "Comoros",
    "Congo",
    "Costa Rica",
    "Cote d'Ivoire",
    "Croatia",
    "Cuba",
    "Cyprus",
    "Czechia",
    "Democratic Republic of the Congo",
    "Denmark",
    "Djibouti",
    "Dominica",
    "Dominican Republic",
    "Ecuador",
    "Egypt",
    "El Salvador",
    "Equatorial Guinea",
    "Eritrea",
    "Estonia",
    "Eswatini",
    "Ethiopia",
    "Fiji",
    "Finland",
    "France",
    "Gabon",
    "Gambia",
    "Georgia",
    "Germany",
    "Ghana",
    "Greece",
    "Grenada",
    "Guatemala",
    "Guinea",
    "Guinea-Bissau",
    "Guyana",
    "Haiti",
    "Honduras",
    "Hungary",
    "Iceland",
    "India",
    "Indonesia",
    "Iran",
    "Iraq",
    "Ireland",
    "Israel",
    "Italy",
    "Jamaica",
    "Japan",
    "Jordan",
    "Kazakhstan",
    "Kenya",
    "Kiribati",
    "Kuwait",
    "Kyrgyzstan",
    "Laos",
    "Latvia",
    "Lebanon",
    "Lesotho",
    "Liberia",
    "Libya",
    "Liechtenstein",
    "Lithuania",
    "Luxembourg",
    "Madagascar",
    "Malawi",
    "Malaysia",
    "Maldives",
    "Mali",
    "Malta",
    "Marshall Islands",
    "Mauritania",
    "Mauritius",
    "Mexico",
    "Micronesia",
    "Moldova",
    "Monaco",
    "Mongolia",
    "Montenegro",
    "Morocco",
    "Mozambique",
    "Myanmar",
    "Namibia",
    "Nauru",
    "Nepal",
    "Netherlands",
    "New Zealand",
    "Nicaragua",
    "Niger",
    "Nigeria",
    "North Korea",
    "North Macedonia",
    "Norway",
    "Oman",
    "Pakistan",
    "Palau",
    "Palestine",
    "Panama",
    "Papua New Guinea",
    "Paraguay",
    "Peru",
    "Philippines",
    "Poland",
    "Portugal",
    "Qatar",
    "Romania",
    "Russia",
    "Rwanda",
    "Saint Kitts and Nevis",
    "Saint Lucia",
    "Saint Vincent and the Grenadines",
    "Samoa",
    "San Marino",
    "Sao Tome and Principe",
    "Saudi Arabia",
    "Senegal",
    "Serbia",
    "Seychelles",
    "Sierra Leone",
    "Singapore",
    "Slovakia",
    "Slovenia",
    "Solomon Islands",
    "Somalia",
    "South Africa",
    "South Korea",
    "South Sudan",
    "Spain",
    "Sri Lanka",
    "Sudan",
    "Suriname",
    "Sweden",
    "Switzerland",
    "Syria",
    "Taiwan",
    "Tajikistan",
    "Tanzania",
    "Thailand",
    "Timor-Leste",
    "Togo",
    "Tonga",
    "Trinidad and Tobago",
    "Tunisia",
    "Turkey",
    "Turkmenistan",
    "Tuvalu",
    "Uganda",
    "Ukraine",
    "United Arab Emirates",
    "United Kingdom",
    "United States",
    "Uruguay",
    "Uzbekistan",
    "Vanuatu",
    "Vatican City",
    "Venezuela",
    "Vietnam",
    "Yemen",
    "Zambia",
    "Zimbabwe",
];

// ── DOM refs ───────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const searchPanel = $('#searchPanel');
const statusPanel = $('#statusPanel');
const resultsPanel = $('#resultsPanel');
const historyPanel = $('#historyPanel');

// ── Init ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initCountrySelector();
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

function initCountrySelector() {
    const locationSelect = $('#location');
    if (!locationSelect) return;

    const fragment = document.createDocumentFragment();
    COUNTRY_LIST.forEach(country => {
        const option = document.createElement('option');
        option.value = country;
        option.textContent = country;
        fragment.appendChild(option);
    });
    locationSelect.appendChild(fragment);
}


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
        toast('Please select at least one platform', 'error');
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
    btn.innerHTML = '<span class="spinner"></span> Creating job...';

    try {
        const resp = await fetch(`${API}/jobs`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();

        if (!resp.ok) {
            toast(data.detail || 'Failed to create job', 'error');
            btn.disabled = false;
            btn.innerHTML = '<span class="btn-icon">🚀</span> Start Scan';
            return;
        }

        currentJobId = data.job_id;
        startTime = Date.now();

        // Auto-generate tab name
        const tabName = `${keywords[0]} ${location || ''} ${new Date().toLocaleDateString('en-US')}`.trim();
        $('#tabName').value = tabName;

        // Show status panel
        showStatusPanel(platforms.length);
        startPolling();

        toast('Job created. Scanning...', 'info');

    } catch (err) {
        toast(`Server connection error: ${err.message}`, 'error');
    }

    btn.disabled = false;
    btn.innerHTML = '<span class="btn-icon">🚀</span> Start Scan';
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
            $('#progressText').textContent = `Scanning... found ${data.candidate_count} candidates`;
        }
        else if (data.status === 'succeeded') {
            stopPolling();
            $('#progressFill').style.width = '100%';
            $('#progressText').textContent = `Completed! ${data.candidate_count} candidates`;
            $('#statusIcon').textContent = '✅';
            $('#statusTitle').textContent = 'Scan Completed!';
            $('#statusSubtitle').textContent = `Found ${data.candidate_count} candidates across platforms`;

            toast(`Found ${data.candidate_count} candidates!`, 'success');

            // Load results
            await loadResults();
            loadHistory();
        }
        else if (data.status === 'failed') {
            stopPolling();
            $('#progressFill').style.width = '100%';
            $('#progressFill').style.background = 'var(--danger)';
            $('#progressText').textContent = `Error: ${data.error || 'Unknown error'}`;
            $('#statusIcon').textContent = '❌';
            $('#statusTitle').textContent = 'Scan Failed';
            $('#statusSubtitle').textContent = data.error || 'An error occurred';
            toast('Job failed: ' + (data.error || '').substring(0, 80), 'error');
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
        candidates = sortCandidatesByFollowers(data.candidates || []);

        $('#resultCount').textContent = candidates.length;

        renderTable(candidates);
        renderCards(candidates);

        // Show results panel
        resultsPanel.classList.remove('hidden');

    } catch (err) {
        toast('Unable to load results', 'error');
    }
}

function buildSocialLinks(c) {
    const links = [];
    if (c.linkedin_url) links.push(`<a href="${c.linkedin_url}" target="_blank" class="link-pill">LinkedIn</a>`);
    if (c.artstation_url) links.push(`<a href="${c.artstation_url}" target="_blank" class="link-pill">ArtStation</a>`);
    if (c.x_url) links.push(`<a href="${c.x_url}" target="_blank" class="link-pill">X/Twitter</a>`);
    if (c.instagram_url) links.push(`<a href="${c.instagram_url}" target="_blank" class="link-pill">Instagram</a>`);
    if (c.behance_url) links.push(`<a href="${c.behance_url}" target="_blank" class="link-pill">Behance</a>`);
    if (c.portfolio_url) links.push(`<a href="${c.portfolio_url}" target="_blank" class="link-pill">Portfolio</a>`);
    if (c.source_url && !links.some(l => l.includes(c.source_url))) {
        links.push(`<a href="${c.source_url}" target="_blank" class="link-pill">Profile</a>`);
    }
    return links;
}

function buildSkillTags(c) {
    const skills = c.skills || [];
    const software = c.software || [];
    const all = [...skills.slice(0, 5), ...software.slice(0, 3)];
    if (!all.length) return '';
    return `<div class="skill-tags">${all.map(s => `<span class="skill-tag">${esc(s)}</span>`).join('')}</div>`;
}

function hasCrossPlatformData(c) {
    return c.raw?.cross_platform && Object.keys(c.raw.cross_platform).length > 0;
}

function getFollowerCount(c) {
    const value = Number(c?.followers_count);
    if (!Number.isFinite(value) || value < 0) return null;
    return Math.round(value);
}

function getCrossPlatformSummary(c) {
    const raw = c?.raw?.cross_platform;
    if (!raw || typeof raw !== 'object') {
        return { count: 0, labels: [] };
    }
    const labels = Object.keys(raw)
        .filter(Boolean)
        .map(key => CROSS_PLATFORM_LABELS[key.toLowerCase()] || key);
    return { count: labels.length, labels };
}

function getValueByPath(obj, path) {
    return path.split('.').reduce((acc, key) => (acc && typeof acc === 'object' ? acc[key] : undefined), obj);
}

function isValidEmail(email) {
    if (typeof email !== 'string') return false;
    const normalized = email.trim().toLowerCase();
    if (!normalized) return false;
    if (!/^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i.test(normalized)) return false;
    return !EMAIL_BLOCKLIST_PREFIXES.some(prefix => normalized.startsWith(prefix));
}

function extractEmailsFromText(text) {
    if (typeof text !== 'string' || !text.trim()) return [];
    const matches = text.match(EMAIL_REGEX) || [];
    return matches.filter(isValidEmail);
}

function resolveCandidateEmail(c) {
    const structuredPaths = [
        'email',
        'raw.public_email',
        'raw.email',
        'raw.contactEmail',
        'raw.emailAddress',
        'raw.profile.public_email',
        'raw.profile.email',
        'raw.profile.contact_email',
        'raw.user.email',
    ];

    for (const path of structuredPaths) {
        const value = getValueByPath(c, path);
        if (typeof value === 'string' && isValidEmail(value)) {
            return { email: value.trim(), confidence: 'exact' };
        }
    }

    const textSources = [
        c?.bio,
        c?.title,
        getValueByPath(c, 'raw.description'),
        getValueByPath(c, 'raw.summary'),
        getValueByPath(c, 'raw.profile.summary'),
        getValueByPath(c, 'raw.profile.headline'),
        getValueByPath(c, 'raw.user.description'),
    ];

    for (const source of textSources) {
        const found = extractEmailsFromText(source);
        if (found.length > 0) {
            return { email: found[0], confidence: 'inferred' };
        }
    }

    return { email: '', confidence: 'none' };
}

function sortCandidatesByFollowers(items) {
    return [...items].sort((a, b) => {
        const fb = getFollowerCount(b) ?? -1;
        const fa = getFollowerCount(a) ?? -1;
        return fb - fa;
    });
}

function renderTable(items) {
    const tbody = $('#resultsBody');
    tbody.innerHTML = '';
    const topFollower = Math.max(...items.map(getFollowerCount).filter(v => v !== null), 0);

    items.forEach((c, i) => {
        const links = buildSocialLinks(c);
        const platformClass = (c.source_platform || '').toLowerCase();
        const isTwitter = platformClass === 'x';
        const enriched = hasCrossPlatformData(c);
        const enrich = getCrossPlatformSummary(c);
        const email = resolveCandidateEmail(c);
        const followerCount = getFollowerCount(c);
        const isTopFollower = followerCount !== null && followerCount > 0 && followerCount === topFollower;
        const linkCount = [c.linkedin_url, c.artstation_url, c.x_url, c.instagram_url, c.behance_url, c.portfolio_url].filter(Boolean).length;

        const tr = document.createElement('tr');
        tr.innerHTML = `
      <td style="color:var(--text-muted)">${i + 1}</td>
      <td>
        <strong>${esc(c.full_name || 'N/A')}</strong>
        ${enriched ? '<span class="enriched-badge" title="Cross-platform enriched">+</span>' : ''}
      </td>
      <td style="max-width:200px;color:var(--text-secondary)">${esc((c.title || '').substring(0, 60))}</td>
      <td style="color:var(--text-secondary)">${esc(c.location || '')}</td>
      <td>
        <span class="platform-badge ${platformClass}">${esc(c.source_platform || '')}</span>
        ${linkCount > 1 ? `<span class="link-count" title="${linkCount} platforms">${linkCount}</span>` : ''}
      </td>
      <td class="followers-cell">
        ${followerCount !== null ? `<span>${followerCount.toLocaleString()}</span>${isTopFollower ? '<span class="followers-top-badge" title="Highest followers">TOP</span>' : ''}` : '<span style="color:var(--text-muted)">—</span>'}
      </td>
      <td class="enrich-cell">
        ${enrich.count > 0
                ? `<div class="enrich-chip-wrap">${enrich.labels.map(label => `<span class="enrich-chip">${esc(label)}</span>`).join('')}</div>`
                : '<span class="enrich-none">—</span>'
            }
      </td>
      <td>
        ${email.email
                ? `<div class="email-cell"><span class="email-text">${esc(email.email)}</span><span class="email-source ${email.confidence}">${email.confidence === 'exact' ? 'exact' : 'from bio'}</span></div>`
                : '<span style="color:var(--text-muted)">—</span>'
            }
      </td>
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
    const topFollower = Math.max(...items.map(getFollowerCount).filter(v => v !== null), 0);

    items.forEach(c => {
        const links = [];
        if (c.linkedin_url) links.push(`<a href="${c.linkedin_url}" target="_blank" class="link-pill">💼 LinkedIn</a>`);
        if (c.artstation_url) links.push(`<a href="${c.artstation_url}" target="_blank" class="link-pill">🎨 ArtStation</a>`);
        if (c.x_url) links.push(`<a href="${c.x_url}" target="_blank" class="link-pill">🐦 X/Twitter</a>`);
        if (c.instagram_url) links.push(`<a href="${c.instagram_url}" target="_blank" class="link-pill">📸 Instagram</a>`);
        if (c.behance_url) links.push(`<a href="${c.behance_url}" target="_blank" class="link-pill">🅱️ Behance</a>`);
        if (c.portfolio_url) links.push(`<a href="${c.portfolio_url}" target="_blank" class="link-pill">🌐 Portfolio</a>`);

        const platformClass = (c.source_platform || '').toLowerCase();
        const isTwitter = platformClass === 'x';
        const enriched = hasCrossPlatformData(c);
        const skillsHtml = buildSkillTags(c);
        const enrich = getCrossPlatformSummary(c);
        const email = resolveCandidateEmail(c);
        const followerCount = getFollowerCount(c);
        const isTopFollower = followerCount !== null && followerCount > 0 && followerCount === topFollower;

        const card = document.createElement('div');
        card.className = 'candidate-card';
        card.innerHTML = `
      <div class="candidate-card-header">
        <div>
          <div class="candidate-name">
            ${esc(c.full_name || 'N/A')}
            ${enriched ? '<span class="enriched-badge" title="Cross-platform enriched">+</span>' : ''}
          </div>
          <div class="candidate-title">${esc(c.title || c.bio || '')}</div>
          ${c.location ? `<div class="candidate-location">${esc(c.location)}</div>` : ''}
        </div>
        <span class="platform-badge ${platformClass}">${esc(c.source_platform || '')}</span>
      </div>
      ${email.email ? `<div class="card-metric-line">📧 <span class="email-text">${esc(email.email)}</span><span class="email-source ${email.confidence}">${email.confidence === 'exact' ? 'exact' : 'from bio'}</span></div>` : ''}
      ${followerCount !== null ? `<div class="card-metric-line">👥 ${followerCount.toLocaleString()} followers ${isTopFollower ? '<span class="followers-top-badge">TOP</span>' : ''}</div>` : ''}
      <div class="card-metric-line">🔀 Enrich: ${enrich.count > 0 ? enrich.labels.map(label => `<span class="enrich-chip">${esc(label)}</span>`).join('') : '<span class="enrich-none">—</span>'}</div>
      ${skillsHtml}
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
        const enrich = getCrossPlatformSummary(c);
        const email = resolveCandidateEmail(c);
        const text = [
            c.full_name,
            c.title,
            c.location,
            email.email,
            c.source_platform,
            c.bio,
            ...(c.skills || []),
            ...(enrich.labels || []),
            String(getFollowerCount(c) ?? ''),
        ].join(' ').toLowerCase();
        return text.includes(query);
    });

    const sortedFiltered = sortCandidatesByFollowers(filtered);
    renderTable(sortedFiltered);
    renderCards(sortedFiltered);
}


// ═══ Export ════════════════════════════════════════
async function handleExport() {
    if (!currentJobId) return;

    const sheetId = $('#sheetId').value.trim();
    const tabName = $('#tabName').value.trim() || 'Candidates';

    if (!sheetId) {
        toast('Please enter a Google Sheet ID', 'error');
        return;
    }

    const btn = $('#btnExport');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Exporting...';

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
            resultEl.innerHTML = `✅ Exported <strong>${data.exported_count}</strong> candidates! <a href="${data.sheet_url}" target="_blank" style="color:var(--success)">Open Google Sheet →</a>`;
            toast('Export successful!', 'success');
        } else {
            resultEl.className = 'export-result error';
            resultEl.textContent = `❌ Error: ${data.detail || 'Unknown error'}`;
            toast('Export failed', 'error');
        }

    } catch (err) {
        toast(`Connection error: ${err.message}`, 'error');
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
            list.innerHTML = '<p class="empty-state">No scan history yet</p>';
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
        toast('Unable to load job', 'error');
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
    $('#progressText').textContent = 'Initializing...';
    $('#statusIcon').textContent = '⏳';
    $('#statusTitle').textContent = 'Scanning...';
    $('#statusSubtitle').textContent = 'The system is searching for candidates across platforms';
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
        toast('Username not found for deep scan', 'error');
        return;
    }

    if (!confirm(`Do you want to deep scan followers of @${screenName} to find more candidates?`)) {
        return;
    }

    const payload = {
        screen_name: screenName,
        connection_type: "followers",
        max_items: 20
    };

    try {
        toast('Starting deep scan...', 'info');
        const resp = await fetch(`${API}/jobs/deep-scan`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();

        if (!resp.ok) {
            toast(data.detail || 'Failed to create deep scan job', 'error');
            return;
        }

        currentJobId = data.job_id;
        startTime = Date.now();

        // Show status panel
        showStatusPanel(1);
        $('#statusTitle').textContent = `Deep scanning connections of @${screenName}`;
        startPolling();

    } catch (err) {
        toast(`Error: ${err.message}`, 'error');
    }
}

function esc(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}
