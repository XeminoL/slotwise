const SPREAD_TIGHT = 2.0;
const NEAR_COMPANION_MIN = 50;
const SPREAD_AXIS_MIN = 4.5;
const SPREAD_AXIS_PAD = 0.5;
const DOT_OPACITY = 0.62;
const SCATTER_BOTTOM_INSET = 264;
const SCATTER_BOTTOM_MIN = 40;
const CHART_HEIGHT_MIN = 320;
const CHART_HEIGHT_BASE = 60;
const CHART_HEIGHT_PER_ROW = 40;
const WEAK_BOARD_LIMIT = 6;
const DIST_MIN_BAR_PCT = 4;

const COLOR_GOOD = '#16a34a';
const COLOR_WARN = '#e0930f';
const COLOR_BAD = '#e11d64';
const COLOR_INK = '#334155';
const COLOR_DIM = '#94a3b8';
const COLOR_GRID = '#eef1f5';
const COLOR_AXIS = '#cbd5e1';
const COLOR_TRACK = '#f1f5f9';
const CHART_FONT = 'ui-sans-serif,system-ui,"Segoe UI",sans-serif';
const MONO_FONT = 'ui-monospace,Consolas,monospace';

let dashboardData = null;
let comboChart = null;

async function loadDash(){
  if(dashboardData){ drawCombo(); return; }
  try{
    dashboardData = await (await fetch('/api/dashboard')).json();
    if(dashboardData.error){ $('#dashLoad').textContent = dashboardData.error; return; }
  } catch(e){
    $('#dashLoad').textContent = 'Could not load data.';
    return;
  }
  $('#dashLoad').classList.add('hide');
  $('#dashBody').classList.remove('hide');
  drawCombo();
}

function scoreOf(result){
  const chosen = (result.candidates||[]).find(c=> c.aisle === result.aisle);
  return chosen ? chosen.share_pct : 0;
}

function fitColor(score){ return score >= FIT_HIGH ? COLOR_GOOD : score >= FIT_MID ? COLOR_WARN : COLOR_BAD; }
function fitLabel(score){ return score >= FIT_HIGH ? 'High' : score >= FIT_MID ? 'Medium' : 'Low'; }

function comboPoints(rows){
  return rows.map(r=>{
    const near = (r.score_parts || {}).companion;
    return {
      code: skuLabel(r.typed || r.item),
      fit: scoreOf(r),
      spread: r.spread != null ? r.spread : 0,
      nearCompanion: near,
      noCompanion: near == null,
    };
  });
}

function comboKpiHtml(points){
  const total = points.length;
  const avgFit = Math.round(points.reduce((sum,p)=> sum + p.fit, 0) / total);
  const tight = points.filter(p=> (p.spread||0) <= SPREAD_TIGHT).length;
  const measured = points.filter(p=> !p.noCompanion).length;
  const nearby = points.filter(p=> !p.noCompanion && p.nearCompanion >= NEAR_COMPANION_MIN).length;

  return [
    ['SKUs looked up', total, ''],
    ['Medium fit', avgFit, avgFit >= FIT_HIGH ? 'good' : 'warn'],
    ['Refill hotspots', tight + '/' + total, tight >= total/2 ? 'good' : 'warn'],
    ['Near companions', measured ? nearby + '/' + measured : '-', nearby >= measured/2 ? 'good' : 'warn'],
  ].map(([label,value,cls])=>`<div class="ck ${cls}"><div class="v">${value}</div><div class="l">${label}</div></div>`).join('');
}

