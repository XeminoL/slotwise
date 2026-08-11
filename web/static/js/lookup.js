const SUGGEST_MIN_CHARS = 2;
const SUGGEST_DEBOUNCE_MS = 120;
const SUGGEST_BLUR_HIDE_MS = 180;
const TEXTAREA_BASE_HEIGHT = 56;
const TEXTAREA_MULTILINE_AT = 58;
const TEXTAREA_MAX_HEIGHT = 140;
const ALT_CANDIDATE_LIMIT = 2;
const PICK_HEAT_UNMEASURED = -1;
const COMPANION_LIMIT = 3;
const STEP_DELAY_MS = 340;
const STEP_LAST_DELAY_MS = 220;
const STATUS_RESET_MS = 1800;
const RESET_FEEDBACK_MS = 1500;
const EXPORT_FILENAME = 'suggested_locations.xlsx';

const PLACE_STEPS = [
  'Reading companion history...',
  'Scoring candidate aisles...',
  'Choosing a free cell...',
  'Done.',
];

const TRAILING_SEGMENT = /^([\s\S]*,\s*)?[^,]*$/;
const SEGMENT_SPLIT = /[\n,]+/;

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

const qText = $('#qText');
const acBox = $('#acBox');
let pickTarget = null;
let allSkus = null;

function autosize(){
  qText.style.height = TEXTAREA_BASE_HEIGHT + 'px';
  if(qText.value.indexOf('\n') >= 0 || qText.scrollHeight > TEXTAREA_MULTILINE_AT){
    qText.classList.add('multi');
    qText.style.height = Math.min(qText.scrollHeight, TEXTAREA_MAX_HEIGHT) + 'px';
  } else {
    qText.classList.remove('multi');
  }
  $('#qClear').style.display = qText.value.trim() ? 'flex' : 'none';
}

function bareCode(value){
  return String(value || '').replace(/^(sku|sp)[-\s]?/i,'').trim();
}

function canSuggest(query){
  return String(query || '').trim().length >= SUGGEST_MIN_CHARS;
}

function lastSegment(text){
  return text.split(SEGMENT_SPLIT).pop().trim();
}

function replaceLastSegment(text, code, suffix=''){
  const m = text.match(TRAILING_SEGMENT);
  return (m && m[1] ? m[1] : '') + code + suffix;
}

function codesOnCards(){
  const codes = new Set();
  (QRESULTS||[]).forEach(r=>{
    if(r.id) codes.add(String(r.id));
    [r.typed, r.item, r.name].forEach(value=>{
      const code = bareCode(value);
      if(code) codes.add(code.toUpperCase());
    });
  });
  return codes;
}

function isDuplicate(existing, entry){
  if(entry && entry.id && existing.has(String(entry.id))) return true;
  return existing.has(bareCode(entry && entry.code).toUpperCase());
}

async function fetchSuggestions(query){
  const res = await fetch('/api/suggest?q=' + encodeURIComponent(query));
  return res.json();
}

function suggestionHtml(entry, index, duplicate){
  return `<div data-i="${index}"${duplicate ? ' class="dup"' : ''}><span class="c">${entry.code}</span>`
    + `<span class="n">${entry.name||''}</span>`
    + (duplicate ? '<span class="dupmsg">added</span>' : '') + '</div>';
}

function hideSuggestions(){
  acBox.classList.add('hide');
  acItems = [];
  acIndex = -1;
}

let acItems = [], acIndex = -1, acTimer = null, acSeq = 0;

async function loadSuggestions(){
  const query = lastSegment(qText.value);
  if(!canSuggest(query)){ hideSuggestions(); return; }
  const seq = ++acSeq;
  try{
    const entries = await fetchSuggestions(query);
    if(seq !== acSeq) return;
    if(!entries.length){ hideSuggestions(); return; }
    const existing = codesOnCards();
    acItems = entries.map(entry => Object.assign({}, entry, {duplicate: isDuplicate(existing, entry)}));
    acIndex = -1;
    acBox.innerHTML = acItems.map((entry,i)=> suggestionHtml(entry, i, entry.duplicate)).join('');
    acBox.classList.remove('hide');
    acBox.querySelectorAll('div').forEach(el=> el.onclick = ()=> pickSuggestion(+el.dataset.i));
  } catch(e){
    if(seq === acSeq) hideSuggestions();
  }
}

