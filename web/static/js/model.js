const CLUSTER_PALETTE = ['#3987e5','#d95926','#199e70','#c98500','#d55181','#9085e9','#e66767','#2d7d46','#e87ba4','#4a5ec0','#8a3a7a','#5ab0c0'];
const CATEGORY_PALETTE = ['#3987e5','#d95926','#199e70','#c98500'];

const BYTES_PER_MB = 1048576;
const LEARN_POLL_MS = 900;
const LEARN_PROGRESS_START = 5;
const LEARN_PROGRESS_STEP = 3;
const LEARN_PROGRESS_BASE = 8;
const LEARN_PROGRESS_CAP = 92;

const MAP_PADDING = 20;
const DOT_RADIUS_MIN = 1.5;
const DOT_RADIUS_BASE = 3;
const DENSE_POINT_COUNT = 1500;
const DENSE_SHRINK = 1.4;
const DOT_ALPHA = 0.72;
const CULL_MARGIN = 5;
const HOVER_RADIUS_SQ = 500;
const ZOOM_STEP = 1.15;
const ZOOM_MAX = 8;
const ZOOM_MIN = 1;
const FULL_CIRCLE = Math.PI * 2;

let clusterInfo = {};
let categories = [];
let view = {scale: ZOOM_MIN, ox: 0, oy: 0};
let dragStart = null;

function bindDrop(dropSelector, inputSelector, listSelector, onChange){
  const drop = $(dropSelector), input = $(inputSelector);
  if(!drop || !input) return ()=>[];

  let files = [];
  const stop = e => e.preventDefault();

  input.onchange = e => add([...e.target.files]);
  ['dragover','dragenter'].forEach(type=> drop.addEventListener(type, e=>{ stop(e); drop.style.borderColor = 'var(--accent)'; }));
  ['dragleave','drop'].forEach(type=> drop.addEventListener(type, e=>{ stop(e); drop.style.borderColor = ''; }));
  drop.addEventListener('drop', e=>{ if(e.dataTransfer.files.length) add([...e.dataTransfer.files]); });

  function add(incoming){
    incoming.forEach(f=>{
      if(!files.some(existing=> existing.name === f.name && existing.size === f.size)) files.push(f);
    });
    render();
  }

  function render(){
    const list = $(listSelector);
    list.innerHTML = files.map((f,i)=>
      `<div class="filerow"><span class="fname">${f.name}</span>`
      + `<span class="fsize">${(f.size/BYTES_PER_MB).toFixed(1)} MB</span>`
      + `<button type="button" class="fdel" data-i="${i}" title="Remove">&times;</button></div>`).join('');
    list.querySelectorAll('.fdel').forEach(b=> b.onclick = ()=>{ files.splice(+b.dataset.i, 1); render(); });
    onChange(files);
  }

  return ()=> files;
}

const getLearnFiles = bindDrop('#lDrop','#lFile','#lFileList', files => $('#btnLearn').disabled = !files.length);

$('#btnLearn').onclick = async ()=>{
  const form = new FormData();
  getLearnFiles().forEach((f,i)=> form.append('file' + i, f));
  $('#lErr').classList.add('hide');
  $('#btnLearn').disabled = true;
  $('#lWarn').textContent = 'Detecting files and loading...';

  const data = await (await fetch('/api/load-history',{method:'POST', body:form})).json();
  $('#btnLearn').disabled = false;
  if(data.error){
    $('#lWarn').textContent = '';
    showErr('#lErr', data.error);
    return;
  }
  const detected = Object.entries(data.detected||{}).map(([kind,file])=>`${kind}: ${file}`).join(', ');
  $('#lWarn').textContent = 'Detected: ' + detected + '. Training...';
  if(data.job) pollLearn(data.job);
  else checkBrain();
};