function comboOption(points, ranked, chartHeight){
  const codes = ranked.map(p=>p.code);
  const scatterBottom = Math.max(chartHeight - SCATTER_BOTTOM_INSET, SCATTER_BOTTOM_MIN);
  const plotted = points.filter(p=> !p.noCompanion);
  const unmeasured = points.length - plotted.length;
  const spreadMax = Math.max(...points.map(p=> p.spread || 0), 0);
  const xMax = Math.max(SPREAD_AXIS_MIN, Math.ceil(spreadMax + SPREAD_AXIS_PAD));

  return {
    backgroundColor:'transparent', textStyle:{fontFamily:CHART_FONT},
    tooltip:{ backgroundColor:'#fff', borderColor:'#e2e8f0', borderWidth:1, padding:[10,14],
      textStyle:{color:COLOR_INK, fontSize:12}, extraCssText:'box-shadow:0 6px 24px rgba(15,23,42,.12);border-radius:8px',
      formatter: p => {
        const d = (p.seriesIndex <= 1) ? points.find(x=> x.code === (p.data.code || p.name)) : ranked[p.dataIndex];
        if(!d) return '';
        return `<b style="font-size:13px;color:#1e293b">${d.code}</b><br/>`
          + `<span style="color:${fitColor(d.fit)}">●</span> Fit: <b>${d.fit}</b>/100 <span style="color:${COLOR_DIM}">(${fitLabel(d.fit)})</span><br/>`
          + `Near companions: <b>${d.noCompanion ? 'not measured' : d.nearCompanion + '/100'}</b><br/>`
          + `Refill spread: <b>${d.spread}</b> aisles`;
      }
    },
    grid:[
      { left:58, right:'58%', top:56, bottom:scatterBottom },
      { left:'50%', right:70, top:56, bottom:40 }
    ],
    graphic:[
      { type:'text', left:44, top:28, style:{text:'① Refill spread × Near companions', fill:'#64748b', fontSize:12, fontWeight:700, fontFamily:CHART_FONT} },
      { type:'text', left:'50%', top:28, style:{text:'② Fit ranking', fill:'#64748b', fontSize:12, fontWeight:700, fontFamily:CHART_FONT} },
      ...(unmeasured ? [{ type:'text', left:58, bottom:scatterBottom - 22,
        style:{text:`${unmeasured} SKU with no companion measure, not plotted`, fill:COLOR_DIM, fontSize:11, fontFamily:CHART_FONT} }] : [])
    ],
    xAxis:[
      { gridIndex:0, type:'value', name:'← Refill concentrated   ·   Refill scattered →', min:0, max:xMax, nameLocation:'middle', nameGap:24,
        nameTextStyle:{color:COLOR_DIM, fontSize:10, fontWeight:600},
        axisLabel:{color:COLOR_DIM, fontSize:10}, axisLine:{lineStyle:{color:COLOR_AXIS}}, axisTick:{show:false},
        splitLine:{lineStyle:{color:COLOR_GRID}} },
      { gridIndex:1, type:'value', min:0, max:100,
        axisLabel:{show:false}, axisLine:{show:false}, axisTick:{show:false},
        splitLine:{lineStyle:{color:COLOR_GRID}} }
    ],
    yAxis:[
      { gridIndex:0, type:'value', name:'Near companions →', min:0, max:100,
        nameLocation:'middle', nameGap:38, nameTextStyle:{color:COLOR_DIM, fontSize:10, fontWeight:600},
        axisLabel:{color:COLOR_DIM, fontSize:10}, axisLine:{show:false}, axisTick:{show:false},
        splitLine:{lineStyle:{color:COLOR_GRID}} },
      { gridIndex:1, type:'category', data:codes,
        axisLabel:{color:COLOR_INK, fontSize:10, fontWeight:600, fontFamily:MONO_FONT},
        axisLine:{show:false}, axisTick:{show:false} }
    ],
    series:[
      { id:'scatter', type:'scatter', xAxisIndex:0, yAxisIndex:0, symbolSize:9, z:3,
        data: plotted.map(p=>({ value:[p.spread || 0, p.nearCompanion], code:p.code,
          itemStyle:{color:fitColor(p.fit), opacity:DOT_OPACITY, borderColor:'#fff', borderWidth:1.5,
            shadowColor:'rgba(15,23,42,.12)', shadowBlur:3} })),
        emphasis:{scale:1.8, focus:'series',
          itemStyle:{borderColor:'#fff', borderWidth:1.5, shadowBlur:8},
          label:{show:true, position:'right', distance:6, color:COLOR_INK, fontSize:11, fontWeight:600,
            backgroundColor:'#fff', padding:[2,5], borderRadius:4, formatter:p=>p.data.code} },
        markLine:{ silent:true, symbol:'none', lineStyle:{color:COLOR_AXIS, type:'dashed', width:1},
          label:{show:false},
          data:[{xAxis:SPREAD_TIGHT}, {yAxis:NEAR_COMPANION_MIN}] } },

      { type:'bar', xAxisIndex:1, yAxisIndex:1, data:codes.map(()=>100), barWidth:13, barGap:'-100%',
        silent:true, itemStyle:{color:COLOR_TRACK, borderRadius:6}, z:1 },

      { id:'bar', type:'bar', xAxisIndex:1, yAxisIndex:1, barWidth:13, z:2,
        data: ranked.map(p=>({ value:p.fit, code:p.code, itemStyle:{color:fitColor(p.fit), borderRadius:6} })),
        label:{show:true, position:'right', color:COLOR_INK, fontWeight:700, fontSize:11, formatter:p=>ranked[p.dataIndex].fit},
        emphasis:{focus:'series'},
        markLine:{ silent:true, symbol:'none', lineStyle:{color:COLOR_AXIS, type:'dashed', width:1},
          label:{color:COLOR_DIM, fontSize:9, fontWeight:600, position:'end', formatter:String(FIT_HIGH)},
          data:[{xAxis:FIT_HIGH}] } }
    ],
    animationDurationUpdate:400, animationEasingUpdate:'cubicOut'
  };
}