function pickSuggestion(index){
  const entry = acItems[index];
  if(!entry) return;
  if(entry.duplicate){ showErr('#qErr', entry.code + ' is already in the list.'); return; }
  qText.value = replaceLastSegment(qText.value, entry.code);
  hideSuggestions();
  autosize();
  qText.focus();
}

function moveSuggestion(step){
  for(let n = 0; n < acItems.length; n++){
    acIndex = (acIndex + step + acItems.length) % acItems.length;
    if(!acItems[acIndex].duplicate) break;
  }
  acBox.querySelectorAll('div').forEach((el,i)=> el.classList.toggle('on', i === acIndex));
}

function attachAutocomplete(input, box){
  let entries = [], seq = 0, timer = null;
  const hide = ()=> box.classList.add('hide');
  async function look(){
    const query = lastSegment(input.value);
    if(!canSuggest(query)){ hide(); return; }
    const my = ++seq;
    try{
      const found = await fetchSuggestions(query);
      if(my !== seq) return;
      if(!found.length){ hide(); return; }
      entries = found;
      box.innerHTML = entries.map((entry,i)=> suggestionHtml(entry, i, false)).join('');
      box.classList.remove('hide');
      box.querySelectorAll('div').forEach(el=> el.onclick = ()=>{
        input.value = replaceLastSegment(input.value, entries[+el.dataset.i].code, ', ');
        hide();
        input.focus();
      });
    } catch(e){ if(my === seq) hide(); }
  }
  input.addEventListener('input', ()=>{ clearTimeout(timer); timer = setTimeout(look, SUGGEST_DEBOUNCE_MS); });
  input.addEventListener('blur', ()=> setTimeout(hide, SUGGEST_BLUR_HIDE_MS));
}

qText.addEventListener('input', autosize);
qText.addEventListener('input', ()=>{ clearTimeout(acTimer); acTimer = setTimeout(loadSuggestions, SUGGEST_DEBOUNCE_MS); });
qText.addEventListener('keydown', e=>{
  const open = !acBox.classList.contains('hide') && acItems.length;
  if(open && (e.key === 'ArrowDown' || e.key === 'ArrowUp')){
    e.preventDefault();
    moveSuggestion(e.key === 'ArrowDown' ? 1 : -1);
    return;
  }
  if(e.key === 'Enter' && !e.shiftKey){
    e.preventDefault();
    if(open && acIndex >= 0){ pickSuggestion(acIndex); return; }
    hideSuggestions();
    doQuery();
  }
  if(e.key === 'Escape') hideSuggestions();
});
document.addEventListener('click', e=>{ if(!e.target.closest('.searchbox')) hideSuggestions(); });

async function loadSkus(){
  if(allSkus) return allSkus;
  try{
    const data = await (await fetch('/api/all-skus')).json();
    allSkus = data.items || [];
    const cats = data.cats || [];
    $('#skuCat').innerHTML = '<option value="">All categories</option>'
      + cats.map(c=>`<option value="${c}">${c}</option>`).join('');
    const datalist = $('#catList');
    if(datalist) datalist.innerHTML = cats.map(c=>`<option value="${c}">`).join('');
  } catch(e){ allSkus = []; }
  return allSkus;
}

function renderSkuList(){
  const filter = ($('#skuFilter').value || '').trim().toLowerCase();
  const cat = $('#skuCat').value;
  const existing = pickTarget === qText ? codesOnCards() : new Set();
  const matches = (allSkus||[]).filter(s=>
    (!cat || s.cat === cat) &&
    (!filter || s.code.toLowerCase().includes(filter) || (s.name||'').toLowerCase().includes(filter)));

  const list = $('#skuList');
  list.innerHTML = matches.map(s=>{
    const duplicate = isDuplicate(existing, s);
    return `<button data-code="${s.code}"${duplicate ? ' class="dup" disabled' : ''}>`
      + `<span class="sc">${s.code}</span><span class="sn">${s.name||''}</span>`
      + (duplicate ? '<span class="dupmsg">added</span>' : '') + '</button>';
  }).join('') || '<div class="nomatch">No matching code.</div>';

  list.querySelectorAll('button:not(.dup)').forEach(b=> b.onclick = ()=>{
    const target = pickTarget || qText;
    const current = target.value.trim();
    target.value = current ? current + ', ' + b.dataset.code : b.dataset.code;
    if(target === qText) autosize();
    $('#skuPanel').classList.add('hide');
    target.focus();
  });
}

