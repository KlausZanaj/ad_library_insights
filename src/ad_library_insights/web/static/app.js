/* Ad Library Insights: one page, no build step.
   State lives in S; every change re-renders the part of the page it touches. */
'use strict';

const COUNTRIES = ['IT', 'US', 'GB', 'DE', 'FR', 'ES', 'PT', 'NL', 'BE', 'AT', 'CH', 'IE', 'SE', 'DK', 'NO',
  'FI', 'PL', 'CZ', 'RO', 'GR', 'HU', 'BG', 'HR', 'SK', 'SI', 'CA', 'AU', 'NZ', 'BR', 'MX', 'AR', 'CL',
  'CO', 'IN', 'JP', 'KR', 'SG', 'AE', 'SA', 'TR', 'ZA', 'IL'];
const PLATFORMS = { facebook: 'Facebook', instagram: 'Instagram', audience_network: 'Audience Network',
  messenger: 'Messenger', threads: 'Threads', whatsapp: 'WhatsApp' };
const MODES = ['keyword', 'company', 'compare', 'news'];
const LEVELS = ['data', 'analysis', 'plan'];
const STUDIO_TABS = ['overview', 'ads', 'seismo', 'durata', 'structure', 'strategy'];
const IS_MCP_APP = Boolean(window.__MCP_APP_MODE__ && window.McpExtApps && window.McpExtApps.App);
let mcpApp = null;
const mcpMediaCache = new Map();

const store = {
  get(key, fallback) { try { return localStorage.getItem(key) || fallback; } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } },
};

const LEVELS_STATE = 'levelsState';
/* The chosen level is the open row. Both are remembered; level 1 is chosen and open the first time. */
function loadLevel() {
  try {
    const saved = JSON.parse(store.get(LEVELS_STATE, ''));
    if (saved && ['data', 'analysis', 'plan'].includes(saved.level)) return { level: saved.level, open: saved.open !== false };
  } catch { /* nothing saved yet */ }
  return { level: 'data', open: true };
}
const START = loadLevel();

const _savedLang = store.get('lang', 'it');
const _savedTheme = store.get('theme', 'light');
const S = {
  lang: _savedLang === 'en' ? 'en' : 'it', theme: _savedTheme === 'dark' ? 'dark' : 'light',
  mode: 'company', level: START.level, levelOpen: START.open, deep: 10, frames: false, deepChoices: [10, 20, 50],
  country: 'IT', query: '', company: '', companyB: '', cmp: null, resultMode: null,
  pages: null, busy: null, busyMode: null, job: null, result: null, jobId: null, notice: null,
  project: null, overlay: null, estimate: null, pending: null,
  history: null, news: null, sort: 'score', filter: 'all', tableQuery: '',
  tab: 'overview', adsView: 'table', stratLevel: 'analysis', stratNeedProject: false,
  seismoWeek: null, archFocus: 'copy',
  searchExpandedManual: false, wayHint: false, mcpSent: false,
  aiJob: null, aiElapsed: 0, aiCopied: false, videoInspect: {},
  durataWindow: 90, durataBusy: false, durataError: false, durataCancelSeq: 0, durataElapsed: 0,
  searchSeq: 0, aiSeq: 0, newsSeq: 0, estSeq: 0,
  simPrice: null, simCost: null, simVat: null, simShip: null, simFeePct: null, simRetPct: null, simItFee: null,
  cmpCopied: false,
  link: { quick: null, mcp: 'checking', running: false, result: null, error: null, test: null, copy: null, hint: false },
};
let T = window.__STRINGS__ || { it: {}, en: {} };
let themeTimer = null;

/* ---------- helpers ---------- */
const $ = (selector, root = document) => root.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function t(key, vars) {
  let text = (T[S.lang] && T[S.lang][key]) ?? (T.en && T.en[key]) ?? key;
  for (const name in vars || {}) text = text.replaceAll(`{${name}}`, vars[name]);
  return text;
}
const hasT = (key) => Boolean((T[S.lang] && T[S.lang][key]) ?? (T.en && T.en[key]));
const num = (value) => (value == null ? '—' : new Intl.NumberFormat(S.lang, { useGrouping: 'always' }).format(value));
const pct = (share) => `${Math.round((share || 0) * 100)}%`;
/* A number with its noun, singular for one: count(1, 'n.days') is "1 giorno" / "1 day". */
const oneOrMore = (key, n) => t(n === 1 ? `${key}.one` : key, { n: num(n) });
const count = (n, key) => t(`${key}.${n === 1 ? 'one' : 'other'}`, { n: num(n) });
const days = (n) => (n == null ? '—' : count(n, 'n.days'));
/* An age span as the targeting has it; 65 is the top Meta offers and means 65 and over. */
function ageRange(low, high) {
  if (low == null && high == null) return '—';
  const from = low ?? 18;
  if (high == null || high >= 65) return from >= 65 ? '65+' : `${from}-65+`;
  return from === high ? `${from}` : `${from}-${high}`;
}
function named(type, code) {
  try { return new Intl.DisplayNames([S.lang], { type }).of(code) || code; } catch { return code; }
}
const region = (code) => (code ? named('region', code) : '');

/* The library names places in English; show countries in the language of the page. */
const ISO = ('AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ '
  + 'CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR '
  + 'GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP '
  + 'KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT '
  + 'MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW '
  + 'SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ '
  + 'UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW').split(' ');
const BY_ENGLISH_NAME = { 'czech republic': 'CZ', turkey: 'TR', macedonia: 'MK', 'ivory coast': 'CI',
  'the netherlands': 'NL', 'south korea': 'KR', russia: 'RU', 'united states': 'US', 'united kingdom': 'GB' };
try {
  const english = new Intl.DisplayNames(['en'], { type: 'region' });
  ISO.forEach((code) => { BY_ENGLISH_NAME[english.of(code).toLowerCase()] ??= code; });
} catch { /* names stay in English */ }
function placeLabel(place) {
  const type = String(place.type || 'countries').toLowerCase();
  const code = type.startsWith('countr') && !type.includes('group') && BY_ENGLISH_NAME[String(place.name).toLowerCase()];
  if (code) return region(code);
  return type.includes('group') ? `${place.name} (${t('type.country_groups')})` : place.name;
}
function day(iso) {
  if (!iso) return '—';
  const d = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return '—';
  return new Intl.DateTimeFormat(S.lang, { day: 'numeric', month: 'short', year: 'numeric' }).format(d);
}
function clock(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return new Intl.DateTimeFormat(S.lang, { hour: '2-digit', minute: '2-digit' }).format(d);
}
function dur(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  if (seconds < 60) return `${seconds} s`;
  const rest = seconds % 60;
  return rest ? `${Math.floor(seconds / 60)} min ${rest} s` : `${seconds / 60} min`;
}
const initials = (name) => (name || '?').split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
function mediaAttr(src) {
  if (!src) return '';
  if (src.startsWith('/') || src.startsWith('data:') || src.startsWith('http')) return `src="${esc(src)}"`;
  const cached = mcpMediaCache.get(src);
  return cached ? `src="${esc(cached)}"` : `data-media-name="${esc(src)}"`;
}
function mediaImg(src, cls, alt = '', lazy = false) {
  if (!src) return '';
  const lzy = lazy && (src.startsWith('/') || src.startsWith('http')) ? ' loading="lazy"' : '';
  return `<img class="${cls}" ${mediaAttr(src)} alt="${esc(alt)}"${lzy}>`;
}
const avatar = (src, name, big) => (src
  ? `<img class="avatar${big ? ' big' : ''}" ${mediaAttr(src)} alt="" data-initials="${esc(initials(name))}">`
  : `<span class="avatar txt${big ? ' big' : ''}">${esc(initials(name))}</span>`);
// a logo or thumbnail that does not load falls back to initials or a clean tile
document.addEventListener('error', (event) => {
  const img = event.target;
  if (!(img instanceof HTMLImageElement)) return;
  if (img.classList.contains('avatar')) {
    const span = document.createElement('span');
    span.className = `avatar txt${img.classList.contains('big') ? ' big' : ''}`;
    span.textContent = img.dataset.initials || '?';
    img.replaceWith(span);
    return;
  }
  if (img.classList.contains('top-card-thumb')) {
    const span = document.createElement('span');
    span.className = 'top-card-thumb';
    img.replaceWith(span);
    return;
  }
  if (img.classList.contains('thumb')) {
    const span = document.createElement('span');
    span.className = 'thumb';
    img.replaceWith(span);
    return;
  }
  img.remove();
}, true);
const firstLine = (ad) => ((ad.body || '').trim().split('\n')[0] || ad.headline || '');

function _unwrapMcp(res) {
  if (!res) return {};
  if (res.structuredContent && typeof res.structuredContent === 'object') return res.structuredContent;
  const textBlock = (res.content || []).find((c) => c && c.type === 'text' && c.text);
  if (textBlock) {
    try { return JSON.parse(textBlock.text); } catch { return { ok: false, error: textBlock.text }; }
  }
  return {};
}
async function mcpCall(action, payload = {}) {
  if (!mcpApp) throw new Error('MCP App not connected');
  const raw = await mcpApp.callServerTool({ name: 'app_studio_action', arguments: { action, payload } });
  const data = _unwrapMcp(raw);
  if (data && data.ok === false && data.error) throw Object.assign(new Error(data.error), { data });
  return data;
}
function _baseName(p) {
  if (!p) return null;
  if (!p.includes('/') && !p.includes('\\') && !p.startsWith('data:')) return p;
  if (p.startsWith('data:') || p.startsWith('/media/')) return p;
  return String(p).split(/[/\\]/).pop() || null;
}
function _normalizeIncomingResult(raw) {
  const r = { ...raw };
  r.mode = r.mode || (r.page ? 'company' : 'keyword');
  r.ads = (r.ads || []).map((ad) => ({
    ...ad,
    thumbnail: ad.thumbnail || _baseName(ad.thumbnail_path),
    logo: ad.logo || _baseName(ad.logo_path),
    frames: (ad.frames || []).map(_baseName).filter(Boolean),
  }));
  if (r.page) r.page = { ...r.page, logo: r.page.logo || _baseName(r.page.logo_path) };
  r.request = r.request || { mode: r.mode, country: r.country || S.country, level: S.level, deep: S.deep, frames: false };
  r._live = true;
  return r;
}
function _resetViewFilters() {
  S.sort = 'score'; S.filter = 'all'; S.tableQuery = ''; S.seismoWeek = null;
  S.aiJob = null; S.aiCopied = false; S.mcpSent = false; S.stratNeedProject = false;
  S.cmpCopied = false; S.durataCancelSeq++; S.durataBusy = false; S.durataError = false;
}
function hydrateFromMcpPayload(data) {
  if (!data || typeof data !== 'object') return;
  if (data.view === 'home') {
    if (data.country) S.country = data.country;
    if ('project' in data) S.project = data.project;
    if (Array.isArray(data.deep_choices)) S.deepChoices = data.deep_choices;
    if (Array.isArray(data.subjects)) S.history = data.subjects;
    S.busy = null; S.busyMode = null;
    render();
    return;
  }
  if (data.view === 'pages' || data.outcome === 'choose_page') {
    S.mode = 'company'; S.pages = data; S.cmp = null; S.notice = null; S.overlay = null;
    S.busy = null; S.busyMode = null; S.searchExpandedManual = false;
    render();
    hydrateMcpImages();
    return;
  }
  if (data.view === 'result' && data.result) {
    const r = _normalizeIncomingResult(data.result);
    _resetViewFilters();
    S.mode = r.mode; S.result = r; S.resultMode = r.mode; S.tab = 'overview';
    S.pages = null; S.cmp = null; S.notice = null; S.overlay = null;
    S.busy = null; S.busyMode = null; S.searchExpandedManual = false;
    render();
    hydrateMcpImages();
    return;
  }
  if (Array.isArray(data.ads)) {
    const r = _normalizeIncomingResult(data);
    _resetViewFilters();
    S.mode = r.mode; S.result = r; S.resultMode = r.mode; S.tab = 'overview';
    S.pages = null; S.cmp = null; S.notice = null; S.overlay = null;
    S.busy = null; S.busyMode = null; S.searchExpandedManual = false;
    render();
    hydrateMcpImages();
    return;
  }
  if (data.rows && data.names) {
    const mkSide = (name, ads) => ({ query: name, page: { name }, ads_parsed: (ads || []).length, ads: (ads || []).map((a) => ({ ...a, thumbnail: _baseName(a.thumbnail || a.thumbnail_path) })) });
    const topA = (data.top_ads && data.top_ads.a) || [];
    const topB = (data.top_ads && data.top_ads.b) || [];
    _resetViewFilters();
    S.mode = 'compare'; S.resultMode = 'compare'; S.cmp = null; S.pages = null; S.notice = null; S.overlay = null;
    S.busy = null; S.busyMode = null;
    S.result = { mode: 'compare', country: data.country || S.country, comparison: data, sides: [mkSide(data.names.a, topA), mkSide(data.names.b, topB)] };
    render();
    hydrateMcpImages();
  }
}
let _hydratingMedia = false;
async function hydrateMcpImages() {
  if (!IS_MCP_APP || !mcpApp || _hydratingMedia) return;
  _hydratingMedia = true;
  try {
    for (;;) {
      const nodes = [...document.querySelectorAll('img[data-media-name]')];
      const names = [...new Set(nodes.map((n) => n.dataset.mediaName).filter(Boolean))];
      if (!names.length) break;
      const batch = names.slice(0, 3);
      await Promise.all(batch.map(async (name) => {
        if (mcpMediaCache.has(name)) return;
        try {
          const got = await mcpCall('media', { name });
          mcpMediaCache.set(name, (got && got.data_uri) || '');
        } catch { mcpMediaCache.set(name, ''); }
      }));
      nodes.forEach((img) => {
        const key = img.dataset.mediaName;
        if (!key || !mcpMediaCache.has(key)) return;
        const uri = mcpMediaCache.get(key);
        img.removeAttribute('data-media-name');
        if (uri) img.src = uri;
        else if (img.classList.contains('avatar')) img.dispatchEvent(new Event('error'));
      });
    }
  } finally { _hydratingMedia = false; }
}

async function _mcpRoute(path, options = {}) {
  const url = new URL(path, 'http://local');
  const body = options.body || {};
  if (url.pathname === '/api/state') return mcpCall('state');
  if (url.pathname === '/api/pages') return mcpCall('pages', { name: url.searchParams.get('name') || '', country: url.searchParams.get('country') || S.country });
  if (url.pathname === '/api/estimate') {
    const lvl = url.searchParams.get('level') || 'data';
    const ads = Number(url.searchParams.get('ads') || 10);
    const fr = url.searchParams.get('frames') === '1';
    if (lvl === 'data') return { level: lvl, uses_assistant: false, ads, images: 0, tokens: 0, band: 'none', concepts: ads, ceiling: ads * 2, seconds: ads * 3 };
    const tokens = (2500 + ads * 400) * (lvl === 'plan' ? 4 : 3) + 3000;
    const band = tokens < 35000 ? 'low' : tokens < 110000 ? 'medium' : 'high';
    return { level: lvl, uses_assistant: true, ads, images: fr ? Math.min(ads, 10) * 3 : 0, tokens, band, concepts: ads, ceiling: ads * 2, seconds: ads * 4 + (fr ? 15 : 0) };
  }
  if (url.pathname === '/api/project' && options.method === 'PUT') return mcpCall('save_project', body);
  if (url.pathname === '/api/precheck') return mcpCall('precheck', body);
  if (url.pathname === '/api/durata') return { id: 'mcp-durata', status: 'done', result: await mcpCall('durata', body) };
  if (url.pathname === '/api/video/inspect') return mcpCall('video_inspect', body);
  if (url.pathname === '/api/history') return { subjects: (await mcpCall('state')).subjects || [] };
  if (url.pathname === '/api/history/changes') return mcpCall('changes', { key: url.searchParams.get('key') || '' });
  if (url.pathname === '/api/jobs' && options.method === 'POST') {
    const act = body.mode === 'keyword' ? 'keyword' : body.mode === 'compare' ? 'compare' : 'company';
    const res = await mcpCall(act, body);
    const out = act === 'compare' ? res : (res.result ? _normalizeIncomingResult(res.result) : res);
    return { id: 'mcp-job', status: 'done', params: body, result: out };
  }
  throw new Error('unsupported in MCP view');
}

async function api(path, options = {}) {
  if (IS_MCP_APP) return _mcpRoute(path, options);
  const init = { method: options.method || 'GET', headers: { ...(options.headers || {}) } };
  if (options.body) { init.body = JSON.stringify(options.body); init.headers['Content-Type'] = 'application/json'; }
  const response = await fetch(path, init);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw Object.assign(new Error(data.error || response.statusText), { status: response.status, data });
  return data;
}

/* ---------- top bar ---------- */
function toggle(name, values, current, label) {
  return values.map((value) => `<button data-action="${name}" data-value="${value}" aria-pressed="${value === current}">${esc(label(value))}</button>`).join('');
}
function renderTop() {
  document.documentElement.lang = S.lang;
  document.documentElement.dataset.theme = S.theme;
  $('#modes').innerHTML = MODES.map((mode) => `<button data-action="mode" data-value="${mode}" aria-current="${mode === S.mode}">${esc(t(`mode.${mode}`))}</button>`).join('');
  const conn = $('#conn-pill');
  if (conn) {
    if (IS_MCP_APP) {
      conn.innerHTML = `<span class="conn-pill ok"><i class="conn-dot"></i>${esc(t('conn.mcp'))}</span>`;
    } else if (S.link.quick && S.link.quick.claude && S.link.mcp === 'connected' && S.link.quick.skills && S.link.quick.skills.installed) {
      conn.innerHTML = `<span class="conn-pill ok"><i class="conn-dot"></i>${esc(t('conn.ok'))}</span>`;
    } else {
      conn.innerHTML = `<button type="button" class="conn-pill" data-action="conn-open"><i class="conn-dot"></i>${esc(t('conn.setup'))}</button>`;
    }
  }
  const tut = $('#tut-btn');
  if (tut) tut.textContent = t('tut.btn');
  const langEl = $('#lang');
  if (langEl) {
    langEl.setAttribute('aria-label', t('lang.label'));
    langEl.innerHTML = toggle('lang', ['it', 'en'], S.lang, (v) => v.toUpperCase());
  }
  $('#theme').setAttribute('aria-label', t('theme.label'));
  $('#theme').innerHTML = toggle('theme', ['light', 'dark'], S.theme, (v) => t(`theme.${v}`));
}