function pollLearn(jobId){
  $('#lProg').classList.remove('hide');
  $('#lBar').style.width = LEARN_PROGRESS_START + '%';
  const log = $('#lLog');
  log.innerHTML = '';
  let ticks = 0;

  const poll = async ()=>{
    const job = await (await fetch('/api/status/' + jobId)).json();
    log.innerHTML = (job.progress||[]).map(line=>`<div>${line}</div>`).join('');
    log.scrollTop = log.scrollHeight;
    ticks++;
    $('#lBar').style.width = Math.min(LEARN_PROGRESS_CAP, LEARN_PROGRESS_BASE + ticks * LEARN_PROGRESS_STEP) + '%';

    if(job.status === 'running'){ setTimeout(poll, LEARN_POLL_MS); return; }
    if(job.status === 'error'){
      $('#lBar').style.background = 'var(--guess)';
      showErr('#lErr', job.error || 'Error');
      return;
    }
    $('#lBar').style.width = '100%';
    log.innerHTML += '<div><b>Done. Press Ctrl+R to reload.</b></div>';
    log.scrollTop = log.scrollHeight;
    MODEL = {ready:true, meta:job.result.meta, stats:job.result.stats, gu_map:job.result.gu_map};
    fillModelTab(MODEL);
    await checkBrain();
  };
  poll();
}

function fillModelTab(model){
  const stats = model.stats || {};
  const cells = [
    ['Orders learned', formatNumber(stats.orders)],
    ['Items', formatNumber(stats.items)],
    ['Aisles', formatNumber(stats.aisles)],
  ];
  if(stats.purity != null) cells.push(['Cluster purity', stats.purity + '%']);
  $('#mKpis').innerHTML = cells.map(([label,value])=>`<div class="kpi"><b>${value}</b><span class="l">${label}</span></div>`).join('');
}

function colorOf(point){
  return MCOLOR === 'cluster'
    ? CLUSTER_PALETTE[point.cluster % CLUSTER_PALETTE.length]
    : CATEGORY_PALETTE[categories.indexOf(point.category) % CATEGORY_PALETTE.length];
}

function buildClusterInfo(){
  clusterInfo = {};
  MPOINTS.forEach(p=>{
    const info = clusterInfo[p.cluster] = clusterInfo[p.cluster] || {n:0, cats:{}};
    info.n++;
    info.cats[p.category] = (info.cats[p.category] || 0) + 1;
  });
  Object.values(clusterInfo).forEach(info=>{
    info.mainCat = Object.entries(info.cats).sort((a,b)=> b[1] - a[1])[0][0];
  });
}

function renderModelLegend(){
  const legend = $('#mLegend');
  if(!legend) return;
  if(MCOLOR === 'cluster'){
    const clusters = new Set(MPOINTS.map(p=>p.cluster)).size;
    legend.innerHTML = `<span class="lg">${clusters} clusters · ${MPOINTS.length} SKU</span>`;
    return;
  }
  const counts = {};
  MPOINTS.forEach(p=>{ counts[p.category] = (counts[p.category] || 0) + 1; });
  legend.innerHTML = categories.map((cat,i)=>
    `<span class="lg"><i style="background:${CATEGORY_PALETTE[i % CATEGORY_PALETTE.length]}"></i>${cat} (${counts[cat]})</span>`).join('');
}

function drawModel(){
  const points = (MODEL && MODEL.gu_map) || [];
  const canvas = $('#mCanvas');
  if(!canvas || !points.length) return;

  const usableW = canvas.width - MAP_PADDING*2;
  const usableH = canvas.height - MAP_PADDING*2;
  MPOINTS = points.map(p=>({...p, px: MAP_PADDING + p.x*usableW, py: MAP_PADDING + p.y*usableH}));
  categories = [...new Set(MPOINTS.map(p=>p.category))];

  buildClusterInfo();
  paintModel();
  renderModelLegend();
}