async function toggleSkuPanel(target, anchorSelector){
  const panel = $('#skuPanel');
  if(!panel.classList.contains('hide') && pickTarget === target){
    panel.classList.add('hide');
    return;
  }
  pickTarget = target;
  const anchor = $(anchorSelector);
  if(anchor && panel.parentNode !== anchor) anchor.appendChild(panel);
  await loadSkus();
  renderSkuList();
  panel.classList.remove('hide');
}

async function withButtonFeedback(button, action, doneText, failText, resetMs){
  const original = button.textContent;
  try{
    await action();
    button.textContent = doneText;
  } catch(e){
    button.textContent = failText;
  }
  setTimeout(()=>{ button.textContent = original; button.disabled = false; }, resetMs);
}

$('#btnPickSku').onclick = ()=> toggleSkuPanel(qText, '#skuAnchorTop');
$('#skuCat').addEventListener('change', renderSkuList);
$('#skuFilter').addEventListener('input', renderSkuList);

const btnPickComp = $('#btnPickComp');
if(btnPickComp) btnPickComp.onclick = ()=> toggleSkuPanel($('#qComp'), '#skuAnchorBottom');
if($('#qComp') && $('#acComp')) attachAutocomplete($('#qComp'), $('#acComp'));

$('#btnRefreshStock').onclick = ()=>{
  const button = $('#btnRefreshStock');
  button.disabled = true;
  button.textContent = 'Updating...';
  withButtonFeedback(button, ()=> fetch('/api/refresh-stock',{method:'POST'}),
    'Stock updated', 'Error, retry', STATUS_RESET_MS);
};

$('#btnResetSession').onclick = ()=>{
  const button = $('#btnResetSession');
  withButtonFeedback(button, ()=> fetch('/api/reset-session',{method:'POST'}),
    'Session reset', 'Error', RESET_FEEDBACK_MS);
  SESSION = {};
  renderSession();
};

$('#qClear').onclick = ()=>{ qText.value = ''; autosize(); qText.focus(); hideSuggestions(); };
$('#btnQuery').onclick = doQuery;

function parseCodes(text){
  return text.split(SEGMENT_SPLIT).map(segment=>{
    const parts = segment.trim().split(/\s+/).filter(Boolean);
    return parts.length ? {item: parts[0], lpn: parts[1] || ''} : null;
  }).filter(Boolean);
}

function doQuery(){
  let codes = parseCodes(qText.value);
  if(!codes.length){ showErr('#qErr','No item codes given.'); return; }

  const existing = codesOnCards();
  const known = code => existing.has(bareCode(code.item).toUpperCase());
  const duplicates = codes.filter(known).map(c=> c.item);
  codes = codes.filter(c=> !known(c));

  if(!codes.length){
    showErr('#qErr', duplicates.join(', ') + (duplicates.length > 1 ? ' are' : ' is') + ' already in the list.');
    return;
  }
  if(duplicates.length) showErr('#qErr', 'Skipped duplicates: ' + duplicates.join(', '));
  else $('#qErr').classList.add('hide');

  const companions = ($('#qComp')?.value || '').split(SEGMENT_SPLIT)
    .map(s=>s.trim()).filter(Boolean).map(name=>({name}));
  const category = ($('#qCat')?.value || '').trim();
  if(companions.length || category){
    codes.forEach(c=>{
      if(companions.length) c.companions = companions;
      if(category) c.category = category;
    });
  }

  qText.value = '';
  autosize();
  hideSuggestions();
  runPlace(codes);
}