/* ---------- search band ---------- */
function countryOptions(selected) {
  const rows = COUNTRIES.map((code) => [region(code), code]).sort((a, b) => a[0].localeCompare(b[0], S.lang));
  return rows.map(([name, code]) => `<option value="${code}"${code === selected ? ' selected' : ''}>${esc(name)}</option>`).join('');
}
function hasModeResult(mode = S.mode) {
  if (!S.result || S.resultMode !== mode) return false;
  return mode === 'compare' ? Boolean(S.result.comparison) : Boolean((S.result.ads || []).length);
}
function hasModeJob(mode = S.mode) {
  return Boolean(S.job && S.job.params && S.job.params.mode === mode);
}
function hasModeBusy(mode = S.mode) {
  return Boolean(S.busy && S.busyMode === mode);
}
function noticeText() {
  if (!S.notice) return '';
  return S.notice.key ? t(S.notice.key, S.notice.vars) : (S.notice.text || '');
}
function isSearchCollapsed() {
  return (S.mode === 'keyword' || S.mode === 'company')
    && Boolean(hasModeBusy() || (S.pages && S.mode === 'company') || hasModeJob() || hasModeResult())
    && !S.searchExpandedManual;
}
function quickChipsHtml() {
  const list = (S.history || []).slice(0, 4);
  if (!list.length || S.job || S.busy) return '';
  const btns = list.map((row) => `<button type="button" class="quick-chip" data-action="quick-reopen" data-value="${esc(row.key)}">${esc(row.label)} · ${esc(row.country)}</button>`).join('');
  return `<div class="quick-chips"><span>${esc(t('search.quick.label'))}</span>${btns}</div>`;
}
function renderSearch() {
  const active = S.mode === 'keyword' || S.mode === 'company';
  if (isSearchCollapsed()) {
    const label = (S.result && S.resultMode === S.mode)
      ? ((S.result.page && S.result.page.name) || S.result.query || S.company || S.query)
      : (S.mode === 'company' ? (S.company || t('mode.company')) : (S.query || t('mode.keyword')));
    const projBtn = `<button class="linklike compact-pill" data-action="project">${esc(S.project
      ? t('project.saved', { product: S.project.product, price: num(S.project.price) }) : t('project.missing'))}</button>`;
    const freshBtn = S.result && S.resultMode === S.mode && !S.job && !S.busy
      ? `<button class="btn quiet small" data-action="search-fresh">${esc(t('search.fresh'))}</button>` : '';
    $('#search').innerHTML = `<div class="search-compact">
      <span class="compact-title">${esc(label || t(`mode.${S.mode}`))}</span>
      <div class="compact-pills">
        <span class="compact-pill">${esc(region(S.country))}</span>
        <span class="compact-pill">${esc(t(`level.${S.level}`))}</span>
        <span class="compact-pill">${esc(`${num(S.deep)} ${t('deep.after')}`)}</span>
        ${projBtn}
      </div>
      <div class="compact-actions">${freshBtn}<button class="btn quiet small" data-action="search-expand">${esc(t('search.edit'))}</button></div>
    </div>`;
    return;
  }
  let html = `<div class="search-in"><div class="search-head"><div><h1>${esc(t(`mode.${S.mode}`))}</h1><p>${esc(t(`${S.mode}.lead`))}</p></div></div>`;
  if (S.mode === 'compare') {
    const off = S.job || S.busy ? 'disabled' : '';
    const name = (bind, label) => `<label class="field"><span>${esc(t(label))}</span>
      <input type="text" data-bind="${bind}" value="${esc(S[bind])}" placeholder="${esc(t('field.company.hint'))}" ${off} autocomplete="off"></label>`;
    html += `<div class="fields two">${name('company', 'field.companyA')}${name('companyB', 'field.companyB')}
      <label class="field"><span>${esc(t('field.country'))}</span><select data-bind="country" ${off}>${countryOptions(S.country)}</select></label>
      <button class="btn" data-action="submit" ${off}>${esc(t('button.compare'))}</button></div>
      <div class="options"><span>${esc(t('deep.before'))}</span>
      <div class="switch" role="group">${toggle('deep', S.deepChoices, S.deep, String)}</div>
      <span>${esc(t('cmp.deep.after'))}</span><span class="gap"></span><span>${esc(t('cmp.level'))}</span></div>`;
    if (hasModeJob('compare') || hasModeBusy('compare')) html += '<div class="progress"><p><span id="ptext"></span><span class="muted num" id="pleft"></span></p><div class="bar" id="pbar"><i></i></div></div>';
    else if (S.notice) html += `<p class="notice${S.notice.err ? ' err' : ''}">${esc(noticeText())}</p>`;
    $('#search').innerHTML = `${html}</div>`;
    updateProgress();
    return;
  }
  if (!active) {
    $('#search').innerHTML = `${html}</div>`;
    return;
  }
  const company = S.mode === 'company';
  const locked = Boolean(S.job || S.busy);
  html += `<div class="fields">
    <label class="field"><span>${esc(t(company ? 'field.company' : 'field.keyword'))}</span>
      <input type="text" data-bind="${company ? 'company' : 'query'}" value="${esc(company ? S.company : S.query)}"
        placeholder="${esc(t(company ? 'field.company.hint' : 'field.keyword.hint'))}" ${locked ? 'disabled' : ''} autocomplete="off"></label>
    <label class="field"><span>${esc(t('field.country'))}</span>
      <select data-bind="country" ${locked ? 'disabled' : ''}>${countryOptions(S.country)}</select></label>
    <button class="btn" data-action="submit" ${locked ? 'disabled' : ''}>${esc(t(company ? 'button.find' : 'button.search'))}</button>
  </div>
  ${quickChipsHtml()}
  <div class="levels-head"><h2>${esc(t('lv.title'))}</h2><p>${esc(t('lv.sub'))}</p></div>
  <div class="levels">${levelRows(locked)}</div>
  <div class="options">
    <span>${esc(t('deep.before'))}</span>
    <div class="switch" role="group">${toggle('deep', S.deepChoices, S.deep, String)}</div>
    <span>${esc(t('deep.after'))}${S.estimate && S.estimate.seconds ? ` · ${esc(t('deep.time', { time: dur(S.estimate.seconds) }))}` : ''}</span>
    <span class="gap"></span>
    ${S.level === 'analysis' ? '' : `<span class="proj-pill${S.level === 'plan' ? ' active' : ''}"><span>${esc(t('project.label'))}:</span> <button class="linklike" data-action="project">${esc(S.project
      ? t('project.saved', { product: S.project.product, price: num(S.project.price) }) : t('project.missing'))}</button></span>`}
  </div>`;
  html += IS_MCP_APP ? '' : '<section class="way" id="way"></section>';
  if (S.notice) html += `<p class="notice${S.notice.err ? ' err' : ''}">${esc(noticeText())}</p>`;
  $('#search').innerHTML = `${html}</div>`;
  if (!IS_MCP_APP) renderWay();
  updateProgress();
}
function simNumbers() {
  const pr = S.project;
  const p = Number(S.simPrice ?? (pr && pr.price) ?? 180);
  const c = Number(S.simCost ?? (pr && pr.product_cost) ?? 62);
  const vat = Math.min(99.9, Math.max(0, Number(S.simVat ?? (pr && pr.vat_pct) ?? 0)));
  const ship = Math.max(0, Number(S.simShip ?? (pr && pr.shipping_cost) ?? 0));
  const feePctPay = Math.min(99.9, Math.max(0, Number(S.simFeePct ?? (pr && pr.payment_fee_pct) ?? 0)));
  const retPct = Math.min(99.9, Math.max(0, Number(S.simRetPct ?? (pr && pr.return_rate_pct) ?? 0)));
  const fixedPay = Math.max(0, Number((pr && pr.payment_fee_fixed) ?? 0));
  const otherCost = Math.max(0, Number((pr && pr.other_costs) ?? 0));
  const market = (pr && pr.market) || S.country;
  const itFee = S.simItFee !== null ? S.simItFee : (pr && pr.ad_fee_pct != null ? pr.ad_fee_pct > 0 : market === 'IT');
  const adFeePct = itFee ? (pr && pr.ad_fee_pct > 0 ? Number(pr.ad_fee_pct) : 3) : 0;

  const netPrice = vat > 0 ? p / (1 + vat / 100) : p;
  const payFee = p * (feePctPay / 100) + fixedPay;
  const rawMargin = Math.max(0, (netPrice - c) * (1 - retPct / 100) - ship - payFee - otherCost);
  const cpaRaw = rawMargin / (1 + adFeePct / 100);
  const cpa = Math.round(cpaRaw * 10) / 10;
  const lowCut = Math.round(cpaRaw * 2 * 10) / 10;
  const highCut = Math.round(cpaRaw * 3 * 10) / 10;
  const perAd = Math.round(cpaRaw * 2.5 * 10) / 10;
  const round1 = Math.round(perAd * 5 * 10) / 10;
  const billed = Math.round(round1 * (1 + adFeePct / 100) * 10) / 10;
  const roas = cpaRaw > 0 ? (p / cpaRaw).toFixed(2) : '—';
  const cpcs = [1, 2, 3].map((cvr) => {
    const cpc = Math.round(cpaRaw * (cvr / 100) * 100) / 100;
    const zone = cpc < 0.82 ? 'below_iqr' : cpc < 1.06 ? 'below_median' : cpc <= 1.28 ? 'within_iqr' : 'above_iqr';
    return { cvr, cpc, zone };
  });
  const zeroProb = cpaRaw > 0 ? Math.exp(-round1 / cpaRaw) : 1;
  const oneIn = zeroProb > 1e-12 && zeroProb < 1 ? Math.round(1 / zeroProb) : null;
  const isEur = !market || _EUR_MARKETS.has(String(market).toUpperCase());
  return {
    p, c, vat, ship, feePctPay, retPct, itFee, adFeePct, isEur,
    margin: Math.round(rawMargin * 10) / 10, cpa, lowCut, highCut, round1, billed, roas, cpcs, oneIn,
  };
}
const _EUR_MARKETS = new Set(['AT','BE','BG','CY','DE','EE','ES','FI','FR','GR','HR','IE','IT','LT','LU','LV','MT','NL','PT','SI','SK']);
function simMoney(val, isEur) {
  const s = num(val);
  if (!isEur) return s;
  return S.lang === 'it' ? `${s} €` : `€${s}`;
}
function precheckCpcRowsHtml(cpcs, isEur = true) {
  return cpcs.map((row) => {
    const cls = row.zone === 'below_iqr' || row.zone === 'below_median' ? ' hard' : row.zone === 'above_iqr' ? ' ok' : '';
    return `<div class="cpc-row${cls}"><span>${esc(t('pre.cpc.cvr', { n: row.cvr }))}</span><strong>${esc(simMoney(row.cpc, isEur))}</strong><small>${esc(t(`pre.zone.${row.zone}`))}</small></div>`;
  }).join('');
}
function updateSimDom() {
  const { cpa, lowCut, highCut, round1, billed, roas, cpcs, oneIn, isEur } = simNumbers();
  const cpcHtml = precheckCpcRowsHtml(cpcs, isEur);
  const riskText = t('pre.risk.line', {
    spend: simMoney(round1, isEur),
    billed: simMoney(billed, isEur),
    onein: oneIn != null ? num(oneIn) : '—',
  });
  document.querySelectorAll('[data-sim-out="cpa"]').forEach((el) => { el.textContent = num(cpa); });
  document.querySelectorAll('[data-sim-out="roas"]').forEach((el) => { el.textContent = t('lv.v3.sim.roas', { roas }); });
  document.querySelectorAll('[data-sim-out="stop"]').forEach((el) => { el.textContent = `${num(lowCut)} - ${num(highCut)}`; });
  document.querySelectorAll('[data-sim-out="budget"]').forEach((el) => { el.textContent = num(round1); });
  document.querySelectorAll('[data-sim-out="cpc-rows"]').forEach((el) => { el.innerHTML = cpcHtml; });
  document.querySelectorAll('[data-sim-out="risk-line"]').forEach((el) => { el.textContent = riskText; });
}
function levelVisual(level, withIds = true) {
  if (level === 'data') {
    return `<div class="lvl-vis">
      <div class="vis-top"><span class="vis-title">${esc(t('lv.v1.badge'))}</span><span class="vis-pill ok">${esc(t('lv.v1.status'))}</span></div>
      <div class="vis-score"><strong>97 <small>/ 100</small></strong><span class="muted num">${esc(t('lv.v1.meta'))}</span></div>
      <div class="scorebar three"><i style="width:57%"></i><i style="width:25%"></i><i style="width:15%"></i></div>
      <div class="vis-parts num"><span>${esc(t('lv.v1.p1'))}</span><span>${esc(t('lv.v1.p2'))}</span><span>${esc(t('lv.v1.p3'))}</span></div>
    </div>`;
  }
  if (level === 'analysis') {
    return `<div class="lvl-vis">
      <div class="vis-top"><span class="vis-title">${esc(t('lv.v2.badge'))}</span></div>
      <div class="vis-lenses">
        ${[1, 2, 3, 4].map((n) => `<div class="vis-lens"><strong>${esc(t(`lv.v2.c${n}.t`))}</strong><span>${esc(t(`lv.v2.c${n}.d`))}</span></div>`).join('')}
      </div>
    </div>`;
  }
  const { p, c, vat, ship, feePctPay, retPct, itFee, cpa, lowCut, highCut, round1, billed, roas, cpcs, oneIn, isEur } = simNumbers();
  const cpcHelp = `<span class="help-wrap"><button type="button" class="help-btn" data-action="help-toggle" aria-label="${esc(t('help.aria', { topic: t('pre.cpc.title') }))}" aria-expanded="false">?</button><div class="help-pop right" role="tooltip"><h4>${esc(t('pre.cpc.title'))}</h4><p>${esc(t('pre.cpc.help'))}</p></div></span>`;
  return `<div class="lvl-vis">
    <div class="vis-top"><span class="vis-title">${esc(t('lv.v3.badge'))}${simplePop('strat.calc.title', 'help.strat.calc.title', 'help.strat.calc.body')}</span><button class="linklike" data-action="lv-project" style="font-size:.78rem">${esc(t('lv.v3.sim.edit'))}</button></div>
    <div class="sim-inputs">
      <label class="sim-field"><span>${esc(t('lv.v3.sim.price'))}${simplePop('lv.v3.sim.price', 'help.sim.price.title', 'help.sim.price.body')}</span><input type="number" min="1" step="1" data-sim="price" value="${esc(p)}"></label>
      <label class="sim-field"><span>${esc(t('lv.v3.sim.cost'))}${simplePop('lv.v3.sim.cost', 'help.sim.cost.title', 'help.sim.cost.body', null, true)}</span><input type="number" min="0" step="1" data-sim="cost" value="${esc(c)}"></label>
    </div>
    <details class="sim-extra">
      <summary>${esc(t('lv.v3.sim.extra'))}</summary>
      <div class="sim-extra-grid">
        <label class="sim-field"><span>${esc(t('lv.v3.sim.vat'))}</span><input type="number" min="0" max="99" step="1" data-sim="vat" value="${esc(vat)}"></label>
        <label class="sim-field"><span>${esc(t('lv.v3.sim.ship'))}</span><input type="number" min="0" step="0.5" data-sim="ship" value="${esc(ship)}"></label>
        <label class="sim-field"><span>${esc(t('lv.v3.sim.fee'))}</span><input type="number" min="0" max="99" step="0.1" data-sim="feePct" value="${esc(feePctPay)}"></label>
        <label class="sim-field"><span>${esc(t('lv.v3.sim.ret'))}</span><input type="number" min="0" max="99" step="1" data-sim="retPct" value="${esc(retPct)}"></label>
      </div>
      <label class="sim-check"><input type="checkbox" data-sim-check="itFee" ${itFee ? 'checked' : ''}><span>${esc(t('lv.v3.sim.itfee'))}</span></label>
    </details>
    <div class="vis-econ num">
      <div class="vis-kpi"><span>${esc(t('lv.v3.cpa'))}${simplePop('lv.v3.cpa', 'help.sim.cpa.title', 'help.sim.cpa.body')}</span><strong${withIds ? ' id="sim-cpa"' : ''} data-sim-out="cpa">${num(cpa)}</strong><small${withIds ? ' id="sim-roas"' : ''} data-sim-out="roas">${esc(t('lv.v3.sim.roas', { roas }))}</small></div>
      <div class="vis-kpi"><span>${esc(t('lv.v3.stop'))}${simplePop('lv.v3.stop', 'help.sim.stop.title', 'help.sim.stop.body')}</span><strong${withIds ? ' id="sim-stop"' : ''} data-sim-out="stop">${num(lowCut)} - ${num(highCut)}</strong><small>${esc(t('lv.v3.stop.sub'))}</small></div>
      <div class="vis-kpi"><span>${esc(t('lv.v3.budget'))}${simplePop('lv.v3.budget', 'help.sim.budget.title', 'help.sim.budget.body', null, true)}</span><strong${withIds ? ' id="sim-budget"' : ''} data-sim-out="budget">${num(round1)}</strong><small>${esc(t('lv.v3.budget.sub'))}</small></div>
    </div>
    <div class="precheck-box">
      <div class="precheck-head"><span>${esc(t('pre.cpc.title'))}</span>${cpcHelp}</div>
      <div class="cpc-grid"${withIds ? ' id="sim-cpc-rows"' : ''} data-sim-out="cpc-rows">${precheckCpcRowsHtml(cpcs, isEur)}</div>
      <p class="precheck-bench">${esc(t('pre.cpc.bench'))}</p>
      <p class="precheck-risk"${withIds ? ' id="sim-risk-line"' : ''} data-sim-out="risk-line">${esc(t('pre.risk.line', { spend: simMoney(round1, isEur), billed: simMoney(billed, isEur), onein: oneIn != null ? num(oneIn) : '—' }))}</p>
    </div>
    <div class="jury-box">
      <p class="jury-title">${esc(t('pre.jury.title'))}</p>
      <div class="jury-grid">${[1, 2, 3, 4].map((n) => `<div class="jury-card">${esc(t(`pre.jury.${n}`))}</div>`).join('')}</div>
    </div>
  </div>`;
}
function levelRows(locked) {
  return LEVELS.map((level, index) => {
    const chosen = S.level === level, open = chosen && S.levelOpen;
    const vKey = level === 'data' ? 'v1' : level === 'analysis' ? 'v2' : 'v3';
    return `<div class="lvl${open ? ' open' : ''}${chosen ? ' chosen' : ''}">
      <button class="lvl-head" data-action="lv-toggle" data-value="${level}" aria-expanded="${open}" aria-current="${chosen}" aria-controls="lv-${level}">
        <span class="lvl-n">${index + 1}</span>
        <span class="lvl-t"><strong>${esc(t(`lv.${level}.title`))}</strong><span>${esc(t(`lv.${level}.sub`))}</span></span>
        <span class="lvl-tag">${esc(t(`lv.${level}.tag`))}</span>
        <span class="lvl-arrow" aria-hidden="true"></span>
      </button>
      <div class="lvl-body" id="lv-${level}" ${open ? '' : 'hidden'}>
        <div class="lvl-grid">
          <ol>${[1, 2, 3, 4].map((n) => `<li>${esc(t(`lv.${level}.${n}`))}</li>`).join('')}</ol>
          ${levelVisual(level)}
        </div>
        <details class="lvl-details">
          <summary>${esc(t(`lv.${vKey}.more`))}</summary>
          <p>${esc(t(`lv.${vKey}.more.text`))}</p>
        </details>
        <div class="lvl-foot"><p>${esc(t(`lv.${level}.note`))}</p></div>
      </div>
    </div>`;
  }).join('');
}

/* ---------- connection to Claude Code ---------- */
const INSTALL_URL = 'https://claude.com/product/claude-code';
function linkStates() {
  const { quick, mcp } = S.link;
  const claude = !quick ? 'checking' : quick.claude ? 'ok' : 'todo';
  let server = 'checking';
  if (quick && !quick.claude) server = 'todo';
  else if (quick) server = { connected: 'ok', missing: 'todo', unknown: 'unknown', no_claude: 'todo' }[mcp] || 'checking';
  const skills = !quick ? 'checking' : quick.skills.installed ? 'ok' : 'todo';
  return { claude, server, skills, all: claude === 'ok' && server === 'ok' && skills === 'ok' };
}
function exampleSentence() {
  return t('link.example', { keyword: S.query.trim() || t('link.example.keyword'), country: region(S.country) });
}
function linkMessages(L, states) {
  let html = '';
  if (L.error) {
    const code = L.error.error;
    const key = `link.err.${code}`;
    html += `<p class="way-msg warn">${esc(T[S.lang][key] || T.en[key] ? t(key) : t('link.err.other'))}</p>`;
    if (code === 'claude_missing') html += `<p class="way-msg"><a href="${INSTALL_URL}" target="_blank" rel="noopener noreferrer">${esc(t('link.install'))}</a></p>`;
    if (code === 'command_failed' && L.error.detail) html += `<p class="way-detail"><span>${esc(t('link.detail'))}</span> ${esc(L.error.detail)}</p>`;
  } else if (!S.link.quick || S.link.quick.claude === false) {
    if (S.link.quick) html += `<p class="way-msg warn">${esc(t('link.err.claude_missing'))}</p><p class="way-msg"><a href="${INSTALL_URL}" target="_blank" rel="noopener noreferrer">${esc(t('link.install'))}</a></p>`;
  }
  if (L.result && L.result.ok) {
    const copied = L.result.skills.copied;
    html += `<p class="way-msg">${esc(t(L.result.server === 'added' ? 'link.done.added' : 'link.done.already'))}${copied ? ` ${esc(count(copied, 'link.done.skills'))}` : ''}</p>`;
    if (L.result.skills.kept.length) html += `<p class="way-msg warn">${esc(t('link.kept', { n: num(L.result.skills.kept.length) }))} <button class="linklike" data-action="link-overwrite-open">${esc(t('link.kept.btn'))}</button></p>`;
  }
  return html;
}
function renderWay() {
  const el = $('#way');
  if (!el) return;
  const L = S.link, states = linkStates();
  const mark = (name, state) => `<li class="${state}"><span class="mark" aria-hidden="true"></span><span>${esc(t(`link.${name}`))}</span>
      <span class="state">${esc(t(`link.state.${{ ok: 'ok', todo: 'todo', checking: 'checking', unknown: 'unknown' }[state]}`))}</span></li>`;
  const busy = L.running || !L.quick || !L.quick.claude || states.all;
  const connectLabel = L.running ? 'link.btn.running' : states.all ? 'link.btn.done' : 'link.btn';
  const showTest = states.all || (L.result && L.result.ok);
  const testNote = L.test ? `<p class="way-msg" role="status">${esc(t(L.test === 'running' ? 'link.test.running' : `link.test.${L.test}`))}</p>` : '';
  const after = showTest ? `<div class="way-after"><p class="way-label">${esc(t('link.example.label'))}</p>
      <div class="cmdline"><p class="command">${esc(exampleSentence())}</p><button class="btn quiet small" data-action="link-copy">${esc(t('link.copy'))}</button></div>
      ${L.copy ? `<p class="way-msg${L.copy === 'failed' ? ' warn' : ''}" role="status">${esc(t(L.copy === 'ok' ? 'link.copied' : 'link.copy.failed'))}</p>` : ''}
      <p class="way-msg">${esc(t('link.restart'))}</p></div>` : '';
  el.innerHTML = `<h2 class="way-title">${esc(t('way.title'))}</h2><p class="way-lead">${esc(t('way.lead'))}</p>
    <div class="ways">
      <article class="way-card">
        <p class="way-badge">${esc(t('way.a.badge'))}</p>
        <h3>${esc(t('way.a.title'))}</h3><p>${esc(t('way.a.text'))}</p>
        <ul class="checks">${mark('claude', states.claude)}${mark('mcp', states.server)}${mark('skills', states.skills)}</ul>
        ${linkMessages(L, states)}
        <div class="way-act"><button class="btn" data-action="link-open" ${busy ? 'disabled' : ''}>${esc(t(connectLabel))}</button>
          ${showTest ? `<button class="btn quiet" data-action="link-test" ${L.test === 'running' ? 'disabled' : ''}>${esc(t('link.test'))}</button>` : ''}</div>
        ${testNote}${after}
      </article>
      <article class="way-card">
        <p class="way-badge"></p>
        <h3>${esc(t('way.b.title'))}</h3><p>${esc(t('way.b.text'))}</p>
        <div class="way-act"><button class="btn quiet" data-action="way-run" ${!L.quick || !L.quick.claude ? 'disabled' : ''}>${esc(t('way.b.btn'))}</button></div>
        ${S.wayHint ? `<p class="way-msg" role="status">${esc(t('way.b.hint'))}</p>` : ''}
      </article>
      <article class="way-card">
        <p class="way-badge"></p>
        <h3>${esc(t('way.c.title'))}</h3><p>${esc(t('way.c.text'))}</p>
        <div class="way-act"><button class="btn quiet" data-action="way-copy">${esc(t('way.c.btn'))}</button></div>
        ${L.hint ? `<p class="way-msg" role="status">${esc(t('way.c.hint'))}</p>` : ''}
      </article>
    </div>
    <details class="lvl-details multi-cli">
      <summary>${esc(t('way.multi.title'))}</summary>
      <div class="multi-grid">
        <div class="multi-box"><strong>${esc(t('way.multi.ag.t'))}</strong><span>${esc(t('way.multi.ag.d'))}</span><code>${esc((L.quick && L.quick.antigravity_entry) || '{"ad-library-insights": {"command": "python", "args": ["-m", "ad_library_insights"]}}')}</code></div>
        <div class="multi-box"><strong>${esc(t('way.multi.cx.t'))}</strong><span>${esc(t('way.multi.cx.d'))}</span><code>${esc((L.quick && L.quick.codex_command) || 'codex mcp add ad-library-insights -- python -m ad_library_insights')}</code></div>
      </div>
    </details>
    <p class="way-how"><button class="linklike" data-action="how-open">${esc(t('way.how'))}</button></p>`;
}
let linkSeq = 0;
async function loadLink(connectedNow = false) {
  const L = S.link, seq = ++linkSeq;
  if (!connectedNow) L.mcp = 'checking';
  try { L.quick = await api('/api/link/status'); } catch { L.quick = { claude: false, skills: { installed: false, modified: [] }, command: '', skills_folder: '~/.claude/skills' }; }
  if (seq !== linkSeq) return;
  if (connectedNow && L.quick.claude) L.mcp = 'connected';
  renderTop();
  renderWay();
  if (L.quick.claude) {
    try {
      const { state } = await api('/api/link/mcp');
      if (seq === linkSeq) L.mcp = connectedNow && state === 'unknown' ? 'connected' : state;
    } catch { if (seq === linkSeq && !connectedNow) L.mcp = 'unknown'; }
  } else if (seq === linkSeq) L.mcp = 'no_claude';
  if (seq === linkSeq) { renderTop(); renderWay(); }
}
function newToken() {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}
async function runConnect(overwrite) {
  const L = S.link;
  L.running = true; L.error = null; L.result = null; L.test = null; renderWay();
  const token = newToken();
  try {
    L.result = await api('/api/link/connect', { method: 'POST', headers: { 'X-Link-Token': token }, body: { token, overwrite_skills: overwrite } });
  } catch (error) {
    L.error = { error: (error.data && error.data.error) || 'other', detail: error.data && error.data.detail };
  }
  L.running = false;
  await loadLink(Boolean(L.result && L.result.ok));
}
async function testLink() {
  const L = S.link;
  L.test = 'running'; renderWay();
  try {
    const { state } = await api('/api/link/mcp');
    L.mcp = state;
    L.test = state === 'connected' ? 'ok' : state === 'unknown' ? 'unknown' : 'no';
  } catch { L.test = 'unknown'; }
  renderWay();
}
function linkDialog(overlay) {
  const q = S.link.quick || {};
  if (overlay.overwrite) {
    const kept = S.link.result && S.link.result.skills ? S.link.result.skills.kept : [];
    const files = kept.length ? kept : ((q.skills && q.skills.modified) || []);
    return `<div class="dialog" role="dialog" aria-modal="true"><h2>${esc(t('link.overwrite.title'))}</h2><p class="lead">${esc(t('link.overwrite.lead'))}</p>
      <ul class="files">${files.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>
      <div class="foot"><button class="btn quiet" data-action="close">${esc(t('link.cancel'))}</button><button class="btn" data-action="link-go">${esc(t('link.overwrite.go'))}</button></div></div>`;
  }
  return `<div class="dialog wide" role="dialog" aria-modal="true"><h2>${esc(t('link.confirm.title'))}</h2><p class="lead">${esc(t('link.confirm.lead'))}</p>
    <div class="cmdline"><p class="command">${esc(q.command || '')}</p></div>
    <p class="smallnote">${esc(t('link.confirm.skills', { folder: q.skills_folder || '' }))}</p>
    <div class="foot"><button class="btn quiet" data-action="close">${esc(t('link.cancel'))}</button><button class="btn" data-action="link-go">${esc(t('link.confirm.go'))}</button></div></div>`;
}
function howDialog(overlay) {
  const n = overlay.step;
  const shot = n === 1 ? `<img src="/docs/images/levels.png" alt="">`
    : n === 2 ? `<img src="/docs/images/brief-dialog.png" alt="">`
    : `<div class="tut-shot-pair"><img src="/docs/images/results-table.png" alt=""><img src="/docs/images/ad-panel.png" alt=""></div>`;
  return `<div class="dialog wide" role="dialog" aria-modal="true" aria-label="${esc(t('how.title'))}"><p class="how-step">${esc(t('how.step', { n }))}</p>
    <h2 class="how-title">${esc(t(`how.${n}.title`))}</h2><p class="lead">${esc(t(`how.${n}.text`))}</p>
    <figure class="tut-shot">${shot}<figcaption>${esc(t(`how.${n}.cap`))}</figcaption></figure>
    <div class="foot"><button class="btn quiet" data-action="how-prev" ${n === 1 ? 'disabled' : ''}>${esc(t('how.prev'))}</button>
      ${n === 3 ? `<button class="btn" data-action="close">${esc(t('button.close'))}</button>` : `<button class="btn" data-action="how-next">${esc(t('how.next'))}</button>`}</div></div>`;
}
function updateProgress() {
  const text = $('#ptext');
  if (!text) return;
  const bar = $('#pbar');
  let label = t('pages.searching'), left = '', share = null, activeIdx = 0;
  if (S.job) {
    const { phase, detail = {} } = S.job;
    if (phase === 'details') {
      label = t('phase.details', detail);
      share = detail.total ? detail.done / detail.total : 0;
      if (detail.eta_seconds) left = t('phase.left', { time: dur(detail.eta_seconds) });
      activeIdx = 2;
    } else if (phase === 'waiting') {
      label = t('phase.waiting', detail);
      activeIdx = 1;
    } else if (phase === 'media') {
      label = t('phase.media');
      share = 0.92;
      activeIdx = 3;
    } else if (phase === 'list' && (S.job.params && S.job.params.mode !== 'keyword')) {
      label = t('phase.list.company');
      activeIdx = 1;
    } else {
      label = hasT(`phase.${phase}`) ? t(`phase.${phase}`) : t('phase.queued');
      activeIdx = phase === 'list' ? 1 : 0;
    }
    if (detail.side) label = t('cmp.side', { n: detail.side }) + label;
  }
  text.textContent = label;
  if ($('#pleft')) $('#pleft').textContent = left;
  if (bar && bar.firstElementChild) {
    bar.classList.toggle('open', share === null);
    bar.firstElementChild.style.width = share === null ? '' : `${Math.max(3, Math.round(share * 100))}%`;
  }
  document.querySelectorAll('.step-item').forEach((node, idx) => {
    node.classList.toggle('done', idx < activeIdx);
    node.classList.toggle('active', idx === activeIdx);
  });
}

