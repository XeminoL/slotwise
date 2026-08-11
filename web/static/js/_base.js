const FIT_HIGH = 70;
const FIT_MID = 50;
const CANDIDATE_MIN_SHARE = 8;
const SPREAD_WARN = 3.5;
const REASON_CHIP_LIMIT = 3;
const AISLE_DIGITS = 2;

const EMPTY_HTML = '<div class="empty"><svg viewBox="0 0 24 24" stroke-width="1.5"><path d="M3 7l9-4 9 4-9 4-9-4z"/><path d="M3 7v10l9 4 9-4V7"/><path d="M12 11v10"/></svg><div class="big">Enter a code to see its location</div></div>';

const $ = selector => document.querySelector(selector);
const formatNumber = value => (value || 0).toLocaleString('en-US');

let QRESULTS = [], MODEL = null, MPOINTS = [], MCOLOR = 'cluster';
let SESSION = {};

function fitLevel(score){
  if(score >= FIT_HIGH) return {label:'Fit: High', cls:'fit-high'};
  if(score >= FIT_MID) return {label:'Fit: Medium', cls:'fit-mid'};
  return {label:'Fit: Low', cls:'fit-low'};
}

function reasonText(result){
  const chip = (text, cls='') => `<span class="rchip ${cls}">${text}</span>`;
  const pickAisle = result.pick_aisle || '';
  const zonePrefix = pickAisle.replace(/\d+/,'');
  const centerAisle = result.serve_center != null
    ? zonePrefix + String(result.serve_center).padStart(AISLE_DIGITS, '0')
    : pickAisle;

  let chips;
  if(result.by_own && result.own_days && result.own_days.length){
    chips = result.own_days.slice(0, REASON_CHIP_LIMIT)
      .map(d=>chip(`${d.aisle} <b>${d.pct}%</b>`));
  } else {
    chips = [chip(`picks ${pickAisle}`)];
  }
  if(result.spread != null && result.spread > SPREAD_WARN){
    chips.push(chip(`spread ±${result.spread.toFixed(1)}`, 'warn'));
  }
  return chips.join('');
}

document.documentElement.setAttribute('data-theme','dark');