function showSteps(){
  const box = $('#overlay .box');
  box.classList.add('steps');
  box.innerHTML = PLACE_STEPS.map((text,i)=>
    `<div class="stepline wait" data-step="${i}"><span class="stepdot"></span><span>${text}</span></div>`).join('');
  $('#overlay').classList.remove('hide');
}

function markStep(current){
  document.querySelectorAll('#overlay .stepline').forEach((el,i)=>{
    el.classList.remove('wait','active','done');
    el.classList.add(i < current ? 'done' : i === current ? 'active' : 'wait');
  });
}

function hideOverlay(){ $('#overlay').classList.add('hide'); }

async function runPlace(items){
  showSteps();
  const pending = fetch('/api/place',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({items})
  }).then(r=>r.json());

  try{
    for(let i = 0; i < PLACE_STEPS.length; i++){
      markStep(i);
      await delay(i === PLACE_STEPS.length - 1 ? STEP_LAST_DELAY_MS : STEP_DELAY_MS);
    }
    const data = await pending;
    if(data.error){ hideOverlay(); showErr('#qErr', data.error); return; }
    if(data.warning) showErr('#qErr', data.warning);

    const lpnByItem = {};
    items.forEach(it=>{ if(it.lpn) lpnByItem[it.item] = it.lpn; });
    (data.results||[]).forEach(r=>{ r.lpn = lpnByItem[r.typed] || lpnByItem[r.item] || ''; });
    appendResults(data.results || []);
  } catch(e){
    showErr('#qErr','Lookup failed. Check the connection.');
  } finally {
    hideOverlay();
  }
}

function appendResults(incoming){
  const skipped = [];
  incoming.forEach(next=>{
    const index = next.id
      ? QRESULTS.findIndex(old=> old.id === next.id)
      : QRESULTS.findIndex(old=> (old.typed||old.item) === (next.typed||next.item));
    if(index >= 0){
      if((QRESULTS[index].typed||'') !== (next.typed||'')) skipped.push(next.typed || next.item);
      QRESULTS[index] = next;
    } else {
      QRESULTS.push(next);
    }
  });
  if(skipped.length) showErr('#qErr', skipped.join(', ')
    + (skipped.length > 1 ? ' duplicate items' : ' duplicates an item') + ' already in the list.');
  renderResults();
}

function highlightsFromResults(){
  const reserveAisles = new Set();
  const reserveCount = {};
  const pickHeat = {};

  QRESULTS.forEach(r=>{
    if(r.aisle){
      reserveAisles.add(r.aisle);
      reserveCount[r.aisle] = (reserveCount[r.aisle] || 0) + 1;
    }
    if(r.own_days && r.own_days.length){
      r.own_days.forEach(d=>{ pickHeat[d.aisle] = Math.max(pickHeat[d.aisle] || 0, d.pct); });
    } else if(r.pick_aisle){
      const zonePrefix = r.pick_aisle.replace(/\d+/,'');
      const center = r.serve_center != null
        ? Math.round(r.serve_center)
        : parseInt((r.pick_aisle.match(/\d+/)||[0])[0], 10);
      const code = zonePrefix + String(center).padStart(2,'0');
      if(pickHeat[code] == null) pickHeat[code] = PICK_HEAT_UNMEASURED;
    }
  });
  return {reserveAisles, reserveCount, pickHeat};
}

function renderResults(){
  QRESULTS.forEach(r=>{ if(r && !r.not_found && r.aisle) SESSION[r.typed||r.item] = r; });

  const emptyState = $('#emptyState');
  if(emptyState) emptyState.classList.add('hide');

  const wrap = $('#results');
  wrap.className = 'results grid';
  QRESULTS.forEach((r,i)=> r._i = i);
  wrap.innerHTML = QRESULTS.map(cardHtml).join('');

  wrap.querySelectorAll('.cardx').forEach(button=> button.onclick = ()=>{
    QRESULTS.splice(+button.dataset.x, 1);
    if(QRESULTS.length){
      renderResults();
    } else {
      wrap.className = 'results';
      wrap.innerHTML = EMPTY_HTML;
      $('#exportRow').classList.add('hide');
    }
  });
  $('#exportRow').classList.toggle('hide', !QRESULTS.length);

  const {reserveAisles, reserveCount, pickHeat} = highlightsFromResults();
  drawMap(reserveAisles, pickHeat, reserveCount);
  renderSession();
}