/* ---------- results ---------- */
function pagesSheet() {
  const rows = S.pages.pages.map((page) => `<tr>
    <td><div class="who">${avatar(page.logo, page.name)}<div><div>${esc(page.name)}${page.verified ? ` <span class="dim">· ${esc(t('pages.verified'))}</span>` : ''}</div>
      ${page.instagram ? `<small class="dim">@${esc(page.instagram)}</small>` : ''}</div></div></td>
    <td>${esc(page.category || '—')}</td><td class="r">${num(page.followers)}</td>
    <td class="r"><button class="btn small${page.page_id === S.pages.suggested_page_id ? '' : ' quiet'}" data-action="choose-page" data-value="${esc(page.page_id)}">${esc(t('pages.choose'))}</button></td></tr>`).join('');
  return `<div class="sheet"><section><h2 style="margin-bottom:18px">${esc(t('pages.title'))}</h2><div class="table-scroll"><table>
    <thead><tr><th>${esc(t('pages.page'))}</th><th>${esc(t('pages.category'))}</th><th class="r">${esc(t('pages.followers'))}</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></div></section></div>`;
}
function headSection(r) {
  const company = r.mode === 'company';
  const page = r.page || {};
  const total = (r.signals && r.signals.active_ads) ?? (r.ads || []).length;
  const loaded = t('result.loaded', { loaded: num(r.ads_parsed), total: num(total),
    time: `${t(r.from_cache ? 'result.cache' : 'result.fresh')}${r.fetched_at && clock(r.fetched_at) ? `, ${clock(r.fetched_at)}` : ''}` });
  const title = company ? esc(page.name || r.query) : esc(t('result.keyword', { query: r.query, country: region(r.country) }));
  const facts = { category: page.category, followers: num(page.followers), country: region(r.country) };
  const sub = company ? `${esc(t(page.category ? 'result.sub.company' : 'result.sub.company.nocat', facts))}<br>${esc(loaded)}` : esc(loaded);
  return `<section class="rhead">${company ? avatar(page.logo, page.name, true) : ''}
    <div class="grow"><h1>${title}</h1><p>${sub}</p></div>
    <div class="rlinks"><a href="${esc(r.url)}" target="_blank" rel="noopener">${esc(t('link.meta'))}</a>
    <button class="linklike" data-action="kpi-open">${esc(t('kpi.btn'))}</button>
    <button class="linklike" data-action="guide">${esc(t('link.guide'))}</button></div></section>`;
}
function changesSection(r) {
  const c = r.changes;
  if (!c) return '';
  if (!c.available) return `<section class="changes"><p class="muted">${esc(t('changes.first'))}</p></section>`;
  const date = c.previous_taken_at ? `${day(c.previous_taken_at)}, ${clock(c.previous_taken_at)}` : '—';
  const { new: fresh = 0, stopped = 0, changed = 0 } = c.counts || {};
  const text = fresh + stopped + changed ? t('changes.since', { date, new: fresh, stopped, changed }) : t('changes.same', { date });
  return `<section class="changes"><p>${esc(text)}</p><button class="btn quiet small" data-action="news-open" data-value="${esc(c.key)}">${esc(t('news.view'))}</button></section>`;
}
function readySection(r) {
  const level = (r.request && r.request.level) || 'data';
  if (level === 'data' || S.tab === 'strategy') return '';
  if (IS_MCP_APP) {
    return `<section class="ready"><p>${esc(t(`brief.ready.${level}`))}</p>
      <button type="button" class="btn small" data-action="rtab" data-value="strategy">${esc(t('strat.ai.title'))} &rarr;</button></section>`;
  }
  return `<section class="ready"><p>${esc(t(`brief.ready.${level}`))}</p>
    <button type="button" class="btn small" data-action="rtab" data-value="strategy">${esc(t('strat.ai.title'))} &rarr;</button>
    <button type="button" class="btn quiet small" data-action="brief">${esc(t(`brief.make.${level}`))}</button></section>`;
}
/* When the ceiling of ads opened stopped the reading, say it with the numbers. */
function cappedSection(r) {
  const d = r.deep;
  let out = '';
  if (d && d.capped) {
    let text = t(d.concepts === 1 ? 'deep.capped.one' : 'deep.capped.other',
      { n: num(d.concepts), requested: num(d.requested), ceiling: num(d.ceiling) });
    if (d.left_out) text += ` ${count(d.left_out, 'deep.left')}`;
    out += `<section class="changes capped"><p>${esc(text)}</p></section>`;
  }
  const off = (r.signals && r.signals.off_query) || 0;
  if (r.mode === 'keyword' && ((r.ads || []).length <= 3 || (off > 0 && off * 2 >= (r.ads || []).length))) {
    out += `<section class="changes"><p class="muted">${esc(t('result.thin.keyword', { off: num(off), total: num((r.ads || []).length) }))}</p></section>`;
  }
  return out;
}
function metricsSection(r) {
  const s = r.signals || {};
  const reachObj = s.reach || {};
  const reach = reachObj.available ? reachObj.median_reach_per_day : null;
  const cells = [
    [num(s.active_ads), t('m.active'), t(r.mode === 'company' ? 'm.active.x' : 'm.active.x.keyword'), 'help.m.active.body', false],
    [pct(s.video_share), t('m.video'), t('m.video.x'), 'help.m.video.body', false],
    [num(s.new_per_week), t('m.weekly'), t('m.weekly.x'), 'help.m.weekly.body', false],
    [reach == null ? '—' : num(reach), t('m.reachday'), t(reach == null ? 'm.reachday.none' : 'm.reachday.x'), 'help.m.reachday.body', false],
    [num(s.started_last_30_days), t('m.new30'), `${t('m.new30.x')} ${t('m.new30.share', { share: pct(s.share_started_last_30_days) })}.`, 'help.m.new30.body', true],
  ];
  return `<section>
    <div style="margin-bottom:14px">
      <div class="sec-eyebrow">${esc(t('overview.kpis.eyebrow'))}</div>
      <h2 class="sec-title-line">${esc(t('overview.kpis.title'))}${simplePop('overview.kpis.title', 'help.kpis.title', 'help.kpis.body')}</h2>
    </div>
    <div class="metrics">${cells.map(([value, label, why, bodyKey, right]) => `<div class="metric">
      <div class="metric-head"><span class="metric-lbl">${esc(label)}</span>${helpPopover(label, '', `<p>${esc(t(bodyKey))}</p>`, right, label)}</div>
      <b>${esc(value)}</b><small>${esc(why)}</small>
    </div>`).join('')}</div>
  </section>`;
}
/* The first few places, then "e altri N": `all` is the full count when the list was cut. */
function placeNames(places, total, all, limit = 8) {
  if (!places.length) return esc(t('f.places.none'));
  const shown = places.slice(0, limit).map((place) => {
    const share = total && place.ads < total ? ` ${t('f.places.count', { n: place.ads, total })}` : '';
    return esc(placeLabel(place)) + (share ? `<span class="dim">${esc(share)}</span>` : '');
  });
  const every = Math.max(all ?? 0, places.length), rest = every - shown.length;
  if (rest <= 0) return shown.join(', ');
  return `<span class="dim">${esc(count(every, 'n.places'))}: </span>${shown.join(', ')}<span class="dim"> ${esc(count(rest, 'list.more'))}</span>`;
}
function ageNames(ranges, total) {
  if (!ranges.length) return '—';
  const [main] = ranges;
  const share = total && main.ads < total ? ` ${t('f.places.count', { n: main.ads, total })}` : '';
  const others = ranges.length > 1 ? `${share ? ',' : ''} ${count(ranges.length - 1, 'f.age.more')}` : '';
  return esc(ageRange(main.age_min, main.age_max)) + (share || others ? `<span class="dim">${esc(share + others)}</span>` : '');
}
const shareRows = (rows, label) => `<ul class="rows">${(rows || []).slice(0, 5).map((row) => `<li><span>${esc(label(row))}</span><span>${pct(row.share)}</span></li>`).join('') || `<li><span class="dim">—</span></li>`}</ul>`;
function factsSection(r) {
  const s = r.signals || {}, audience = s.audience, reach = s.reach || {};
  const places = audience && (audience.locations_included || []).length
    ? `<dl><dt>${esc(t('f.places.in'))}</dt><dd>${placeNames(audience.locations_included || [], audience.ads_with_audience, audience.locations_included_count)}</dd>
       <dt>${esc(t('f.places.out'))}</dt><dd>${placeNames(audience.locations_excluded || [], audience.ads_with_audience, audience.locations_excluded_count, 3)}</dd></dl>
       <p class="note">${esc(t('f.places.note'))}</p>`
    : `<p class="note" style="margin-top:0">${esc(t('f.places.unread'))} ${esc(t('f.places.note'))}</p>`;
  const who = audience ? `<dl>
      <dt>${esc(t('f.audience.age'))}</dt><dd>${ageNames(audience.age_ranges || [], audience.ads_with_audience)}</dd>
      <dt>${esc(t('f.audience.gender'))}</dt><dd>${Object.keys(audience.genders || {}).map((g) => esc(t(`gender.${g}`))).join(', ') || '—'}</dd>
      <dt>${esc(t('f.audience.breadth'))}</dt><dd>${Object.keys(audience.breadth || {}).map((b) => esc(t(`breadth.${b}`))).join(', ') || '—'}</dd></dl>`
    : '<p class="dim">—</p>';
  const coverage = !reach.available ? `<p class="note" style="margin-top:0">${esc(t('f.reach.none'))}</p>`
    : !reach.ads_with_market_reach ? `<p class="note" style="margin-top:0">${esc(t('f.reach.elsewhere', { country: region(r.country) }))}</p>`
    : `<dl>
      <dt>${esc(t('f.reach.perday.median'))}</dt><dd class="num">${num(reach.median_reach_per_day)}</dd>
      <dt>${esc(t('f.reach.perday.best'))}</dt><dd class="num">${num(reach.highest_reach_per_day)}</dd>
      <dt>${esc(t('f.reach.total.median'))}</dt><dd class="num">${num(reach.median_reach_total)}</dd>
      <dt>${esc(t('f.reach.total.best'))}</dt><dd class="num">${num(reach.highest_reach_total)}</dd></dl>
      <p class="note">${esc(t('f.reach.note', { n: reach.ads_with_market_reach, country: region(r.country) }))}</p>`;
  const reused = ((s.copy_patterns && s.copy_patterns.reused_texts) || []).slice(0, 4).map((row) => `<li><span>${esc(row.opening)}</span><span>${esc(oneOrMore('f.reused.n', row.creatives))}</span></li>`).join('');
  return `<section class="facts">
    <div style="margin-bottom:16px">
      <div class="sec-eyebrow">${esc(t('overview.facts.eyebrow'))}</div>
      <h2 class="sec-title-line">${esc(t('overview.facts.title'))}${simplePop('overview.facts.title', 'help.facts.title', 'help.facts.body')}</h2>
    </div>
    <div class="facts-grid">
      <div class="fact wide"><h2>${esc(t('f.places'))}${simplePop('f.places', 'f.places', 'help.f.places.body')}</h2>${places}</div>
      <div class="fact"><h2>${esc(t('f.audience'))}${simplePop('f.audience', 'f.audience', 'help.f.audience.body', null, true)}</h2>${who}</div>
      <div class="fact"><h2>${esc(t('f.reach'))}${simplePop('f.reach', 'f.reach', 'help.f.reach.body')}</h2>${coverage}</div>
      <div class="fact"><h2>${esc(t('f.langs'))}${simplePop('f.langs', 'f.langs', 'help.f.langs.body')}</h2>${shareRows(s.languages, (row) => named('language', row.language))}</div>
      <div class="fact"><h2>${esc(t('f.platforms'))}${simplePop('f.platforms', 'f.platforms', 'help.f.platforms.body', null, true)}</h2>${shareRows(s.platforms, (row) => PLATFORMS[row.platform] || row.platform)}</div>
      <div class="fact"><h2>${esc(t('f.buttons'))}${simplePop('f.buttons', 'f.buttons', 'help.f.buttons.body')}</h2>${shareRows(s.buttons, (row) => row.button)}</div>
      <div class="fact"><h2>${esc(t('f.dest'))}${simplePop('f.dest', 'f.dest', 'help.f.dest.body')}</h2>${shareRows(s.destinations, (row) => row.domain)}</div>
      <div class="fact"><h2>${esc(t('f.reused'))}${simplePop('f.reused', 'f.reused', 'help.f.reused.body', null, true)}</h2><ul class="rows">${reused || '<li><span class="dim">—</span></li>'}</ul></div>
    </div>
  </section>`;
}
/* "k of m ads read" for a concept whose reach was summed over some of its ads. */
function cardsNote(ad) {
  if (ad.reach_total == null || (ad.cards || 1) < 2) return '';
  return (ad.reach_cards_read || 1) > 1 ? t('d.reach.cards', { k: ad.reach_cards_read, n: ad.cards }) : t('d.reach.cards.one', { n: ad.cards });
}
function reachCells(ad) {
  if (ad.reach_total != null) {
    const tip = cardsNote(ad) ? ` title="${esc(cardsNote(ad))}"` : '';
    return `<td class="r"${tip}>${num(ad.reach_total)}</td><td class="r"${tip}>${num(ad.reach_per_day)}</td>`;
  }
  if (!ad.reach) return '<td class="r dim">—</td><td class="r dim">—</td>';
  if (!ad.reach.available) return `<td class="r dim" colspan="2">${esc(t('t.nopub'))}</td>`;
  if (ad.reach_total == null) return `<td class="r dim" colspan="2">${esc(t('t.elsewhere'))}</td>`;
  return `<td class="r">${num(ad.reach_total)}</td><td class="r">${num(ad.reach_per_day)}</td>`;
}
const SORTS = {
  score: (a, b) => b.score - a.score,
  perday: (a, b) => (b.reach_per_day ?? -1) - (a.reach_per_day ?? -1) || b.score - a.score,
  days: (a, b) => (b.days_running ?? -1) - (a.days_running ?? -1) || b.score - a.score,
};
const kindTag = (ad) => (ad.kind && ad.kind !== 'standard' ? t(`kind.${ad.kind}`) : '');
function verdictCell(ad) {
  return `<span class="v-${ad.verdict}">${esc(t(`verdict.${ad.verdict}`))}</span><span class="rel">${esc(t(`reliability.${ad.reliability}`))}</span>`;
}
function tableLegend() {
  return `<details class="table-legend">
    <summary>${esc(t('leg.title'))}</summary>
    <div class="leg-grid">
      <div class="leg-col"><h4>${esc(t('leg.g1'))}</h4><ul class="leg-list">
        <li><strong class="v-scaling">${esc(t('verdict.scaling'))}:</strong><span>${esc(t('leg.v.scaling'))}</span></li>
        <li><strong class="v-holding">${esc(t('verdict.holding'))}:</strong><span>${esc(t('leg.v.holding'))}</span></li>
        <li><strong class="v-testing">${esc(t('verdict.testing'))}:</strong><span>${esc(t('leg.v.testing'))}</span></li>
        <li><strong class="v-review">${esc(t('verdict.review'))}:</strong><span>${esc(t('leg.v.review'))}</span></li>
        <li><strong class="v-average">${esc(t('verdict.average'))}:</strong><span>${esc(t('leg.v.other'))}</span></li>
      </ul></div>
      <div class="leg-col"><h4>${esc(t('leg.g2'))}</h4><ul class="leg-list">
        <li><strong>${esc(t('reliability.high'))}:</strong><span>${esc(t('leg.r.high'))}</span></li>
        <li><strong>${esc(t('reliability.medium'))}:</strong><span>${esc(t('leg.r.medium'))}</span></li>
        <li><strong>${esc(t('reliability.low'))}:</strong><span>${esc(t('leg.r.low'))}</span></li>
      </ul></div>
      <div class="leg-col"><h4>${esc(t('leg.g3'))}</h4><ul class="leg-list">
        <li><strong>${esc(t('t.score'))}:</strong><span>${esc(t('leg.c.score'))}</span></li>
        <li><strong>${esc(t('t.creatives'))}:</strong><span>${esc(t('leg.c.creatives'))}</span></li>
        <li><strong>${esc(t('t.perday'))}:</strong><span>${esc(t('leg.c.perday'))}</span></li>
      </ul></div>
    </div>
  </details>`;
}
function filteredAds(r) {
  const q = (S.tableQuery || '').trim().toLowerCase();
  return [...(r.ads || [])].filter((ad) => {
    if (S.filter === 'scaling' && ad.verdict !== 'scaling') return false;
    if (S.filter === 'video' && ad.media_type !== 'video') return false;
    if (S.filter === 'high' && ad.reliability !== 'high') return false;
    if (q) {
      const hay = `${ad.body || ''} ${ad.headline || ''} ${ad.advertiser || ''} ${ad.landing_domain || ''}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  }).sort(SORTS[S.sort] || SORTS.score);
}
function tableRowsHtml(r) {
  const company = r.mode === 'company';
  const ads = filteredAds(r);
  return ads.map((ad, index) => {
    const thumb = ad.thumbnail ? mediaImg(ad.thumbnail, 'thumb', '', true) : '<span class="thumb"></span>';
    const sub = company
      ? esc([t(`format.${ad.media_type || 'unknown'}`), ad.cta, kindTag(ad)].filter(Boolean).join(' · '))
      : `${ad.advertiser ? `<button type="button" class="adv-jump" data-action="jump-company" data-value="${esc(ad.advertiser)}">${esc(ad.advertiser)}</button>` : ''}${kindTag(ad) ? ` · ${esc(kindTag(ad))}` : ''}`;
    return `<tr class="pick" data-action="open-ad" data-value="${esc(ad.library_id)}">
    <td class="rank">${index + 1}</td>
    <td><div class="adcell">${thumb}<div class="adtext"><div>${esc(firstLine(ad) || t('t.notext'))}</div><small>${sub}</small></div></div></td>
    <td class="tier">${verdictCell(ad)}</td>
    <td class="r">${Math.round(ad.score)}</td><td class="r">${num(ad.days_running)}</td><td class="r">${num(ad.creatives)}</td>
    ${company ? '' : `<td class="fmt">${esc(t(`format.${ad.media_type || 'unknown'}`))}</td>`}${reachCells(ad)}</tr>`;
  }).join('');
}
function cardsGridHtml(r) {
  const company = r.mode === 'company';
  return filteredAds(r).map((ad) => {
    const media = ad.thumbnail ? mediaImg(ad.thumbnail, '', '', true) : `<span class="dim">${esc(t(`format.${ad.media_type || 'unknown'}`))}</span>`;
    const reachTxt = ad.reach_per_day != null ? t('n.perday.short', { n: num(ad.reach_per_day) }) : (ad.impression_rank ? `#${num(ad.impression_rank)}` : '');
    const sub = [days(ad.days_running), oneOrMore('f.reused.n', ad.creatives || 1), reachTxt].filter(Boolean).join(' · ');
    return `<button type="button" class="ad-card" data-action="open-ad" data-value="${esc(ad.library_id)}">
      <div class="ad-card-media">${media}</div>
      <div class="ad-card-body">
        <div class="ad-card-head"><span class="v-${ad.verdict}">${esc(t(`verdict.${ad.verdict}`))}</span><span class="ad-card-score">${Math.round(ad.score)}/100</span></div>
        <div class="ad-card-copy">${esc(firstLine(ad) || t('t.notext'))}</div>
        <div class="ad-card-meta">${company ? esc(sub) : `${esc(ad.advertiser || '')} · ${esc(sub)}`}</div>
      </div>
    </button>`;
  }).join('');
}
function helpPopover(topic, titleKey, bodyHtml, alignRight = false, rawTitle = null) {
  const heading = rawTitle || (titleKey ? t(titleKey) : topic);
  return `<span class="help-wrap"><button type="button" class="help-btn" data-action="help-toggle" aria-label="${esc(t('help.aria', { topic }))}" aria-expanded="false">?</button><div class="help-pop${alignRight ? ' right' : ''}" role="tooltip"><h4>${esc(heading)}</h4>${bodyHtml}</div></span>`;
}
function simplePop(topicKey, titleKey, bodyKey, howKey = null, alignRight = false) {
  const topic = hasT(topicKey) ? t(topicKey) : topicKey;
  const howHtml = howKey ? `<p class="hp-how">${esc(t(howKey))}</p>` : '';
  return helpPopover(topic, titleKey, `<p>${esc(t(bodyKey))}</p>${howHtml}`, alignRight);
}
function adColPop() {
  return simplePop('t.ad', 'help.col.ad.title', 'help.col.ad.body');
}
function tierScalePop() {
  const rows = [
    ['verdict.scaling', 'leg.v.scaling'],
    ['verdict.holding', 'leg.v.holding'],
    ['verdict.testing', 'leg.v.testing'],
    ['verdict.review', 'leg.v.review'],
    ['verdict.average', 'leg.v.other'],
  ].map(([k, desc]) => `<li><strong>${esc(t(k))}:</strong>${esc(t(desc))}</li>`).join('');
  return helpPopover(t('t.tier'), 'help.tier.title', `<ul class="help-scale">${rows}</ul>`);
}
function scoreScalePop(alignRight = true) {
  const bands = [1, 2, 3, 4].map((n) => `<li>${esc(t(`help.score.b${n}`))}</li>`).join('');
  return helpPopover(t('t.score'), 'help.score.title', `<p>${esc(t('help.score.formula'))}</p><ul class="help-scale">${bands}</ul>`, alignRight);
}
function daysColPop(alignRight = true) {
  return simplePop('t.days', 'help.col.days.title', 'help.col.days.body', null, alignRight);
}
function creativesColPop(alignRight = true) {
  return simplePop('t.creatives', 'help.col.creatives.title', 'help.col.creatives.body', null, alignRight);
}
function reachedColPop(countryName, alignRight = true) {
  const label = t('t.reached', { country: countryName });
  return helpPopover(label, 'help.col.reached.title', `<p>${esc(t('help.col.reached.body'))}</p>`, alignRight);
}
function perdayPop(alignRight = true) {
  return helpPopover(t('t.perday'), 'help.perday.title', `<p>${esc(t('help.perday.body'))}</p>`, alignRight);
}
function durataPop() {
  return helpPopover(t('dur.title'), 'help.durata.title', `<p>${esc(t('help.durata.body'))}</p>`);
}
function weibullPop() {
  const rows = [1, 2, 3].map((n) => `<li>${esc(t(`help.weibull.r${n}`))}</li>`).join('');
  return helpPopover(t('dur.kpi.weibull'), 'help.weibull.title', `<ul class="help-scale">${rows}</ul>`);
}
function lindyPop(alignRight = true) {
  return helpPopover(t('dur.kpi.lindy'), 'help.lindy.title', `<p>${esc(t('help.lindy.body'))}</p>`, alignRight);
}
function ritmoPop() {
  return helpPopover(t('rit.title'), 'help.ritmo.title', `<p>${esc(t('help.ritmo.body'))}</p>`);
}
function staLtaPop() {
  return helpPopover(t('rit.kpi.stalta'), 'help.stalta.title', `<p>${esc(t('help.stalta.body'))}</p>`);
}
function cusumPop() {
  return helpPopover(t('rit.kpi.cusum'), 'help.cusum.title', `<p>${esc(t('help.cusum.body'))}</p>`);
}
function littlePop(alignRight = true) {
  return helpPopover(t('rit.kpi.little'), 'help.little.title', `<p>${esc(t('help.little.body'))}</p>`, alignRight);
}
function strutturaPop() {
  return helpPopover(t('str.title'), 'help.struttura.title', `<p>${esc(t('help.struttura.body'))}</p>`);
}
function concPop() {
  return helpPopover(t('str.kpi.conc'), 'help.conc.title', `<p>${esc(t('help.conc.body'))}</p>`);
}
function ncdPop() {
  return helpPopover(t('str.kpi.copy'), 'help.ncd.title', `<p>${esc(t('help.ncd.body'))}</p>`);
}
function shannonPop(alignRight = true) {
  return helpPopover(t('str.kpi.shannon'), 'help.shannon.title', `<p>${esc(t('help.shannon.body'))}</p>`, alignRight);
}
function anomaliePop() {
  return helpPopover(t('anom.title'), 'help.anomalie.title', `<p>${esc(t('help.anomalie.body'))}</p>`);
}
function piankaPop() {
  return helpPopover(t('cmp.pianka.title'), 'help.pianka.title', `<p>${esc(t('help.pianka.body'))}</p>`);
}
function tldrSection(r) {
  const s = r.signals || {}, v = s.verdicts || {};
  const concepts = count(r.distinct_ads ?? (r.ads || []).length, 'n.concepts');
  let main = r.mode === 'company'
    ? t('tldr.company', { active: num(s.active_ads), concepts, video: pct(s.video_share), weekly: num(s.new_per_week) })
    : t('tldr.keyword', { loaded: num(r.ads_parsed), concepts, video: pct(s.video_share) });
  const reach = s.reach && s.reach.available ? s.reach.median_reach_per_day : null;
  main += reach != null
    ? t('tldr.reach', { reach: num(reach), country: region(r.country) })
    : t('tldr.noreach', { country: region(r.country) });
  let sub = t('tldr.verdicts', { scaling: num(v.scaling || 0), holding: num(v.holding || 0), review: num(v.review || 0) });
  if (r.durata && r.durata.available) {
    sub += r.durata.median_reached
      ? t('tldr.durata.median', { window: num(r.durata.window_days || 90), median: num(r.durata.median_days) })
      : t('tldr.durata.open', { window: num(r.durata.window_days || 90) });
  }
  if (r.mode === 'company' && r.ritmo && r.ritmo.available) {
    const m = r.ritmo;
    if (m.trigger_ai) {
      const parts = [];
      if (m.sta_lta && m.sta_lta.trigger_ai) {
        parts.push(m.sta_lta.ratio != null ? t('tldr.ritmo.spike_part', { ratio: num(m.sta_lta.ratio) }) : t('tldr.ritmo.burst_part'));
      }
      if (m.cusum && m.cusum.trigger_ai && m.cusum.primary) {
        const p = m.cusum.primary;
        const fmt = hasT(`format.${p.format}`) ? t(`format.${p.format}`) : p.format;
        parts.push(t('tldr.ritmo.drift_part', { fmt, from: Math.round(p.baseline_share * 100), to: Math.round(p.recent_share * 100) }));
      }
      sub += t('tldr.ritmo.alert', { detail: parts.join(' · ') });
    } else {
      const stKey = (m.sta_lta && m.sta_lta.measurable && m.sta_lta.state) ? m.sta_lta.state : 'steady';
      sub += t('tldr.ritmo.steady', { state: t(`rit.state.${stKey}`).toLowerCase() });
    }
  }
  if (r.struttura && r.struttura.copy_families && r.struttura.copy_families.measurable) {
    const cf = r.struttura.copy_families;
    sub += t('tldr.struttura.families', { k: num(cf.families_count), m: num(cf.evaluated) });
  }
  if (r.anomalie && r.anomalie.available && (r.anomalie.items || []).length) {
    const anomN = r.anomalie.items.length;
    sub += anomN === 1 ? t('tldr.anomalie.flagged.one') : t('tldr.anomalie.flagged', { n: num(anomN) });
  }

  let overviewExtras = '';
  if (S.tab === 'overview') {
    const st = (r.ritmo && r.ritmo.available && r.ritmo.sta_lta && r.ritmo.sta_lta.state) || 'steady';
    const stLbl = hasT(`rit.state.${st}`) ? t(`rit.state.${st}`) : st;
    const p1Val = t('tldr.p1.v', { scaling: num(v.scaling || 0), concepts });
    const p1Sub = reach != null
      ? t('tldr.p1.s', { reach: num(reach), country: region(r.country), active: num(s.active_ads) })
      : t('tldr.p1.empty', { country: region(r.country) });
    const p2Val = t('tldr.p2.v.ritmo', { state: stLbl, weekly: num(s.new_per_week) });
    const p2Sub = (r.durata && r.durata.available && r.durata.median_reached)
      ? t('tldr.p2.s.dur', { median: num(r.durata.median_days) })
      : t('tldr.p2.s.nodur', { video: pct(s.video_share), holding: num(v.holding || 0) });
    const cf = r.struttura && r.struttura.copy_families;
    const anomCount = (r.anomalie && r.anomalie.available && (r.anomalie.items || []).length) || 0;
    const anomStr = anomCount === 1 ? t('tldr.p3.anom.one') : t('tldr.p3.anom.many', { n: num(anomCount) });
    const p3Val = (cf && cf.measurable) ? t('tldr.p3.v', { fam: num(cf.families_count), anom: anomStr }) : t('tldr.p3.fallback', { concepts, video: pct(s.video_share) });
    const p3Sub = t('tldr.p3.s');

    overviewExtras = `<div class="tldr-pillars">
        <div class="tldr-pillar">
          <div class="tldr-pillar-k">${esc(t('tldr.p1.k'))}${simplePop('tldr.p1.k', 'help.p1.title', 'help.p1.body')}</div>
          <div class="tldr-pillar-v">${esc(p1Val)}</div>
          <div class="tldr-pillar-s">${esc(p1Sub)}</div>
        </div>
        <div class="tldr-pillar">
          <div class="tldr-pillar-k">${esc(t('tldr.p2.k'))}${simplePop('tldr.p2.k', 'help.p2.title', 'help.p2.body')}</div>
          <div class="tldr-pillar-v">${esc(p2Val)}</div>
          <div class="tldr-pillar-s">${esc(p2Sub)}</div>
        </div>
        <div class="tldr-pillar">
          <div class="tldr-pillar-k">${esc(t('tldr.p3.k'))}${simplePop('tldr.p3.k', 'help.p3.title', 'help.p3.body', null, true)}</div>
          <div class="tldr-pillar-v">${esc(p3Val)}</div>
          <div class="tldr-pillar-s">${esc(p3Sub)}</div>
        </div>
      </div>
      <div class="verdict-mini-legend">
        <strong>${esc(t('leg.mini.label'))}</strong>
        <span class="vleg-item"><span class="v-scaling">${esc(t('verdict.scaling'))}</span><span>${esc(t('leg.mini.scaling'))}</span></span>
        <span class="vleg-item"><span class="v-holding">${esc(t('verdict.holding'))}</span><span>${esc(t('leg.mini.holding'))}</span></span>
        <span class="vleg-item"><span class="v-testing">${esc(t('verdict.testing'))}</span><span>${esc(t('leg.mini.testing'))}</span></span>
        <span class="vleg-item"><span class="v-review">${esc(t('verdict.review'))}</span><span>${esc(t('leg.mini.review'))}</span></span>
        <button type="button" class="linklike" data-action="rtab" data-value="ads" style="margin-left:auto">${esc(t('leg.mini.more'))}</button>
      </div>`;
  }

  return `<section class="tldr" aria-label="${esc(t('tldr.label'))}">
    <div class="tldr-head">
      <div class="tldr-title-group">
        <div class="tldr-eyebrow-row"><span class="tldr-label">${esc(t('tldr.label'))}</span></div>
        <h2 class="tldr-hero-title">${esc(t(r.mode === 'company' ? 'tldr.hero.company' : 'tldr.hero.keyword'))}${simplePop('tldr.label', 'help.quadro.title', 'help.quadro.body', 'help.quadro.how')}</h2>
      </div>
      <div class="tldr-act"><button class="linklike" data-action="guide">${esc(t('tldr.help'))}</button></div>
    </div>
    <div class="tldr-lines"><strong>${esc(main)}</strong><span>${esc(sub)}</span></div>
    ${overviewExtras}
  </section>`;
}
function renderKmSvg(d) {
  const W = 640, H = 188, padL = 42, padR = 16, padT = 12, padB = 26;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const maxX = Math.max(Number(d.tau_days || d.max_observed_days || 1), 1);
  const px = (dayVal) => +(padL + (Math.min(dayVal, maxX) / maxX) * plotW).toFixed(1);
  const py = (surv) => +(padT + (1 - Math.max(0, Math.min(1, surv))) * plotH).toFixed(1);
  const steps = d.curve || [];

  const kmPts = [[px(0), py(1)]];
  const topPts = [[px(0), py(1)]];
  const botPts = [[px(0), py(1)]];
  let prevS = 1, prevHi = 1, prevLo = 1;
  for (const step of steps) {
    const x = px(step.day);
    kmPts.push([x, py(prevS)], [x, py(step.survival)]);
    topPts.push([x, py(prevHi)], [x, py(step.ci_high)]);
    botPts.push([x, py(prevLo)], [x, py(step.ci_low)]);
    prevS = step.survival;
    prevHi = step.ci_high;
    prevLo = step.ci_low;
  }
  const endX = px(maxX);
  kmPts.push([endX, py(prevS)]);
  topPts.push([endX, py(prevHi)]);
  botPts.push([endX, py(prevLo)]);

  const linePath = kmPts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x},${y}`).join(' ');
  const bandPts = topPts.concat(botPts.reverse()).map(([x, y]) => `${x},${y}`).join(' ');

  const yTicks = [1.0, 0.5, 0.0].map((val) => {
    const y = py(val);
    const dash = val === 0.5 ? ' stroke-dasharray="4 4"' : '';
    return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--line-soft)"${dash} stroke-width="1"/>
      <text x="${padL - 8}" y="${y + 4}" text-anchor="end" fill="var(--muted)" font-size="11">${Math.round(val * 100)}%</text>`;
  }).join('');

  const xCandidates = [0, 7, 14, 30, 60, 90, 120, 180].filter((v) => v <= maxX);
  if (xCandidates[xCandidates.length - 1] !== maxX) xCandidates.push(maxX);
  const xTicks = [];
  let lastTickX = -999;
  for (const val of xCandidates) {
    const x = px(val);
    if (x - lastTickX < 36 && val !== maxX) continue;
    lastTickX = x;
    const lbl = val === 0 ? '0' : t('dur.days.short', { n: val });
    xTicks.push(`<text x="${x}" y="${H - 6}" text-anchor="middle" fill="var(--muted)" font-size="11">${esc(lbl)}</text>`);
  }

  let medianMark = '';
  if (d.median_reached && d.median_days != null && d.median_days <= maxX) {
    const mx = px(d.median_days), my = py(0.5);
    medianMark = `<line x1="${mx}" y1="${my}" x2="${mx}" y2="${py(0)}" stroke="var(--warn)" stroke-dasharray="3 3" stroke-width="1.4"/>
      <circle cx="${mx}" cy="${my}" r="4" fill="var(--warn)" stroke="var(--surface)" stroke-width="1.5"/>`;
  }

  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t('dur.chart.title'))}">
    ${yTicks}${xTicks.join('')}
    <polygon points="${bandPts}" fill="var(--accent)" fill-opacity="0.14"/>
    <path d="${linePath}" fill="none" stroke="var(--accent)" stroke-width="2.2" stroke-linejoin="round"/>
    ${medianMark}
  </svg>`;
}
function durataUnavailableText(d) {
  if (d.reason === 'partial_list' && d.loaded_share == null) return t('dur.unavail.unverified');
  const share = d.loaded_share != null ? pct(d.loaded_share) : '—';
  if (d.reason === 'partial_list') return t('dur.unavail.partial_list', { share });
  if (d.reason === 'too_few_concepts') return t('dur.unavail.too_few_concepts', { found: num(d.concepts_in_window), window: num(d.window_days || 90) });
  if (d.reason === 'too_few_ended') return t('dur.unavail.too_few_ended', { ended: num(d.ended_in_window), found: num(d.concepts_in_window), window: num(d.window_days || 90) });
  return t('dur.unavail.other', { reason: d.reason || '—' });
}
function durFunnelHtml(d) {
  const raw = d.milestones || {};
  const entries = [7, 14, 30, 60, 90]
    .filter((age) => raw[String(age)] != null)
    .map((age) => ({ age, surv: Number(raw[String(age)]), isMedian: false }));
  if (d.median_reached && d.median_days != null) {
    const medAge = Math.max(1, Math.round(Number(d.median_days)));
    const match = entries.find((row) => row.age === medAge);
    if (match) match.isMedian = true;
    else entries.push({ age: medAge, surv: 0.5, isMedian: true });
  }
  if (!entries.length) return '';
  entries.sort((a, b) => a.age - b.age);

  const metaFor = (row) => {
    if (row.isMedian) return { phase: t('dur.funnel.pmed'), cls: 'warn', text: t('dur.funnel.mmed', { d: num(row.age) }), stage: t('dur.funnel.stage.med', { d: num(row.age) }) };
    if (row.age <= 7) return { phase: t('dur.funnel.p7'), cls: '', text: t('dur.funnel.m7'), stage: t('dur.funnel.stage.d', { d: num(row.age) }) };
    if (row.age <= 14) return { phase: t('dur.funnel.p14'), cls: '', text: t('dur.funnel.m14'), stage: t('dur.funnel.stage.d', { d: num(row.age) }) };
    if (row.age <= 30) return { phase: t('dur.funnel.p30'), cls: 'accent', text: t('dur.funnel.m30'), stage: t('dur.funnel.stage.d', { d: num(row.age) }) };
    if (row.age <= 60) return { phase: t('dur.funnel.p60'), cls: 'accent', text: t('dur.funnel.m60'), stage: t('dur.funnel.stage.d', { d: num(row.age) }) };
    return { phase: t('dur.funnel.p90'), cls: 'ok', text: t('dur.funnel.m90'), stage: t('dur.funnel.stage.d', { d: num(row.age) }) };
  };

  const rowsHtml = entries.map((row) => {
    const m = metaFor(row);
    const activePct = Math.max(0, Math.min(100, Math.round(row.surv * 100)));
    const endedPct = `${100 - activePct}%`;
    return `<tr${row.isMedian ? ' class="is-median"' : ''}>
      <td><strong>${esc(m.stage)}</strong></td>
      <td><div class="surv-bar-wrap"><div class="surv-track"><div class="surv-fill" style="width:${activePct}%"></div></div><strong class="num">${activePct}%</strong></div></td>
      <td class="num muted">${esc(t('dur.funnel.ended.val', { pct: endedPct }))}</td>
      <td><span class="phase-badge ${m.cls}">${esc(m.phase)}</span></td>
      <td class="muted">${esc(m.text)}</td>
    </tr>`;
  }).join('');

  return `<div class="lifecycle-card">
    <div class="sec-eyebrow">${esc(t('dur.funnel.eyebrow'))}${simplePop('dur.funnel.eyebrow', 'help.funnel.title', 'help.funnel.body')}</div>
    <h3 style="font-size:1rem;font-weight:660;margin-top:2px">${esc(t('dur.funnel.title'))}</h3>
    <div class="table-scroll"><table class="lifecycle-table">
      <thead><tr><th>${esc(t('dur.funnel.col.stage'))}</th><th>${esc(t('dur.funnel.col.active'))}</th><th>${esc(t('dur.funnel.col.ended'))}</th><th>${esc(t('dur.funnel.col.phase'))}</th><th>${esc(t('dur.funnel.col.meaning'))}</th></tr></thead>
      <tbody>${rowsHtml}</tbody>
    </table></div>
  </div>`;
}
function durataSection(r) {
  if (r.mode !== 'company') {
    return `<section class="durata-locked"><p class="muted">${esc(t('dur.locked'))}</p></section>`;
  }
  const d = r.durata;
  const activeWin = Number(S.durataWindow || (d && d.window_days) || 90);
  const windows = `<div class="switch" role="group" aria-label="${esc(t('dur.window'))}">${toggle('durata-window', [60, 90, 120, 180], activeWin, (v) => t('dur.days.short', { n: v }))}</div>`;
  const busy = S.durataBusy || Boolean(S.job || S.busy);
  let body = '';
  if (S.durataBusy) {
    body = `<div class="durata-busy-card">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap">
        <div>
          <strong>${esc(t('dur.loading', { window: activeWin }))}</strong>
          <small id="durata-elapsed" style="display:block;color:var(--muted);margin-top:3px">${esc(t('dur.elapsed', { sec: S.durataElapsed || 0 }))}</small>
        </div>
        <button type="button" class="btn quiet small" data-action="durata-cancel">${esc(t('dur.cancel'))}</button>
      </div>
      <div class="bar open" style="margin-top:12px"><i></i></div>
    </div>`;
  } else if (S.durataError) {
    body = `<p class="notice err" style="margin-top:14px">${esc(t('dur.err'))}</p>`;
  } else if (d && d.available) {
    const share = d.loaded_share != null ? pct(d.loaded_share) : '—';
    const lead = d.median_reached
      ? t('dur.summary.reached', { total: num(d.concepts_in_window), window: num(d.window_days || activeWin), active: num(d.active_in_window), ended: num(d.ended_in_window), share, median: num(d.median_days) })
      : t('dur.summary.open', { total: num(d.concepts_in_window), window: num(d.window_days || activeWin), active: num(d.active_in_window), ended: num(d.ended_in_window), share });
    const w = d.weibull;
    const weibullHtml = w
      ? `<strong>${esc(t(`dur.regime.${w.regime}`))}</strong><small>${esc(t('dur.kpi.weibull.meta', { k: num(w.shape_k), scale: num(w.scale_days) }))}</small>`
      : `<strong>${esc(t('dur.kpi.weibull.none'))}</strong><small>${esc(t('dur.kpi.weibull.none.sub'))}</small>`;
    const lindyHtml = (d.lindy && d.lindy.length)
      ? `<ul class="durata-lindy">${d.lindy.map((row) => `<li>${esc(t('dur.kpi.lindy.row', { age: num(row.after_days), share: pct(row.still_active_share), risk: num(row.at_risk) }))}</li>`).join('')}</ul>`
      : `<strong>${esc(t('dur.kpi.lindy.none'))}</strong><small>${esc(t('dur.kpi.lindy.none.sub'))}</small>`;
    const longItem = (d.longest_active || [])[0];
    const fastItem = (d.fastest_ended || [])[0];
    const exLong = (d.longest_active || []).slice(0, 2).map((x) => `${x.library_id} (${t('dur.days.short', { n: x.days })})`).join(', ');
    const exFast = (d.fastest_ended || []).slice(0, 2).map((x) => `${x.library_id} (${t('dur.days.short', { n: x.days })})`).join(', ');
    const smallNote = (d.small_sample || Number(d.ended_in_window || 0) < 20)
      ? `<p class="notice" style="margin-top:10px">${esc(t('dur.small_sample', { ended: num(d.ended_in_window || 0) }))}</p>`
      : '';
    body = `<p class="durata-lead">${esc(lead)}</p>
      ${smallNote}
      <div class="durata-kpis">
        <div class="durata-kpi"><span class="durata-kpi-label">${esc(t('dur.kpi.median'))}${simplePop('dur.kpi.median', 'help.dur.median.title', 'help.dur.median.body')}</span>
          <strong>${esc(d.median_reached ? days(d.median_days) : t('dur.kpi.open'))}</strong>
          <small>${esc(t('dur.kpi.rmst', { tau: num(d.tau_days || d.max_observed_days), days: num(d.rmst_days) }))}</small></div>
        <div class="durata-kpi"><span class="durata-kpi-label">${esc(t('dur.kpi.weibull'))}${weibullPop()}</span>${weibullHtml}</div>
        <div class="durata-kpi"><span class="durata-kpi-label">${esc(t('dur.kpi.lindy'))}${lindyPop(true)}</span>${lindyHtml}</div>
      </div>
      <div class="km-layout">
        <div class="durata-chart">
          <div class="durata-chart-head"><span>${esc(t('dur.chart.prob'))}${simplePop('dur.chart.prob', 'help.km.chart.title', 'help.km.chart.body')}</span>${d.median_reached ? `<strong>${esc(t('dur.chart.median', { n: num(d.median_days) }))}</strong>` : ''}</div>
          ${renderKmSvg(d)}
        </div>
        <div class="km-extremes-box">
          <div class="sec-eyebrow">${esc(t('dur.extremes.eyebrow'))}${simplePop('dur.extremes.eyebrow', 'help.extremes.title', 'help.extremes.body', null, true)}</div>
          <h3 style="font-size:1rem;font-weight:660;margin-top:2px">${esc(t('dur.extremes.title'))}</h3>
          <div class="km-extremes-rows">
            <div class="km-extreme-row"><span>${esc(t('dur.extremes.active_max'))}</span><strong class="num">${esc(longItem ? days(longItem.days) : '—')}</strong></div>
            <div class="km-extreme-row"><span>${esc(t('dur.extremes.fast_cut'))}</span><strong class="num">${esc(fastItem ? days(fastItem.days) : '—')}</strong></div>
            <div class="km-extreme-row"><span>${esc(t('dur.extremes.cohort', { window: num(d.window_days || activeWin) }))}</span><strong class="num">${esc(t('dur.extremes.cohort.val', { total: num(d.concepts_in_window), active: num(d.active_in_window), ended: num(d.ended_in_window) }))}</strong></div>
          </div>
          ${(exLong || exFast) ? `<div class="durata-examples">${exLong ? `<span>${esc(t('dur.examples.long'))}: ${esc(exLong)}</span>` : ''}${exFast ? `<span>${esc(t('dur.examples.fast'))}: ${esc(exFast)}</span>` : ''}</div>` : ''}
        </div>
      </div>
      ${durFunnelHtml(d)}
      <p class="tablenote">${esc(t('dur.note'))}</p>`;
  } else if (d && !d.available) {
    body = `<p class="notice" style="margin-top:14px">${esc(durataUnavailableText(d))}</p><p class="tablenote">${esc(t('dur.note'))}</p>`;
  } else {
    body = `<p class="muted" style="margin-top:12px">${esc(t('dur.idle'))}</p>`;
  }
  return `<section class="durata-sec">
    <div class="durata-head">
      <div class="durata-head-title">
        <div class="sec-eyebrow">${esc(t('dur.eyebrow'))}</div>
        <h2>${esc(t('dur.title'))}${durataPop()}</h2>
        <p>${esc(t('dur.sub'))}</p>
      </div>
      <div class="durata-controls">
        <span>${esc(t('dur.window'))}</span>${windows}
        <button class="btn small${d ? ' quiet' : ''}" data-action="durata-run" ${busy ? 'disabled' : ''}>${esc(t(d ? 'dur.rerun' : 'dur.run'))}</button>
      </div>
    </div>
    ${body}
  </section>`;
}
function renderRitmoSvg(m) {
  const st = m.sta_lta || {};
  const weeks = st.weeks || [];
  if (!weeks.length) return '';
  const selIdx = S.seismoWeek != null && S.seismoWeek >= 0 && S.seismoWeek < weeks.length
    ? S.seismoWeek : weeks.length - 1;
  const W = 640, H = 152, padL = 34, padR = 14, padT = 18, padB = 24;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const maxY = Math.max(1, Number(st.lta_mean || 0), ...weeks.map((w) => Number(w.concepts || 0)));
  const slot = plotW / weeks.length;
  const barW = Math.max(18, Math.round(slot * 0.56));
  const yOf = (val) => +(padT + (1 - Math.max(0, val) / maxY) * plotH).toFixed(1);

  const bars = weeks.map((w, idx) => {
    const cx = padL + slot * (idx + 0.5);
    const x = +(cx - barW / 2).toFixed(1);
    const countVal = Number(w.concepts || 0);
    const rawH = Math.round((countVal / maxY) * plotH);
    const bh = Math.max(4, rawH);
    const y = +(padT + plotH - bh).toFixed(1);
    const fill = w.is_sta ? (m.trigger_ai ? 'var(--warn)' : 'var(--accent)') : 'var(--line)';
    const lbl = (w.week_start || '').slice(5);
    const isSel = idx === selIdx;
    const strokeAttr = isSel ? ' stroke="var(--text)" stroke-width="2"' : '';
    const hitX0 = +(padL + slot * idx).toFixed(1);
    const hitX1 = +(padL + slot * (idx + 1)).toFixed(1);
    return `<g class="ritmo-bar-hit" data-action="seismo-week" data-value="${idx}">
      <path class="bar-bg" d="M${hitX0},${padT} H${hitX1} V${padT + plotH} H${hitX0} Z" fill="var(--text)" opacity="0"/>
      <rect x="${x}" y="${y}" width="${barW}" height="${bh}" rx="3" fill="${fill}" fill-opacity="${w.is_sta ? '0.92' : '0.86'}"${strokeAttr}/>
      <text x="${cx.toFixed(1)}" y="${Math.max(11, y - 4).toFixed(1)}" text-anchor="middle" fill="${isSel ? 'var(--text)' : 'var(--muted)'}" font-size="10" font-weight="${isSel ? '700' : '500'}">${countVal}</text>
      <text x="${cx.toFixed(1)}" y="${H - 6}" text-anchor="middle" fill="${isSel ? 'var(--text)' : 'var(--muted)'}" font-size="10" font-weight="${isSel ? '700' : '500'}">${esc(lbl)}</text>
    </g>`;
  }).join('');

  const meanVal = Number(st.lta_mean || 0);
  const meanLine = meanVal > 0
    ? `<line x1="${padL}" y1="${yOf(meanVal)}" x2="${W - padR}" y2="${yOf(meanVal)}" stroke="var(--accent)" stroke-dasharray="4 4" stroke-width="1.3"/>`
    : '';
  const baseLine = `<line x1="${padL}" y1="${padT + plotH}" x2="${W - padR}" y2="${padT + plotH}" stroke="var(--line-soft)" stroke-width="1"/>`;
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t('rit.chart.title'))}">
    ${baseLine}${meanLine}${bars}
  </svg>`;
}
function ritWeekInspectorHtml(m, st) {
  const weeks = st.weeks || [];
  if (!weeks.length) return '';
  const idx = S.seismoWeek != null && S.seismoWeek >= 0 && S.seismoWeek < weeks.length
    ? S.seismoWeek : weeks.length - 1;
  const w = weeks[idx];
  const baseMean = Number(st.lta_mean || 0);
  const ratioVal = baseMean > 0 ? Math.round((Number(w.concepts || 0) / baseMean) * 100) / 100 : 0;
  const dateLbl = w.week_start ? day(w.week_start) : `W${idx + 1}`;
  let desc = '';
  if (Number(w.concepts || 0) === 0) desc = t('rit.week.desc.zero');
  else if (ratioVal >= 2.5) desc = t('rit.week.desc.spike', { lta: num(st.lta_mean || 0) });
  else desc = t('rit.week.desc.norm', { lta: num(st.lta_mean || 0) });

  return `<aside class="week-detail-card">
    <div class="sec-eyebrow">${esc(t('rit.week.eyebrow', { idx: idx + 1, tot: weeks.length }))}</div>
    <h3 style="font-size:1rem;font-weight:660;margin-top:2px">${esc(t('rit.week.title', { date: dateLbl, n: num(w.concepts || 0) }))}</h3>
    <div style="margin:10px 0">
      <div class="week-stat"><span class="muted">${esc(t('rit.week.ratio'))}</span><strong class="num">${esc(t('rit.week.ratio.val', { ratio: num(ratioVal) }))}</strong></div>
      <div class="week-stat"><span class="muted">${esc((t('rit.chart.baseline', { n: num(st.lta_mean || 0) }).split(':')[0] || '').trim())}</span><strong class="num">${esc((t('rit.chart.baseline', { n: num(st.lta_mean || 0) }).split(':')[1] || '').trim())}</strong></div>
    </div>
    <p style="font-size:.86rem;color:var(--muted);line-height:1.48">${esc(desc)}</p>
    <p style="font-size:.78rem;color:var(--muted);margin-top:10px">${esc(t('rit.week.hint'))}</p>
  </aside>`;
}
function ritmoUnavailableText(m) {
  const share = m.loaded_share != null ? pct(m.loaded_share) : '—';
  if (m.reason === 'partial_list') return t('rit.unavail.partial_list', { share });
  if (m.reason === 'insufficient_history') return t('rit.unavail.insufficient_history');
  return t('rit.unavail.other', { reason: m.reason || '—' });
}
function ritmoSection(r, inNews = false) {
  if (!r) return '';
  if (r.mode !== 'company') {
    return !inNews ? `<section class="ritmo-locked"><p class="muted">${esc(t('rit.locked'))}</p></section>` : '';
  }
  if (!r.ritmo) return '';
  const m = r.ritmo;
  const busy = S.durataBusy || Boolean(S.job || S.busy);
  const refreshBtn = !inNews && r.page && r.page.page_id
    ? `<div class="ritmo-controls"><button class="btn small quiet" data-action="ritmo-refresh" ${busy ? 'disabled' : ''}>${esc(t('rit.refresh'))}</button></div>`
    : '';

  const ritNoteTxt = (m.snapshots || 0) === 1 ? t('rit.note.one') : t('rit.note', { snapshots: num(m.snapshots || 0) });
  let body = '';
  if (!m.available) {
    body = `<p class="notice" style="margin-top:14px">${esc(ritmoUnavailableText(m))}</p>
      <p class="ritmo-note">${esc(ritNoteTxt)}</p>`;
  } else {
    const st = m.sta_lta || {};
    const cu = m.cusum || {};
    const lt = m.littles_law || {};

    let stHtml;
    if (st.measurable) {
      const head = st.ratio != null ? t('rit.stalta.ratio', { ratio: num(st.ratio) }) : t('rit.stalta.burst');
      const stateLbl = hasT(`rit.state.${st.state}`) ? t(`rit.state.${st.state}`) : (st.state || '');
      stHtml = `<strong>${esc(head)}</strong>
        <small>${esc(stateLbl)} · ${esc(t('rit.stalta.meta', { sta: num(st.sta_count), lta: num(st.lta_mean), p: num(st.p_value) }))}</small>
        ${st.survivor_bias_caveat ? `<small>${esc(t('rit.stalta.caveat'))}</small>` : ''}`;
    } else {
      stHtml = `<strong>${esc(t('rit.state.none'))}</strong>
        <small>${esc(t('rit.stalta.none_sub', { sta: num(st.sta_count || 0), lta: num(st.lta_total || 0) }))}</small>`;
    }

    let cuHtml;
    if (cu.measurable && cu.primary) {
      const p = cu.primary;
      const fmtLbl = hasT(`format.${p.format}`) ? t(`format.${p.format}`) : p.format;
      const head = cu.drift_detected
        ? t('rit.cusum.shift', { fmt: fmtLbl, from: Math.round(p.baseline_share * 100), to: Math.round(p.recent_share * 100) })
        : t('rit.cusum.steady');
      cuHtml = `<strong>${esc(head)}</strong>
        <small>${esc(t('rit.cusum.meta', { n: num(cu.concepts), days: num(cu.span_days), peak: num(p.cusum_peak), h: num(p.threshold) }))}</small>
        ${cu.drift_detected && p.changepoint_date ? `<small>${esc(t('rit.cusum.cp', { date: day(p.changepoint_date) }))}</small>` : ''}`;
    } else {
      cuHtml = `<strong>${esc(t('rit.state.none'))}</strong><small>${esc(t('rit.cusum.none_sub'))}</small>`;
    }

    let ltHtml;
    if (lt.measurable) {
      const stateKey = `rit.little.${lt.balance_state}`;
      const head = lt.steady_state_checked && hasT(stateKey)
        ? t(stateKey)
        : t('rit.little.implied', { days: num(lt.implied_mean_days) });
      const meta = lt.steady_state_checked
        ? t('rit.little.meta_checked', { active: num(lt.active_concepts), rate: num(lt.lambda_per_week), rmst: num(lt.mean_duration_days), exp: num(lt.expected_active), ratio: num(lt.balance_ratio) })
        : t('rit.little.meta_implied', { active: num(lt.active_concepts), rate: num(lt.lambda_per_week) });
      ltHtml = `<strong>${esc(head)}</strong><small>${esc(meta)}</small>`;
    } else {
      ltHtml = `<strong>${esc(t('rit.state.none'))}</strong><small>${esc(t('rit.little.none_sub'))}</small>`;
    }

    let alertHtml = '';
    if (m.trigger_ai) {
      const parts = [];
      if (st.trigger_ai) parts.push(st.ratio != null ? t('tldr.ritmo.spike_part', { ratio: num(st.ratio) }) : t('tldr.ritmo.burst_part'));
      if (cu.trigger_ai && cu.primary) {
        const p = cu.primary;
        const fmtLbl = hasT(`format.${p.format}`) ? t(`format.${p.format}`) : p.format;
        parts.push(t('tldr.ritmo.drift_part', { fmt: fmtLbl, from: Math.round(p.baseline_share * 100), to: Math.round(p.recent_share * 100) }));
      }
      const exIds = [...new Set([...(st.trigger_ai ? (st.recent_ids || []) : []), ...(cu.trigger_ai ? (cu.example_ids || []) : [])])].slice(0, 4);
      alertHtml = `<div class="ritmo-alert">
        <strong>${esc(t('rit.alert.lead'))} ${esc(parts.join(' · '))}</strong>
        <small>${esc(t('rit.alert.ids', { ids: exIds.join(', ') || '—' }))}</small>
      </div>`;
    }

    const chartHtml = st.weeks && st.weeks.length
      ? `<div class="ritmo-inspector-grid">
          <div class="ritmo-chart">
            <div class="chart-legend">
              <span><i class="leg-dot" style="background:var(--warn)"></i>${esc(t('rit.leg.spike'))}</span>
              <span><i class="leg-dot" style="background:var(--accent)"></i>${esc(t('rit.leg.current'))}</span>
              <span><i class="leg-dot" style="background:var(--line)"></i>${esc(t('rit.leg.normal'))}</span>
            </div>
            <div class="ritmo-chart-head"><span>${esc(t('rit.chart.title'))}</span><span>${esc(t('rit.chart.baseline', { n: num(st.lta_mean || 0) }))} · <strong>${esc(t('rit.chart.sta', { n: num(st.sta_count || 0) }))}</strong></span></div>
            ${renderRitmoSvg(m)}
          </div>
          ${ritWeekInspectorHtml(m, st)}
        </div>` : '';

    body = `${alertHtml}
      <div class="ritmo-kpis">
        <div class="ritmo-kpi"><span class="ritmo-kpi-label">${esc(t('rit.kpi.stalta'))}${staLtaPop()}</span>${stHtml}</div>
        <div class="ritmo-kpi"><span class="ritmo-kpi-label">${esc(t('rit.kpi.cusum'))}${cusumPop()}</span>${cuHtml}</div>
        <div class="ritmo-kpi"><span class="ritmo-kpi-label">${esc(t('rit.kpi.little'))}${littlePop(true)}</span>${ltHtml}</div>
      </div>
      ${chartHtml}
      <p class="ritmo-note">${esc(ritNoteTxt)}</p>`;
  }

  return `<section class="ritmo-sec">
    <div class="ritmo-head">
      <div class="ritmo-head-title">
        <div class="sec-eyebrow">${esc(t('rit.eyebrow'))}${simplePop('rit.eyebrow', 'help.ritmo.eyebrow.title', 'help.ritmo.eyebrow.body')}</div>
        <h2>${esc(t('rit.title'))}${ritmoPop()}</h2>
        <p>${esc(t('rit.sub'))}</p>
      </div>
      ${refreshBtn}
    </div>
    ${body}
  </section>`;
}
function strutturaSection(r) {
  if (!r || !r.struttura) return '';
  const s = r.struttura;
  const subKey = r.mode === 'company' ? 'str.sub.company' : 'str.sub.keyword';
  const rc = s.reach_concentration || {};
  const cf = s.copy_families || {};
  const sh = s.shannon || {};

  let concHtml;
  if (rc.measurable) {
    const lvlKey = `str.conc.level.${rc.level}`;
    const lvl = hasT(lvlKey) ? t(lvlKey) : (rc.level || '');
    concHtml = `<strong>${esc(t('str.conc.head', { top1: pct(rc.top1_share), top3: pct(rc.top3_share) }))}</strong>
      <small>${esc(t('str.conc.meta', { level: lvl, n: num(rc.concepts_with_reach), hhi: num(rc.hhi), eff: num(rc.effective_n), gini: num(rc.gini) }))}</small>
      ${rc.scope === 'eu_uk' ? `<small>${esc(t('str.conc.scope_eu'))}</small>` : ''}`;
  } else {
    concHtml = `<strong>${esc(t('str.conc.none'))}</strong><small>${esc(t('str.conc.none_sub'))}</small>`;
  }

  let copyHtml;
  if (cf.measurable) {
    copyHtml = `<strong>${esc(t('str.copy.head', { k: num(cf.families_count), m: num(cf.evaluated) }))}</strong>
      <small>${esc(t('str.copy.meta', { ratio: num(cf.diversity_ratio), max: pct(cf.largest_family_share), ncd: num(cf.median_pairwise_ncd) }))}</small>`;
  } else {
    copyHtml = `<strong>${esc(t('str.copy.none'))}</strong><small>${esc(t('str.copy.none_sub'))}</small>`;
  }

  const shLine = (row, strKey, labelFn) => {
    if (!row || !row.measurable) return '';
    const lblKey = `str.shannon.label.${row.label}`;
    const lbl = hasT(lblKey) ? t(lblKey) : (row.label || '');
    const dom = labelFn ? labelFn(row.dominant) : row.dominant;
    return `<small>${esc(t(strKey, { label: lbl, eff: num(row.effective_k), k: num(row.categories), dom, share: pct(row.dominant_share) }))}</small>`;
  };
  const fmtLine = shLine(sh.formats, 'str.shannon.fmt', (d) => (hasT(`format.${d}`) ? t(`format.${d}`) : d));
  const destLine = shLine(sh.destinations, 'str.shannon.dest');
  let shHtml = `<strong>${esc(t('str.kpi.shannon'))}</strong>`;
  if (fmtLine || destLine) shHtml += `${fmtLine}${destLine}`;
  else shHtml += `<small>${esc(t('str.shannon.none'))}</small>`;

  let famHtml = '';
  if (cf.measurable && (cf.top_families || []).length) {
    const chips = cf.top_families.map((fam) => {
      const famHead = fam.size === 1
        ? t('str.families.item.one', { share: pct(fam.share), id: fam.representative_id })
        : t('str.families.item', { size: num(fam.size), share: pct(fam.share), id: fam.representative_id });
      return `<button type="button" class="fam-chip" data-action="open-ad" data-value="${esc(fam.representative_id)}">
      <strong>${esc(famHead)}</strong>
      <span>${esc(fam.opening || '—')}</span>
    </button>`;
    }).join('');
    famHtml = `<div class="struttura-families">
      <div class="struttura-families-head">${esc(t('str.families.title'))}${simplePop('str.families.title', 'help.families.title', 'help.families.body')}</div>
      <div class="fam-chips">${chips}</div>
    </div>`;
  }

  const noteText = rc.measurable ? t('str.note', { n: num(rc.concepts_with_reach) }) : t('str.note.noreach');
  return `<section class="struttura-sec">
    <div class="struttura-head">
      <div class="struttura-head-title">
        <div class="sec-eyebrow">${esc(t('str.eyebrow'))}</div>
        <h2>${esc(t('str.title'))}${strutturaPop()}</h2>
        <p>${esc(t(subKey))}</p>
      </div>
    </div>
    <div class="struttura-kpis">
      <div class="struttura-kpi"><span class="struttura-kpi-label">${esc(t('str.kpi.conc'))}${concPop()}</span>${concHtml}</div>
      <div class="struttura-kpi"><span class="struttura-kpi-label">${esc(t('str.kpi.copy'))}${ncdPop()}</span>${copyHtml}</div>
      <div class="struttura-kpi"><span class="struttura-kpi-label">${esc(t('str.kpi.shannon'))}${shannonPop(true)}</span>${shHtml}</div>
    </div>
    ${famHtml}
    <p class="struttura-note">${esc(noteText)}</p>
  </section>`;
}
function anomDetailText(item, baselines) {
  const m = item.metrics || {};
  const b = baselines || {};
  const perDay = t('t.perday').toLowerCase();
  const rpd = m.reach_per_day != null ? `${num(Math.round(m.reach_per_day))} ${perDay}` : '—';
  const medianRpd = b.median_reach_per_day != null ? `${num(Math.round(b.median_reach_per_day))} ${perDay}` : '—';
  const daysStr = m.days_running != null ? days(m.days_running) : '—';
  const medDaysStr = b.median_days != null ? days(Math.round(Number(b.median_days))) : '—';
  const medCharsStr = b.median_body_chars != null ? num(Math.round(Number(b.median_body_chars))) : '—';
  const creativesStr = oneOrMore('f.reused.n', m.creatives || 1);
  if (item.kind === 'long_live_low_reach') {
    return t('anom.detail.long_live_low_reach', { days: daysStr, median_days: medDaysStr, rpd, median_rpd: medianRpd });
  }
  if (item.kind === 'fast_breakout_reach') {
    return t('anom.detail.fast_breakout_reach', { days: daysStr, rpd, median_rpd: medianRpd });
  }
  if (item.kind === 'high_reach_minimal_copy') {
    return t('anom.detail.high_reach_minimal_copy', { rpd, median_rpd: medianRpd, chars: num(m.body_chars ?? 0), median_chars: medCharsStr });
  }
  if (item.kind === 'many_creatives_low_reach') {
    return t('anom.detail.many_creatives_low_reach', { creatives: creativesStr, rpd, median_rpd: medianRpd });
  }
  if (item.kind === 'long_live_single_creative_top_rank') {
    const basis = m.reach_per_day != null
      ? rpd
      : (m.impression_rank != null ? t('anom.norpd', { rank: num(m.impression_rank) }) : '—');
    return t('anom.detail.long_live_single_creative_top_rank', { days: daysStr, basis });
  }
  return item.detail || '';
}
function anomalieSection(r) {
  if (!r || !r.anomalie) return '';
  const a = r.anomalie;
  const subKey = r.mode === 'company' ? 'anom.sub.company' : 'anom.sub.keyword';
  let body = '';
  if (!a.available) {
    body = `<p class="notice" style="margin-top:14px">${esc(t('anom.unavail'))}</p>`;
  } else if (!(a.items || []).length) {
    body = `<p class="muted" style="margin-top:14px">${esc(t('anom.empty'))}</p>`;
  } else {
    const cards = a.items.map((item) => {
      const m = item.metrics || {};
      const kindKey = `anom.kind.${item.kind}`;
      const kindLbl = hasT(kindKey) ? t(kindKey) : item.kind;
      const rpdTxt = m.reach_per_day != null
        ? `${num(m.reach_per_day)} ${t('t.perday').toLowerCase()}`
        : (m.impression_rank != null ? t('anom.norpd', { rank: num(m.impression_rank) }) : '—');
      const metaTxt = t('anom.meta', {
        days: m.days_running != null ? days(m.days_running) : '—',
        creatives: oneOrMore('f.reused.n', m.creatives || 1),
        rpd: rpdTxt,
      });
      return `<button type="button" class="anom-card" data-action="open-ad" data-value="${esc(item.library_id)}">
        <span class="anom-tag">${esc(kindLbl)} · id ${esc(item.library_id)}</span>
        <strong class="anom-open">${esc(item.opening || t('t.notext'))}</strong>
        <small class="anom-detail">${esc(anomDetailText(item, a.baselines))}</small>
        <span class="anom-meta">${esc(metaTxt)}</span>
      </button>`;
    }).join('');
    body = `<div class="anomalie-grid">${cards}</div>`;
  }
  return `<section class="anomalie-sec">
    <div class="anomalie-head">
      <div class="anomalie-head-title">
        <div class="sec-eyebrow">${esc(t('anom.eyebrow'))}</div>
        <h2>${esc(t('anom.title'))}${anomaliePop()}</h2>
        <p>${esc(t(subKey))}</p>
      </div>
    </div>
    ${body}
    <p class="anomalie-note">${esc(t('anom.note'))}</p>
  </section>`;
}
function tierPanelHtml() {
  const tiers = [
    ['v-scaling', 'tier.s.tag', 'tier.s.desc'],
    ['v-holding', 'tier.a.tag', 'tier.a.desc'],
    ['v-average', 'tier.b.tag', 'tier.b.desc'],
    ['v-testing', 'tier.t.tag', 'tier.t.desc'],
    ['v-review', 'tier.r.tag', 'tier.r.desc'],
  ].map(([cls, tag, desc]) => `<div class="tier-item">
    <span class="${cls}">${esc(t(tag))}</span>
    <p>${esc(t(desc))}</p>
  </div>`).join('');
  return `<div class="tier-panel">
    <div class="tier-panel-head">
      <span class="sec-eyebrow" style="margin-bottom:0">${esc(t('tier.panel.title'))}${tierScalePop()}</span>
      <span class="muted" style="font-size:.78rem">${esc(t('tier.panel.sub'))}</span>
    </div>
    <div class="tier-legend-grid">${tiers}</div>
    <div class="rel-strip">
      <strong>${esc(t('tier.rel.title'))}</strong>
      <span><strong>${esc(t('reliability.high'))}:</strong> ${esc(t('leg.r.high'))}</span>
      <span><strong>${esc(t('reliability.medium'))}:</strong> ${esc(t('leg.r.medium'))}</span>
      <span><strong>${esc(t('reliability.low'))}:</strong> ${esc(t('leg.r.low'))}</span>
    </div>
  </div>`;
}
function tableSection(r) {
  const company = r.mode === 'company';
  const isCards = S.adsView === 'cards';
  const countryName = region(r.country);
  const bodyHtml = isCards
    ? `<div class="ads-grid" id="ads-grid">${cardsGridHtml(r)}</div>`
    : `<div class="table-scroll"><table class="ads${company ? '' : ' mixed'}"><thead><tr><th></th><th>${esc(t('t.ad'))}${adColPop()}</th><th>${esc(t('t.tier'))}${tierScalePop()}</th>
    <th class="r">${esc(t('t.score'))}${scoreScalePop(true)}</th><th class="r">${esc(t('t.days'))}${daysColPop(true)}</th><th class="r">${esc(t('t.creatives'))}${creativesColPop(true)}</th>
    ${company ? '' : `<th>${esc(t('t.format'))}</th>`}<th class="r">${esc(t('t.reached', { country: countryName }))}${reachedColPop(countryName, true)}</th><th class="r">${esc(t('t.perday'))}${perdayPop(true)}</th></tr></thead>
    <tbody id="ads-tbody">${tableRowsHtml(r)}</tbody></table></div>`;
  const opened = r.deep ? r.deep.read : r.ads.reduce((sum, ad) => sum + (ad.reach ? 1 : 0) + Object.keys(ad.card_reach || {}).length, 0);
  const concepts = r.deep ? r.deep.concepts : r.ads.filter((ad) => ad.reach).length;
  return `<section>
    <div class="sec-eyebrow">${esc(t('ads.eyebrow'))}</div>
    <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:14px">
      <div>
        <h2 class="sec-title-line">${esc(t('ads.title', { country: countryName }))}${simplePop('ads.eyebrow', 'help.ads.sec.title', 'help.ads.sec.body')}</h2>
        <p class="muted" style="font-size:.9rem;margin-top:3px">${esc(t('ads.sub'))}</p>
      </div>
    </div>
    ${tierPanelHtml()}
    <div class="sortbar">
      <span>${esc(t('sort.by'))}</span><div class="switch" role="group">${toggle('sort', ['score', 'perday', 'days'], S.sort, (v) => t(`sort.${v}`))}</div>
      <div class="switch" role="group">${toggle('tfilter', ['all', 'scaling', 'video', 'high'], S.filter, (v) => t(`filter.${v}`))}</div>
      <div class="switch" role="group">${toggle('ads-view', ['table', 'cards'], S.adsView, (v) => t(`ads.view.${v}`))}</div>
      <span class="sort-spacer"></span>
      <input type="search" class="tbl-search" id="tbl-q" data-bind="tableQuery" value="${esc(S.tableQuery)}" placeholder="${esc(t('filter.search'))}" autocomplete="off">
      <button class="btn quiet small" data-action="export-csv">${esc(t('export.csv'))}</button>
    </div>
    ${tableLegend()}
    ${bodyHtml}<p class="tablenote">${esc(t(concepts === 1 ? 't.note.one' : 't.note', { concepts: count(concepts, 'n.concepts'), opened: count(opened, 'n.ads') }))}</p></section>`;
}
function liveStepperHtml() {
  const title = S.mode === 'company' ? (S.company || t('mode.company')) : (S.query || t(`mode.${S.mode}`));
  return `<div class="live-stepper">
    <h2>${esc(title)}</h2>
    <div class="step-meta"><span id="ptext"></span><span class="num" id="pleft"></span></div>
    <div class="bar open" id="pbar"><i></i></div>
    <div class="step-row">${[1, 2, 3, 4].map((n) => `<div class="step-item">${esc(t(`step.${n}`))}</div>`).join('')}</div>
  </div>`;
}
function studioTabBadge(r, tab) {
  if (tab === 'ads') return num((r.ads || []).length);
  if (tab === 'seismo' && r.ritmo && r.ritmo.sta_lta && r.ritmo.sta_lta.state === 'spike' && r.ritmo.sta_lta.ratio != null) {
    return `${num(r.ritmo.sta_lta.ratio)}x`;
  }
  if (tab === 'durata' && r.durata && r.durata.available && r.durata.median_reached && r.durata.median_days != null) {
    return t('dur.days.short', { n: num(r.durata.median_days) });
  }
  if (tab === 'structure' && r.anomalie && (r.anomalie.items || []).length) {
    return num(r.anomalie.items.length);
  }
  if (tab === 'strategy') return t(`level.${S.stratLevel === 'plan' ? 'plan' : 'analysis'}`);
  return null;
}
function studioTabsHtml(r) {
  const btns = STUDIO_TABS.map((tab, idx) => {
    const badge = studioTabBadge(r, tab);
    return `<button type="button" class="studio-tab" role="tab" data-action="rtab" data-value="${tab}" aria-selected="${S.tab === tab}">
      <span class="tab-num">${idx + 1}.</span><span>${esc(t(`tab.${tab}`))}</span>${badge != null ? `<span class="tab-badge">${esc(badge)}</span>` : ''}
    </button>`;
  }).join('');
  return `<nav class="studio-tabs" role="tablist">${btns}<span class="tab-hint">${esc(t('tab.hint'))}</span></nav>`;
}
function topPreviewSection(r) {
  const top = (r.ads || []).slice(0, 3);
  if (!top.length) return '';
  const cards = top.map((ad) => {
    const thumb = ad.thumbnail ? mediaImg(ad.thumbnail, 'top-card-thumb', '', true) : '<span class="top-card-thumb"></span>';
    const meta = [days(ad.days_running), ad.reach_per_day != null ? t('n.perday.short', { n: num(ad.reach_per_day) }) : ''].filter(Boolean).join(' · ');
    return `<button type="button" class="top-card" data-action="open-ad" data-value="${esc(ad.library_id)}">
      ${thumb}<div class="top-card-body">
        <div class="top-card-top"><span class="v-${ad.verdict}">${esc(t(`verdict.${ad.verdict}`))}</span><strong>${Math.round(ad.score)}/100</strong></div>
        <div class="top-card-copy">${esc(firstLine(ad) || t('t.notext'))}</div>
        <div class="top-card-meta">${esc(meta)}</div>
      </div>
    </button>`;
  }).join('');
  return `<section class="top-preview">
    <div class="sec-eyebrow">${esc(t('top.eyebrow'))}</div>
    <div class="top-preview-head"><h2>${esc(t('top.title'))}${simplePop('top.title', 'help.top.title', 'help.top.body')}</h2><button type="button" class="linklike" data-action="rtab" data-value="ads">${esc(t('top.all', { n: num((r.ads || []).length) }))}</button></div>
    <div class="top-cards">${cards}</div>
  </section>`;
}
function keywordJumpSection(r) {
  if (r.mode !== 'keyword' || !(r.advertisers || []).length) return '';
  const btns = r.advertisers.slice(0, 6).map((row) => `<button type="button" class="btn quiet small" data-action="jump-company" data-value="${esc(row.advertiser)}">${esc(row.advertiser)} (${num(row.ads)})</button>`).join('');
  return `<section class="jump-box"><p class="muted">${esc(t('jump.kw_note'))}</p><div class="jump-list">${btns}</div></section>`;
}
function linkifyAdIds(escapedHtml) {
  return escapedHtml.replace(/(?<![\d/\w])(\d{12,18})(?!\d)/g, '<button type="button" class="linklike id-link" data-action="open-ad" data-value="$1">$1</button>');
}
function formatInlineMd(raw) {
  let s = esc(raw);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  return linkifyAdIds(s);
}
function _mdCells(row) {
  return row.replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
}
function renderMarkdownSafe(md) {
  const lines = String(md || '').split(/\r?\n/);
  const out = [];
  let inList = false;
  let inTable = false;
  const closeList = () => { if (inList) { out.push('</ul>'); inList = false; } };
  const closeTable = () => { if (inTable) { out.push('</tbody></table></div>'); inTable = false; } };
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (!trimmed) { closeList(); closeTable(); continue; }
    const isPipe = trimmed.startsWith('|') && trimmed.slice(1).includes('|');
    if (!inTable && isPipe) {
      const next = (lines[i + 1] || '').trim();
      if (next.includes('-') && next.includes('|') && /^\|?[\s:|-]+\|?$/.test(next)) {
        closeList();
        const ths = _mdCells(trimmed).map((c) => `<th>${formatInlineMd(c)}</th>`).join('');
        out.push(`<div class="table-scroll"><table class="md-table"><thead><tr>${ths}</tr></thead><tbody>`);
        inTable = true;
        i++;
        continue;
      }
    }
    if (inTable) {
      if (isPipe) {
        out.push(`<tr>${_mdCells(trimmed).map((c) => `<td>${formatInlineMd(c)}</td>`).join('')}</tr>`);
        continue;
      }
      closeTable();
    }
    const h = trimmed.match(/^(#{1,3})\s+(.+)$/);
    if (h) { closeList(); const lvl = Math.min(3, h[1].length); out.push(`<h${lvl}>${formatInlineMd(h[2])}</h${lvl}>`); continue; }
    const li = trimmed.match(/^[-*]\s+(.+)$/);
    if (li) { if (!inList) { out.push('<ul>'); inList = true; } out.push(`<li>${formatInlineMd(li[1])}</li>`); continue; }
    closeList();
    out.push(`<p>${formatInlineMd(trimmed)}</p>`);
  }
  closeList();
  closeTable();
  return out.join('');
}
const ARCH_ICONS = {
  root: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2.5"/><path d="M8 9h8M8 13h5M8 17h3"/></svg>',
  copy: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
  video: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2.5"/><path d="m10 9 5 3-5 3V9Z"/></svg>',
  reach: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3.6 9h16.8M3.6 15h16.8"/><path d="M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
  cadence: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l3-7 4 14 3-7h4"/></svg>',
  jury: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3 4 7v5c0 5 3.4 8.3 8 9 4.6-.7 8-4 8-9V7l-8-4Z"/><path d="m9 12 2 2 4-4"/></svg>',
  audit: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
};
const ARROW_DOWN_SVG = '<svg width="14" height="10" viewBox="0 0 14 10" fill="currentColor" aria-hidden="true"><polygon points="7,9 1,2 13,2"/></svg>';
function archSchemaHtml(lvl) {
  const focus = S.archFocus || 'copy';
  const specs = [
    { key: 'copy', file: 'copy.md', right: false },
    { key: 'video', file: 'creative.md + frames/', right: false },
    { key: 'reach', file: 'reach.md', right: true },
    { key: 'cadence', file: 'testing.md', right: true },
  ];
  const nodeMeta = {
    root: { title: t('arch.root.title'), desc: t('arch.root.desc') },
    copy: { title: t('arch.copy.name'), desc: t('arch.copy.desc') },
    video: { title: t('arch.video.name'), desc: t('arch.video.desc') },
    reach: { title: t('arch.reach.name'), desc: t('arch.reach.desc') },
    cadence: { title: t('arch.cadence.name'), desc: t('arch.cadence.desc') },
    jury: { title: t('arch.jury.name'), desc: t('arch.jury.desc') },
    audit: { title: t('arch.audit.name'), desc: t('arch.audit.desc') },
  };
  const cur = nodeMeta[focus] || nodeMeta.copy;

  const specCards = specs.map((sp) => `<div class="arch-node${focus === sp.key ? ' active' : ''}" data-action="arch-focus" data-value="${sp.key}">
    <div class="arch-node-top">
      <span class="arch-icon">${ARCH_ICONS[sp.key]}</span>
      ${simplePop(`arch.${sp.key}.name`, `help.arch.${sp.key}.title`, `help.arch.${sp.key}.body`, `help.arch.${sp.key}.how`, sp.right)}
    </div>
    <div>
      <h4>${esc(t(`arch.${sp.key}.name`))}</h4>
      <p>${esc(t(`arch.${sp.key}.desc`))}</p>
    </div>
    <div class="arch-io">${esc(sp.file)}</div>
  </div>`).join('');

  const juryDimmed = lvl === 'analysis';
  const gateX = juryDimmed ? 762 : 238;
  return `<div class="arch-card">
    <div class="arch-head">
      <div>
        <div class="sec-eyebrow">${esc(t('arch.eyebrow'))}</div>
        <h3>${esc(t('arch.title'))}${simplePop('arch.eyebrow', 'help.arch.main.title', 'help.arch.main.body')}</h3>
      </div>
    </div>
    <div class="arch-schema">
      <div class="arch-root-wrap">
        <div class="arch-root" data-action="arch-focus" data-value="root" style="cursor:pointer">
          <span class="arch-icon">${ARCH_ICONS.root}</span>
          <div class="arch-root-body">
            <div class="arch-root-top">
              <h4>${esc(t('arch.root.title'))}</h4>
              ${simplePop('arch.root.title', 'help.arch.root.title', 'help.arch.root.body', 'help.arch.root.how')}
            </div>
            <p>${esc(t('arch.root.desc'))}</p>
          </div>
        </div>
      </div>

      <svg class="arch-tree-svg" viewBox="0 0 1000 34" aria-hidden="true">
        <path d="M500,0 V14 M125,14 H875 M125,14 V29 M375,14 V29 M625,14 V29 M875,14 V29 M120,23 L125,30 L130,23 M370,23 L375,30 L380,23 M620,23 L625,30 L630,23 M870,23 L875,30 L880,23" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <div class="arch-mobile-arrow">${ARROW_DOWN_SVG}</div>

      <div class="arch-specialists">${specCards}</div>

      <svg class="arch-tree-svg" viewBox="0 0 1000 34" aria-hidden="true">
        <path d="M125,2 V16 M375,2 V16 M625,2 V16 M875,2 V16 M125,16 H875 M${gateX},16 V30 M${gateX - 5},24 L${gateX},31 L${gateX + 5},24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <div class="arch-mobile-arrow">${ARROW_DOWN_SVG}</div>

      <div class="arch-gate-row">
        <div class="arch-node${focus === 'jury' ? ' active' : ''}${juryDimmed ? ' dimmed' : ''}" data-action="arch-focus" data-value="jury">
          <div class="arch-node-top">
            <span class="arch-icon">${ARCH_ICONS.jury}</span>
            ${simplePop('arch.jury.name', 'help.arch.jury.title', 'help.arch.jury.body', 'help.arch.jury.how')}
          </div>
          <div>
            <h4><span>${esc(t('arch.jury.name'))}</span>${juryDimmed ? `<span class="phase-badge">${esc(t('arch.l3only'))}</span>` : ''}</h4>
            <p>${esc(t('arch.jury.desc'))}</p>
          </div>
          <div class="arch-io">project.md + 5 script</div>
        </div>

        <div class="arch-arrow-mid" aria-hidden="true">
          <svg viewBox="0 0 42 18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M2 9h35"/><path d="m32 4 6 5-6 5"/></svg>
        </div>

        <div class="arch-node${focus === 'audit' ? ' active' : ''}" data-action="arch-focus" data-value="audit">
          <div class="arch-node-top">
            <span class="arch-icon">${ARCH_ICONS.audit}</span>
            ${simplePop('arch.audit.name', 'help.arch.audit.title', 'help.arch.audit.body', 'help.arch.audit.how', true)}
          </div>
          <div>
            <h4>${esc(t('arch.audit.name'))}</h4>
            <p>${esc(t('arch.audit.desc'))}</p>
          </div>
          <div class="arch-io">manifest.json · check_report</div>
        </div>
      </div>
    </div>
    <div class="arch-foot-bar">
      <span><strong>${esc(t('arch.focus.lbl'))} ${esc(cur.title)}</strong> · ${esc(cur.desc)}</span>
      <span class="code-pill">${esc(t('arch.verify.pill'))}</span>
    </div>
  </div>`;
}
function strategyTabSection(r) {
  const lvl = S.stratLevel === 'plan' ? 'plan' : 'analysis';
  const subj = (r.page && r.page.name) || r.query || t(`mode.${r.mode}`);
  const hasClaude = Boolean(S.link.quick && S.link.quick.claude);
  const running = Boolean(S.aiJob && S.aiJob.status === 'running');
  let primaryBtn = '';
  if (IS_MCP_APP) {
    const canMsg = Boolean(mcpApp && mcpApp.getHostCapabilities && mcpApp.getHostCapabilities()?.message);
    primaryBtn = canMsg
      ? `<button type="button" class="btn" data-action="mcp-send-ai">${esc(t('strat.ai.mcp'))}</button>`
      : `<p class="muted" style="font-size:.88rem">${esc(t('strat.ai.mcp_global', { name: subj }))}</p>`;
  } else if (hasClaude) {
    primaryBtn = `<button type="button" class="btn" data-action="ai-run" ${running ? 'disabled' : ''}>${esc(t('strat.ai.run'))}</button>`;
  }
  let outputHtml = '';
  if (S.stratNeedProject) {
    outputHtml = `<p class="notice err">${esc(t('strat.ai.project_needed'))} <button type="button" class="linklike" data-action="project">${esc(t('project.missing'))}</button></p>`;
  } else if (IS_MCP_APP && S.mcpSent) {
    outputHtml = `<p class="audit-pill ok">${esc(t('strat.ai.mcp_sent'))}</p>`;
  } else if (S.aiJob) {
    if (S.aiJob.status === 'running') {
      outputHtml = `<div class="progress" style="margin-top:4px;padding-top:8px"><p><span>${esc(t('strat.ai.running', { folder: S.aiJob.folder_name || 'pack' }))}</span><span class="muted num" id="ai-elapsed">${S.aiElapsed ? `${S.aiElapsed} s` : ''}</span></p><div class="bar open"><i></i></div></div>`;
    } else if (S.aiJob.status === 'error') {
      outputHtml = `<p class="notice err">${esc(t('strat.ai.err'))}: ${esc(S.aiJob.detail || S.aiJob.error || '')}</p>`;
    } else if (S.aiJob.markdown) {
      const a = S.aiJob.audit;
      const auditHtml = a ? (a.warning_count === 0
        ? `<div class="audit-pill ok">${esc(t('strat.ai.audit.ok', { n: num((a.checked_ad_ids || []).length) }))}</div>`
        : `<div class="audit-pill warn">${esc(t('strat.ai.audit.warn', { n: num(a.warning_count) }))}</div>`) : '';
      outputHtml = `${auditHtml}<div class="ai-report-view">${renderMarkdownSafe(S.aiJob.markdown)}</div>
        <div class="ai-actions"><button type="button" class="btn quiet small" data-action="copy-ai-report">${esc(t(S.aiCopied ? 'strat.ai.copied' : 'strat.ai.copy_report'))}</button></div>`;
    }
  }
  const exportBtn = IS_MCP_APP ? '' : `<button type="button" class="btn quiet small" data-action="brief">${esc(t('strat.ai.export'))}</button>`;
  const modeBar = `<div class="strat-mode-bar" role="group" aria-label="${esc(t('strat.ai.title'))}">
    <button type="button" class="strat-mode-btn${lvl === 'analysis' ? ' active' : ''}" data-action="strat-level" data-value="analysis">
      <div><strong>${esc(t('strat.lvl2.title'))}</strong><span>${esc(t('strat.lvl2.sub'))}</span></div>
      <span class="code-pill">${esc(t('strat.lvl2.tag'))}</span>
    </button>
    <button type="button" class="strat-mode-btn${lvl === 'plan' ? ' active' : ''}" data-action="strat-level" data-value="plan">
      <div><strong>${esc(t('strat.lvl3.title'))}</strong><span>${esc(t('strat.lvl3.sub'))}</span></div>
      <span class="code-pill">${esc(t('strat.lvl3.tag'))}</span>
    </button>
  </div>`;

  const calcCol = lvl === 'plan'
    ? `<div><h2 class="sec-title-line" style="margin-bottom:12px">${esc(t('strat.calc.title'))}${simplePop('strat.calc.title', 'help.strat.calc.title', 'help.strat.calc.body')}</h2>${levelVisual('plan', isSearchCollapsed())}</div>`
    : '';
  const runTitle = t(lvl === 'plan' ? 'strat.run.title.l3' : 'strat.run.title.l2');
  const runSub = t(lvl === 'plan' ? 'strat.ai.sub.l3' : 'strat.ai.sub.l2');

  return `<section class="strat-stack">
    <div>
      <div class="sec-eyebrow">${esc(t('strat.eyebrow'))}</div>
      <h2 class="sec-title-line">${esc(t('strat.ai.title'))}${simplePop('strat.ai.title', 'help.arch.main.title', 'help.arch.main.body')}</h2>
    </div>
    ${modeBar}
    ${archSchemaHtml(lvl)}
    <div class="strategy-grid${lvl === 'analysis' ? ' single' : ''}">
      ${calcCol}
      <div class="ai-studio-card">
        <div class="ai-studio-head">
          <div class="sec-eyebrow">${esc(t('strat.run.eyebrow'))}</div>
          <h2>${esc(runTitle)}</h2>
          <p>${esc(runSub)}</p>
        </div>
        <div class="ai-actions">${primaryBtn}${exportBtn}</div>
        <div id="ai-job-region">${outputHtml}</div>
      </div>
    </div>
  </section>`;
}
function renderResults() {
  const el = $('#results');
  if (S.mode === 'news') { renderNews(); hydrateMcpImages(); return; }
  if (S.mode === 'compare') {
    el.innerHTML = S.cmp ? cmpChooser() : (hasModeResult('compare') ? compareSheet(S.result) : '');
    hydrateMcpImages();
    return;
  }
  if ((hasModeBusy() || hasModeJob()) && !(S.pages && S.mode === 'company') && !hasModeResult()) {
    el.innerHTML = liveStepperHtml();
    updateProgress();
    return;
  }
  if (S.pages && S.mode === 'company') { el.innerHTML = pagesSheet(); hydrateMcpImages(); return; }
  if (!hasModeResult()) { el.innerHTML = ''; return; }
  const r = S.result;
  if (!STUDIO_TABS.includes(S.tab)) S.tab = 'overview';
  let tabBody = '';
  if (S.tab === 'overview') tabBody = `${cappedSection(r)}${changesSection(r)}${metricsSection(r)}${topPreviewSection(r)}${factsSection(r)}`;
  else if (S.tab === 'ads') tabBody = `${tableSection(r)}`;
  else if (S.tab === 'seismo') tabBody = `${ritmoSection(r)}${keywordJumpSection(r)}`;
  else if (S.tab === 'durata') tabBody = `${durataSection(r)}${keywordJumpSection(r)}`;
  else if (S.tab === 'structure') tabBody = `${strutturaSection(r)}${anomalieSection(r)}`;
  else if (S.tab === 'strategy') tabBody = `${strategyTabSection(r)}`;
  el.innerHTML = `<div class="sheet">${headSection(r)}${tldrSection(r)}${readySection(r)}${studioTabsHtml(r)}${tabBody}</div>`;
  hydrateMcpImages();
}

/* ---------- two companies ---------- */
function cmpChooser() {
  return S.cmp.sides.map((side, index) => {
    if (side.picked) return `<div class="sheet"><section><p class="picked">${esc(t('cmp.picked', { name: side.name }))}</p></section></div>`;
    const rows = side.pages.map((page) => `<tr>
      <td><div class="who">${avatar(page.logo, page.name)}<div><div>${esc(page.name)}${page.verified ? ` <span class="dim">· ${esc(t('pages.verified'))}</span>` : ''}</div>
        ${page.instagram ? `<small class="dim">@${esc(page.instagram)}</small>` : ''}</div></div></td>
      <td>${esc(page.category || '—')}</td><td class="r">${num(page.followers)}</td>
      <td class="r"><button class="btn small${page.page_id === side.suggested ? '' : ' quiet'}" data-action="cmp-pick" data-side="${index}" data-value="${esc(page.page_id)}">${esc(t('pages.choose'))}</button></td></tr>`).join('');
    return `<div class="sheet"><section><h2 style="margin-bottom:18px">${esc(t('cmp.pick', { name: side.name }))}</h2><div class="table-scroll"><table>
      <thead><tr><th>${esc(t('pages.page'))}</th><th>${esc(t('pages.category'))}</th><th class="r">${esc(t('pages.followers'))}</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div></section></div>`;
  }).join('');
}
function cmpValue(row, value) {
  const list = (items, label) => (items && items.length ? items.map(label).join(', ') : '—');
  switch (row.kind) {
    case 'number': return num(value);
    case 'percent': return value == null ? '—' : pct(value);
    case 'shares': return esc(list(value, (i) => `${row.key === 'formats' ? t(`format.${i.label}`) : i.label} ${pct(i.share)}`));
    case 'languages': return esc(list(value, (i) => `${named('language', i.label)} ${pct(i.share)}`));
    case 'platforms': return esc(list(value, (i) => `${PLATFORMS[i.label] || i.label} ${pct(i.share)}`));
    case 'genders': return esc(list(value, (g) => t(`gender.${g}`)));
    case 'breadths': return esc(list(value, (b) => t(`breadth.${b}`)));
    case 'places': return value && value.length ? placeNames(value, null, value.length, row.key === 'locations_excluded' ? 3 : 8) : '—';
    case 'text': return esc(row.key === 'age_range' && value ? ageRange(...String(value).split('-').map((part) => (/^\d+$/.test(part) ? Number(part) : null))) : value ?? '—');
    default: return esc(value ?? '—');
  }
}
function genderLabel(g) {
  if (g === 'female' && hasT('gender.Women')) return t('gender.Women');
  if (g === 'male' && hasT('gender.Men')) return t('gender.Men');
  if (g === 'all' && hasT('gender.All')) return t('gender.All');
  if (g === 'unknown' && hasT('gender.unknown')) return t('gender.unknown');
  return hasT(`gender.${g}`) ? t(`gender.${g}`) : (g || '—');
}
function piankaSection(c) {
  const ov = c.audience_overlap;
  if (!ov) return '';
  if (!ov.measurable) {
    return `<section class="pianka-sec">
      <div class="pianka-head"><h2>${esc(t('cmp.pianka.title'))}${piankaPop()}</h2></div>
      <p class="muted" style="margin-top:8px">${esc(t('cmp.pianka.none'))}</p>
    </section>`;
  }
  const pctVal = Math.round((ov.overlap || 0) * 100);
  const bandKey = `cmp.pianka.band.${ov.band}`;
  const bandLbl = hasT(bandKey) ? t(bandKey) : (ov.band || '');
  const segText = (row) => `${region(row.country)} · ${row.age_range} · ${genderLabel(row.gender)} (${pct(row.share_a)} vs ${pct(row.share_b)})`;
  const listCol = (title, items) => (items && items.length
    ? `<div><h4>${esc(title)}</h4><ul>${items.map((x) => `<li>${esc(segText(x))}</li>`).join('')}</ul></div>` : '');
  const cols = `${listCol(t('cmp.pianka.shared'), ov.shared_segments)}${listCol(t('cmp.pianka.only_a', { name: c.names.a }), ov.distinct_a)}${listCol(t('cmp.pianka.only_b', { name: c.names.b }), ov.distinct_b)}`;
  return `<section class="pianka-sec">
    <div class="pianka-head"><h2>${esc(t('cmp.pianka.title'))}${piankaPop()}</h2></div>
    <div class="pianka-bar-row">
      <div class="pianka-track"><div class="pianka-fill" style="width:${pctVal}%"></div></div>
      <span class="pianka-pct">${esc(`${pctVal}%`)}</span>
    </div>
    <p class="pianka-sub">${esc(t('cmp.pianka.meta', { pct: `${pctVal}%`, band: bandLbl, a: num(ov.ads_a), b: num(ov.ads_b) }))}</p>
    ${cols ? `<div class="pianka-cols">${cols}</div>` : ''}
  </section>`;
}
function compareSheet(r) {
  const c = r.comparison, [a = {}, b = {}] = r.sides || [];
  const head = (side) => { const page = side.page || {}; return `<div>${avatar(page.logo, page.name, true)}<div><h1>${esc(page.name || side.query)}</h1>
    <p>${esc(t('cmp.sub', { category: page.category || '—', followers: num(page.followers), loaded: num(side.ads_parsed) }))}</p></div></div>`; };
  const fmt = (note, value) => (note.key === 'video_share' ? pct(value) : num(value));
  const notes = (c.highlights || []).map((note) => `<li>${esc(t(`hl.${note.key}`, {
    leader: c.names[note.leader], other: c.names[note.leader === 'a' ? 'b' : 'a'],
    ratio: num(note.ratio), lead: fmt(note, note.lead), trail: fmt(note, note.trail) }))}</li>`).join('');
  let group = null;
  const rows = (c.rows || []).map((row) => {
    const title = row.group !== group ? `<tr class="group"><td colspan="3">${esc(t(`cmp.group.${row.group}`))}</td></tr>` : '';
    group = row.group;
    const numeric = row.kind === 'number' || row.kind === 'percent' ? ' class="num"' : '';
    return `${title}<tr><td>${esc(t(`cmp.row.${row.key}`, { country: region(r.country) }))}</td><td${numeric}>${cmpValue(row, row.a)}</td><td${numeric}>${cmpValue(row, row.b)}</td></tr>`;
  }).join('');
  const top = (side) => `<div><div class="table-scroll"><table class="ads"><tbody>${(side.ads || []).slice(0, 5).map((ad) => `<tr class="pick" data-action="open-ad" data-value="${esc(ad.library_id)}">
    <td><div class="adcell">${ad.thumbnail ? mediaImg(ad.thumbnail, 'thumb', '', true) : '<span class="thumb"></span>'}
      <div class="adtext"><div>${esc(firstLine(ad) || t('t.notext'))}</div><small>${esc(`${t(`verdict.${ad.verdict}`)} · ${days(ad.days_running)} · ${oneOrMore('f.reused.n', ad.creatives)}`)}</small></div></div></td>
    <td class="r">${Math.round(ad.score || 0)}</td></tr>`).join('')}</tbody></table></div></div>`;
  return `<div class="sheet">
    <section class="cmphead">${head(a)}${head(b)}</section>
    <section class="ready"><p>${esc(t(S.cmpCopied ? 'cmp.brief.copied' : 'cmp.brief.ready'))}</p>
      <button class="btn quiet small" data-action="copy-cmp-brief">${esc(t('cmp.brief.btn'))}</button></section>
    <section><h2>${esc(t('cmp.highlights'))}</h2>${notes ? `<ul class="notes">${notes}</ul>` : `<p class="muted" style="margin-top:8px">${esc(t('cmp.none'))}</p>`}
      <p class="pianka-note">${esc(t('cmp.note'))}</p></section>
    ${piankaSection(c)}
    <section><div class="table-scroll"><table class="cmp"><thead><tr><th></th><th>${esc(c.names.a)}</th><th>${esc(c.names.b)}</th></tr></thead><tbody>${rows}</tbody></table></div></section>
    <section><h2 style="margin-bottom:14px">${esc(t('cmp.top'))}</h2><div class="tops">${top(a)}${top(b)}</div>
      <p class="pianka-note"><button class="linklike" data-action="guide">${esc(t('link.guide'))}</button></p></section>
  </div>`;
}
function buildCompareBrief(r) {
  const c = r.comparison, [a, b] = r.sides;
  const lines = [`# Competitive Comparison: ${c.names.a} vs ${c.names.b} (${region(r.country)})`, ''];
  c.rows.forEach((row) => {
    lines.push(`- ${t(`cmp.row.${row.key}`, { country: region(r.country) })}: ${c.names.a} = ${JSON.stringify(row.a)} | ${c.names.b} = ${JSON.stringify(row.b)}`);
  });
  if (c.audience_overlap && c.audience_overlap.measurable) {
    lines.push(`- EU+UK audience overlap (Pianka): ${Math.round(c.audience_overlap.overlap * 100)}% (${c.audience_overlap.band})`);
  }
  lines.push('', `## Top concepts of ${c.names.a}`);
  a.ads.slice(0, 5).forEach((ad, i) => lines.push(`${i + 1}. [Score ${Math.round(ad.score)} · ${ad.days_running}d] ${firstLine(ad)}`));
  lines.push('', `## Top concepts of ${c.names.b}`);
  b.ads.slice(0, 5).forEach((ad, i) => lines.push(`${i + 1}. [Score ${Math.round(ad.score)} · ${ad.days_running}d] ${firstLine(ad)}`));
  lines.push('', 'Please write an executive head-to-head diagnosis: (1) where each advertiser is strongest, (2) which hooks and formats hold up best for each, and (3) three concrete creative gaps a challenger can exploit.');
  return lines.join('\n');
}
function exportCsv(r) {
  const headers = ['Rank', 'Library_ID', 'Advertiser', 'Verdict', 'Reliability', 'Score', 'Scale_60', 'Staying_25', 'Creatives_15', 'Days_Running', 'Creatives_Count', 'Format', 'Reach_Country', 'Reach_Per_Day', 'CTA', 'Domain', 'Copy_Opening', 'Ad_URL'];
  const csvEsc = (v) => `"${String(v ?? '').replaceAll('"', '""')}"`;
  const rows = filteredAds(r).map((ad, idx) => {
    const pts = ad.score_points || {};
    return [idx + 1, ad.library_id, ad.advertiser, t(`verdict.${ad.verdict}`), t(`reliability.${ad.reliability}`), Math.round(ad.score),
      Math.round(pts.scale || 0), Math.round(pts.staying || 0), Math.round(pts.creative || 0), ad.days_running, ad.creatives,
      ad.media_type, ad.reach_total ?? '', ad.reach_per_day ?? '', ad.cta ?? '', ad.landing_domain ?? '', firstLine(ad), ad.ad_url].map(csvEsc).join(',');
  });
  const blob = new Blob([`\uFEFF${headers.join(',')}\n${rows.join('\n')}\n`], { type: 'text/csv;charset=utf-8' });
  const link = document.createElement('a');
  const url = URL.createObjectURL(blob);
  link.href = url;
  link.download = `ad-library-insights-${(r.page && r.page.name) || r.query || 'export'}-${r.country}.csv`.replace(/[^a-zA-Z0-9._-]+/g, '-');
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const findAd = (id) => {
  const pools = S.result ? (S.result.sides ? S.result.sides.map((side) => side.ads || []) : [S.result.ads || []]) : [];
  const all = pools.flat().filter(Boolean);
  return all.find((item) => item.library_id === id)
    || all.find((item) => item.card_reach && Object.prototype.hasOwnProperty.call(item.card_reach, id));
};
async function submitCompare() {
  const names = [S.company.trim(), S.companyB.trim()];
  if (!names[0] || !names[1]) return note('error.input', null, true);
  const seq = ++S.searchSeq;
  S.result = null; S.resultMode = null; S.cmp = null; S.busy = 'pages'; S.busyMode = 'compare'; render();
  try {
    const sides = [];
    for (const name of names) {
      const found = await api(`/api/pages?name=${encodeURIComponent(name)}&country=${S.country}`);
      if (S.searchSeq !== seq) return;
      if (!found.pages.length) { S.busy = null; S.busyMode = null; return note('pages.none.named', { name, country: region(S.country) }); }
      sides.push({ name, pages: found.pages, suggested: found.suggested_page_id,
        picked: found.pages.length === 1 ? found.pages[0].page_id : null });
    }
    if (S.searchSeq !== seq) return;
    S.busy = null; S.busyMode = null; S.cmp = { sides };
    if (sides.every((side) => side.picked)) {
      if (sides[0].picked === sides[1].picked) { S.cmp = null; return note('error.same_page', null, true); }
      return launchCompare();
    }
    render();
  } catch (error) { if (S.searchSeq === seq) { S.busy = null; S.busyMode = null; note('error.title', null, true); } }
}
function launchCompare() {
  if (!S.cmp || !S.cmp.sides || S.cmp.sides.length < 2) return;
  const [first, second] = S.cmp.sides;
  if (first.picked === second.picked) { S.cmp = null; return note('error.same_page', null, true); }
  S.pending = { mode: 'compare', page_id: first.picked, page_id_b: second.picked, country: S.country, fresh: false };
  S.cmp = null;
  return launch();
}

/* ---------- what changed ---------- */
const stamp = (iso) => (iso ? `${day(iso)}, ${clock(iso)}` : '—');
function adCell(ad, keyword) {
  return `<div class="adcell">${ad.thumbnail ? mediaImg(ad.thumbnail, 'thumb', '', true) : '<span class="thumb"></span>'}
    <div class="adtext"><div><a href="${esc(ad.ad_url)}" target="_blank" rel="noopener">${esc(ad.opening || t('t.notext'))}</a></div>
    <small>${esc([keyword ? ad.advertiser : t(`format.${ad.media_type || 'unknown'}`), ad.cta].filter(Boolean).join(' · '))}</small></div></div>`;
}
function newsList(title, ads, keyword, extraHead, extraCell) {
  const body = ads.length ? `<div class="table-scroll"><table class="ads"><thead><tr><th>${esc(t('t.ad'))}</th>${extraHead}<th class="r">${esc(t('news.started'))}</th><th class="r">${esc(t('news.ran'))}</th><th class="r">${esc(t('t.score'))}</th></tr></thead>
    <tbody>${ads.map((ad) => `<tr><td>${adCell(ad, keyword)}</td>${extraCell(ad)}<td class="r">${ad.started ? esc(day(ad.started)) : '—'}</td><td class="r">${num(ad.days_running)}</td><td class="r">${(ad.score ?? ad.longevity_score) == null ? '—' : Math.round(ad.score ?? ad.longevity_score)}</td></tr>`).join('')}</tbody></table></div>`
    : `<p class="muted">${esc(t('news.none'))}</p>`;
  return `<section><div class="listhead"><h2>${esc(title)}</h2><span>${ads.length}</span></div>${body}</section>`;
}
function jsDriftBar(d) {
  const stKey = `news.drift.state.${d.state}`;
  const stateLbl = hasT(stKey) ? t(stKey) : (d.state || '');
  const gains = (d.top_gainers || []).map((g) => `${region(g.country)} ${g.age_range} ${genderLabel(g.gender)} (+${Math.round(g.delta * 100)}pp)`).join(', ');
  return `<section class="js-drift-bar">
    <strong>${esc(t('news.drift.title'))}</strong>
    <small>${esc(t('news.drift.meta', { dist: num(d.js_distance), state: stateLbl, days: num(d.days_between), n: num(d.snapshots_with_audience) }))}${gains ? ` · ${esc(t('news.drift.gainers', { list: gains }))}` : ''}</small>
  </section>`;
}
function newsDetail(c) {
  const keyword = c.subject.mode === 'keyword';
  const title = keyword ? t('result.keyword', { query: c.subject.label, country: region(c.subject.country) }) : `${c.subject.label} · ${region(c.subject.country)}`;
  const cells = [
    [c.counts.new, t('news.new'), `${t('news.new.x')} ${t('news.new.texts', { n: c.counts.new_texts })}`],
    [c.counts.stopped, t('news.stopped'), t('news.stopped.x')],
    [c.counts.changed, t('news.changed'), t('news.changed.x')],
  ];
  const what = (ad) => `<td>${ad.fields.map((f) => esc(t(`field.${f}`))).join(', ')}${ad.before.opening && ad.fields.includes('text') ? `<span class="was">${esc(t('news.before', { value: ad.before.opening }))}</span>` : ''}</td>`;
  const kind = (ad) => `<td class="dim">${esc(t(ad.new_text ? 'news.newtext' : 'news.reused'))}</td>`;
  return `<div class="sheet">
    <section class="rhead"><div class="grow"><h1>${esc(title)}</h1><p>${esc(t('news.span', { from: stamp(c.previous.taken_at), to: stamp(c.current.taken_at), gap: c.days_between < 1 ? oneOrMore('gap.hours', Math.max(1, Math.round(c.days_between * 24))) : days(Math.round(c.days_between)) }))}</p></div>
      <div class="rlinks"><button class="linklike" data-action="news-refresh" data-value="${esc(c.subject.key)}">${esc(t('news.refresh'))}</button></div></section>
    <section class="metrics three">${cells.map(([value, label, why]) => `<div class="metric"><div class="metric-head"><span class="metric-lbl">${esc(label)}</span></div><b>${num(value)}</b><small>${esc(why)}</small></div>`).join('')}</section>
    ${c.sample ? `<section><p class="muted">${esc(t('news.sample'))}</p></section>` : ''}
    ${c.subject && c.subject.mode === 'company' && c.ritmo ? ritmoSection({ mode: 'company', ritmo: c.ritmo, page: { page_id: c.subject.page_id }, country: c.subject.country }, true) : ''}
    ${c.audience_drift && c.audience_drift.measurable ? jsDriftBar(c.audience_drift) : ''}
    ${newsList(t('news.new'), c.new, keyword, '<th></th>', kind)}
    ${newsList(t('news.stopped'), c.stopped, keyword, '', () => '')}
    ${newsList(t('news.changed'), c.changed, keyword, `<th>${esc(t('news.what'))}</th>`, what)}
  </div>`;
}
function renderNews() {
  const el = $('#results');
  if (!S.history) { el.innerHTML = ''; return; }
  if (!S.history.length) { el.innerHTML = `<div class="sheet"><section><p class="muted">${esc(t('news.empty'))}</p></section></div>`; return; }
  const rows = S.history.map((row) => `<tr>
    <td>${esc(row.label)}</td><td>${esc(t(`news.kind.${row.mode}`))}</td><td>${esc(region(row.country))}</td>
    <td class="r">${row.snapshots}</td><td class="r">${esc(stamp(row.last_taken_at))}</td>
    <td class="r">${row.snapshots > 1 ? `<button class="btn small${S.news && S.news.subject.key === row.key ? '' : ' quiet'}" data-action="news-open" data-value="${esc(row.key)}">${esc(t('news.view'))}</button>` : `<span class="dim">${esc(t('news.second'))}</span>`}</td>
    <td class="r"><button class="btn quiet small" data-action="news-refresh" data-value="${esc(row.key)}">${esc(t('news.refresh'))}</button></td></tr>`).join('');
  el.innerHTML = `<div class="sheet"><section><h2 style="margin-bottom:18px">${esc(t('news.saved'))}</h2><div class="table-scroll"><table>
    <thead><tr><th>${esc(t('news.subject'))}</th><th>${esc(t('news.kind'))}</th><th>${esc(t('field.country'))}</th><th class="r">${esc(t('news.count'))}</th><th class="r">${esc(t('news.last'))}</th><th></th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></div></section></div>${S.news ? newsDetail(S.news) : ''}`;
}
async function loadHistory() {
  try { S.history = (await api('/api/history')).subjects; } catch { S.history = []; }
  if (S.mode === 'news') renderResults();
}
async function openNews(key) {
  const seq = ++S.newsSeq;
  S.mode = 'news'; S.pages = null; S.notice = null; S.overlay = null;
  render();
  await loadHistory();
  if (S.newsSeq !== seq || S.mode !== 'news') return;
  try { S.news = await api(`/api/history/changes?key=${encodeURIComponent(key)}`); } catch { S.news = null; }
  if (S.newsSeq !== seq || S.mode !== 'news') return;
  if (S.news && !S.news.available) S.news = null;
  renderResults();
}
function refreshSubject(key) {
  const row = (S.history || []).find((item) => item.key === key) || (S.news && S.news.subject);
  if (!row) return;
  S.mode = row.mode; S.country = row.country; S.news = null;
  if (row.mode === 'keyword') S.query = row.label; else S.company = row.label;
  render();
  gate(row.mode === 'keyword' ? { mode: 'keyword', query: row.query || row.label, fresh: true }
    : { mode: 'company', page_id: row.page_id, fresh: true });
}

/* ---------- drawer: one ad ---------- */
function adDrawer(ad, r) {
  const points = ad.score_points || { scale: 0, staying: 0, creative: 0 };
  const weights = ad.score_weights || { scale: 60, staying: 25, creative: 15 };
  const where = region(r.country);
  const rateDays = ad.reach_days ?? Math.max(ad.ad_days ?? ad.days_running ?? 0, 7);
  const cardsNoteText = cardsNote(ad);
  const ageNote = ad.ad_days != null && ad.days_running != null && ad.days_running - ad.ad_days >= 30
    ? t('d.concept.age', { days: days(ad.days_running), ad: days(ad.ad_days) }) : '';
  const scaleWhy = ad.scale_basis === 'reach' ? t('d.scale.reach', { n: num(ad.reach_per_day), country: where, total: num(ad.reach_total) })
    : ad.reach_per_day_estimate != null ? t('d.scale.estimate', { n: num(ad.reach_per_day_estimate), rank: num(ad.impression_rank) })
    : ad.scale_basis === 'impressions' ? t('d.scale.impressions', { n: num(ad.impression_rank) }) : t('d.scale.none');
  const reach = ad.reach, audience = ad.audience;
  const places = (list, limit) => placeNames(list || [], null, (list || []).length, limit);
  let reachHtml;
  if (!reach) reachHtml = `<p class="muted">${esc(t('d.reach.unread'))}</p>`;
  else if (!reach.available) reachHtml = `<p class="muted">${esc(t('d.reach.none'))}</p>`;
  else {
    const countries = (reach.regions || []).flatMap((g) => g.countries || []).sort((a, b) => b.reach - a.reach).slice(0, 8);
    reachHtml = `<dl>
      ${ad.reach_total != null ? `<dt>${esc(t('d.reach.country', { country: where }))}</dt><dd>${num(ad.reach_total)}</dd>
      <dt>${esc(t('d.reach.perday', { country: where }))}</dt><dd>${num(ad.reach_per_day)}${(ad.reach_cards_read || 1) > 1 ? '' : ` <span class="muted">· ${esc(t('d.reach.perday.x', { total: num(ad.reach_total), days: days(rateDays) }))}</span>`}</dd>` : ''}
      ${reach.eu_total != null ? `<dt>${esc(t('d.reach.total'))}</dt><dd>${num(reach.eu_total)}</dd>` : ''}
      ${reach.uk_total != null ? `<dt>${esc(t('d.reach.uk'))}</dt><dd>${num(reach.uk_total)}</dd>` : ''}</dl>
      ${ad.reach_in_market === false ? `<p class="smallnote">${esc(t('d.reach.elsewhere'))}</p>` : ''}
      ${ad.reach_total === 0 ? `<p class="smallnote">${esc(t('d.reach.zero', { country: where }))}</p>` : ''}
      ${cardsNoteText ? `<p class="smallnote">${esc(cardsNoteText)}</p>` : ''}
      ${ad.reach_total ? `<p class="smallnote">${esc(t('d.reach.unique'))}</p>` : ''}
      ${countries.length > 1 ? `<h3 style="margin-top:16px">${esc(t('d.reach.bycountry'))}</h3><ul class="rows">${countries.map((c) => `<li><span>${esc(region(c.country))}</span><span>${num(c.reach)}</span></li>`).join('')}</ul>` : ''}`;
  }
  const review = ad.needs_review ? `<p class="review" style="margin-top:12px;font-size:1rem">${esc(t(ad.review && ad.review.basis === 'impressions' ? 'd.review.impressions' : 'd.review'))}</p>` : '';
  const recent = ad.too_recent ? `<p class="review" style="margin-top:12px;font-size:1rem">${esc(t('d.recent', { days: days(ad.days_running) }))}</p>` : '';
  const isVideo = ad.media_type === 'video' && /^\d{5,25}$/.test(String(ad.library_id || ''));
  const vi = isVideo ? S.videoInspect[ad.library_id] : null;
  let vidHtml = '';
  if (isVideo) {
    let viBody = '';
    if (vi && vi.loading) {
      viBody = `<div class="progress" style="margin-top:10px;padding-top:10px"><p><span>${esc(t('vid.loading'))}</span></p><div class="bar open"><i></i></div></div>`;
    } else if (vi && (vi.err || (vi.data && !vi.data.ok))) {
      viBody = `<p class="notice err" style="margin-top:10px;padding-top:10px">${esc((vi.data && vi.data.note) || t('vid.err'))}</p>`;
    } else if (vi && vi.data && vi.data.ok) {
      const vd = vi.data;
      const durTxt = vd.duration != null ? `${num(Math.round(vd.duration * 10) / 10)} s` : '—';
      const sheets = [
        vd.hook_sheet ? `<div class="vid-sheet-card"><strong>${esc(t('vid.hook'))}</strong>${mediaImg(vd.hook_sheet, 'vid-sheet-img', t('vid.hook'))}</div>` : '',
        vd.body_sheet ? `<div class="vid-sheet-card"><strong>${esc(t('vid.body'))}</strong>${mediaImg(vd.body_sheet, 'vid-sheet-img', t('vid.body'))}</div>` : '',
      ].filter(Boolean).join('');
      viBody = `<p class="smallnote" style="margin-top:8px">${esc(t('vid.meta', { dur: durTxt, ratio: vd.aspect_ratio || '—' }))}</p>
        ${sheets ? `<div class="vid-sheets">${sheets}</div>` : ''}`;
    }
    vidHtml = `<section class="vid-inspect-box"><div class="vid-inspect-head"><h3>${esc(t('vid.title'))}</h3>
      <button type="button" class="btn quiet small" data-action="video-inspect" data-value="${esc(ad.library_id)}" ${vi && vi.loading ? 'disabled' : ''}>${esc(t('vid.btn'))}</button>
      </div>${viBody}</section>`;
  }
  return `<aside class="drawer" role="dialog" aria-modal="true"><header><h2>${esc(ad.advertiser || '')}</h2><div class="drawer-nav"><button type="button" class="btn quiet small" data-action="ad-step" data-value="-1" aria-label="Previous">&larr;</button><button type="button" class="btn quiet small" data-action="ad-step" data-value="1" aria-label="Next">&rarr;</button></div><button class="x" data-action="close">${esc(t('button.close'))}</button></header><div class="body">
    <section><div class="hero">${ad.thumbnail ? mediaImg(ad.thumbnail, '', '') : ''}<div>
      <p><strong>${esc(ad.status === 'inactive' ? t('d.inactive') : t('d.active', { date: ad.started ? day(ad.started) : '—' }))}</strong></p>
      <p class="muted">${esc(days(ad.days_running))} · ${esc(t(`format.${ad.media_type || 'unknown'}`))}</p>
      ${ad.impression_rank ? `<p class="muted">${esc(t('d.rank', { n: ad.impression_rank }))}</p>` : ''}
      <p style="margin-top:10px"><a href="${esc(ad.ad_url)}" target="_blank" rel="noopener">${esc(t('link.meta'))}</a></p></div></div></section>
    ${vidHtml}
    <section><h3>${esc(t('d.score', { score: Math.round(ad.score) }))} · ${esc(t(`verdict.${ad.verdict}`))}${scoreScalePop(true)}</h3>
      <div class="scorebar three">${['scale', 'staying', 'creative'].map((part) => `<i style="width:${points[part]}%"></i>`).join('')}</div>
      <dl>
        <dt>${esc(t('d.part.scale'))}</dt><dd>${esc(t('d.score.of', { n: num(Math.round(points.scale)), max: weights.scale }))} <span class="muted">· ${esc(scaleWhy)}</span></dd>
        <dt>${esc(t('d.part.staying'))}</dt><dd>${esc(t('d.score.of', { n: num(Math.round(points.staying)), max: weights.staying }))} <span class="muted">· ${esc(t('d.staying.days', { days: days(ad.days_running) }))}</span></dd>
        <dt>${esc(t('d.part.creative'))}</dt><dd>${esc(t('d.score.of', { n: num(Math.round(points.creative)), max: weights.creative }))} <span class="muted">· ${esc(oneOrMore('d.creative.n', ad.creatives))}</span></dd>
      </dl>
      <p class="smallnote">${esc(t(`reliability.${ad.reliability}.x`))}</p>${ageNote ? `<p class="smallnote">${esc(ageNote)}</p>` : ''}${review}${recent}
      <h3 style="margin-top:18px">${esc(t('d.variants'))}</h3>
      <dl><dt>${esc(t('d.variants.cards'))}</dt><dd>${num(ad.cards)}</dd>
        <dt>${esc(t('d.variants.copies'))}</dt><dd>${num(ad.copies_total)}</dd>
        ${(ad.languages || []).length > 1 ? `<dt>${esc(t('d.variants.languages'))}</dt><dd>${ad.languages.map((code) => esc(named('language', code))).join(', ')}</dd>` : ''}
        ${ad.products ? `<dt>${esc(t('d.variants.products'))}</dt><dd>${num(ad.products)}</dd>` : ''}</dl>
      ${ad.kind && ad.kind !== 'standard' ? `<p class="smallnote">${esc(t(`d.kind.${ad.kind}`))}</p>` : ''}
      <p class="smallnote">${esc(t('d.longevity', { n: ad.longevity_score != null ? Math.round(ad.longevity_score) : '—' }))}</p>
      <p style="margin-top:12px"><button class="linklike" data-action="guide">${esc(t('link.guide'))}</button></p></section>
    <section><h3>${esc(t('d.text'))}</h3><p class="copy">${esc(ad.body || t('t.notext'))}</p>
      <dl style="margin-top:14px">${ad.headline ? `<dt>${esc(t('d.headline'))}</dt><dd>${esc(ad.headline)}</dd>` : ''}
      <dt>${esc(t('d.button'))}</dt><dd>${esc(ad.cta || '—')}</dd><dt>${esc(t('d.dest'))}</dt><dd>${esc(ad.landing_domain || '—')}</dd>
      <dt>${esc(t('d.platforms'))}</dt><dd>${(ad.platforms || []).map((p) => esc(PLATFORMS[p] || p)).join(', ') || '—'}</dd></dl></section>
    <section><h3>${esc(t('d.reach'))}</h3>${reachHtml}</section>
    ${audience ? `<section><h3>${esc(t('d.audience'))}</h3><dl>
      <dt>${esc(t('f.audience.age'))}</dt><dd>${esc(ageRange(audience.age_min, audience.age_max))}</dd>
      <dt>${esc(t('f.audience.gender'))}</dt><dd>${esc(t(`gender.${audience.gender || 'All'}`))}</dd>
      <dt>${esc(t('f.places.in'))}</dt><dd>${places(audience.locations_included, 8)}</dd>
      <dt>${esc(t('f.places.out'))}</dt><dd>${places(audience.locations_excluded, 3)}</dd></dl>
      <p class="smallnote">${esc(t('f.places.note'))}</p></section>` : ''}
    ${(ad.frames || []).length ? `<section><h3>${esc(t('d.frames'))}</h3><div class="frames">${ad.frames.map((src) => mediaImg(src, '', '')).join('')}</div></section>` : ''}
  </div></aside>`;
}
function guideDrawer() {
  const items = [1, 2, 3, 4, 5, 6, 7, 8].map((n) => `<section class="qa"><h3>${esc(t(`guide.q${n}`))}</h3><p>${esc(t(`guide.a${n}`))}</p>${n === 3 ? `<p class="eg muted">${esc(t('guide.example'))}</p>` : ''}</section>`).join('');
  return `<aside class="drawer" role="dialog" aria-modal="true"><header><h2>${esc(t('guide.title'))}</h2><button class="x" data-action="close">${esc(t('button.close'))}</button></header><div class="body">${items}</div></aside>`;
}

/* ---------- dialogs ---------- */
function confirmDialog() {
  const e = S.estimate || {};
  return `<div class="dialog" role="dialog" aria-modal="true"><h2>${esc(t('confirm.title'))}</h2>
    <div class="use">
      <div><span class="k">${esc(t('confirm.data'))}</span><span>${esc(t('confirm.data.x'))}</span></div>
      <div><span class="k">${esc(t(`level.${S.level}`))}</span><span>${esc(t('confirm.ai.x'))}</span></div>
      <div><span class="k">${esc(t('confirm.ads'))}</span><span class="v"><span class="switch" role="group">${toggle('deep', S.deepChoices, S.deep, String)}</span></span></div>
      <div><span class="k">${esc(t('confirm.opened'))}</span><span class="v">${esc(t('confirm.opened.v', { n: num(e.ceiling ?? S.deep * 2) }))}</span></div>
      <div><span class="k">${esc(t('confirm.frames'))}</span><span class="v"><label class="check"><input type="checkbox" data-change="frames" ${S.frames ? 'checked' : ''}>${esc(t('confirm.frames.on'))}</label><span class="muted">${esc(count(e.images ?? 0, 'n.images'))}</span></span></div>
      <div><span class="k">${esc(t('confirm.tokens'))}</span><span class="v">${esc(t('confirm.tokens.v', { n: num(e.tokens ?? 0) }))}</span></div>
      <div><span class="k">${esc(t('confirm.band'))}</span><span class="v big">${esc(e.band && hasT(`band.${e.band}`) ? t(`band.${e.band}`) : '—')}</span></div>
      <div><span class="k">${esc(t('confirm.time'))}</span><span class="v">${e.seconds ? esc(t('confirm.time.v', { time: dur(e.seconds) })) : '—'}</span></div>
    </div>
    <p class="smallnote">${esc(t('confirm.note'))}</p>
    <div class="foot"><button class="btn quiet" data-action="close">${esc(t('button.back'))}</button><button class="btn" data-action="confirm-go">${esc(t('confirm.go'))}</button></div></div>`;
}
function projectDialog(overlay) {
  const p = overlay.draft, errors = overlay.errors || {};
  const field = (name, key, body, full) => `<label class="field${full ? ' full' : ''}${errors[name] ? ' bad' : ''}"><span>${esc(t(key))}</span>${body}${errors[name] ? `<em>${esc(t(`proj.err.${errors[name]}`))}</em>` : ''}</label>`;
  const input = (name, hint) => `<input type="text" data-pf="${name}" value="${esc(p[name] ?? '')}" placeholder="${esc(hint ? t(hint) : '')}" autocomplete="off">`;
  const goalPeriods = [t('proj.goal.day'), t('proj.goal.week'), t('proj.goal.month')];
  const savedPeriod = overlay.goalPeriod || goalPeriods[0];
  const goalInput = `<div style="display:flex;gap:8px">${input('goal', 'proj.goal.hint')}<select id="goal-period" style="width:170px;flex:none" aria-label="${esc(t('proj.goal'))}">
    ${goalPeriods.map((opt) => `<option value="${esc(opt)}"${opt === savedPeriod ? ' selected' : ''}>${esc(opt)}</option>`).join('')}</select></div>`;
  const optFields = ['vat_pct', 'shipping_cost', 'payment_fee_pct', 'payment_fee_fixed', 'return_rate_pct', 'other_costs'];
  const openExtra = optFields.some((k) => (p[k] !== undefined && p[k] !== null && String(p[k]).trim() !== '') || errors[k]);
  return `<div class="dialog" role="dialog" aria-modal="true"><h2>${esc(t('proj.title'))}</h2><p class="lead">${esc(t('proj.lead'))}</p>
    <div class="form">
      ${field('product', 'proj.product', input('product'), true)}
      ${field('price', 'proj.price', input('price'))}
      ${field('product_cost', 'proj.cost', input('product_cost'))}
      <p class="full smallnote" style="margin-top:-6px">${esc(t('proj.costs.note'))}</p>
      ${field('market', 'proj.market', `<select data-pf="market">${countryOptions(p.market || S.country)}</select>`)}
      ${field('goal', 'proj.goal', goalInput)}
      ${field('main_problem', 'proj.problem', input('main_problem', 'proj.problem.hint'), true)}
      <details class="proj-extra"${openExtra ? ' open' : ''}>
        <summary>${esc(t('proj.opt.title'))}</summary>
        <div class="proj-extra-grid">
          ${field('vat_pct', 'proj.opt.vat', input('vat_pct'))}
          ${field('shipping_cost', 'proj.opt.ship', input('shipping_cost'))}
          ${field('payment_fee_pct', 'proj.opt.fee_pct', input('payment_fee_pct'))}
          ${field('payment_fee_fixed', 'proj.opt.fee_fix', input('payment_fee_fixed'))}
          ${field('return_rate_pct', 'proj.opt.ret', input('return_rate_pct'))}
          ${field('other_costs', 'proj.opt.other', input('other_costs'))}
        </div>
      </details>
    </div>
    <div class="foot"><button class="btn quiet" data-action="close">${esc(t('button.back'))}</button><button class="btn" data-action="save-project">${esc(t('button.save'))}</button></div></div>`;
}
function briefDialog(overlay) {
  const made = overlay.made;
  const choices = S.deepChoices.filter((n) => n <= made.collected.ads);
  const frames = made.collected.frames
    ? `<label class="check"><input type="checkbox" data-change="brief-frames" ${made.frames ? 'checked' : ''}>${esc(t('confirm.frames.on'))}</label>`
    : `<span class="muted">${esc(t('brief.frames.none'))}</span>`;
  /* The text itself is never shown: the user copies it, and the stills open in their own folder. */
  const stills = made.images.length && made.frames_key
    ? `<div><span class="k">${esc(t('brief.stills'))}</span><span class="v"><span>${esc(count(made.images.length, 'brief.stills.v'))}</span>
        <button class="btn quiet small" data-action="open-frames">${esc(t('button.frames'))}</button></span></div>` : '';
  const status = overlay.status || {};
  return `<div class="dialog wide" role="dialog" aria-modal="true"><h2>${esc(t(`brief.title.${made.level}`))}</h2><p class="lead">${esc(t('brief.how'))}</p>
    <div class="use tight">
      <div><span class="k">${esc(t('brief.ads'))}</span><span class="v">${choices.length > 1 ? `<span class="switch" role="group">${toggle('brief-ads', choices, made.ads, String)}</span>` : num(made.ads)}</span></div>
      <div><span class="k">${esc(t('brief.frames'))}</span><span class="v">${frames}</span></div>${stills}
      <div><span class="k">${esc(t('confirm.band'))}</span><span class="v">${esc(t('brief.size', { n: num(made.size.tokens), band: t(`band.${made.size.band}`).toLowerCase() }))}</span></div>
    </div>
    <h3 class="sub">${esc(t('brief.code'))}</h3><p class="smallnote" style="margin-top:4px">${esc(t('brief.code.x'))}</p>
    <div class="cmdline"><p class="command">${esc(t(`brief.command.${made.level}`, { folder: made.folder_name }))}</p>
      <button class="btn quiet small" data-action="copy-command">${esc(t('button.copy.command'))}</button></div>
    <p class="status${status.err ? ' err' : ''}" role="status" aria-live="polite">${esc(status.text || '')}</p>
    <div class="foot"><button class="btn quiet" data-action="close">${esc(t('button.close'))}</button><button class="btn" data-action="copy-brief">${esc(t('button.copy'))}</button></div></div>`;
}
/* Copy to the clipboard; where the clipboard API is missing or refused, a hidden
   text box and the older copy command do it. Returns whether the copy went through. */
async function copyText(text) {
  try {
    if (navigator.clipboard && navigator.clipboard.writeText) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* fall back below */ }
  const box = document.createElement('textarea');
  box.value = text;
  box.setAttribute('readonly', '');
  box.setAttribute('aria-hidden', 'true');
  box.className = 'offscreen';
  document.body.appendChild(box);
  box.select();
  let done = false;
  try { done = document.execCommand('copy'); } catch { done = false; }
  box.remove();
  return done;
}
function briefStatus(text, err) {
  if (!S.overlay || S.overlay.type !== 'brief') return;
  S.overlay.status = { text, err };
  renderOverlay();
}
function tutorialDialog(overlay) {
  const tab = Number(overlay.tab || 1);
  const tabs = [1, 2, 3, 4, 5, 6].map((n) => `<button data-action="tut-tab" data-value="${n}" aria-selected="${n === tab}">${esc(t(`tut.t${n}`))}</button>`).join('');
  const intro = `<div class="tut-intro">${esc(t(`tut.${tab}.intro`))}</div>`;
  const shotMap = {
    1: '<img src="/docs/images/results-summary.png" alt="">',
    2: '<img src="/docs/images/levels.png" alt="">',
    3: '<img src="/docs/images/usage-estimate.png" alt="">',
    4: '<div class="tut-shot-pair"><img src="/docs/images/results-table.png" alt=""><img src="/docs/images/ad-panel.png" alt=""></div>',
    6: '<img src="/docs/images/brief-dialog.png" alt="">',
  };
  const shot = shotMap[tab] ? `<figure class="tut-shot">${shotMap[tab]}<figcaption>${esc(t(`tut.${tab}.cap`))}</figcaption></figure>` : '';
  let body = '';
  if (tab === 5) {
    const kpiCard = (k) => `<div class="tut-card"><strong>${esc(t(`kpi.${k}.t`))}</strong><span class="tut-formula">${esc(t(`kpi.${k}.f`))}</span><p>${esc(t(`kpi.${k}.d`))}</p></div>`;
    body = `<h4 class="kpi-group-title">${esc(t('kpi.g1'))}</h4>
      <div class="kpi-grid">${[1, 2, 3, 4, 5, 6, 7, 8].map(kpiCard).join('')}</div>
      <h4 class="kpi-group-title">${esc(t('kpi.g2'))}</h4>
      <div class="kpi-grid">${[9, 10, 11, 12].map(kpiCard).join('')}</div>`;
  } else {
    body = `${shot}<div class="tut-cards">${[1, 2, 3, 4].map((c) => `<div class="tut-card">
      <strong>${esc(t(`tut.${tab}.c${c}.t`))}</strong>
      <span class="tut-formula">${esc(t(`tut.${tab}.c${c}.f`))}</span>
      <p>${esc(t(`tut.${tab}.c${c}.d`))}</p>
      <div class="tut-tip">${esc(t(`tut.${tab}.c${c}.tip`))}</div>
    </div>`).join('')}</div>`;
  }
  return `<div class="dialog xl" role="dialog" aria-modal="true"><h2>${esc(t('tut.title'))}</h2><p class="lead">${esc(t('tut.lead'))}</p>
    <div class="tut-tabs" role="tablist">${tabs}</div>
    ${intro}${body}
    <div class="foot">
      ${tab > 1 ? `<button class="btn quiet" data-action="tut-tab" data-value="${tab - 1}">${esc(t('how.prev'))}</button>` : ''}
      ${tab < 6 ? `<button class="btn" data-action="tut-tab" data-value="${tab + 1}">${esc(t('how.next'))}</button>` : `<button class="btn" data-action="close">${esc(t('button.close'))}</button>`}
    </div></div>`;
}
function renderOverlay() {
  const overlay = S.overlay, el = $('#overlay');
  if (!overlay) { el.innerHTML = ''; return; }
  let inner = '';
  if (overlay.type === 'ad') {
    const ad = findAd(overlay.id);
    inner = ad ? adDrawer(ad, S.result) : '';
  } else if (overlay.type === 'guide') inner = guideDrawer();
  else if (overlay.type === 'confirm') inner = confirmDialog();
  else if (overlay.type === 'project') inner = projectDialog(overlay);
  else if (overlay.type === 'brief') inner = briefDialog(overlay);
  else if (overlay.type === 'link-confirm') inner = linkDialog(overlay);
  else if (overlay.type === 'how') inner = howDialog(overlay);
  else if (overlay.type === 'tutorial') inner = tutorialDialog(overlay);
  if (!inner) { S.overlay = null; el.innerHTML = ''; return; }
  el.innerHTML = `<div class="scrim" data-action="close"></div>${inner}`;
  hydrateMcpImages();
}
function render() { renderTop(); renderSearch(); renderResults(); renderOverlay(); }

/* ---------- actions ---------- */
async function refreshEstimate() {
  const seq = ++S.estSeq;
  try {
    const est = await api(`/api/estimate?level=${S.level}&ads=${S.deep}&frames=${S.frames && S.level !== 'data' ? 1 : 0}`);
    if (S.estSeq !== seq) return;
    S.estimate = est;
  } catch { if (S.estSeq !== seq) return; S.estimate = null; }
  const searchEl = $('#search');
  const typingInSearch = Boolean(searchEl && document.activeElement && searchEl.contains(document.activeElement)
    && document.activeElement.matches && document.activeElement.matches('input, textarea, select'));
  if (!S.job && !S.busy && !typingInSearch) renderSearch();
  if (S.overlay && S.overlay.type === 'confirm') renderOverlay();
}
function note(key, vars, err) { S.notice = { key, vars, err }; render(); }

async function submit() {
  S.notice = null; S.searchExpandedManual = false; S.wayHint = false;
  if (S.mode === 'compare') return submitCompare();
  if (S.mode === 'keyword') {
    if (!S.query.trim()) return note('error.input', null, true);
    return gate({ mode: 'keyword', query: S.query.trim() });
  }
  if (!S.company.trim()) return note('error.input', null, true);
  const seq = ++S.searchSeq;
  S.pages = null; S.result = null; S.resultMode = null; S.busy = 'pages'; S.busyMode = 'company'; render();
  try {
    const found = await api(`/api/pages?name=${encodeURIComponent(S.company.trim())}&country=${S.country}`);
    if (S.searchSeq !== seq) return;
    S.busy = null; S.busyMode = null;
    if (!found.pages.length) return note('pages.none', { country: region(S.country) });
    if (found.pages.length === 1) { render(); return gate({ mode: 'company', page_id: found.pages[0].page_id }); }
    S.pages = found; render();
    window.scrollTo({ top: 0, behavior: 'instant' });
  } catch (error) { if (S.searchSeq === seq) { S.busy = null; S.busyMode = null; note('error.title', null, true); } }
}
function gate(request) {
  S.searchExpandedManual = false;
  S.pending = { fresh: false, ...request, country: S.country };
  if (S.level === 'plan' && !S.project) return openProject(true);
  if (S.level !== 'data') { S.overlay = { type: 'confirm' }; renderOverlay(); return refreshEstimate(); }
  return launch();
}
async function launch() {
  const seq = ++S.searchSeq;
  S.overlay = null; S.pages = null; S.result = null; S.resultMode = null; S.notice = null;
  S.searchExpandedManual = false;
  _resetViewFilters();
  S.aiSeq++;
  try {
    S.job = await api('/api/jobs', { method: 'POST', body: { ...S.pending, level: S.pending.mode === 'compare' ? 'data' : S.level, deep: S.deep, frames: S.frames } });
  } catch (error) {
    if (S.searchSeq !== seq) return;
    if (error.data && error.data.error === 'project_required') return openProject(true);
    return note('error.title', null, true);
  }
  if (S.searchSeq !== seq) return;
  render();
  while (S.job && S.job.status === 'running' && S.searchSeq === seq) {
    await sleep(700);
    if (S.searchSeq !== seq || !S.job) break;
    try { S.job = await api(`/api/jobs/${S.job.id}`); } catch { break; }
    if (S.searchSeq !== seq) break;
    updateProgress();
  }
  if (S.searchSeq !== seq) return;
  const job = S.job; S.job = null;
  if (!job || job.status !== 'done') return note('error.title', null, true);
  const found = job.result.sides ? job.result.sides.every((side) => (side.ads || []).length) : (job.result.ads || []).length;
  if (!found) {
    const blocked = job.result.sides
      ? job.result.sides.some((side) => side.outcome === 'blocked')
      : job.result.outcome === 'blocked';
    return note(`error.${blocked ? 'blocked' : 'no_results'}`);
  }
  S.result = job.result; S.result._live = true; S.resultMode = job.params.mode; S.jobId = job.id;
  S.tab = 'overview';
  S.stratLevel = (job.params.level === 'plan') ? 'plan' : 'analysis';
  render();
  window.scrollTo({ top: 0, behavior: 'instant' });
}
function setTab(tab) {
  if (!STUDIO_TABS.includes(tab) || !hasModeResult()) return;
  S.tab = tab; S.stratNeedProject = false;
  renderResults();
}
function stepAd(delta) {
  if (!S.overlay || S.overlay.type !== 'ad' || !S.result) return;
  const list = S.result.sides ? S.result.sides.flatMap((side) => side.ads) : filteredAds(S.result);
  if (!list.length) return;
  const idx = list.findIndex((item) => item.library_id === S.overlay.id);
  const nextIdx = idx < 0 ? 0 : (idx + delta + list.length) % list.length;
  S.overlay = { type: 'ad', id: list[nextIdx].library_id };
  renderOverlay();
}
async function runVideoInspect(adId) {
  if (!adId || (S.videoInspect[adId] && S.videoInspect[adId].loading)) return;
  S.videoInspect[adId] = { loading: true, data: null, err: false };
  renderOverlay();
  try {
    const data = await api('/api/video/inspect', { method: 'POST', body: { ad_id: adId } });
    S.videoInspect[adId] = { loading: false, data, err: false };
  } catch {
    S.videoInspect[adId] = { loading: false, data: null, err: true };
  }
  renderOverlay();
}
async function runAi() {
  const r = S.result;
  if (!r || !S.jobId) return;
  const level = S.stratLevel === 'plan' ? 'plan' : 'analysis';
  if (level === 'plan' && !S.project) { S.stratNeedProject = true; renderResults(); return; }
  const seq = ++S.aiSeq;
  S.stratNeedProject = false; S.aiElapsed = 0; S.aiCopied = false;
  const t0 = performance.now();
  const token = newToken();
  const adsCount = (r.request && r.request.deep) || S.deep;
  const useFrames = Boolean(r.request && r.request.frames);
  try {
    S.aiJob = await api('/api/ai/run', {
      method: 'POST',
      headers: { 'X-Run-Token': token },
      body: { token, job_id: S.jobId, level, ads: adsCount, frames: useFrames, lang: S.lang },
    });
  } catch (error) {
    if (S.aiSeq !== seq) return;
    if (error.data && error.data.error === 'project_required') { S.stratNeedProject = true; renderResults(); return; }
    S.aiJob = { status: 'error', error: (error.data && error.data.error) || 'command_failed', detail: error.message };
    renderResults();
    return;
  }
  if (S.aiSeq !== seq) return;
  renderResults();
  while (S.aiJob && S.aiJob.status === 'running' && S.aiSeq === seq) {
    await sleep(700);
    if (S.aiSeq !== seq || !S.aiJob) break;
    try { S.aiJob = await api(`/api/ai/jobs/${S.aiJob.id}`); } catch { break; }
    if (S.aiSeq !== seq) break;
    if (S.aiJob && S.aiJob.status === 'running') {
      S.aiElapsed = Math.round((performance.now() - t0) / 1000);
      const el = $('#ai-elapsed');
      if (el) el.textContent = `${S.aiElapsed} s`;
    }
  }
  if (S.aiSeq === seq && S.tab === 'strategy') renderResults();
}
async function sendMcpAi() {
  const r = S.result;
  if (!r || !mcpApp) return;
  const level = S.stratLevel === 'plan' ? 'plan' : 'analysis';
  if (level === 'plan' && !S.project) { S.stratNeedProject = true; renderResults(); return; }
  S.stratNeedProject = false;
  const safeQuery = String(r.query || '').replace(/[\r\n]+/g, ' ').trim().slice(0, 120);
  const target = r.mode === 'company' && r.page && r.page.page_id
    ? `page_id ${r.page.page_id}` : `query "${safeQuery}"`;
  const skill = level === 'plan' ? 'competitor-plan' : 'competitor-analysis';
  const prompt = S.lang === 'it'
    ? `Usa ad-library-insights (${skill}, livello ${level === 'plan' ? 3 : 2}) su ${target} in ${r.country}, analizzando ${S.deep} concetti e verifica il report finale con check_report.`
    : `Use ad-library-insights (${skill}, level ${level === 'plan' ? 3 : 2}) on ${target} in ${r.country}, reading ${S.deep} concepts and verify the final draft with check_report.`;
  try {
    await mcpApp.sendMessage({ role: 'user', content: [{ type: 'text', text: prompt }] });
    S.mcpSent = true;
  } catch { S.mcpSent = false; }
  renderResults();
}
function jumpToCompany(name) {
  if (!name) return;
  S.mode = 'company'; S.company = name; S.searchExpandedManual = false;
  submit();
}
async function reopenHistory(key) {
  const row = (S.history || []).find((item) => item.key === key);
  if (!row) return;
  S.mode = row.mode === 'keyword' ? 'keyword' : 'company';
  S.country = row.country || S.country;
  if (S.mode === 'keyword') S.query = row.query || row.label || '';
  else S.company = row.label || '';
  if (!IS_MCP_APP) {
    try {
      const saved = await api(`/api/history/latest?key=${encodeURIComponent(key)}`);
      if (saved && saved.available && saved.result) {
        _resetViewFilters();
        S.pages = null; S.cmp = null; S.notice = null;
        S.result = saved.result; S.resultMode = saved.result.mode; S.jobId = saved.job_id || null;
        S.tab = 'overview'; S.searchExpandedManual = false; render(); return;
      }
    } catch { /* fall back to fresh search */ }
  }
  if (S.mode === 'company' && row.page_id) gate({ mode: 'company', page_id: row.page_id });
  else submit();
}
async function runDurata(fresh = false) {
  const r = S.result;
  if (!r || r.mode !== 'company' || !(r.page && r.page.page_id) || S.durataBusy) return;
  const seq = ++S.durataCancelSeq;
  const t0 = performance.now();
  S.durataBusy = true; S.durataError = false; S.durataElapsed = 0; renderResults();
  try {
    let job = await api('/api/durata', {
      method: 'POST',
      body: { page_id: r.page.page_id, country: r.country, window_days: S.durataWindow, fresh },
    });
    while (job && job.status === 'running' && S.durataCancelSeq === seq) {
      await sleep(700);
      if (S.durataCancelSeq !== seq) break;
      job = await api(`/api/jobs/${job.id}`);
      if (job && job.status === 'running') {
        S.durataElapsed = Math.round((performance.now() - t0) / 1000);
        const el = $('#durata-elapsed');
        if (el) el.textContent = t('dur.elapsed', { sec: S.durataElapsed });
      }
    }
    if (S.durataCancelSeq !== seq) return;
    if (!job || job.status !== 'done' || !job.result || !job.result.durata) throw new Error('durata_failed');
    if (S.result === r) {
      S.result.durata = job.result.durata;
      const hadValidRitmo = Boolean(r.ritmo && r.ritmo.available);
      if (job.result.ritmo && (!hadValidRitmo || job.result.ritmo.available)) {
        S.result.ritmo = job.result.ritmo;
      }
    }
  } catch {
    if (S.result === r && S.durataCancelSeq === seq) S.durataError = true;
  } finally {
    if (S.durataCancelSeq === seq) {
      S.durataBusy = false;
      renderResults();
    }
  }
}
function openProject(thenSearch) {
  S.overlay = { type: 'project', draft: { ...(S.project || { market: S.country }) }, thenSearch };
  renderOverlay();
}
async function saveProject() {
  const overlay = S.overlay;
  if (!overlay || !overlay.draft) return;
  document.querySelectorAll('[data-pf]').forEach((el) => { overlay.draft[el.dataset.pf] = el.value; });
  const rawGoal = String(overlay.draft.goal || '').trim();
  const periodEl = document.getElementById('goal-period');
  if (periodEl && periodEl.value) overlay.goalPeriod = periodEl.value;
  const payload = { ...overlay.draft };
  if (/^\d+(?:[.,]\d+)?$/.test(rawGoal) && periodEl && periodEl.value) {
    payload.goal = `${rawGoal} ${periodEl.value}`;
  }
  let saved;
  try { saved = await api('/api/project', { method: 'PUT', body: payload }); } catch (error) { saved = { errors: {} }; }
  if (!saved.project) { overlay.errors = saved.errors || {}; return renderOverlay(); }
  S.project = saved.project;
  S.simPrice = S.simCost = S.simVat = S.simShip = S.simFeePct = S.simRetPct = S.simItFee = null;
  S.overlay = null; render();
  if (overlay.thenSearch && S.pending) gate(S.pending);
}
async function makeBrief(options = {}) {
  const r = S.result;
  if (!r) return;
  const req = r.request || { level: S.stratLevel, deep: S.deep, frames: S.frames };
  const lvl = (req.level && req.level !== 'data') ? req.level : (S.stratLevel === 'plan' ? 'plan' : 'analysis');
  const before = (S.overlay && S.overlay.type === 'brief' && S.overlay.made) || { ads: req.deep || S.deep, frames: Boolean(req.frames) };
  const ads = options.ads ?? before.ads, frames = options.frames ?? before.frames;
  try {
    const made = await api('/api/brief', { method: 'POST', body: { job_id: S.jobId, level: lvl, ads, frames, lang: S.lang } });
    S.overlay = { type: 'brief', made }; renderOverlay();
  } catch (error) {
    if (error.data && error.data.error === 'project_required') openProject(false);
  }
}

const ACTIONS = {
  mode(value) {
    S.mode = value; S.pages = null; S.cmp = null; S.notice = null;
    S.durataCancelSeq++; S.durataBusy = false; S.durataError = false;
    S.searchExpandedManual = false;
    render();
    if (value === 'news') loadHistory();
  },
  'news-open': openNews, 'news-refresh': refreshSubject,
  rtab: setTab,
  'ads-view'(value) { S.adsView = value === 'cards' ? 'cards' : 'table'; renderResults(); },
  'strat-level'(value) { S.stratLevel = value === 'plan' ? 'plan' : 'analysis'; S.stratNeedProject = false; renderResults(); },
  'search-expand'() { S.searchExpandedManual = true; renderSearch(); const inp = $('#search input[type="text"]'); if (inp) inp.focus(); },
  'search-fresh'() {
    const r = S.result;
    if (!r) return;
    if (r.mode === 'company' && r.page && r.page.page_id) gate({ mode: 'company', page_id: r.page.page_id, fresh: true });
    else if (r.mode === 'keyword' && r.query) gate({ mode: 'keyword', query: r.query, fresh: true });
  },
  'conn-open'() {
    if (S.mode !== 'company' && S.mode !== 'keyword') { S.mode = 'company'; renderTop(); }
    S.searchExpandedManual = true;
    renderSearch();
    const way = $('#way');
    if (way && way.scrollIntoView) way.scrollIntoView({ behavior: 'smooth', block: 'start' });
  },
  'quick-reopen': reopenHistory,
  'jump-company': jumpToCompany,
  'ad-step'(value) { stepAd(Number(value || 1)); },
  'video-inspect': runVideoInspect,
  'ai-run': runAi,
  'mcp-send-ai': sendMcpAi,
  async 'copy-ai-report'() {
    if (S.aiJob && S.aiJob.markdown && await copyText(S.aiJob.markdown)) {
      S.aiCopied = true;
      renderResults();
    }
  },
  sort(value) { S.sort = value; renderResults(); },
  theme(value) {
    if (value === S.theme) return;
    const root = document.documentElement;
    root.classList.add('theme-transition');
    clearTimeout(themeTimer);
    themeTimer = setTimeout(() => root.classList.remove('theme-transition'), 520);
    S.theme = value;
    store.set('theme', value);
    renderTop();
  },
  'durata-window'(value) { S.durataWindow = Number(value); S.durataError = false; renderResults(); },
  'durata-run'() { runDurata(false); },
  'durata-cancel'() { S.durataCancelSeq++; S.durataBusy = false; renderResults(); },
  'seismo-week'(value) { S.seismoWeek = Number(value); renderResults(); },
  'arch-focus'(value) { if (value) { S.archFocus = value; renderResults(); } },
  'ritmo-refresh'() {
    const r = S.result;
    if (r && r.mode === 'company' && r.page && r.page.page_id) {
      gate({ mode: 'company', page_id: r.page.page_id, fresh: true });
    }
  },
  lang(value) { S.lang = value; store.set('lang', value); render(); },
  level(value) { S.level = value; renderSearch(); refreshEstimate(); },
  /* Opening a row chooses its level; the open row is the chosen one. A row opened again closes. */
  'lv-toggle'(value) {
    if ((S.job || S.busy) && S.level !== value) return;
    const changed = S.level !== value;
    S.levelOpen = changed ? true : !S.levelOpen;
    S.level = value;
    store.set(LEVELS_STATE, JSON.stringify({ level: S.level, open: S.levelOpen }));
    renderSearch();
    if (changed) refreshEstimate();
  },
  'link-open'() { S.overlay = { type: 'link-confirm', overwrite: false }; renderOverlay(); },
  'link-overwrite-open'() { S.overlay = { type: 'link-confirm', overwrite: true }; renderOverlay(); },
  'link-go'() { if (!S.overlay) return; const overwrite = Boolean(S.overlay.overwrite); S.overlay = null; renderOverlay(); runConnect(overwrite); },
  'link-test': testLink,
  async 'link-copy'() { S.link.copy = (await copyText(exampleSentence())) ? 'ok' : 'failed'; renderWay(); },
  'way-run'() {
    if (hasModeResult() && S.jobId && S.mode !== 'compare') {
      S.wayHint = false; S.searchExpandedManual = false; S.tab = 'strategy'; render(); runAi(); return;
    }
    S.wayHint = true; renderWay();
  },
  'way-copy'() {
    const r = S.result;
    if (hasModeResult() && S.jobId && S.mode !== 'compare' && r.request && r.request.level !== 'data') { S.link.hint = false; renderWay(); return makeBrief(); }
    S.link.hint = true; renderWay();
  },
  'how-open'() { S.overlay = { type: 'how', step: 1 }; renderOverlay(); },
  'how-next'() { if (!S.overlay) return; S.overlay.step = Math.min(3, (S.overlay.step || 1) + 1); renderOverlay(); },
  'how-prev'() { if (!S.overlay) return; S.overlay.step = Math.max(1, (S.overlay.step || 1) - 1); renderOverlay(); },
  tutorial() { S.overlay = { type: 'tutorial', tab: 1 }; renderOverlay(); },
  'kpi-open'() { S.overlay = { type: 'tutorial', tab: 5 }; renderOverlay(); },
  'tut-tab'(value) { if (S.overlay && S.overlay.type === 'tutorial') { S.overlay.tab = Number(value); renderOverlay(); } },
  tfilter(value) { S.filter = value; renderResults(); },
  'export-csv'() { if (S.result && (S.result.ads || []).length) exportCsv(S.result); },
  async 'copy-cmp-brief'() {
    if (S.result && S.result.comparison) {
      await copyText(buildCompareBrief(S.result));
      S.cmpCopied = true;
      renderResults();
    }
  },
  deep(value) { S.deep = Number(value); renderSearch(); renderOverlay(); refreshEstimate(); },
  submit, guide() { S.overlay = { type: 'guide' }; renderOverlay(); },
  project() { openProject(false); },
  'lv-project'() { openProject(false); },
  'save-project': saveProject, 'confirm-go': launch, brief() { makeBrief(); },
  'brief-ads'(value) { makeBrief({ ads: Number(value) }); },
  'choose-page'(value) { gate({ mode: 'company', page_id: value }); },
  'cmp-pick'(value, el) {
    if (!S.cmp || !S.cmp.sides || !S.cmp.sides[Number(el.dataset.side)]) return;
    S.cmp.sides[Number(el.dataset.side)].picked = value;
    if (S.cmp.sides.every((side) => side.picked)) launchCompare(); else renderResults();
  },
  'open-ad'(value) { S.overlay = { type: 'ad', id: value }; renderOverlay(); },
  close() { S.overlay = null; renderOverlay(); },
  async 'copy-brief'() {
    const made = S.overlay && S.overlay.made;
    if (!made) return;
    if (await copyText(made.text)) briefStatus(t('brief.copied'));
    else briefStatus(t('brief.copy.failed', { folder: made.folder_name }), true);
  },
  async 'copy-command'() {
    const made = S.overlay && S.overlay.made;
    if (!made) return;
    if (await copyText(t(`brief.command.${made.level}`, { folder: made.folder }))) briefStatus(t('brief.copied.command'));
    else briefStatus(t('brief.copy.failed.command'), true);
  },
  async 'open-frames'() {
    const made = S.overlay && S.overlay.made;
    if (!made) return;
    try {
      await api('/api/frames/open', { method: 'POST', body: { key: made.frames_key } });
      briefStatus(t('brief.frames.opened'));
    } catch { briefStatus(t('brief.frames.failed'), true); }
  },
};
let _helpAnchor = null;
function positionHelpPop(wrap, btn) {
  const pop = wrap.querySelector('.help-pop');
  if (!pop || !btn) return;
  pop.style.position = 'fixed';
  pop.style.right = 'auto';
  pop.style.zIndex = '60';
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  pop.style.width = `${Math.min(350, vw - 24)}px`;
  const rect = pop.getBoundingClientRect();
  const w = Math.min(rect.width || pop.offsetWidth || 300, vw - 24);
  const h = Math.min(rect.height || pop.offsetHeight || 160, vh - 24);
  const b = btn.getBoundingClientRect();
  _helpAnchor = { btn, left: b.left, top: b.top, at: performance.now() };
  const topbar = $('.topbar');
  const topMin = (topbar && getComputedStyle(topbar).position === 'sticky')
    ? Math.max(12, Math.round(topbar.getBoundingClientRect().bottom) + 8)
    : 12;
  const preferRight = pop.classList.contains('right');
  const rawLeft = preferRight ? b.right - w : b.left;
  const left = Math.max(12, Math.min(rawLeft, vw - w - 12));
  pop.style.width = `${w}px`;
  pop.style.left = `${left}px`;
  let top = b.bottom + 8;
  if (top + h > vh - 12) {
    const aboveTop = b.top - h - 8;
    if (aboveTop >= topMin) top = aboveTop;
    else top = Math.max(topMin, Math.min(top, vh - h - 12));
  } else {
    top = Math.max(topMin, top);
  }
  pop.style.top = `${top}px`;
}
function closeHelp() {
  _helpAnchor = null;
  document.querySelectorAll('.help-wrap.open').forEach((wrap) => {
    wrap.classList.remove('open');
    const btn = wrap.querySelector('.help-btn');
    if (btn) btn.setAttribute('aria-expanded', 'false');
    const pop = wrap.querySelector('.help-pop');
    if (pop) {
      pop.style.position = '';
      pop.style.left = '';
      pop.style.top = '';
      pop.style.right = '';
      pop.style.width = '';
      pop.style.zIndex = '';
    }
  });
  if (document.activeElement && document.activeElement.closest('.help-wrap')) document.activeElement.blur();
}
document.addEventListener('click', (event) => {
  if (IS_MCP_APP && mcpApp) {
    const extLink = event.target.closest('a[href^="http://"], a[href^="https://"]');
    if (extLink) {
      event.preventDefault();
      if (mcpApp.openLink) mcpApp.openLink({ url: extLink.href }).catch(() => {});
      return;
    }
  }
  const helpBtn = event.target.closest('[data-action="help-toggle"]');
  if (helpBtn) {
    event.preventDefault();
    event.stopPropagation();
    const wrap = helpBtn.closest('.help-wrap');
    const willOpen = wrap && !wrap.classList.contains('open');
    closeHelp();
    if (wrap && willOpen) {
      wrap.classList.add('open');
      helpBtn.setAttribute('aria-expanded', 'true');
      positionHelpPop(wrap, helpBtn);
    } else {
      helpBtn.blur();
    }
    return;
  }
  if (event.target.closest('.help-pop')) return;
  if (!event.target.closest('.help-wrap')) closeHelp();
  const el = event.target.closest('[data-action]');
  if (!el || el.disabled) return;
  const action = ACTIONS[el.dataset.action];
  if (action) action(el.dataset.value, el);
});
window.addEventListener('resize', closeHelp);
window.addEventListener('scroll', (event) => {
  if (!_helpAnchor) return;
  const b = _helpAnchor.btn.getBoundingClientRect();
  const moved = Math.abs(b.top - _helpAnchor.top) > 3 || Math.abs(b.left - _helpAnchor.left) > 3;
  if (!moved && event.isTrusted && performance.now() - _helpAnchor.at < 250) return;
  closeHelp();
}, true);
document.addEventListener('input', (event) => {
  const el = event.target;
  if (el.dataset.bind) {
    S[el.dataset.bind] = el.value;
    if (el.dataset.bind === 'tableQuery' && S.result) {
      const tbody = $('#ads-tbody');
      if (tbody) tbody.innerHTML = tableRowsHtml(S.result);
      const grid = $('#ads-grid');
      if (grid) { grid.innerHTML = cardsGridHtml(S.result); hydrateMcpImages(); }
    }
  }
  if (el.dataset.sim) {
    const n = Number(el.value || 0);
    const safe = Number.isFinite(n) ? n : 0;
    if (el.dataset.sim === 'price') S.simPrice = safe;
    if (el.dataset.sim === 'cost') S.simCost = safe;
    if (el.dataset.sim === 'vat') S.simVat = safe;
    if (el.dataset.sim === 'ship') S.simShip = safe;
    if (el.dataset.sim === 'feePct') S.simFeePct = safe;
    if (el.dataset.sim === 'retPct') S.simRetPct = safe;
    document.querySelectorAll(`[data-sim="${el.dataset.sim}"]`).forEach((other) => {
      if (other !== el) other.value = el.value;
    });
    updateSimDom();
  }
});
document.addEventListener('change', (event) => {
  const el = event.target;
  if (el.dataset.change === 'frames') { S.frames = el.checked; refreshEstimate(); }
  if (el.dataset.change === 'brief-frames') makeBrief({ frames: el.checked });
  if (el.dataset.bind === 'country') {
    S.country = el.value;
    if (S.simItFee === null) {
      const wantIt = ((S.project && S.project.market) || S.country) === 'IT';
      const checks = document.querySelectorAll('[data-sim-check="itFee"]');
      if (checks.length) {
        checks.forEach((cb) => { cb.checked = wantIt; });
        updateSimDom();
      }
    }
  }
  if (el.dataset.simCheck === 'itFee') {
    S.simItFee = el.checked;
    document.querySelectorAll('[data-sim-check="itFee"]').forEach((other) => {
      if (other !== el) other.checked = el.checked;
    });
    updateSimDom();
  }
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    if ($('.help-wrap.open')) { closeHelp(); return; }
    if (S.overlay) { ACTIONS.close(); return; }
  }
  if (event.key === 'Enter' && event.target.dataset && ['query', 'company', 'companyB'].includes(event.target.dataset.bind) && !S.job && !S.busy) { submit(); return; }
  const editing = event.target && event.target.matches && event.target.matches('input, textarea, select, [contenteditable]');
  if (editing || event.ctrlKey || event.metaKey || event.altKey) return;
  if (S.overlay && S.overlay.type === 'ad') {
    if (event.key === 'ArrowRight') { event.preventDefault(); stepAd(1); }
    else if (event.key === 'ArrowLeft') { event.preventDefault(); stepAd(-1); }
    return;
  }
  if (!S.overlay && hasModeResult() && (S.mode === 'company' || S.mode === 'keyword')) {
    const idx = STUDIO_TABS.indexOf(S.tab);
    if (event.key === 'ArrowRight') { event.preventDefault(); setTab(STUDIO_TABS[(idx + 1) % STUDIO_TABS.length]); return; }
    if (event.key === 'ArrowLeft') { event.preventDefault(); setTab(STUDIO_TABS[(idx - 1 + STUDIO_TABS.length) % STUDIO_TABS.length]); return; }
    if (/^[1-6]$/.test(event.key)) { event.preventDefault(); setTab(STUDIO_TABS[Number(event.key) - 1]); return; }
    if (event.key === '/') { event.preventDefault(); ACTIONS['search-expand'](); }
  }
});

function _applyHostCtx(ctx) {
  if (!ctx || !window.McpExtApps) return;
  if (ctx.theme === 'dark' || ctx.theme === 'light') {
    S.theme = ctx.theme;
    window.McpExtApps.applyDocumentTheme(ctx.theme);
  }
  if (ctx.styles && ctx.styles.variables) window.McpExtApps.applyHostStyleVariables(ctx.styles.variables);
  renderTop();
}

(async function start() {
  if (IS_MCP_APP) {
    try {
      mcpApp = new window.McpExtApps.App({ name: 'Ad Library Insights', version: '0.7.0' }, {});
      mcpApp.onhostcontextchanged = _applyHostCtx;
      mcpApp.ontoolinput = ({ arguments: args }) => {
        if (args && (args.name || args.page_id || args.query)) {
          const targetMode = (args.query && !args.page_id && !args.name) ? 'keyword' : 'company';
          S.mode = targetMode; S.busy = 'tool'; S.busyMode = targetMode;
          S.result = null; S.resultMode = null; S.searchExpandedManual = false;
          render();
        }
      };
      mcpApp.ontoolresult = (res) => hydrateFromMcpPayload(_unwrapMcp(res));
      await mcpApp.connect();
      _applyHostCtx(mcpApp.getHostContext());
    } catch { /* graceful standalone fallback */ }
    try {
      const state = await api('/api/state');
      S.project = state.project;
      if (Array.isArray(state.deep_choices)) S.deepChoices = state.deep_choices;
      if (Array.isArray(state.subjects)) S.history = state.subjects;
    } catch { /* ignore */ }
    render();
    hydrateMcpImages();
    return;
  }
  if (!Object.keys(T.it || {}).length) {
    T = await (await fetch('/static/strings.json', { cache: 'no-store' })).json();
  }
  try {
    const state = await api('/api/state');
    S.project = state.project; S.deepChoices = state.deep_choices;
  } catch { /* the page still works without the saved card */ }
  try {
    const hist = await api('/api/history');
    S.history = hist.subjects || [];
  } catch { S.history = []; }
  render();
  refreshEstimate();
  loadLink();
})();
