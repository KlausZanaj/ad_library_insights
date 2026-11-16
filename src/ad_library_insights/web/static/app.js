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

const S = {
  lang: store.get('lang', 'it'), theme: store.get('theme', 'light'),
  mode: 'keyword', level: 'data', deep: 10, frames: false, deepChoices: [10, 20, 50],
  country: 'IT', query: '', company: '', companyB: '', cmp: null, resultMode: null,
  pages: null, busy: null, job: null, result: null, jobId: null, notice: null,
  project: null, overlay: null, estimate: null, pending: null,
  history: null, news: null, sort: 'score',
};
let T = { it: {}, en: {} };

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
const num = (value) => (value == null ? '—' : new Intl.NumberFormat(S.lang, { useGrouping: 'always' }).format(value));
const pct = (share) => `${Math.round((share || 0) * 100)}%`;
/* A number with its noun, singular for one: count(1, 'n.days') is "1 giorno" / "1 day". */
const count = (n, key) => t(`${key}.${n === 1 ? 'one' : 'other'}`, { n: num(n) });
const days = (n) => (n == null ? '—' : count(n, 'n.days'));
/* An age span as the targeting has it; 65 is the top Meta offers and means 65 and over. */
function ageRange(low, high) {
  if (low == null && high == null) return '—';
  return `${low ?? 18}-${high == null ? 65 : high}${high == null || high >= 65 ? '+' : ''}`;
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
  ? `<img class="avatar${big ? ' big' : ''}" src="${esc(src)}" alt="">`
  : `<span class="avatar txt${big ? ' big' : ''}">${esc(initials(name))}</span>`);
const firstLine = (ad) => ((ad.body || '').trim().split('\n')[0] || ad.headline || '');

