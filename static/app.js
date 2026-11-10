const $=id=>document.getElementById(id);
const defaultPool='SPY QQQ SOXX IWM DIA AAPL MSFT NVDA AMZN GOOGL META TSLA AMD AVGO MU INTC NFLX PLTR COIN SMH';
const numericKeys=['volume_n','volume_mult','vwap_n','sigma','lookback','pair_gap'];
const boolKeys=['include_secondary','previous_volume','bullish_only','require_vwap','require_rising','require_macd','require_bottom','require_confirmation','early_mode'];
let state={results:[],running:false,total:0,completed:0,failed:0},mode='candidates',priorityFilter=0,selected=null,chartData=null;
let pending=false,initialized=false,polling=false,chartSerial=0,toastTimer=null,savedSymbols=[];
const chart=new SignalChart($('chart'),$('chartTooltip'));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=2)=>v==null?'—':Number(v).toFixed(d);
const signed=(v,d=2)=>v==null?'—':`${v>=0?'+':''}${Number(v).toFixed(d)}%`;
const tone=v=>v>0?'up':v<0?'down':'muted';
function toast(text,error=false){clearTimeout(toastTimer);$('toast').textContent=text;$('toast').className='toast'+(error?' error':'');$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,error?7000:3500);}
async function api(path,body){const res=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await res.json();if(!res.ok)throw new Error(data.error||`请求失败 (${res.status})`);return data;}
function readRules(){const p={};numericKeys.forEach(k=>p[k]=Number($(k).value));boolKeys.forEach(k=>p[k]=$(k).checked);return p;}
function writeRules(p){numericKeys.forEach(k=>$(k).value=p[k]);boolKeys.forEach(k=>$(k).checked=p[k]);}
const ruleLabels={include_secondary:'包含第二优先',previous_volume:'仅用此前均量',bullish_only:'黄色K线为阳线',require_vwap:'放量上穿VWAP',require_rising:'阶梯柱上升',require_macd:'MACD柱为正',require_bottom:'近5日底背离',require_confirmation:'底背离或MACD金叉确认',early_mode:'稳健左侧启动'};
const valueLabels={volume_n:'均量周期（日）',volume_mult:'放量倍数（×）',vwap_n:'VWAP周期',sigma:'通道倍数',lookback:'信号新鲜度（日）',pair_gap:'信号配合范围'};
function renderRuleFilters(){
  $('ruleChips').innerHTML=boolKeys.filter(k=>$(k).checked).map(k=>`<button type="button" class="rule-chip" data-remove-rule="${k}" aria-label="移除${ruleLabels[k]}">${ruleLabels[k]} <span aria-hidden="true">×</span></button>`).join('')||'<span class="micro">未添加附加条件 · 仍按BBUY与放量配合筛选</span>';
  $('addRule').innerHTML='<option value="">＋ 添加条件</option>'+boolKeys.filter(k=>!$(k).checked).map(k=>`<option value="${k}">${ruleLabels[k]}</option>`).join('');
  for(const k of numericKeys){const el=$('result_'+k);if(el&&document.activeElement!==el)el.value=$(k).value;}
}
function setupRuleValues(){
  for(const k of numericKeys){const source=$(k),copy=source.cloneNode(true);copy.id='result_'+k;copy.setAttribute('aria-label',valueLabels[k]);const label=document.createElement('label');label.append(document.createTextNode(valueLabels[k]),copy);$('ruleValues').append(label);
    copy.addEventListener('input',()=>{source.value=copy.value;queueRuleUpdate();});copy.addEventListener('change',()=>{source.value=copy.value;queueRuleUpdate();});}
}
const liveRules=new LiveRules({busy:()=>state.running||pending,save:async p=>{
  pending=true;busyControls();$('liveRuleStatus').textContent='正在使用已保存行情更新结果…';
  try{await api('/api/settings',{settings:p,symbols:savedSymbols});describeRules(p);chartSerial++;await poll();$('liveRuleStatus').textContent='结果已自动更新 · 条件已保存 · 未请求行情';$('backtestSummary').textContent=' 条件已更新，可重新回测';if(selected)await selectStock(selected);}
  finally{pending=false;busyControls();}
},onError:e=>{$('liveRuleStatus').textContent='更新失败：'+e.message;toast(e.message,true);}});
function queueRuleUpdate(){if(!initialized)return;renderRuleFilters();if(!numericKeys.every(k=>$(k).checkValidity())){$('liveRuleStatus').textContent='请填写范围内的有效数值';return;}$('liveRuleStatus').textContent=state.running?'扫描中，条件将在结束后自动更新':'等待自动更新结果…';liveRules.schedule(readRules());}
setupRuleValues();
$('addRule').addEventListener('change',()=>{const k=$('addRule').value;if(k){$(k).checked=true;queueRuleUpdate();}});
$('ruleChips').addEventListener('click',e=>{const b=e.target.closest('[data-remove-rule]');if(b){$(b.dataset.removeRule).checked=false;queueRuleUpdate();}});
[...numericKeys,...boolKeys].forEach(k=>$(k).addEventListener('change',queueRuleUpdate));
numericKeys.filter(k=>$(k).tagName==='INPUT').forEach(k=>$(k).addEventListener('input',queueRuleUpdate));
function poolCount(){const codes=$('symbols').value.trim().split(/[\s,;，；]+/).filter(Boolean);$('poolCount').textContent=`${new Set(codes).size} 只`;}
function describeRules(p){const relation=p.pair_gap===0?'放量与红柱同日':`放量与红柱相距 ≤ ${p.pair_gap} 日`;$('ruleDescription').textContent=`${p.previous_volume?'此前 ':''}${p.volume_n} 日均量 × ${p.volume_mult} · ${relation} · 最近 ${p.lookback} 个交易日${p.include_secondary?' · 包含仅红柱的第二优先':''}${p.require_confirmation?' · 底背离/MACD金叉确认':''}${p.early_mode?' · 稳健左侧启动':''}`;}
function busyControls(){const busy=state.running||pending;['scanBtn','refreshQuotesBtn','applyBtn','defaultBtn','importBtn'].forEach(id=>$(id).disabled=busy);$('cancelBtn').hidden=!state.running;$('cancelBtn').disabled=pending;$('refreshQuotesBtn').textContent=state.running?'正在更新行情…':pending?'正在提交…':'↻ 更新上一交易日行情';}
function render(){
  const matches=state.results.filter(r=>r.matched&&r.status==='ok');$('matchCount').textContent=matches.length;
  const ok=state.results.filter(r=>['ok','insufficient','stale'].includes(r.status));$('coverage').innerHTML=`${ok.length}<em> / ${state.total||0}</em>`;
  $('coverageNote').textContent=state.running?`已处理 ${state.completed}/${state.total}`:state.failed?`${state.failed} 只获取失败 · 查看全部结果`:state.cancelled?'已取消剩余扫描':state.total?'已收盘行情 · 当前股票池':'等待首次扫描';
  const dates=matches.map(r=>r.signal_date).sort().reverse();$('latestSignal').textContent=dates[0]||'—';
  $('candidateBadge').textContent=matches.length;$('allBadge').textContent=state.results.length;
  $('candidatesTab').classList.toggle('active',mode==='candidates');$('allTab').classList.toggle('active',mode==='all');
  for(const [id,key,title] of [['sectorFilter','sectors','全部板块'],['indexFilter','indices','全部指数']]){
    const el=$(id),current=el.value,names=[...new Set(state.results.flatMap(r=>r[key]||[]))].sort((a,b)=>a.localeCompare(b,'zh-CN'));
    const options='<option value="">'+title+'</option>'+names.map(n=>`<option value="${esc(n)}">${esc(n)}</option>`).join('')+'<option value="__unknown">未分类</option>';
    if(el.innerHTML!==options){el.innerHTML=options;el.value=current;}
  }
  $('metadataNote').textContent=`市值单位：美元 · 分类为富途行业 / 概念板块 · 指数可多重归属 · ${state.metadata_updated_at?'更新 '+new Date(state.metadata_updated_at).toLocaleString('zh-CN'):'尚未取得分类，请扫描更新'}${state.metadata_error?' · 分类更新失败，保留旧数据：'+state.metadata_error:''}`;
  let rows=mode==='candidates'?matches:state.results;
  if(priorityFilter)rows=rows.filter(r=>r.matched&&r.status==='ok'&&r.priority===priorityFilter);
  document.querySelectorAll('[data-priority]').forEach(button=>{const active=Number(button.dataset.priority)===priorityFilter;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
  for(const id of ['sectorFilter','indexFilter'])$(id).classList.toggle('filter-selected',!!$(id).value);
  $('clearFilters').disabled=!priorityFilter&&!$('search').value&&!$('sectorFilter').value&&!$('indexFilter').value;
  const search=$('search').value.trim().toUpperCase();if(search)rows=rows.filter(r=>`${r.symbol} ${r.name}`.toUpperCase().includes(search));
  for(const [id,key] of [['sectorFilter','sectors'],['indexFilter','indices']]){const v=$(id).value;if(v)rows=rows.filter(r=>v==='__unknown'?!(r[key]||[]).length:(r[key]||[]).includes(v));}
  rows=[...rows].sort((a,b)=>Number(b.matched)-Number(a.matched)||($('sortBy').value==='confirmation'?(b.confirmation_rank||0)-(a.confirmation_rank||0):$('sortBy').value==='early'?(b.early_score??-1)-(a.early_score??-1):$('sortBy').value!=='signal'?(a.market_cap==null?(b.market_cap==null?0:1):b.market_cap==null?-1:$('sortBy').value==='cap_desc'?b.market_cap-a.market_cap:a.market_cap-b.market_cap):0)||Number(b.matched)-Number(a.matched)||(a.priority||99)-(b.priority||99)||(b.signal_date||'').localeCompare(a.signal_date||''));
  $('resultRows').innerHTML=rows.map(r=>{
    const valid=['ok','insufficient','stale'].includes(r.status);
    const reason=r.matched?(r.priority===2?'<span class="signal-pill red">第二优先 · BBUY ↑</span><span class="signal-note">缺少放量确认</span>':'<span class="signal-pill">第一优先 · 黄色放量</span><span class="signal-pill red">BBUY ↑</span>'):`<span class="signal-note" title="${esc(r.error||'本窗口无组合信号')}">${esc(r.error||(r.latest_heavy?'最新日放量 · 暂无组合':r.latest_bbuy?'最新日红柱 · 暂无组合':'本窗口无组合信号'))}</span>`;
    const capital=r.capital_value==null?'资金指标：历史不足或尚未重算':`资金动能 ${fmt(r.capital_value)}%（${r.capital_value>0?'正值':r.capital_value<0?'负值':'零轴'}） · ${r.capital_up?'上穿零轴':r.capital_down?'下穿零轴':r.capital_rising?'抬升':'回落'}${r.capital_up_dates?.length?' · 近5日上穿 '+r.capital_up_dates.join('、'):''}`;
    return `<tr data-symbol="${esc(r.symbol)}" class="${selected===r.symbol?'selected':''}"><td><div class="ticker">${esc(r.symbol.replace(/^US\./,''))}${r.stale?'<span class="stale-tag">缓存待更新</span>':''}</div><div class="company">${esc(r.name)}</div></td><td class="classification-cell"><span class="num" title="${esc(r.market_cap_at||'市值未知')}">${r.market_cap==null?'—':fmt(r.market_cap/1e8)+' 亿'}</span><small title="${esc((r.sectors||[]).join(' / '))}">${esc((r.sectors||[]).slice(0,3).join(' / ')||'未分类')}${(r.sectors||[]).length>3?' 等 '+r.sectors.length+' 个板块':''}</small><small>${esc((r.indices||[]).join(' / ')||'无所选指数归属')}</small></td><td class="price-cell"><span class="num">${valid?fmt(r.close):'—'}</span><small class="${tone(r.change)}">${valid?signed(r.change):''}</small></td><td class="num">${esc(r.signal_date||'—')}</td><td class="num ${r.matched?'accent':''}">${fmt(r.volume_ratio??r.latest_volume_ratio)}×</td><td class="num ${tone(r.vwap_distance)}">${signed(r.vwap_distance)}</td><td>${r.matched?`<span class="signal-pill grade-${esc(r.confirmation_grade||'C')}">${esc(r.confirmation_grade||'C')}级 · ${r.confirmation_grade==='A'?'多信号配合':r.confirmation_grade==='B'?'动能确认':'初步转强'}</span><div class="signal-note">${esc((r.confirmation_reasons||[]).join(' · '))}</div>`:''}${reason}<div class="signal-note" title="${esc(r.early_reason||'')}">低位条件满足 ${r.early_score??'—'} / 100 · ${esc(r.early_reason||'')}</div><div class="signal-note" title="价格推算，非真实资金流">${esc(capital)}</div></td></tr>`;
  }).join('');
  $('resultRows').querySelectorAll('tr').forEach(row=>row.addEventListener('click',()=>selectStock(row.dataset.symbol)));
  $('emptyState').hidden=rows.length>0;
  if(!rows.length){const started=state.total>0;$('emptyState').innerHTML=started?`<span class="empty-icon">⌁</span><h3>${search?'没有搜索结果':state.running?'正在寻找组合信号':'当前条件暂无候选'}</h3><p>${search?'试试其他代码或名称。':state.running?'已完成的股票会陆续出现在全部结果中。':'查看全部结果和历史信号，或调整新鲜度、放量倍数与配合范围。'}</p>${!search?'<button id="viewAllEmpty" class="small-button">查看全部结果 →</button>':''}`:'<span class="empty-icon">⌁</span><h3>等待第一组信号</h3><p>设置左侧条件并扫描，查看放量与红柱共同出现的股票。</p>';if($('viewAllEmpty'))$('viewAllEmpty').onclick=()=>{mode='all';render();};}
  $('progressBox').hidden=!state.running;
  const percent=state.total?Math.round(state.completed/state.total*100):0;
  $('progressBar').value=percent;$('progressPercent').textContent=percent+'%';$('progressText').textContent=`扫描 ${state.current?.replace(/^US\./,'')||'准备中'} · 已处理 ${state.completed}/${state.total}`;
  const notice=state.error|| (state.failed?`有 ${state.failed} 只股票未能获取行情，请在“全部结果”查看原因。`:state.historical?`这是截至 ${state.cutoff} 的旧扫描结果，请更新行情；旧信号不进入当前候选。`:'');$('statusNotice').hidden=!notice;$('statusNotice').textContent=notice;
  $('resultFootnote').textContent=`${mode==='candidates'?'候选':'全部结果'} ${rows.length} 只 · ${state.cutoff?'截至 '+state.cutoff+' 已收盘日线':'等待行情'} · 规则匹配不保证上涨`;
  busyControls();
}
async function selectStock(symbol){
  const serial=++chartSerial;selected=symbol;$('detailPanel').hidden=true;render();
  try{const data=await api('/api/chart/'+encodeURIComponent(symbol));if(serial!==chartSerial)return;chartData=data;
    const last=data.rows.at(-1),prev=data.rows.at(-2);$('detailPanel').hidden=false;
    $('stockSymbol').textContent=symbol.replace(/^US\./,'');$('stockName').textContent=data.name;$('stockPrice').textContent=fmt(last.close);
    const change=prev?(last.close/prev.close-1)*100:0;$('stockChange').textContent=signed(change);$('stockChange').className=tone(change);
    $('chartDataInfo').textContent=`${data.rows.length} 根日线 · 收盘 ${last.date}`;
    const notes=[];if(!data.long_history)notes.push('不足 330 根，长周期趋势线仅作部分历史参考；放量红柱照常计算。');if(data.stale)notes.push('当前为旧缓存，请扫描更新行情。');$('chartNotice').hidden=!notes.length;$('chartNotice').textContent=notes.join(' ');
    chart.setData(data);
    const events=data.events.slice(0,30);$('signalHistory').innerHTML=events.length?events.map((e,i)=>`<button class="history-card" data-event="${i}"><strong>${esc(e.signal_date)}</strong><span>${e.priority===2?'第二优先 · 仅红柱':e.same_day?'第一优先 · 同日配合':'第一优先 · 附近配合'} · ${fmt(e.volume_ratio)}×</span><small>${e.priority===2?'缺少放量确认':'黄色 '+esc(e.volume_date)} / 红柱 ${esc(e.bbuy_date)}</small><small>至最新收盘 <span class="${tone(e.since_signal)}">${signed(e.since_signal)}</span></small></button>`).join(''):'<p class="micro">当前缓存历史中没有符合此组合的信号。</p>';
    $('signalHistory').querySelectorAll('[data-event]').forEach(btn=>btn.addEventListener('click',()=>{const e=events[Number(btn.dataset.event)];chart.focus(e.index);}));
  }catch(error){if(serial===chartSerial)toast(error.message,true);}
}
async function poll(){if(polling)return;polling=true;try{
  const [status,results]=await Promise.all([api('/api/status'),api('/api/results')]);
  const firstPoll=!initialized, resultsChanged=JSON.stringify(state)!==JSON.stringify(results);
  if(!initialized){writeRules(status.settings);$('symbols').value=status.symbols.map(x=>x.replace(/^US\./,'')).join(', ');describeRules(status.settings);poolCount();savedSymbols=status.symbols;initialized=true;renderRuleFilters();}
  savedSymbols=status.symbols;const wasRunning=state.running;state=results;liveRules.resume();
  $('dataDate').textContent=`已收盘 ${status.cutoff}`;$('refreshTarget').textContent=`更新目标：${status.cutoff} · 使用已保存的股票池和规则`;
  const op=status.opend;$('connectionDot').className='dot '+(op.connected?'green':op.checking?'':'error');$('connectionText').textContent=op.connected?'OpenD 连接已验证':op.checking?'检查 OpenD…':'OpenD 未连接';$('connectionText').title=op.error||(op.checked_at?'上次验证 '+new Date(op.checked_at).toLocaleString():'');
  $('quota').textContent=op.remain==null?'—':op.remain.toLocaleString();$('quotaNote').textContent=op.used==null?'等待连接状态':`剩余股票数 · 已用 ${op.used}`;
  if(firstPoll||resultsChanged)render();
  if(!selected&&state.results.some(r=>r.status==='ok')){const first=state.results.find(r=>r.matched)||state.results.find(r=>r.status==='ok');selectStock(first.symbol);}
  if(wasRunning&&!state.running){toast(state.cancelled?'已取消剩余扫描':`扫描完成：${state.results.filter(r=>r.matched).length} 只候选，${state.failed} 只失败`);if(selected)await selectStock(selected);}
}catch(error){$('connectionDot').className='dot error';$('connectionText').textContent='本机服务未连接';$('statusNotice').hidden=false;$('statusNotice').textContent='无法连接本机服务，请运行项目中的“启动筛选器.command”。';}finally{polling=false;}}
$('ruleForm').addEventListener('submit',async e=>{e.preventDefault();if(!e.target.reportValidity())return;pending=true;busyControls();try{const p=readRules();const saved=await api('/api/settings',{settings:p,symbols:$('symbols').value});savedSymbols=saved.symbols;describeRules(p);chartSerial++;await poll();if(selected)await selectStock(selected);toast('条件已应用，使用缓存重算；缺少缓存的股票需要扫描。');}catch(err){toast(err.message,true);}finally{pending=false;busyControls();}});
$('scanBtn').onclick=async()=>{if(!$('ruleForm').reportValidity())return;pending=true;busyControls();try{const p=readRules();await api('/api/scan',{settings:p,symbols:$('symbols').value});describeRules(p);await poll();}catch(err){toast(err.message,true);}finally{pending=false;busyControls();}};
$('cancelBtn').onclick=async()=>{try{await api('/api/scan/cancel',{});$('cancelBtn').disabled=true;toast('正在结束当前请求，剩余股票将取消。');}catch(err){toast(err.message,true);}};
$('connectBtn').onclick=async()=>{try{await api('/api/connect',{});toast('正在重新检查 OpenD');await poll();}catch(err){toast(err.message,true);}};
$('candidatesTab').onclick=()=>{mode='candidates';render();};$('allTab').onclick=()=>{mode='all';render();};$('search').oninput=render;
$('symbols').oninput=poolCount;$('defaultBtn').onclick=()=>{$('symbols').value=defaultPool.split(' ').join(', ');poolCount();toast('已填入示例股票池，点击应用或扫描。');};
$('importBtn').onclick=()=>$('importFile').click();$('importFile').onchange=async e=>{const file=e.target.files[0];if(!file)return;if(file.size>200000){toast('文件过大，最多 200 KB',true);return;}$('symbols').value=await file.text();poolCount();toast('已读入文件，点击应用或扫描验证代码。');e.target.value='';};
$('exportBtn').onclick=()=>{window.location.href='/api/export?matched='+(mode==='candidates'?'1':'0');};
$('helpBtn').onclick=()=>$('helpDialog').showModal();$('closeHelp').onclick=()=>$('helpDialog').close();$('helpDialog').onclick=e=>{if(e.target===$('helpDialog')){const r=e.target.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)e.target.close();}};
$('zoomIn').onclick=()=>chart.zoom(.8);$('zoomOut').onclick=()=>chart.zoom(1.25);$('chartReset').onclick=()=>chart.reset();$('showKdj').onchange=()=>{chart.showKdj=$('showKdj').checked;chart.draw();};
poll();setInterval(poll,1800);

['sortBy','sectorFilter','indexFilter'].forEach(id=>$(id).addEventListener('change',render));

document.querySelectorAll('[data-priority]').forEach(button=>button.addEventListener('click',()=>{priorityFilter=Number(button.dataset.priority);render();}));

document.addEventListener('themechange',()=>chart.draw());

(()=>{
  const handle=$('resultsResize'),viewport=$('resultsViewport');
  let height=560,drag=null;
  const setHeight=value=>{height=Math.max(200,Math.min(1600,value));viewport.style.setProperty('--results-height',height+'px');handle.setAttribute('aria-valuenow',String(Math.round(height)));};
  const save=()=>{try{localStorage.setItem('signal-desk-results-height',String(height));}catch{}};
  try{const stored=Number(localStorage.getItem('signal-desk-results-height'));if(Number.isFinite(stored)&&stored>=200)setHeight(stored);}catch{}
  handle.addEventListener('pointerdown',event=>{if(event.button!==0)return;drag={y:event.clientY,height};handle.setPointerCapture(event.pointerId);document.body.classList.add('resizing-results');event.preventDefault();});
  handle.addEventListener('pointermove',event=>{if(drag)setHeight(drag.height+event.clientY-drag.y);});
  const finish=()=>{if(!drag)return;drag=null;document.body.classList.remove('resizing-results');save();};
  handle.addEventListener('pointerup',finish);handle.addEventListener('pointercancel',finish);handle.addEventListener('lostpointercapture',finish);
  handle.addEventListener('dblclick',()=>{setHeight(560);save();});
  handle.addEventListener('keydown',event=>{if(!['ArrowUp','ArrowDown','Home','End'].includes(event.key))return;event.preventDefault();setHeight(event.key==='Home'?200:event.key==='End'?1600:height+(event.key==='ArrowDown'?50:-50));save();});
})();

$('showVolatility').onchange=()=>{chart.showVolatility=$('showVolatility').checked;chart.draw();};

function showBacktest(r){if(!r.test)return;if(r.rules_changed){$('backtestSummary').textContent=' 规则、股票池或行情日期已变化，请重新回测';return;}const t=r.test;$('backtestMethod').textContent=`回测覆盖 ${r.coverage}/${r.total} · 测试段自 ${r.split} · ${r.methodology}`;$('backtestSummary').textContent=` 截至 ${r.cutoff} · 后30%样本 ${t.n} · 5日上涨占比 ${fmt(t.up_rate)}% · 平均收益 ${fmt(t.mean_return)}% · 平均区间最低收益 ${fmt(t.mean_drawdown)}% · ${r.evidence}`;$('backtestSummary').title=r.methodology;}
$('backtestBtn').onclick=async()=>{const b=$('backtestBtn');b.disabled=true;$('backtestSummary').textContent=' 正在评估缓存日线，请稍候…';try{showBacktest(await api('/api/backtest',{}));}catch(e){$('backtestSummary').textContent=' 回测失败：'+e.message;}finally{b.disabled=false;}};
api('/api/backtest').then(showBacktest).catch(()=>{});

$('symbols').addEventListener('change',()=>{$('backtestSummary').textContent=' 股票池已修改，请保存股票池';});

$('clearFilters').onclick=()=>{priorityFilter=0;$('sectorFilter').value='';$('indexFilter').value='';$('search').value='';render();};

$('refreshQuotesBtn').onclick=async()=>{
  if(pending||state.running)return;
  pending=true;busyControls();
  try{
    const s=await api('/api/status');
    if(s.scan.running){toast('已有扫描正在运行');await poll();return;}
    await api('/api/scan',{settings:s.settings,symbols:s.symbols});
    toast(`开始更新 ${s.cutoff} 已收盘行情`);
    await poll();
  }catch(e){toast('行情更新失败：'+e.message,true);}
  finally{pending=false;busyControls();}
};

$('showCapital').onchange=()=>{chart.showCapital=$('showCapital').checked;chart.draw();};
