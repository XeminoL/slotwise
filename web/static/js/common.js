async function checkBrain(){
  const state = $('#brainState');
  try{
    const data = await (await fetch('/api/brain')).json();
    if(!data.ready){
      state.innerHTML = '<span class="dot"></span>No model';
      return;
    }
    const meta = data.meta || {};
    state.innerHTML = `<span class="dot on"></span>${formatNumber(meta.items)} SKU`;
    $('#tabModel').disabled = false;
    MODEL = data;
    fillModelTab(data);
  } catch(e){
    state.innerHTML = '<span class="dot"></span>Connection failed';
  }
}

function showErr(selector, message){
  const el = $(selector);
  el.textContent = message;
  el.classList.remove('hide');
}

const advTabButtons = document.querySelectorAll('#advanced .advtabs button[data-tab]');

function goAdvTab(name){
  advTabButtons.forEach(b=> b.classList.toggle('on', b.dataset.tab === name));
  document.querySelectorAll('#advanced [data-panel]').forEach(p=> p.classList.toggle('hide', p.dataset.panel !== name));
  if(name === 'model' && MODEL) drawModel();
  if(name === 'dash') loadDash();
}
advTabButtons.forEach(b=> b.onclick = ()=> goAdvTab(b.dataset.tab));

const btnClear = $('#btnClear');
if(btnClear) btnClear.onclick = async ()=>{
  if(!confirm('Clear all loaded warehouse data?')) return;
  await fetch('/api/clear',{method:'POST'});
  location.reload();
};