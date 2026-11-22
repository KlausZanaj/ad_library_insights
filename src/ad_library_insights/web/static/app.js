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

const S = {
  lang: store.get('lang', 'it'), theme: store.get('theme', 'light'),
  mode: 'keyword', level: START.level, levelOpen: START.open, deep: 10, frames: false, deepChoices: [10, 20, 50],
  country: 'IT', query: '', company: '', companyB: '', cmp: null, resultMode: null,
  pages: null, busy: null, job: null, result: null, jobId: null, notice: null,
  project: null, overlay: null, estimate: null, pending: null,
  history: null, news: null, sort: 'score', filter: 'all', tableQuery: '',
  durataWindow: 90, durataBusy: false, durataError: false,
  simPrice: null, simCost: null, simVat: null, simShip: null, simFeePct: null, simRetPct: null, simItFee: null,
  cmpCopied: false,
  link: { quick: null, mcp: 'checking', running: false, result: null, error: null, test: null, copy: null, hint: false },
};
let T = { it: {}, en: {} };
let themeTimer = null;

/* ---------- helpers ---------- */
const $ = (selector, root = document) => root.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function t(key, vars) {
  let text = T[S.lang][key] ?? T.en[key] ?? key;
  for (const name in vars || {}) text = text.replaceAll(`{${name}}`, vars[name]);
  return text;
}
const hasT = (key) => Boolean(T[S.lang][key] ?? T.en[key]);
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
const day = (iso) => new Intl.DateTimeFormat(S.lang, { day: 'numeric', month: 'short', year: 'numeric' })
  .format(new Date(`${iso}T00:00:00`));
const clock = (iso) => new Intl.DateTimeFormat(S.lang, { hour: '2-digit', minute: '2-digit' }).format(new Date(iso));
function dur(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  if (seconds < 60) return `${seconds} s`;
  const rest = seconds % 60;
  return rest ? `${Math.floor(seconds / 60)} min ${rest} s` : `${seconds / 60} min`;
}
const initials = (name) => (name || '?').split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();
const avatar = (src, name, big) => (src
  ? `<img class="avatar${big ? ' big' : ''}" src="${esc(src)}" alt="" data-initials="${esc(initials(name))}">`
  : `<span class="avatar txt${big ? ' big' : ''}">${esc(initials(name))}</span>`);
// a logo that does not load gives way to the initials of the page
document.addEventListener('error', (event) => {
  const img = event.target;
  if (!(img instanceof HTMLImageElement) || !img.classList.contains('avatar')) return;
  const span = document.createElement('span');
  span.className = `avatar txt${img.classList.contains('big') ? ' big' : ''}`;
  span.textContent = img.dataset.initials || '?';
  img.replaceWith(span);
}, true);
const firstLine = (ad) => ((ad.body || '').trim().split('\n')[0] || ad.headline || '');