function bindComboCrossHighlight(points, ranked){
  const plotted = points.filter(p=> !p.noCompanion);
  comboChart.off('mouseover');
  comboChart.off('mouseout');
  comboChart.on('mouseover', p => {
    const code = p.data && (p.data.code || p.name);
    if(!code) return;
    const barIndex = ranked.findIndex(x=> x.code === code);
    const scatterIndex = plotted.findIndex(x=> x.code === code);
    if(scatterIndex >= 0) comboChart.dispatchAction({type:'highlight', seriesId:'scatter', dataIndex:scatterIndex});
    if(barIndex >= 0) comboChart.dispatchAction({type:'highlight', seriesId:'bar', dataIndex:barIndex});
  });
  comboChart.on('mouseout', ()=>{
    comboChart.dispatchAction({type:'downplay', seriesId:'scatter'});
    comboChart.dispatchAction({type:'downplay', seriesId:'bar'});
  });
}

function drawCombo(){
  const el = document.getElementById('cCombo');
  if(!el || !window.echarts) return;
  if(!comboChart) comboChart = echarts.init(el, null, {renderer:'canvas'});

  const rows = Object.values(SESSION);
  const kpiEl = document.getElementById('comboKpi');

  if(!rows.length){
    comboChart.clear();
    if(kpiEl) kpiEl.innerHTML = '';
    el.style.height = '0px';
    return;
  }

  const points = comboPoints(rows);
  const ranked = points.slice().sort((a,b)=> a.fit - b.fit);
  if(kpiEl) kpiEl.innerHTML = comboKpiHtml(points);

  const chartHeight = Math.max(CHART_HEIGHT_BASE + ranked.length * CHART_HEIGHT_PER_ROW, CHART_HEIGHT_MIN);
  el.style.height = chartHeight + 'px';

  comboChart.setOption(comboOption(points, ranked, chartHeight), true);
  comboChart.resize();
  bindComboCrossHighlight(points, ranked);
}

window.addEventListener('resize', ()=>{ if(comboChart) comboChart.resize(); });

function renderSession(){
  const rows = Object.values(SESSION);
  const empty = $('#sessEmpty'), body = $('#sessBody');
  drawCombo();

  if(!rows.length){
    if(empty) empty.classList.remove('hide');
    if(body) body.classList.add('hide');
    return;
  }
  if(empty) empty.classList.add('hide');
  if(body) body.classList.remove('hide');

  let high = 0, mid = 0, low = 0;
  rows.forEach(r=>{
    const score = scoreOf(r);
    if(score >= FIT_HIGH) high++;
    else if(score >= FIT_MID) mid++;
    else low++;
  });
  const average = Math.round(rows.reduce((sum,r)=> sum + scoreOf(r), 0) / rows.length);

  $('#sessKpis').innerHTML = [
    ['SKUs looked up', rows.length, ''],
    ['Avg score', average, 'hi'],
    ['High', high, ''],
    ['Needs review', mid + low, ''],
  ].map(([label,value,cls])=>`<div class="k ${cls}"><div class="v">${value}</div><div class="l">${label}</div></div>`).join('');

  const total = rows.length;
  $('#sessDist').innerHTML = [['high','High',high],['mid','Medium',mid],['low','Low',low]]
    .map(([cls,label,count])=>`<div class="row ${cls}"><span class="lbl">${label}</span>`
      + `<span class="track"><i style="width:${count ? Math.max(count/total*100, DIST_MIN_BAR_PCT) : 0}%"></i></span>`
      + `<span class="n">${count}</span></div>`).join('');

  const weak = rows.filter(r=> scoreOf(r) < FIT_HIGH);
  const board = (weak.length ? weak : rows).slice()
    .sort((a,b)=> scoreOf(a) - scoreOf(b) || (b.spread||0) - (a.spread||0))
    .slice(0, WEAK_BOARD_LIMIT);

  $('#sessBoardTitle').textContent = weak.length ? 'SKUs to review' : 'Lowest score';
  $('#sessBoard').innerHTML = board.map(r=>{
    const score = scoreOf(r);
    const cls = score < FIT_MID ? 'bad' : score < FIT_HIGH ? 'mid' : '';
    const spread = r.spread != null ? ` · spread ${Math.round(r.spread)}` : '';
    return `<dt>${skuLabel(r.typed || r.item)}</dt><dd class="${cls}">${score}/100${spread}</dd>`;
  }).join('');
}