function paintModel(){
  const canvas = $('#mCanvas');
  if(!canvas || !MPOINTS.length) return;
  const ctx = canvas.getContext('2d');
  const {width, height} = canvas;
  ctx.clearRect(0, 0, width, height);

  const radius = Math.max(DOT_RADIUS_MIN, DOT_RADIUS_BASE * view.scale)
    / (MPOINTS.length > DENSE_POINT_COUNT ? DENSE_SHRINK : 1);
  ctx.globalAlpha = DOT_ALPHA;
  MPOINTS.forEach(p=>{
    const x = p.px*view.scale + view.ox, y = p.py*view.scale + view.oy;
    if(x < -CULL_MARGIN || x > width + CULL_MARGIN || y < -CULL_MARGIN || y > height + CULL_MARGIN) return;
    ctx.fillStyle = colorOf(p);
    ctx.beginPath();
    ctx.arc(x, y, radius, 0, FULL_CIRCLE);
    ctx.fill();
  });
  ctx.globalAlpha = 1;
}

function canvasPointer(event){
  const canvas = $('#mCanvas');
  const rect = canvas.getBoundingClientRect();
  const scale = canvas.width / rect.width;
  return {x: (event.clientX - rect.left)*scale, y: (event.clientY - rect.top)*scale, rect, scale};
}

function nearestPoint(x, y){
  let best = null, bestDist = Infinity;
  MPOINTS.forEach(p=>{
    const px = p.px*view.scale + view.ox, py = p.py*view.scale + view.oy;
    const dist = (px - x)**2 + (py - y)**2;
    if(dist < bestDist){ bestDist = dist; best = p; }
  });
  return bestDist < HOVER_RADIUS_SQ ? best : null;
}

function pointLabel(point){
  const number = String(point.name||'').replace(/^sku/i,'');
  return /^\d+$/.test(number) ? 'SKU' + number : point.name;
}

$('#mToggle').onclick = ()=>{
  MCOLOR = MCOLOR === 'cluster' ? 'category' : 'cluster';
  $('#mToggle').textContent = MCOLOR === 'cluster' ? 'Color by category' : 'Color by cluster';
  drawModel();
};

$('#mCanvas').onmousedown = e=>{ dragStart = {x:e.clientX, y:e.clientY, ox:view.ox, oy:view.oy}; };
window.addEventListener('mouseup', ()=>{ dragStart = null; });

$('#mCanvas').onmousemove = e=>{
  if(!MPOINTS.length) return;
  const canvas = $('#mCanvas'), tip = $('#mTip');
  const {x, y, rect, scale} = canvasPointer(e);

  if(dragStart){
    view.ox = dragStart.ox + (e.clientX - dragStart.x)*scale;
    view.oy = dragStart.oy + (e.clientY - dragStart.y)*scale;
    paintModel();
    tip.classList.add('hide');
    canvas.style.cursor = 'grabbing';
    return;
  }

  const point = nearestPoint(x, y);
  if(!point){
    tip.classList.add('hide');
    canvas.style.cursor = 'grab';
    return;
  }
  const info = clusterInfo[point.cluster];
  const groupHtml = info ? `<div class="m">Cluster ${point.cluster}: ${info.n} SKU · ${info.mainCat}</div>` : '';
  tip.innerHTML = `<span class="c">${pointLabel(point)}</span><div class="m">aisle ${point.aisle}</div>${groupHtml}`;
  tip.style.left = (e.clientX - rect.left) + 'px';
  tip.style.top = (e.clientY - rect.top) + 'px';
  tip.classList.remove('hide');
  canvas.style.cursor = 'pointer';
};

$('#mCanvas').onmouseleave = ()=>{
  const tip = $('#mTip');
  if(tip) tip.classList.add('hide');
  dragStart = null;
};

$('#mCanvas').onwheel = e=>{
  if(!MPOINTS.length) return;
  e.preventDefault();
  const {x, y} = canvasPointer(e);
  const factor = e.deltaY < 0 ? ZOOM_STEP : 1/ZOOM_STEP;
  const next = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, view.scale * factor));
  const ratio = next / view.scale;
  view.ox = x - (x - view.ox)*ratio;
  view.oy = y - (y - view.oy)*ratio;
  view.scale = next;
  if(next === ZOOM_MIN){ view.ox = 0; view.oy = 0; }
  paintModel();
};