async function api(path, options = {}) {
  const init = { method: options.method || 'GET', headers: {} };
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
  const lang = `<div class="switch" role="group" aria-label="${esc(t('lang.label'))}">${toggle('lang', ['it', 'en'], S.lang, (v) => v.toUpperCase())}</div>`;
  let html = `<div class="search-in"><div class="search-head"><div><h1>${esc(t(`mode.${S.mode}`))}</h1><p>${esc(t(`${S.mode}.lead`))}</p></div>${lang}</div>`;
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
  <p class="levels-title"><span>${esc(t('level.title'))}</span><span>${esc(t('level.note'))}</span></p>
  <div class="levels" role="radiogroup">${LEVELS.map((level, depth) => `
    <button class="level" role="radio" data-action="level" data-value="${level}" aria-checked="${level === S.level}" ${locked ? 'disabled' : ''}>
      <span class="lv-head"><strong>${esc(t(`level.${level}`))}</strong><span class="steps" aria-hidden="true">${[0, 1, 2].map((n) => `<i${n <= depth ? ' class="on"' : ''}></i>`).join('')}</span></span>
      <span class="lv-q">${esc(t(`level.${level}.q`))}</span>
      <span class="lv-list">${[1, 2, 3].map((n) => `<span>${esc(t(`level.${level}.${n}`))}</span>`).join('')}</span>
      <span class="lv-foot"><span>${esc(t('level.who'))}</span><span>${esc(t(`level.${level}.who`))}</span><span>${esc(t('level.cost'))}</span><span>${esc(t(`level.${level}.use`))}</span></span>
    </button>`).join('')}</div>
  <div class="options">
    <span>${esc(t('deep.before'))}</span>
    <div class="switch" role="group">${toggle('deep', S.deepChoices, S.deep, String)}</div>
    <span>${esc(t('deep.after'))}${S.estimate && S.estimate.seconds ? ` · ${esc(t('deep.time', { time: dur(S.estimate.seconds) }))}` : ''}</span>
    <span class="gap"></span>
    <span>${esc(t('project.label'))}:</span>
    <button class="linklike" data-action="project">${esc(S.project
      ? t('project.saved', { product: S.project.product, price: num(S.project.price) }) : t('project.missing'))}</button>
  </div>`;
  if (S.job || S.busy) html += '<div class="progress"><p><span id="ptext"></span><span class="muted num" id="pleft"></span></p><div class="bar" id="pbar"><i></i></div></div>';
  else if (S.notice) html += `<p class="notice${S.notice.err ? ' err' : ''}">${esc(S.notice.text)}</p>`;
  $('#search').innerHTML = `${html}</div>`;
  updateProgress();
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
  return `<div class="sheet"><section><h2 style="margin-bottom:18px">${esc(t('pages.title'))}</h2><table>
    <thead><tr><th>${esc(t('pages.page'))}</th><th>${esc(t('pages.category'))}</th><th class="r">${esc(t('pages.followers'))}</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></section></div>`;
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
  if (!d || !d.capped) return '';
  let text = t(d.concepts === 1 ? 'deep.capped.one' : 'deep.capped.other',
    { n: num(d.concepts), requested: num(d.requested), ceiling: num(d.ceiling) });
  if (d.left_out) text += ` ${count(d.left_out, 'deep.left')}`;
  return `<section class="changes capped"><p>${esc(text)}</p></section>`;
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
  const reused = s.copy_patterns.reused_texts.slice(0, 4).map((row) => `<li><span>${esc(row.opening)}</span><span>${esc(t('f.reused.n', { n: row.creatives }))}</span></li>`).join('');
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
function reachCells(ad) {
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
function tableSection(r) {
  const company = r.mode === 'company';
  const ads = [...r.ads].sort(SORTS[S.sort] || SORTS.score);
  const rows = ads.map((ad, index) => `<tr class="pick" data-action="open-ad" data-value="${esc(ad.library_id)}">
    <td class="rank">${index + 1}</td>
    <td><div class="adcell">${ad.thumbnail ? `<img class="thumb" src="${esc(ad.thumbnail)}" alt="" loading="lazy">` : '<span class="thumb"></span>'}
      <div class="adtext"><div>${esc(firstLine(ad) || t('t.notext'))}</div><small>${esc([company ? t(`format.${ad.media_type || 'unknown'}`) : ad.advertiser, company ? ad.cta : '', kindTag(ad)].filter(Boolean).join(' · '))}</small></div></div></td>
    <td class="tier">${verdictCell(ad)}</td>
    <td class="r">${Math.round(ad.score)}</td><td class="r">${num(ad.days_running)}</td><td class="r">${num(ad.creatives)}</td>
    ${company ? '' : `<td class="fmt">${esc(t(`format.${ad.media_type || 'unknown'}`))}</td>`}${reachCells(ad)}</tr>`).join('');
  const opened = r.deep ? r.deep.read : r.ads.reduce((sum, ad) => sum + (ad.reach ? 1 : 0) + Object.keys(ad.card_reach || {}).length, 0);
  const concepts = r.deep ? r.deep.concepts : r.ads.filter((ad) => ad.reach).length;
  return `<section><div class="sortbar"><span>${esc(t('sort.by'))}</span><div class="switch" role="group">${toggle('sort', ['score', 'perday', 'days'], S.sort, (v) => t(`sort.${v}`))}</div></div>
    <table class="ads${company ? '' : ' mixed'}"><thead><tr><th></th><th>${esc(t('t.ad'))}</th><th>${esc(t('t.tier'))}</th>
    <th class="r">${esc(t('t.score'))}</th><th class="r">${esc(t('t.days'))}</th><th class="r">${esc(t('t.creatives'))}</th>
    ${company ? '' : `<th>${esc(t('t.format'))}</th>`}<th class="r">${esc(t('t.reached', { country: region(r.country) }))}</th><th class="r">${esc(t('t.perday'))}</th></tr></thead>
    <tbody>${rows}</tbody></table><p class="tablenote">${esc(t(concepts === 1 ? 't.note.one' : 't.note', { concepts: count(concepts, 'n.concepts'), opened: count(opened, 'n.ads') }))}</p></section>`;
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
  el.innerHTML = `<div class="sheet">${headSection(r)}${readySection(r)}${cappedSection(r)}${changesSection(r)}${metricsSection(r)}${factsSection(r)}${tableSection(r)}</div>`;
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
    return `<div class="sheet"><section><h2 style="margin-bottom:18px">${esc(t('cmp.pick', { name: side.name }))}</h2><table>
      <thead><tr><th>${esc(t('pages.page'))}</th><th>${esc(t('pages.category'))}</th><th class="r">${esc(t('pages.followers'))}</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></section></div>`;
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
  const top = (side) => `<div><table class="ads"><tbody>${side.ads.slice(0, 5).map((ad) => `<tr class="pick" data-action="open-ad" data-value="${esc(ad.library_id)}">
    <td><div class="adcell">${ad.thumbnail ? `<img class="thumb" src="${esc(ad.thumbnail)}" alt="" loading="lazy">` : '<span class="thumb"></span>'}
      <div class="adtext"><div>${esc(firstLine(ad) || t('t.notext'))}</div><small>${esc(`${t(`verdict.${ad.verdict}`)} · ${days(ad.days_running)} · ${t('f.reused.n', { n: num(ad.creatives) })}`)}</small></div></div></td>
    <td class="r">${Math.round(ad.score)}</td></tr>`).join('')}</tbody></table></div>`;
  return `<div class="sheet">
    <section class="cmphead">${head(a)}${head(b)}</section>
    <section><h2>${esc(t('cmp.highlights'))}</h2>${notes ? `<ul class="notes">${notes}</ul>` : `<p class="muted" style="margin-top:8px">${esc(t('cmp.none'))}</p>`}
      <p class="tablenote">${esc(t('cmp.note'))}</p></section>
    <section><table class="cmp"><thead><tr><th></th><th>${esc(c.names.a)}</th><th>${esc(c.names.b)}</th></tr></thead><tbody>${rows}</tbody></table></section>
    <section><h2 style="margin-bottom:14px">${esc(t('cmp.top'))}</h2><div class="tops">${top(a)}${top(b)}</div>
      <p class="tablenote"><button class="linklike" data-action="guide">${esc(t('link.guide'))}</button></p></section>
  </div>`;
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
  const body = ads.length ? `<table class="ads"><thead><tr><th>${esc(t('t.ad'))}</th>${extraHead}<th class="r">${esc(t('news.started'))}</th><th class="r">${esc(t('news.ran'))}</th><th class="r">${esc(t('t.score'))}</th></tr></thead>
    <tbody>${ads.map((ad) => `<tr><td>${adCell(ad, keyword)}</td>${extraCell(ad)}<td class="r">${ad.started ? esc(day(ad.started)) : '—'}</td><td class="r">${num(ad.days_running)}</td><td class="r">${(ad.score ?? ad.longevity_score) == null ? '—' : Math.round(ad.score ?? ad.longevity_score)}</td></tr>`).join('')}</tbody></table>`
    : `<p class="muted">${esc(t('news.none'))}</p>`;
  return `<section><div class="listhead"><h2>${esc(title)}</h2><span>${ads.length}</span></div>${body}</section>`;
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
    <section class="rhead"><div class="grow"><h1>${esc(title)}</h1><p>${esc(t('news.span', { from: stamp(c.previous.taken_at), to: stamp(c.current.taken_at), gap: c.days_between < 1 ? t('gap.hours', { n: Math.max(1, Math.round(c.days_between * 24)) }) : days(Math.round(c.days_between)) }))}</p></div>
      <div class="rlinks"><button class="linklike" data-action="news-refresh" data-value="${esc(c.subject.key)}">${esc(t('news.refresh'))}</button></div></section>
    <section class="metrics three">${cells.map(([value, label, why]) => `<div class="metric"><b>${num(value)}</b><span>${esc(label)}</span><small>${esc(why)}</small></div>`).join('')}</section>
    ${c.sample ? `<section><p class="muted">${esc(t('news.sample'))}</p></section>` : ''}
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
  el.innerHTML = `<div class="sheet"><section><h2 style="margin-bottom:18px">${esc(t('news.saved'))}</h2><table>
    <thead><tr><th>${esc(t('news.subject'))}</th><th>${esc(t('news.kind'))}</th><th>${esc(t('field.country'))}</th><th class="r">${esc(t('news.count'))}</th><th class="r">${esc(t('news.last'))}</th><th></th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></section></div>${S.news ? newsDetail(S.news) : ''}`;
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
  const cardsNote = ad.reach_total == null || (ad.cards || 1) < 2 ? ''
    : (ad.reach_cards_read || 1) > 1 ? t('d.reach.cards', { k: ad.reach_cards_read, n: ad.cards }) : t('d.reach.cards.one', { n: ad.cards });
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
      ${cardsNote ? `<p class="smallnote">${esc(cardsNote)}</p>` : ''}
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
    <section><h3>${esc(t('d.score', { score: Math.round(ad.score) }))} · ${esc(t(`verdict.${ad.verdict}`))}</h3>
      <div class="scorebar three">${['scale', 'staying', 'creative'].map((part) => `<i style="width:${points[part]}%"></i>`).join('')}</div>
      <dl>
        <dt>${esc(t('d.part.scale'))}</dt><dd>${esc(t('d.score.of', { n: num(Math.round(points.scale)), max: weights.scale }))} <span class="muted">· ${esc(scaleWhy)}</span></dd>
        <dt>${esc(t('d.part.staying'))}</dt><dd>${esc(t('d.score.of', { n: num(Math.round(points.staying)), max: weights.staying }))} <span class="muted">· ${esc(t('d.staying.days', { days: days(ad.days_running) }))}</span></dd>
        <dt>${esc(t('d.part.creative'))}</dt><dd>${esc(t('d.score.of', { n: num(Math.round(points.creative)), max: weights.creative }))} <span class="muted">· ${esc(t('d.creative.n', { n: num(ad.creatives) }))}</span></dd>
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
  return `<div class="dialog" role="dialog" aria-modal="true"><h2>${esc(t('proj.title'))}</h2><p class="lead">${esc(t('proj.lead'))}</p>
    <div class="form">
      ${field('product', 'proj.product', input('product'), true)}
      ${field('price', 'proj.price', input('price'))}
      ${field('product_cost', 'proj.cost', input('product_cost'))}
      ${field('market', 'proj.market', `<select data-pf="market">${countryOptions(p.market || S.country)}</select>`)}
      ${field('goal', 'proj.goal', input('goal', 'proj.goal.hint'))}
      ${field('main_problem', 'proj.problem', input('main_problem', 'proj.problem.hint'), true)}
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
function openProject(thenSearch) {
  S.overlay = { type: 'project', draft: { ...(S.project || { market: S.country }) }, thenSearch };
  renderOverlay();
}
async function saveProject() {
  const overlay = S.overlay;
  document.querySelectorAll('[data-pf]').forEach((el) => { overlay.draft[el.dataset.pf] = el.value; });
  try {
    S.project = (await api('/api/project', { method: 'PUT', body: overlay.draft })).project;
  } catch (error) { overlay.errors = (error.data && error.data.errors) || {}; return renderOverlay(); }
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
  mode(value) { S.mode = value; S.pages = null; S.cmp = null; S.notice = null; render(); if (value === 'news') loadHistory(); },
  'news-open': openNews, 'news-refresh': refreshSubject,
  sort(value) { S.sort = value; renderResults(); },
  theme(value) { S.theme = value; store.set('theme', value); renderTop(); },
  lang(value) { S.lang = value; store.set('lang', value); render(); },
  level(value) { S.level = value; renderSearch(); refreshEstimate(); },
  deep(value) { S.deep = Number(value); renderSearch(); renderOverlay(); refreshEstimate(); },
  submit, guide() { S.overlay = { type: 'guide' }; renderOverlay(); },
  project() { openProject(false); },
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
document.addEventListener('click', (event) => {
  const el = event.target.closest('[data-action]');
  if (!el || el.disabled) return;
  const action = ACTIONS[el.dataset.action];
  if (action) action(el.dataset.value, el);
});
document.addEventListener('input', (event) => {
  const el = event.target;
  if (el.dataset.bind) S[el.dataset.bind] = el.value;
});
document.addEventListener('change', (event) => {
  const el = event.target;
  if (el.dataset.change === 'frames') { S.frames = el.checked; refreshEstimate(); }
  if (el.dataset.change === 'brief-frames') makeBrief({ frames: el.checked });
  if (el.dataset.bind === 'country') S.country = el.value;
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && S.overlay) ACTIONS.close();
  if (event.key === 'Enter' && event.target.dataset && event.target.dataset.bind && !S.job && !S.busy) submit();
});

(async function start() {
  T = await (await fetch('/static/strings.json')).json();
  try {
    const state = await api('/api/state');
    S.project = state.project; S.deepChoices = state.deep_choices;
  } catch { /* the page still works without the saved card */ }
  render();
  refreshEstimate();
})();