function skuLabel(code){
  const bare = String(code||'').replace(/^sku[-\s]?/i,'');
  return /^\d+$/.test(bare) ? 'SKU' + bare : code;
}

function cardTitle(result){
  const parts = [];
  if(result.sku) parts.push(result.sku);
  if(result.name && result.name !== result.sku) parts.push(result.name);
  return parts.length ? parts.join(' · ') : skuLabel(result.typed || result.item);
}

function placementNote(result){
  if(result.moved_from) return ` <span class="note-sm">(moved from ${result.moved_from} · aisle full)</span>`;
  return '';
}

function cardHtml(result){
  if(result.not_found){
    return `<div class="card notfound" data-i="${result._i}">
      <button class="cardx" title="Remove" data-x="${result._i}">&times;</button>
      <div class="queried"><b>${skuLabel(result.typed || result.item)}</b></div>
      <div class="nf">Not in the data</div>
      <div class="rsn">No pick history. Assign manually.</div>
    </div>`;
  }

  const cellCode = result.cell || result.aisle || '-';
  const columnMatch = (result.cell||'').match(/^[A-Za-z]+\d+-(\d+)-\d+$/);
  const columnText = columnMatch ? ('location ' + parseInt(columnMatch[1], 10)) : '';
  const place = [result.aisle||'', columnText, result.floor||''].filter(Boolean).join(' · ');
  const lpnHtml = result.lpn ? ` · <span class="mono">pallet ${result.lpn}</span>` : '';
  const categoryHtml = result.category ? `<div class="qcat">${result.category}</div>` : '';

  const chosen = (result.candidates||[]).find(c=> c.aisle === result.aisle);
  const score = chosen ? chosen.share_pct : 0;
  const level = fitLevel(score);
  const scoreHtml = chosen ? `<span class="pct">${score}<small>/100</small></span>` : '';
  const barHtml = chosen ? `<div class="fitbar"><i style="width:${score}%"></i></div>` : '';

  const alternatives = (result.candidates||[])
    .filter(c=> c.aisle !== result.aisle && c.share_pct >= CANDIDATE_MIN_SHARE)
    .slice(0, ALT_CANDIDATE_LIMIT)
    .map(c=>`<span class="chip mono">${c.cell||c.aisle} <b>${c.share_pct}</b></span>`).join('');
  const altHtml = alternatives ? `<div class="alt">Other: ${alternatives}</div>` : '';

  const companions = (result.companions||[]).slice(0, COMPANION_LIMIT).map(c=>c.name).filter(Boolean);
  const companionHtml = companions.length ? `<div class="comp">Picked with: ${companions.join(', ')}</div>` : '';
  const reasonHtml = (result.aisle && result.pick_aisle) ? `<div class="rsn">${reasonText(result)}</div>` : '';
  const groupedHtml = result.by_filter ? ' <span class="note-sm">(grouped)</span>' : '';

  return `<div class="card ${level.cls}" data-i="${result._i}">
    <button class="cardx" title="Remove" data-x="${result._i}">&times;</button>
    <div class="top">
      <div class="queried"><b>${cardTitle(result)}</b>${lpnHtml}${categoryHtml}</div>
      <span class="badge">${level.label}</span>
    </div>
    <div class="codeline"><span class="code mono">${cellCode}</span>${scoreHtml}</div>
    ${barHtml}
    <div class="place">${place}${groupedHtml}${placementNote(result)}</div>
    ${reasonHtml}
    ${altHtml}
    ${companionHtml}
  </div>`;
}

$('#btnExcel').onclick = async ()=>{
  if(!QRESULTS.length) return;
  const res = await fetch('/api/excel-place',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({results: QRESULTS})
  });
  if(!res.ok){
    showErr('#qErr', 'Excel export failed.');
    return;
  }
  const url = URL.createObjectURL(await res.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = EXPORT_FILENAME;
  link.click();
  URL.revokeObjectURL(url);
};