async function api(path, options = {}) {
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
function renderSearch() {
  const active = S.mode === 'keyword' || S.mode === 'company';
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
    if (S.job || S.busy) html += '<div class="progress"><p><span id="ptext"></span><span class="muted num" id="pleft"></span></p><div class="bar" id="pbar"><i></i></div></div>';
    else if (S.notice) html += `<p class="notice${S.notice.err ? ' err' : ''}">${esc(S.notice.text)}</p>`;
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
  html += '<section class="way" id="way"></section>';
  if (S.job || S.busy) html += '<div class="progress"><p><span id="ptext"></span><span class="muted num" id="pleft"></span></p><div class="bar" id="pbar"><i></i></div></div>';
  else if (S.notice) html += `<p class="notice${S.notice.err ? ' err' : ''}">${esc(S.notice.text)}</p>`;
  $('#search').innerHTML = `${html}</div>`;
  renderWay();
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
  if ($('#sim-cpa')) $('#sim-cpa').textContent = num(cpa);
  if ($('#sim-roas')) $('#sim-roas').textContent = t('lv.v3.sim.roas', { roas });
  if ($('#sim-stop')) $('#sim-stop').textContent = `${num(lowCut)} - ${num(highCut)}`;
  if ($('#sim-budget')) $('#sim-budget').textContent = num(round1);
  if ($('#sim-cpc-rows')) $('#sim-cpc-rows').innerHTML = precheckCpcRowsHtml(cpcs, isEur);
  if ($('#sim-risk-line')) {
    $('#sim-risk-line').textContent = t('pre.risk.line', {
      spend: simMoney(round1, isEur),
      billed: simMoney(billed, isEur),
      onein: oneIn != null ? num(oneIn) : '—',
    });
  }
}
function levelVisual(level) {
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
    <div class="vis-top"><span class="vis-title">${esc(t('lv.v3.badge'))}</span><button class="linklike" data-action="lv-project" style="font-size:.78rem">${esc(t('lv.v3.sim.edit'))}</button></div>
    <div class="sim-inputs">
      <label class="sim-field"><span>${esc(t('lv.v3.sim.price'))}</span><input type="number" min="1" step="1" data-sim="price" value="${esc(p)}"></label>
      <label class="sim-field"><span>${esc(t('lv.v3.sim.cost'))}</span><input type="number" min="0" step="1" data-sim="cost" value="${esc(c)}"></label>
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
      <div class="vis-kpi"><span>${esc(t('lv.v3.cpa'))}</span><strong id="sim-cpa">${num(cpa)}</strong><small id="sim-roas">${esc(t('lv.v3.sim.roas', { roas }))}</small></div>
      <div class="vis-kpi"><span>${esc(t('lv.v3.stop'))}</span><strong id="sim-stop">${num(lowCut)} - ${num(highCut)}</strong><small>${esc(t('lv.v3.stop.sub'))}</small></div>
      <div class="vis-kpi"><span>${esc(t('lv.v3.budget'))}</span><strong id="sim-budget">${num(round1)}</strong><small>${esc(t('lv.v3.budget.sub'))}</small></div>
    </div>
    <div class="precheck-box">
      <div class="precheck-head"><span>${esc(t('pre.cpc.title'))}</span>${cpcHelp}</div>
      <div class="cpc-grid" id="sim-cpc-rows">${precheckCpcRowsHtml(cpcs, isEur)}</div>
      <p class="precheck-bench">${esc(t('pre.cpc.bench'))}</p>
      <p class="precheck-risk" id="sim-risk-line">${esc(t('pre.risk.line', { spend: simMoney(round1, isEur), billed: simMoney(billed, isEur), onein: oneIn != null ? num(oneIn) : '—' }))}</p>
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
        <div class="way-act"><button class="btn quiet" disabled>${esc(t('way.b.btn'))}</button><span class="muted">${esc(t('way.b.soon'))}</span></div>
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
  renderWay();
  if (L.quick.claude) {
    try {
      const { state } = await api('/api/link/mcp');
      if (seq === linkSeq) L.mcp = connectedNow && state === 'unknown' ? 'connected' : state;
    } catch { if (seq === linkSeq && !connectedNow) L.mcp = 'unknown'; }
  } else if (seq === linkSeq) L.mcp = 'no_claude';
  if (seq === linkSeq) renderWay();
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
  let label = t('pages.searching'), left = '', share = null;
  if (S.job) {
    const { phase, detail = {} } = S.job;
    if (phase === 'details') {
      label = t('phase.details', detail);
      share = detail.total ? detail.done / detail.total : 0;
      if (detail.eta_seconds) left = t('phase.left', { time: dur(detail.eta_seconds) });
    } else if (phase === 'waiting') label = t('phase.waiting', detail);
    else if (phase === 'list' && S.job.params.mode !== 'keyword') label = t('phase.list.company');
    else label = t(`phase.${phase}`);
    if (detail.side) label = t('cmp.side', { n: detail.side }) + label;
  }
  text.textContent = label;
  $('#pleft').textContent = left;
  bar.classList.toggle('open', share === null);
  bar.firstElementChild.style.width = share === null ? '' : `${Math.max(3, Math.round(share * 100))}%`;
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
  const total = r.signals.active_ads;
  const loaded = t('result.loaded', { loaded: num(r.ads_parsed), total: num(total),
    time: `${t(r.from_cache ? 'result.cache' : 'result.fresh')}${r.fetched_at ? `, ${clock(r.fetched_at)}` : ''}` });
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
  const date = `${day(c.previous_taken_at.slice(0, 10))}, ${clock(c.previous_taken_at)}`;
  const { new: fresh, stopped, changed } = c.counts;
  const text = fresh + stopped + changed ? t('changes.since', { date, new: fresh, stopped, changed }) : t('changes.same', { date });
  return `<section class="changes"><p>${esc(text)}</p><button class="btn quiet small" data-action="news-open" data-value="${esc(c.key)}">${esc(t('news.view'))}</button></section>`;
}
function readySection(r) {
  const level = r.request.level;
  if (level === 'data') return '';
  return `<section class="ready"><p>${esc(t(`brief.ready.${level}`))}</p>
    <button class="btn" data-action="brief">${esc(t(`brief.make.${level}`))}</button></section>`;
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
  const s = r.signals;
  const reach = s.reach.available ? s.reach.median_reach_per_day : null;
  const cells = [
    [num(s.active_ads), t('m.active'), t(r.mode === 'company' ? 'm.active.x' : 'm.active.x.keyword')],
    [pct(s.video_share), t('m.video'), t('m.video.x')],
    [num(s.new_per_week), t('m.weekly'), t('m.weekly.x')],
    [reach == null ? '—' : num(reach), t('m.reachday'), t(reach == null ? 'm.reachday.none' : 'm.reachday.x')],
    [num(s.started_last_30_days), t('m.new30'), `${t('m.new30.x')} ${t('m.new30.share', { share: pct(s.share_started_last_30_days) })}.`],
  ];
  return `<section class="metrics">${cells.map(([value, label, why]) => `<div class="metric"><b>${esc(value)}</b><span>${esc(label)}</span><small>${esc(why)}</small></div>`).join('')}</section>`;
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
const shareRows = (rows, label) => `<ul class="rows">${rows.slice(0, 5).map((row) => `<li><span>${esc(label(row))}</span><span>${pct(row.share)}</span></li>`).join('') || `<li><span class="dim">—</span></li>`}</ul>`;
function factsSection(r) {
  const s = r.signals, audience = s.audience, reach = s.reach;
  const places = audience && audience.locations_included.length
    ? `<dl><dt>${esc(t('f.places.in'))}</dt><dd>${placeNames(audience.locations_included, audience.ads_with_audience, audience.locations_included_count)}</dd>
       <dt>${esc(t('f.places.out'))}</dt><dd>${placeNames(audience.locations_excluded, audience.ads_with_audience, audience.locations_excluded_count, 3)}</dd></dl>
       <p class="note">${esc(t('f.places.note'))}</p>`
    : `<p class="note" style="margin-top:0">${esc(t('f.places.unread'))} ${esc(t('f.places.note'))}</p>`;
  const who = audience ? `<dl>
      <dt>${esc(t('f.audience.age'))}</dt><dd>${ageNames(audience.age_ranges, audience.ads_with_audience)}</dd>
      <dt>${esc(t('f.audience.gender'))}</dt><dd>${Object.keys(audience.genders).map((g) => esc(t(`gender.${g}`))).join(', ')}</dd>
      <dt>${esc(t('f.audience.breadth'))}</dt><dd>${Object.keys(audience.breadth).map((b) => esc(t(`breadth.${b}`))).join(', ') || '—'}</dd></dl>`
    : '<p class="dim">—</p>';
  const coverage = !reach.available ? `<p class="note" style="margin-top:0">${esc(t('f.reach.none'))}</p>`
    : !reach.ads_with_market_reach ? `<p class="note" style="margin-top:0">${esc(t('f.reach.elsewhere', { country: region(r.country) }))}</p>`
    : `<dl>
      <dt>${esc(t('f.reach.perday.median'))}</dt><dd class="num">${num(reach.median_reach_per_day)}</dd>
      <dt>${esc(t('f.reach.perday.best'))}</dt><dd class="num">${num(reach.highest_reach_per_day)}</dd>
      <dt>${esc(t('f.reach.total.median'))}</dt><dd class="num">${num(reach.median_reach_total)}</dd>
      <dt>${esc(t('f.reach.total.best'))}</dt><dd class="num">${num(reach.highest_reach_total)}</dd></dl>
      <p class="note">${esc(t('f.reach.note', { n: reach.ads_with_market_reach, country: region(r.country) }))}</p>`;
  const reused = s.copy_patterns.reused_texts.slice(0, 4).map((row) => `<li><span>${esc(row.opening)}</span><span>${esc(oneOrMore('f.reused.n', row.creatives))}</span></li>`).join('');
  return `<section class="facts">
    <div class="fact wide"><h2>${esc(t('f.places'))}</h2>${places}</div>
    <div class="fact"><h2>${esc(t('f.audience'))}</h2>${who}</div>
    <div class="fact"><h2>${esc(t('f.reach'))}</h2>${coverage}</div>
    <div class="fact"><h2>${esc(t('f.langs'))}</h2>${shareRows(s.languages, (row) => named('language', row.language))}</div>
    <div class="fact"><h2>${esc(t('f.platforms'))}</h2>${shareRows(s.platforms, (row) => PLATFORMS[row.platform] || row.platform)}</div>
    <div class="fact"><h2>${esc(t('f.buttons'))}</h2>${shareRows(s.buttons, (row) => row.button)}</div>
    <div class="fact"><h2>${esc(t('f.dest'))}</h2>${shareRows(s.destinations, (row) => row.domain)}</div>
    <div class="fact"><h2>${esc(t('f.reused'))}</h2><ul class="rows">${reused || '<li><span class="dim">—</span></li>'}</ul></div>
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
  return ads.map((ad, index) => `<tr class="pick" data-action="open-ad" data-value="${esc(ad.library_id)}">
    <td class="rank">${index + 1}</td>
    <td><div class="adcell">${ad.thumbnail ? `<img class="thumb" src="${esc(ad.thumbnail)}" alt="" loading="lazy">` : '<span class="thumb"></span>'}
      <div class="adtext"><div>${esc(firstLine(ad) || t('t.notext'))}</div><small>${esc([company ? t(`format.${ad.media_type || 'unknown'}`) : ad.advertiser, company ? ad.cta : '', kindTag(ad)].filter(Boolean).join(' · '))}</small></div></div></td>
    <td class="tier">${verdictCell(ad)}</td>
    <td class="r">${Math.round(ad.score)}</td><td class="r">${num(ad.days_running)}</td><td class="r">${num(ad.creatives)}</td>
    ${company ? '' : `<td class="fmt">${esc(t(`format.${ad.media_type || 'unknown'}`))}</td>`}${reachCells(ad)}</tr>`).join('');
}
function helpPopover(topic, titleKey, bodyHtml, alignRight = false) {
  return `<span class="help-wrap"><button type="button" class="help-btn" data-action="help-toggle" aria-label="${esc(t('help.aria', { topic }))}" aria-expanded="false">?</button><div class="help-pop${alignRight ? ' right' : ''}" role="tooltip"><h4>${esc(t(titleKey))}</h4>${bodyHtml}</div></span>`;
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
  return `<section class="tldr" aria-label="${esc(t('tldr.label'))}">
    <span class="tldr-label">${esc(t('tldr.label'))}</span>
    <div class="tldr-lines"><strong>${esc(main)}</strong><span>${esc(sub)}</span></div>
    <div class="tldr-act"><button class="linklike" data-action="guide">${esc(t('tldr.help'))}</button></div>
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
    body = `<div class="progress" style="margin-top:16px;padding-top:16px"><p><span>${esc(t('dur.loading', { window: activeWin }))}</span></p><div class="bar open"><i></i></div></div>`;
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
    const milestones = Object.entries(d.milestones || {}).filter(([, val]) => val != null)
      .map(([age, val]) => `<span><strong>${esc(t('dur.days.short', { n: age }))}</strong>: ${pct(val)}</span>`).join('');
    const exLong = (d.longest_active || []).slice(0, 2).map((x) => `${x.library_id} (${t('dur.days.short', { n: x.days })})`).join(', ');
    const exFast = (d.fastest_ended || []).slice(0, 2).map((x) => `${x.library_id} (${t('dur.days.short', { n: x.days })})`).join(', ');
    const smallNote = (d.small_sample || Number(d.ended_in_window || 0) < 20)
      ? `<p class="notice" style="margin-top:10px">${esc(t('dur.small_sample', { ended: num(d.ended_in_window || 0) }))}</p>`
      : '';
    body = `<p class="durata-lead">${esc(lead)}</p>
      ${smallNote}
      <div class="durata-kpis">
        <div class="durata-kpi"><span class="durata-kpi-label">${esc(t('dur.kpi.median'))}</span>
          <strong>${esc(d.median_reached ? days(d.median_days) : t('dur.kpi.open'))}</strong>
          <small>${esc(t('dur.kpi.rmst', { tau: num(d.tau_days || d.max_observed_days), days: num(d.rmst_days) }))}</small></div>
        <div class="durata-kpi"><span class="durata-kpi-label">${esc(t('dur.kpi.weibull'))}${weibullPop()}</span>${weibullHtml}</div>
        <div class="durata-kpi"><span class="durata-kpi-label">${esc(t('dur.kpi.lindy'))}${lindyPop(true)}</span>${lindyHtml}</div>
      </div>
      <div class="durata-chart">
        <div class="durata-chart-head"><span>${esc(t('dur.chart.title'))}</span>${d.median_reached ? `<strong>${esc(t('dur.chart.median', { n: num(d.median_days) }))}</strong>` : ''}</div>
        ${renderKmSvg(d)}
        ${milestones ? `<div class="durata-milestones"><span>${esc(t('dur.milestones'))}:</span>${milestones}</div>` : ''}
        ${(exLong || exFast) ? `<div class="durata-examples">${exLong ? `<span>${esc(t('dur.examples.long'))}: ${esc(exLong)}</span>` : ''}${exFast ? `<span>${esc(t('dur.examples.fast'))}: ${esc(exFast)}</span>` : ''}</div>` : ''}
      </div>
      <p class="tablenote">${esc(t('dur.note'))}</p>`;
  } else if (d && !d.available) {
    body = `<p class="notice" style="margin-top:14px">${esc(durataUnavailableText(d))}</p><p class="tablenote">${esc(t('dur.note'))}</p>`;
  } else {
    body = `<p class="muted" style="margin-top:12px">${esc(t('dur.idle'))}</p>`;
  }
  return `<section class="durata-sec">
    <div class="durata-head">
      <div class="durata-head-title"><h2>${esc(t('dur.title'))}${durataPop()}</h2><p>${esc(t('dur.sub'))}</p></div>
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
  const W = 640, H = 148, padL = 34, padR = 14, padT = 16, padB = 24;
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
    const bh = Math.max(2, rawH);
    const y = +(padT + plotH - bh).toFixed(1);
    const fill = w.is_sta ? (m.trigger_ai ? 'var(--warn)' : 'var(--accent)') : 'var(--line)';
    const lbl = (w.week_start || '').slice(5);
    return `<rect x="${x}" y="${y}" width="${barW}" height="${bh}" rx="3" fill="${fill}" fill-opacity="${w.is_sta ? '0.9' : '0.85'}"/>
      <text x="${cx.toFixed(1)}" y="${Math.max(11, y - 4).toFixed(1)}" text-anchor="middle" fill="var(--muted)" font-size="10">${countVal}</text>
      <text x="${cx.toFixed(1)}" y="${H - 6}" text-anchor="middle" fill="var(--muted)" font-size="10">${esc(lbl)}</text>`;
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
function ritmoUnavailableText(m) {
  const share = m.loaded_share != null ? pct(m.loaded_share) : '—';
  if (m.reason === 'partial_list') return t('rit.unavail.partial_list', { share });
  if (m.reason === 'insufficient_history') return t('rit.unavail.insufficient_history');
  return t('rit.unavail.other', { reason: m.reason || '—' });
}
function ritmoSection(r, inNews = false) {
  if (!r || r.mode !== 'company' || !r.ritmo) return '';
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
      ? `<div class="ritmo-chart">
          <div class="ritmo-chart-head"><span>${esc(t('rit.chart.title'))}</span><span>${esc(t('rit.chart.baseline', { n: num(st.lta_mean || 0) }))} · <strong>${esc(t('rit.chart.sta', { n: num(st.sta_count || 0) }))}</strong></span></div>
          ${renderRitmoSvg(m)}
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
      <div class="ritmo-head-title"><h2>${esc(t('rit.title'))}${ritmoPop()}</h2><p>${esc(t('rit.sub'))}</p></div>
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
      <div class="struttura-families-head">${esc(t('str.families.title'))}</div>
      <div class="fam-chips">${chips}</div>
    </div>`;
  }

  const noteText = rc.measurable ? t('str.note', { n: num(rc.concepts_with_reach) }) : t('str.note.noreach');
  return `<section class="struttura-sec">
    <div class="struttura-head">
      <div class="struttura-head-title"><h2>${esc(t('str.title'))}${strutturaPop()}</h2><p>${esc(t(subKey))}</p></div>
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
      <div class="anomalie-head-title"><h2>${esc(t('anom.title'))}${anomaliePop()}</h2><p>${esc(t(subKey))}</p></div>
    </div>
    ${body}
    <p class="anomalie-note">${esc(t('anom.note'))}</p>
  </section>`;
}
function tableSection(r) {
  const company = r.mode === 'company';
  const rows = tableRowsHtml(r);
  const opened = r.deep ? r.deep.read : r.ads.reduce((sum, ad) => sum + (ad.reach ? 1 : 0) + Object.keys(ad.card_reach || {}).length, 0);
  const concepts = r.deep ? r.deep.concepts : r.ads.filter((ad) => ad.reach).length;
  return `<section><div class="sortbar">
      <span>${esc(t('sort.by'))}</span><div class="switch" role="group">${toggle('sort', ['score', 'perday', 'days'], S.sort, (v) => t(`sort.${v}`))}</div>
      <div class="switch" role="group">${toggle('tfilter', ['all', 'scaling', 'video', 'high'], S.filter, (v) => t(`filter.${v}`))}</div>
      <span class="sort-spacer"></span>
      <input type="search" class="tbl-search" id="tbl-q" data-bind="tableQuery" value="${esc(S.tableQuery)}" placeholder="${esc(t('filter.search'))}" autocomplete="off">
      <button class="btn quiet small" data-action="export-csv">${esc(t('export.csv'))}</button>
    </div>
    ${tableLegend()}
    <div class="table-scroll"><table class="ads${company ? '' : ' mixed'}"><thead><tr><th></th><th>${esc(t('t.ad'))}</th><th>${esc(t('t.tier'))}${tierScalePop()}</th>
    <th class="r">${esc(t('t.score'))}${scoreScalePop(true)}</th><th class="r">${esc(t('t.days'))}</th><th class="r">${esc(t('t.creatives'))}</th>
    ${company ? '' : `<th>${esc(t('t.format'))}</th>`}<th class="r">${esc(t('t.reached', { country: region(r.country) }))}</th><th class="r">${esc(t('t.perday'))}${perdayPop(true)}</th></tr></thead>
    <tbody id="ads-tbody">${rows}</tbody></table></div><p class="tablenote">${esc(t(concepts === 1 ? 't.note.one' : 't.note', { concepts: count(concepts, 'n.concepts'), opened: count(opened, 'n.ads') }))}</p></section>`;
}
function renderResults() {
  const el = $('#results');
  if (S.mode === 'news') { renderNews(); return; }
  if (S.mode === 'compare') {
    el.innerHTML = S.cmp ? cmpChooser() : (S.result && S.resultMode === 'compare' && S.result.comparison ? compareSheet(S.result) : '');
    return;
  }
  if (S.pages) { el.innerHTML = pagesSheet(); return; }
  const r = S.result;
  if (!r || !(r.ads || []).length || S.resultMode !== S.mode) { el.innerHTML = ''; return; }
  el.innerHTML = `<div class="sheet">${headSection(r)}${tldrSection(r)}${readySection(r)}${cappedSection(r)}${changesSection(r)}${metricsSection(r)}${factsSection(r)}${durataSection(r)}${ritmoSection(r)}${strutturaSection(r)}${anomalieSection(r)}${tableSection(r)}</div>`;
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
  const c = r.comparison, [a, b] = r.sides;
  const head = (side) => { const page = side.page || {}; return `<div>${avatar(page.logo, page.name, true)}<div><h1>${esc(page.name || side.query)}</h1>
    <p>${esc(t('cmp.sub', { category: page.category || '—', followers: num(page.followers), loaded: num(side.ads_parsed) }))}</p></div></div>`; };
  const fmt = (note, value) => (note.key === 'video_share' ? pct(value) : num(value));
  const notes = c.highlights.map((note) => `<li>${esc(t(`hl.${note.key}`, {
    leader: c.names[note.leader], other: c.names[note.leader === 'a' ? 'b' : 'a'],
    ratio: num(note.ratio), lead: fmt(note, note.lead), trail: fmt(note, note.trail) }))}</li>`).join('');
  let group = null;
  const rows = c.rows.map((row) => {
    const title = row.group !== group ? `<tr class="group"><td colspan="3">${esc(t(`cmp.group.${row.group}`))}</td></tr>` : '';
    group = row.group;
    const numeric = row.kind === 'number' || row.kind === 'percent' ? ' class="num"' : '';
    return `${title}<tr><td>${esc(t(`cmp.row.${row.key}`, { country: region(r.country) }))}</td><td${numeric}>${cmpValue(row, row.a)}</td><td${numeric}>${cmpValue(row, row.b)}</td></tr>`;
  }).join('');
  const top = (side) => `<div><div class="table-scroll"><table class="ads"><tbody>${side.ads.slice(0, 5).map((ad) => `<tr class="pick" data-action="open-ad" data-value="${esc(ad.library_id)}">
    <td><div class="adcell">${ad.thumbnail ? `<img class="thumb" src="${esc(ad.thumbnail)}" alt="" loading="lazy">` : '<span class="thumb"></span>'}
      <div class="adtext"><div>${esc(firstLine(ad) || t('t.notext'))}</div><small>${esc(`${t(`verdict.${ad.verdict}`)} · ${days(ad.days_running)} · ${oneOrMore('f.reused.n', ad.creatives)}`)}</small></div></div></td>
    <td class="r">${Math.round(ad.score)}</td></tr>`).join('')}</tbody></table></div></div>`;
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
  link.href = URL.createObjectURL(blob);
  link.download = `ad-library-insights-${(r.page && r.page.name) || r.query || 'export'}-${r.country}.csv`.replace(/[^a-zA-Z0-9._-]+/g, '-');
  document.body.appendChild(link);
  link.click();
  link.remove();
}
const findAd = (id) => {
  const pools = S.result ? (S.result.sides ? S.result.sides.map((side) => side.ads) : [S.result.ads]) : [];
  return pools.flat().find((item) => item.library_id === id);
};
async function submitCompare() {
  const names = [S.company.trim(), S.companyB.trim()];
  if (!names[0] || !names[1]) return note('error.input', null, true);
  S.result = null; S.cmp = null; S.busy = 'pages'; render();
  try {
    const sides = [];
    for (const name of names) {
      const found = await api(`/api/pages?name=${encodeURIComponent(name)}&country=${S.country}`);
      if (!found.pages.length) { S.busy = null; return note('pages.none.named', { name, country: region(S.country) }); }
      sides.push({ name, pages: found.pages, suggested: found.suggested_page_id,
        picked: found.pages.length === 1 ? found.pages[0].page_id : null });
    }
    S.busy = null; S.cmp = { sides };
    if (sides.every((side) => side.picked)) return launchCompare();
    render();
  } catch (error) { S.busy = null; note('error.title', null, true); }
}
function launchCompare() {
  const [first, second] = S.cmp.sides;
  S.pending = { mode: 'compare', page_id: first.picked, page_id_b: second.picked, country: S.country, fresh: false };
  S.cmp = null;
  return launch();
}

/* ---------- what changed ---------- */
const stamp = (iso) => `${day(iso.slice(0, 10))}, ${clock(iso)}`;
function adCell(ad, keyword) {
  return `<div class="adcell">${ad.thumbnail ? `<img class="thumb" src="${esc(ad.thumbnail)}" alt="" loading="lazy">` : '<span class="thumb"></span>'}
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
    <section class="metrics three">${cells.map(([value, label, why]) => `<div class="metric"><b>${num(value)}</b><span>${esc(label)}</span><small>${esc(why)}</small></div>`).join('')}</section>
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
  S.mode = 'news'; S.pages = null; S.notice = null; S.overlay = null;
  render();
  await loadHistory();
  try { S.news = await api(`/api/history/changes?key=${encodeURIComponent(key)}`); } catch { S.news = null; }
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
  const places = (list, limit) => placeNames(list, null, list.length, limit);
  let reachHtml;
  if (!reach) reachHtml = `<p class="muted">${esc(t('d.reach.unread'))}</p>`;
  else if (!reach.available) reachHtml = `<p class="muted">${esc(t('d.reach.none'))}</p>`;
  else {
    const countries = reach.regions.flatMap((g) => g.countries).sort((a, b) => b.reach - a.reach).slice(0, 8);
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
  return `<aside class="drawer" role="dialog" aria-modal="true"><header><h2>${esc(ad.advertiser || '')}</h2><button class="x" data-action="close">${esc(t('button.close'))}</button></header><div class="body">
    <section><div class="hero">${ad.thumbnail ? `<img src="${esc(ad.thumbnail)}" alt="">` : ''}<div>
      <p><strong>${esc(ad.status === 'inactive' ? t('d.inactive') : t('d.active', { date: ad.started ? day(ad.started) : '—' }))}</strong></p>
      <p class="muted">${esc(days(ad.days_running))} · ${esc(t(`format.${ad.media_type || 'unknown'}`))}</p>
      ${ad.impression_rank ? `<p class="muted">${esc(t('d.rank', { n: ad.impression_rank }))}</p>` : ''}
      <p style="margin-top:10px"><a href="${esc(ad.ad_url)}" target="_blank" rel="noopener">${esc(t('link.meta'))}</a></p></div></div></section>
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
      <p class="smallnote">${esc(t('d.longevity', { n: Math.round(ad.longevity_score) }))}</p>
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
    ${(ad.frames || []).length ? `<section><h3>${esc(t('d.frames'))}</h3><div class="frames">${ad.frames.map((src) => `<img src="${esc(src)}" alt="">`).join('')}</div></section>` : ''}
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
      <div><span class="k">${esc(t('confirm.band'))}</span><span class="v big">${esc(e.band ? t(`band.${e.band}`) : '—')}</span></div>
      <div><span class="k">${esc(t('confirm.time'))}</span><span class="v">${e.seconds ? esc(t('confirm.time.v', { time: dur(e.seconds) })) : '—'}</span></div>
    </div>
    <p class="smallnote">${esc(t('confirm.note'))}</p>
    <div class="foot"><button class="btn quiet" data-action="close">${esc(t('button.back'))}</button><button class="btn" data-action="confirm-go">${esc(t('confirm.go'))}</button></div></div>`;
}
function projectDialog(overlay) {
  const p = overlay.draft, errors = overlay.errors || {};
  const field = (name, key, body, full) => `<label class="field${full ? ' full' : ''}${errors[name] ? ' bad' : ''}"><span>${esc(t(key))}</span>${body}${errors[name] ? `<em>${esc(t(`proj.err.${errors[name]}`))}</em>` : ''}</label>`;
  const input = (name, hint) => `<input type="text" data-pf="${name}" value="${esc(p[name] ?? '')}" placeholder="${esc(hint ? t(hint) : '')}" autocomplete="off">`;
  const goalInput = `<div style="display:flex;gap:8px">${input('goal', 'proj.goal.hint')}<select id="goal-period" style="width:170px;flex:none" aria-label="${esc(t('proj.goal'))}">
    <option value="${esc(t('proj.goal.day'))}">${esc(t('proj.goal.day'))}</option>
    <option value="${esc(t('proj.goal.week'))}">${esc(t('proj.goal.week'))}</option>
    <option value="${esc(t('proj.goal.month'))}">${esc(t('proj.goal.month'))}</option></select></div>`;
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
  el.innerHTML = `<div class="scrim" data-action="close"></div>${inner}`;
}
function render() { renderTop(); renderSearch(); renderResults(); renderOverlay(); }

/* ---------- actions ---------- */
async function refreshEstimate() {
  try {
    S.estimate = await api(`/api/estimate?level=${S.level}&ads=${S.deep}&frames=${S.frames && S.level !== 'data' ? 1 : 0}`);
  } catch { S.estimate = null; }
  if (!S.job && !S.busy) renderSearch();
  if (S.overlay && S.overlay.type === 'confirm') renderOverlay();
}
function note(key, vars, err) { S.notice = { text: t(key, vars), err }; render(); }

async function submit() {
  S.notice = null;
  if (S.mode === 'compare') return submitCompare();
  if (S.mode === 'keyword') {
    if (!S.query.trim()) return note('error.input', null, true);
    return gate({ mode: 'keyword', query: S.query.trim() });
  }
  if (!S.company.trim()) return note('error.input', null, true);
  S.pages = null; S.result = null; S.busy = 'pages'; render();
  try {
    const found = await api(`/api/pages?name=${encodeURIComponent(S.company.trim())}&country=${S.country}`);
    S.busy = null;
    if (!found.pages.length) return note('pages.none', { country: region(S.country) });
    if (found.pages.length === 1) { render(); return gate({ mode: 'company', page_id: found.pages[0].page_id }); }
    S.pages = found; render();
  } catch (error) { S.busy = null; note('error.title', null, true); }
}
function gate(request) {
  S.pending = { fresh: false, ...request, country: S.country };
  if (S.level === 'plan' && !S.project) return openProject(true);
  if (S.level !== 'data') { S.overlay = { type: 'confirm' }; renderOverlay(); return refreshEstimate(); }
  return launch();
}
async function launch() {
  S.overlay = null; S.pages = null; S.result = null; S.notice = null;
  S.durataBusy = false; S.durataError = false;
  try {
    S.job = await api('/api/jobs', { method: 'POST', body: { ...S.pending, level: S.pending.mode === 'compare' ? 'data' : S.level, deep: S.deep, frames: S.frames } });
  } catch (error) {
    if (error.data && error.data.error === 'project_required') return openProject(true);
    return note('error.title', null, true);
  }
  render();
  while (S.job && S.job.status === 'running') {
    await sleep(700);
    try { S.job = await api(`/api/jobs/${S.job.id}`); } catch { break; }
    updateProgress();
  }
  const job = S.job; S.job = null;
  if (!job || job.status !== 'done') return note('error.title', null, true);
  const found = job.result.sides ? job.result.sides.every((side) => (side.ads || []).length) : (job.result.ads || []).length;
  if (!found) return note(`error.${job.result.outcome === 'blocked' ? 'blocked' : 'no_results'}`);
  S.result = job.result; S.resultMode = job.params.mode; S.jobId = job.id; render();
  window.scrollTo({ top: $('#results').offsetTop - 12, behavior: 'instant' });
}
async function runDurata(fresh = false) {
  const r = S.result;
  if (!r || r.mode !== 'company' || !(r.page && r.page.page_id) || S.durataBusy) return;
  S.durataBusy = true; S.durataError = false; renderResults();
  try {
    let job = await api('/api/durata', {
      method: 'POST',
      body: { page_id: r.page.page_id, country: r.country, window_days: S.durataWindow, fresh },
    });
    while (job && job.status === 'running') {
      await sleep(700);
      job = await api(`/api/jobs/${job.id}`);
    }
    if (!job || job.status !== 'done' || !job.result || !job.result.durata) throw new Error('durata_failed');
    if (S.result === r) {
      S.result.durata = job.result.durata;
      if (job.result.ritmo) S.result.ritmo = job.result.ritmo;
    }
  } catch {
    if (S.result === r) S.durataError = true;
  } finally {
    S.durataBusy = false;
    renderResults();
  }
}
function openProject(thenSearch) {
  S.overlay = { type: 'project', draft: { ...(S.project || { market: S.country }) }, thenSearch };
  renderOverlay();
}
async function saveProject() {
  const overlay = S.overlay;
  document.querySelectorAll('[data-pf]').forEach((el) => { overlay.draft[el.dataset.pf] = el.value; });
  const rawGoal = String(overlay.draft.goal || '').trim();
  const periodEl = document.getElementById('goal-period');
  if (/^\d+(?:[.,]\d+)?$/.test(rawGoal) && periodEl && periodEl.value) {
    overlay.draft.goal = `${rawGoal} ${periodEl.value}`;
  }
  let saved;
  try { saved = await api('/api/project', { method: 'PUT', body: overlay.draft }); } catch (error) { saved = { errors: {} }; }
  if (!saved.project) { overlay.errors = saved.errors || {}; return renderOverlay(); }
  S.project = saved.project;
  S.simPrice = S.simCost = S.simVat = S.simShip = S.simFeePct = S.simRetPct = S.simItFee = null;
  S.overlay = null; render();
  if (overlay.thenSearch && S.pending) gate(S.pending);
}
async function makeBrief(options = {}) {
  const request = S.result.request;
  const before = (S.overlay && S.overlay.type === 'brief' && S.overlay.made) || { ads: request.deep, frames: request.frames };
  const ads = options.ads ?? before.ads, frames = options.frames ?? before.frames;
  try {
    const made = await api('/api/brief', { method: 'POST', body: { job_id: S.jobId, level: request.level, ads, frames, lang: S.lang } });
    S.overlay = { type: 'brief', made }; renderOverlay();
  } catch (error) {
    if (error.data && error.data.error === 'project_required') openProject(false);
  }
}

const ACTIONS = {
  mode(value) { S.mode = value; S.pages = null; S.cmp = null; S.notice = null; S.durataBusy = false; S.durataError = false; render(); if (value === 'news') loadHistory(); },
  'news-open': openNews, 'news-refresh': refreshSubject,
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
  'link-go'() { const overwrite = S.overlay.overwrite; S.overlay = null; renderOverlay(); runConnect(overwrite); },
  'link-test': testLink,
  async 'link-copy'() { S.link.copy = (await copyText(exampleSentence())) ? 'ok' : 'failed'; renderWay(); },
  'way-copy'() {
    const r = S.result;
    if (r && S.jobId && S.resultMode !== 'compare' && r.request && r.request.level !== 'data') { S.link.hint = false; renderWay(); return makeBrief(); }
    S.link.hint = true; renderWay();
  },
  'how-open'() { S.overlay = { type: 'how', step: 1 }; renderOverlay(); },
  'how-next'() { S.overlay.step = Math.min(3, S.overlay.step + 1); renderOverlay(); },
  'how-prev'() { S.overlay.step = Math.max(1, S.overlay.step - 1); renderOverlay(); },
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
    S.cmp.sides[Number(el.dataset.side)].picked = value;
    if (S.cmp.sides.every((side) => side.picked)) launchCompare(); else renderResults();
  },
  'open-ad'(value) { S.overlay = { type: 'ad', id: value }; renderOverlay(); },
  close() { S.overlay = null; renderOverlay(); },
  async 'copy-brief'() {
    const made = S.overlay.made;
    if (await copyText(made.text)) briefStatus(t('brief.copied'));
    else briefStatus(t('brief.copy.failed', { folder: made.folder_name }), true);
  },
  async 'copy-command'() {
    const made = S.overlay.made;
    if (await copyText(t(`brief.command.${made.level}`, { folder: made.folder }))) briefStatus(t('brief.copied.command'));
    else briefStatus(t('brief.copy.failed.command'), true);
  },
  async 'open-frames'() {
    try {
      await api('/api/frames/open', { method: 'POST', body: { key: S.overlay.made.frames_key } });
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
  pop.style.zIndex = '40';
  const vw = window.innerWidth;
  const w = Math.min(pop.offsetWidth || 280, vw - 24);
  const b = btn.getBoundingClientRect();
  _helpAnchor = { btn, left: b.left, top: b.top, at: performance.now() };
  const preferRight = pop.classList.contains('right');
  const rawLeft = preferRight ? b.right - w : b.left;
  const left = Math.max(12, Math.min(rawLeft, vw - w - 12));
  pop.style.width = `${w}px`;
  pop.style.left = `${left}px`;
  const h = pop.offsetHeight || 160;
  let top = b.bottom + 8;
  if (top + h > window.innerHeight - 12 && b.top - h - 8 >= 12) {
    top = b.top - h - 8;
  }
  pop.style.top = `${Math.max(12, top)}px`;
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
    }
  }
  if (el.dataset.sim) {
    if (el.dataset.sim === 'price') S.simPrice = Number(el.value || 0);
    if (el.dataset.sim === 'cost') S.simCost = Number(el.value || 0);
    if (el.dataset.sim === 'vat') S.simVat = Number(el.value || 0);
    if (el.dataset.sim === 'ship') S.simShip = Number(el.value || 0);
    if (el.dataset.sim === 'feePct') S.simFeePct = Number(el.value || 0);
    if (el.dataset.sim === 'retPct') S.simRetPct = Number(el.value || 0);
    updateSimDom();
  }
});
document.addEventListener('change', (event) => {
  const el = event.target;
  if (el.dataset.change === 'frames') { S.frames = el.checked; refreshEstimate(); }
  if (el.dataset.change === 'brief-frames') makeBrief({ frames: el.checked });
  if (el.dataset.bind === 'country') {
    S.country = el.value;
    if (S.simItFee === null && $('[data-sim-check="itFee"]')) {
      $('[data-sim-check="itFee"]').checked = ((S.project && S.project.market) || S.country) === 'IT';
      updateSimDom();
    }
  }
  if (el.dataset.simCheck === 'itFee') { S.simItFee = el.checked; updateSimDom(); }
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape') {
    if ($('.help-wrap.open')) { closeHelp(); return; }
    if (S.overlay) ACTIONS.close();
  }
  if (event.key === 'Enter' && event.target.dataset && event.target.dataset.bind && !S.job && !S.busy) submit();
});

(async function start() {
  T = await (await fetch('/static/strings.json', { cache: 'no-store' })).json();
  try {
    const state = await api('/api/state');
    S.project = state.project; S.deepChoices = state.deep_choices;
  } catch { /* the page still works without the saved card */ }
  render();
  refreshEstimate();
  loadLink();
})();
