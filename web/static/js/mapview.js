const ZONE_NAME = {R:'Reserve (R)', A:'Pick (A)', P:'Pallet (P)'};
const ZONE_ORDER = ['R','A','P'];

const MAP_WIDTH = 640;
const MAP_PAD_LEFT = 78;
const MAP_PAD_RIGHT = 12;
const MAP_ROW_HEIGHT = 34;
const MAP_CELL_GAP = 4;
const MAP_TOP = 12;
const MAP_BOTTOM = 6;
const MAP_CELL_INSET = 6;
const MAP_LABEL_MIN_WIDTH = 20;
const PICK_OPACITY_BASE = 0.35;
const PICK_OPACITY_RANGE = 0.65;
const BADGE_RADIUS = 7;

let LAYOUT = null;
let HEAT = null;
let HEAT_MODE = 'pick';
let LAST_DRAW = [null, {}, null];

const HEAT_FILL = {pick: '#c0392b', refill_out: '#1e8e4e', refill_in: '#2c7bb6'};
const HEAT_LABEL = {
  pick: 'Pick count',
  refill_out: 'Refill out (source aisle)',
  refill_in: 'Refill in (target aisle)',
};
const HEAT_OPACITY_MAX = 0.55;

function aisleRectHtml(aisle, x, y, width, height, isReserve, pickPct){
  const unmeasured = pickPct === PICK_HEAT_UNMEASURED;
  let cls = 'cellrect', style = '';
  if(isReserve){
    cls += ' lit';
  } else if(pickPct > 0 || unmeasured){
    cls += ' litpick';
    const opacity = unmeasured ? PICK_OPACITY_BASE : PICK_OPACITY_BASE + pickPct/100*PICK_OPACITY_RANGE;
    style = ` style="fill-opacity:${opacity.toFixed(2)}"`;
  }
  let title = aisle;
  if(unmeasured) title += ': refill zone inferred from pick area';
  else if(pickPct > 0) title += `: ${pickPct}% of refills`;
  return `<rect class="${cls}"${style} x="${x.toFixed(1)}" y="${y.toFixed(1)}" `
    + `width="${width.toFixed(1)}" height="${height.toFixed(1)}" rx="2"><title>${title}</title></rect>`;
}

function aisleLabelHtml(aisle, cx, cy){
  const number = aisle.replace(/^[A-Za-z]+/,'');
  return `<text class="maplabel aisleno" x="${cx.toFixed(1)}" y="${cy.toFixed(1)}" text-anchor="middle">${number}</text>`;
}

function extraBadgeHtml(count, cx, cy){
  return `<circle class="mapplusbg" cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="${BADGE_RADIUS}"/>`
    + `<text class="maplabel mapplus" x="${cx.toFixed(1)}" y="${(cy+3).toFixed(1)}" text-anchor="middle">+${count}</text>`;
}

function heatRectHtml(aisle, x, y, width, height){
  if(!HEAT || !HEAT[HEAT_MODE]) return '';
  const pct = HEAT[HEAT_MODE][aisle];
  if(!pct) return '';
  const opacity = (pct/100 * HEAT_OPACITY_MAX).toFixed(3);
  const moves = (HEAT.raw && HEAT.raw[HEAT_MODE] && HEAT.raw[HEAT_MODE][aisle]) || 0;
  const title = `${aisle} · ${HEAT_LABEL[HEAT_MODE]}: ${moves.toLocaleString('en-US')} (${pct}%)`;
  return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${width.toFixed(1)}"`
    + ` height="${height.toFixed(1)}" rx="3" fill="${HEAT_FILL[HEAT_MODE]}"`
    + ` fill-opacity="${opacity}"><title>${title}</title></rect>`;
}

function drawMap(reserveAisles, pickHeat, reserveCount){
  if(!LAYOUT) return;
  LAST_DRAW = [reserveAisles, pickHeat, reserveCount];

  const isReserve = aisle => !!(reserveAisles && reserveAisles.has && reserveAisles.has(aisle));
  const pickPctOf = aisle => (pickHeat && pickHeat[aisle]) || 0;
  const extraOf = aisle => Math.max(0, ((reserveCount && reserveCount[aisle]) || 0) - 1);

  const known = ZONE_ORDER.filter(z=> LAYOUT[z] && LAYOUT[z].length);
  const others = Object.keys(LAYOUT)
    .filter(z=> !ZONE_ORDER.includes(z) && LAYOUT[z] && LAYOUT[z].length)
    .sort();
  const zones = known.concat(others);
  const maxCols = Math.max(1, ...zones.map(z=> LAYOUT[z].length));
  const colWidth = (MAP_WIDTH - MAP_PAD_LEFT - MAP_PAD_RIGHT) / maxCols;
  const height = MAP_TOP + zones.length * MAP_ROW_HEIGHT + MAP_BOTTOM;

  let markup = '';
  zones.forEach((zone, zoneIndex)=>{
    const rowY = MAP_TOP + zoneIndex * MAP_ROW_HEIGHT;
    markup += `<text class="maplabel zlbl" x="8" y="${(rowY + MAP_ROW_HEIGHT/2 + 3).toFixed(1)}">${ZONE_NAME[zone]||zone}</text>`;

    LAYOUT[zone].forEach((aisle, colIndex)=>{
      const x = MAP_PAD_LEFT + colIndex * colWidth + MAP_CELL_GAP/2;
      const width = colWidth - MAP_CELL_GAP;
      const cellHeight = MAP_ROW_HEIGHT - MAP_CELL_GAP - MAP_CELL_INSET;
      const reserved = isReserve(aisle);
      const pickPct = pickPctOf(aisle);

      markup += heatRectHtml(aisle, x, rowY + 3, width, cellHeight);
      markup += aisleRectHtml(aisle, x, rowY + 3, width, cellHeight, reserved, pickPct);
      if(colWidth >= MAP_LABEL_MIN_WIDTH || reserved || pickPct > 0){
        markup += aisleLabelHtml(aisle, x + width/2, rowY + MAP_ROW_HEIGHT/2 + 2);
      }
      const extra = extraOf(aisle);
      if(extra > 0) markup += extraBadgeHtml(extra, x + width - 1, rowY - 1);
    });
  });

  const svg = $('#mapSvg');
  svg.setAttribute('viewBox', `0 0 ${MAP_WIDTH} ${height}`);
  svg.classList.toggle('heaton', !!(HEAT && HEAT[HEAT_MODE]));
  svg.innerHTML = markup;
}

function redrawMap(){ drawMap(...LAST_DRAW); }

function setHeatMode(mode){
  HEAT_MODE = mode;
  document.querySelectorAll('[data-heat]').forEach(b=>{
    b.classList.toggle('on', b.dataset.heat === mode);
  });
  redrawMap();
}

async function loadHeat(){
  try{
    const d = await (await fetch('/api/heat')).json();
    HEAT = d && d.pick ? d : null;
  }catch(e){ HEAT = null; }
  const box = $('#heatSwitch');
  if(box) box.style.display = HEAT ? '' : 'none';
  redrawMap();
}

async function loadLayout(){
  try{ LAYOUT = await (await fetch('/api/layout')).json(); }
  catch(e){ LAYOUT = {}; }
  drawMap(null, {});
  loadHeat();
}
loadLayout();