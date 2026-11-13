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
  country: 'IT', query: '', company: '',
  pages: null, busy: null, job: null, result: null, jobId: null, notice: null,
  project: null, overlay: null, estimate: null, pending: null,
  history: null, news: null,
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
  if (!active) {
    if (S.mode !== 'news') html += `<p class="notice">${esc(t('soon'))}</p>`;
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
    <span>${esc(t('deep.after'))}${S.estimate ? ` · ${esc(t('deep.time', { time: dur(S.estimate.seconds) }))}` : ''}</span>
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
    else if (phase === 'list' && S.job.params.mode === 'company') label = t('phase.list.company');
    else label = t(`phase.${phase}`);
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
  const sub = company ? `${esc(t('result.sub.company', { category: page.category || '—', followers: num(page.followers), country: region(r.country) }))}<br>${esc(loaded)}` : esc(loaded);
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
function placeNames(places, total) {
  if (!places.length) return esc(t('f.places.none'));
  const shown = places.slice(0, 12).map((place) => {
    const count = total && place.ads < total ? ` ${t('f.places.count', { n: place.ads, total })}` : '';
    return esc(placeLabel(place)) + (count ? `<span class="dim">${esc(count)}</span>` : '');
  });
  return shown.join(', ') + (places.length > 12 ? `<span class="dim"> +${places.length - 12}</span>` : '');
}
const shareRows = (rows, label) => `<ul class="rows">${rows.slice(0, 5).map((row) => `<li><span>${esc(label(row))}</span><span>${pct(row.share)}</span></li>`).join('') || `<li><span class="dim">—</span></li>`}</ul>`;
function factsSection(r) {
  const s = r.signals, audience = s.audience, reach = s.reach;
  const places = audience && audience.locations_included.length
    ? `<dl><dt>${esc(t('f.places.in'))}</dt><dd>${placeNames(audience.locations_included, audience.ads_with_audience)}</dd>
       <dt>${esc(t('f.places.out'))}</dt><dd>${placeNames(audience.locations_excluded, audience.ads_with_audience)}</dd></dl>
       <p class="note">${esc(t('f.places.note'))}</p>`
    : `<p class="note" style="margin-top:0">${esc(t('f.places.unread'))} ${esc(t('f.places.note'))}</p>`;
  const who = audience ? `<dl>
      <dt>${esc(t('f.audience.age'))}</dt><dd>${audience.age_ranges.slice(0, 3).map((a) => `${a.age_min}–${a.age_max}${a.age_max >= 65 ? '+' : ''}`).join(', ')}</dd>
      <dt>${esc(t('f.audience.gender'))}</dt><dd>${Object.keys(audience.genders).map((g) => esc(t(`gender.${g}`))).join(', ')}</dd>
      <dt>${esc(t('f.audience.breadth'))}</dt><dd>${Object.keys(audience.breadth).map((b) => esc(t(`breadth.${b}`))).join(', ') || '—'}</dd></dl>`
    : '<p class="dim">—</p>';
  const coverage = reach.available ? `<dl>
      <dt>${esc(t('f.reach.eu'))}</dt><dd class="num">${num(reach.eu_reach_summed)}</dd>
      ${reach.country_reach_summed != null ? `<dt>${esc(region(reach.country))}</dt><dd class="num">${num(reach.country_reach_summed)}</dd>` : ''}
      <dt>${esc(t('f.reach.uk'))}</dt><dd class="num">${reach.uk_reach_summed ? num(reach.uk_reach_summed) : '—'}</dd></dl>
      <p class="note">${esc(t('f.reach.note', { n: reach.ads_with_reach }))}</p>`
    : `<p class="note" style="margin-top:0">${esc(t('f.reach.none'))}</p>`;
  const reused = s.copy_patterns.reused_texts.slice(0, 4).map((row) => `<li><span>${esc(row.opening)}</span><span>${esc(t('f.reused.n', { n: row.ads }))}</span></li>`).join('');
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
  if (!ad.reach) return '<td class="r dim">—</td><td class="r dim">—</td><td class="r dim">—</td>';
  if (!ad.reach.available) return `<td class="r dim" colspan="3">${esc(t('t.nopub'))}</td>`;
  return `<td class="r">${ad.reach.eu_total == null ? '—' : num(ad.reach.eu_total)}</td><td class="r">${num(ad.reach.country_reach)}</td><td class="r">${num(ad.reach_per_day)}</td>`;
}
function tableSection(r) {
  const company = r.mode === 'company';
  const rows = r.ads.map((ad, index) => `<tr class="pick" data-action="open-ad" data-value="${esc(ad.library_id)}">
    <td class="rank">${index + 1}</td>
    <td><div class="adcell">${ad.thumbnail ? `<img class="thumb" src="${esc(ad.thumbnail)}" alt="" loading="lazy">` : '<span class="thumb"></span>'}
      <div class="adtext"><div>${esc(firstLine(ad) || t('t.notext'))}</div><small>${esc(company ? [t(`format.${ad.media_type || 'unknown'}`), ad.cta].filter(Boolean).join(' · ') : ad.advertiser || '')}</small></div></div></td>
    <td class="tier"><span class="tier-${ad.tier}">${esc(t(`tier.${ad.tier}`))}</span>${ad.needs_review ? `<span class="review">${esc(t('flag.review'))}</span>` : ''}</td>
    <td class="r">${Math.round(ad.longevity_score)}</td><td class="r">${num(ad.days_running)}</td><td class="r">${num(ad.repetitions)}</td>
    ${company ? '' : `<td class="fmt">${esc(t(`format.${ad.media_type || 'unknown'}`))}</td>`}${reachCells(ad)}</tr>`).join('');
  const read = r.ads.filter((ad) => ad.reach).length;
  return `<section><table class="ads${company ? '' : ' mixed'}"><thead><tr><th></th><th>${esc(t('t.ad'))}</th><th>${esc(t('t.tier'))}</th>
    <th class="r">${esc(t('t.score'))}</th><th class="r">${esc(t('t.days'))}</th><th class="r">${esc(t('t.reuse'))}</th>
    ${company ? '' : `<th>${esc(t('t.format'))}</th>`}<th class="r">${esc(t('t.eu'))}</th><th class="r">${esc(region(r.country))}</th><th class="r">${esc(t('t.perday'))}</th></tr></thead>
    <tbody>${rows}</tbody></table><p class="tablenote">${esc(t('t.note', { n: read }))}</p></section>`;
}
function renderResults() {
  const el = $('#results');
  if (S.mode === 'news') { renderNews(); return; }
  if (S.pages) { el.innerHTML = pagesSheet(); return; }
  const r = S.result;
  if (!r || !(r.ads || []).length || !(S.mode === 'keyword' || S.mode === 'company')) { el.innerHTML = ''; return; }
  el.innerHTML = `<div class="sheet">${headSection(r)}${readySection(r)}${changesSection(r)}${metricsSection(r)}${factsSection(r)}${tableSection(r)}</div>`;
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
    <tbody>${ads.map((ad) => `<tr><td>${adCell(ad, keyword)}</td>${extraCell(ad)}<td class="r">${ad.started ? esc(day(ad.started)) : '—'}</td><td class="r">${num(ad.days_running)}</td><td class="r">${ad.longevity_score == null ? '—' : Math.round(ad.longevity_score)}</td></tr>`).join('')}</tbody></table>`
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
    <section class="rhead"><div class="grow"><h1>${esc(title)}</h1><p>${esc(t('news.span', { from: stamp(c.previous.taken_at), to: stamp(c.current.taken_at), gap: c.days_between < 1 ? t('gap.hours', { n: Math.max(1, Math.round(c.days_between * 24)) }) : t('gap.days', { n: num(Math.round(c.days_between)) }) }))}</p></div>
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
  const parts = ad.score_parts || { days: 0, reuse: 0 };
  const reach = ad.reach, audience = ad.audience;
  const places = (list) => (list.length ? list.map((p) => esc(placeLabel(p))).join(', ') : esc(t('f.places.none')));
  let reachHtml;
  if (!reach) reachHtml = `<p class="muted">${esc(t('d.reach.unread'))}</p>`;
  else if (!reach.available) reachHtml = `<p class="muted">${esc(t('d.reach.none'))}</p>`;
  else {
    const countries = reach.regions.flatMap((g) => g.countries).sort((a, b) => b.reach - a.reach).slice(0, 8);
    reachHtml = `<dl>
      ${reach.eu_total != null ? `<dt>${esc(t('d.reach.total'))}</dt><dd>${num(reach.eu_total)}</dd>` : ''}
      ${reach.country_reach != null ? `<dt>${esc(region(reach.country))}</dt><dd>${num(reach.country_reach)}</dd>` : ''}
      ${reach.uk_total != null ? `<dt>${esc(t('d.reach.uk'))}</dt><dd>${num(reach.uk_total)}</dd>` : ''}
      <dt>${esc(t('d.reach.perday'))}</dt><dd>${num(ad.reach_per_day)}</dd></dl>
      ${countries.length > 1 ? `<h3 style="margin-top:16px">${esc(t('d.reach.bycountry'))}</h3><ul class="rows">${countries.map((c) => `<li><span>${esc(region(c.country))}</span><span>${num(c.reach)}</span></li>`).join('')}</ul>` : ''}`;
  }
  const review = ad.needs_review ? `<p class="review" style="margin-top:12px;font-size:1rem">${esc(t(ad.review && ad.review.reason.endsWith('low_reach') ? 'd.review.reach' : 'd.review'))}</p>` : '';
  return `<aside class="drawer" role="dialog" aria-modal="true"><header><h2>${esc(ad.advertiser || '')}</h2><button class="x" data-action="close">${esc(t('button.close'))}</button></header><div class="body">
    <section><div class="hero">${ad.thumbnail ? `<img src="${esc(ad.thumbnail)}" alt="">` : ''}<div>
      <p><strong>${esc(ad.status === 'inactive' ? t('d.inactive') : t('d.active', { date: ad.started ? day(ad.started) : '—' }))}</strong></p>
      <p class="muted">${esc(t('d.days', { days: ad.days_running ?? '—' }))} · ${esc(t(`format.${ad.media_type || 'unknown'}`))}</p>
      ${ad.impression_rank ? `<p class="muted">${esc(t('d.rank', { n: ad.impression_rank }))}</p>` : ''}
      <p style="margin-top:10px"><a href="${esc(ad.ad_url)}" target="_blank" rel="noopener">${esc(t('link.meta'))}</a></p></div></div></section>
    <section><h3>${esc(t('d.score', { score: Math.round(ad.longevity_score) }))} · ${esc(t(`tier.${ad.tier}`))}</h3>
      <div class="scorebar"><i style="width:${parts.days}%"></i><i style="width:${parts.reuse}%"></i></div>
      <dl><dt>${esc(t('d.score.days'))}</dt><dd>${esc(t('d.score.of', { n: Math.round(parts.days), max: 60 }))} <span class="muted">· ${esc(t('d.days', { days: ad.days_running ?? '—' }))}</span></dd>
      <dt>${esc(t('d.score.reuse'))}</dt><dd>${esc(t('d.score.of', { n: Math.round(parts.reuse), max: 40 }))} <span class="muted">· ${esc(t('d.score.reuse.n', { n: ad.repetitions }))}</span></dd></dl>${review}
      <p style="margin-top:12px"><button class="linklike" data-action="guide">${esc(t('link.guide'))}</button></p></section>
    <section><h3>${esc(t('d.text'))}</h3><p class="copy">${esc(ad.body || t('t.notext'))}</p>
      <dl style="margin-top:14px">${ad.headline ? `<dt>${esc(t('d.headline'))}</dt><dd>${esc(ad.headline)}</dd>` : ''}
      <dt>${esc(t('d.button'))}</dt><dd>${esc(ad.cta || '—')}</dd><dt>${esc(t('d.dest'))}</dt><dd>${esc(ad.landing_domain || '—')}</dd>
      <dt>${esc(t('d.platforms'))}</dt><dd>${(ad.platforms || []).map((p) => esc(PLATFORMS[p] || p)).join(', ') || '—'}</dd></dl></section>
    <section><h3>${esc(t('d.reach'))}</h3>${reachHtml}</section>
    ${audience ? `<section><h3>${esc(t('d.audience'))}</h3><dl>
      <dt>${esc(t('f.audience.age'))}</dt><dd>${audience.age_min}–${audience.age_max}${audience.age_max >= 65 ? '+' : ''}</dd>
      <dt>${esc(t('f.audience.gender'))}</dt><dd>${esc(t(`gender.${audience.gender || 'All'}`))}</dd>
      <dt>${esc(t('f.places.in'))}</dt><dd>${places(audience.locations_included)}</dd>
      <dt>${esc(t('f.places.out'))}</dt><dd>${places(audience.locations_excluded)}</dd></dl>
      <p class="smallnote">${esc(t('f.places.note'))}</p></section>` : ''}
    ${(ad.frames || []).length ? `<section><h3>${esc(t('d.frames'))}</h3><div class="frames">${ad.frames.map((src) => `<img src="${esc(src)}" alt="">`).join('')}</div></section>` : ''}
  </div></aside>`;
}
function guideDrawer() {
  const items = [1, 2, 3, 4, 5, 6].map((n) => `<section class="qa"><h3>${esc(t(`guide.q${n}`))}</h3><p>${esc(t(`guide.a${n}`))}</p>${n === 3 ? `<p class="eg muted">${esc(t('guide.example'))}</p>` : ''}</section>`).join('');
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
      <div><span class="k">${esc(t('confirm.frames'))}</span><span class="v"><label class="check"><input type="checkbox" data-change="frames" ${S.frames ? 'checked' : ''}>${esc(t('confirm.frames.on'))}</label><span class="muted">${esc(t('confirm.images', { n: num(e.images ?? 0) }))}</span></span></div>
      <div><span class="k">${esc(t('confirm.tokens'))}</span><span class="v">${esc(t('confirm.tokens.v', { n: num(e.tokens ?? 0) }))}</span></div>
      <div><span class="k">${esc(t('confirm.band'))}</span><span class="v big">${esc(e.band ? t(`band.${e.band}`) : '—')}</span></div>
      <div><span class="k">${esc(t('confirm.time'))}</span><span class="v">${e.seconds ? esc(dur(e.seconds)) : '—'}</span></div>
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
  return `<div class="dialog wide" role="dialog" aria-modal="true"><h2>${esc(t(`brief.title.${made.level}`))}</h2><p class="lead">${esc(t('brief.how'))}</p>
    <textarea class="brieftext" id="brieftext" readonly>${esc(made.text)}</textarea>
    <p class="smallnote">${esc(t('brief.size', { n: num(made.size.tokens), band: t(`band.${made.size.band}`).toLowerCase() }))}</p>
    ${made.images.length ? `<p class="smallnote">${esc(t('brief.attach', { n: made.images.length }))}</p><ul class="attach">${made.images.map((path) => `<li>${esc(path)}</li>`).join('')}</ul>` : ''}
    <div class="foot"><button class="btn quiet" data-action="close">${esc(t('button.close'))}</button><button class="btn" data-action="copy-brief">${esc(t('button.copy'))}</button></div></div>`;
}
function renderOverlay() {
  const overlay = S.overlay, el = $('#overlay');
  if (!overlay) { el.innerHTML = ''; return; }
  let inner = '';
  if (overlay.type === 'ad') {
    const ad = S.result && S.result.ads.find((item) => item.library_id === overlay.id);
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
    S.job = await api('/api/jobs', { method: 'POST', body: { ...S.pending, level: S.level, deep: S.deep, frames: S.frames } });
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
  if (!job.result.ads || !job.result.ads.length) return note(`error.${job.result.outcome === 'blocked' ? 'blocked' : 'no_results'}`);
  S.result = job.result; S.jobId = job.id; render();
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
async function makeBrief() {
  const request = S.result.request;
  try {
    const made = await api('/api/brief', { method: 'POST', body: { job_id: S.jobId, level: request.level, ads: request.deep, frames: request.frames, lang: S.lang } });
    S.overlay = { type: 'brief', made }; renderOverlay();
  } catch (error) {
    if (error.data && error.data.error === 'project_required') openProject(false);
  }
}

const ACTIONS = {
  mode(value) { S.mode = value; S.pages = null; S.notice = null; render(); if (value === 'news') loadHistory(); },
  'news-open': openNews, 'news-refresh': refreshSubject,
  theme(value) { S.theme = value; store.set('theme', value); renderTop(); },
  lang(value) { S.lang = value; store.set('lang', value); render(); },
  level(value) { S.level = value; renderSearch(); refreshEstimate(); },
  deep(value) { S.deep = Number(value); renderSearch(); renderOverlay(); refreshEstimate(); },
  submit, guide() { S.overlay = { type: 'guide' }; renderOverlay(); },
  project() { openProject(false); },
  'save-project': saveProject, 'confirm-go': launch, brief: makeBrief,
  'choose-page'(value) { gate({ mode: 'company', page_id: value }); },
  'open-ad'(value) { S.overlay = { type: 'ad', id: value }; renderOverlay(); },
  close() { S.overlay = null; renderOverlay(); },
  async 'copy-brief'(value, el) {
    const box = $('#brieftext');
    try { await navigator.clipboard.writeText(box.value); } catch { box.select(); document.execCommand('copy'); }
    el.textContent = t('button.copied');
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
