const $=id=>document.getElementById(id);
const defaultPool='SPY QQQ SOXX IWM DIA AAPL MSFT NVDA AMZN GOOGL META TSLA AMD AVGO MU INTC NFLX PLTR COIN SMH';
const numericKeys=['volume_n','volume_mult','vwap_n','sigma','lookback','pair_gap'];
const boolKeys=['include_secondary','previous_volume','bullish_only','require_vwap','require_rising','require_macd','require_bottom'];
let state={results:[],running:false,total:0,completed:0,failed:0},mode='candidates',priorityFilter=0,selected=null,chartData=null;
let pending=false,initialized=false,polling=false,chartSerial=0,toastTimer=null;
const chart=new SignalChart($('chart'),$('chartTooltip'));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=(v,d=2)=>v==null?'—':Number(v).toFixed(d);
const signed=(v,d=2)=>v==null?'—':`${v>=0?'+':''}${Number(v).toFixed(d)}%`;
const tone=v=>v>0?'up':v<0?'down':'muted';
function toast(text,error=false){clearTimeout(toastTimer);$('toast').textContent=text;$('toast').className='toast'+(error?' error':'');$('toast').hidden=false;toastTimer=setTimeout(()=>$('toast').hidden=true,error?7000:3500);}
async function api(path,body){const res=await fetch(path,{method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});const data=await res.json();if(!res.ok)throw new Error(data.error||`请求失败 (${res.status})`);return data;}
function readRules(){const p={};numericKeys.forEach(k=>p[k]=Number($(k).value));boolKeys.forEach(k=>p[k]=$(k).checked);return p;}
function writeRules(p){numericKeys.forEach(k=>$(k).value=p[k]);boolKeys.forEach(k=>$(k).checked=p[k]);}
function poolCount(){const codes=$('symbols').value.trim().split(/[\s,;，；]+/).filter(Boolean);$('poolCount').textContent=`${new Set(codes).size} 只`;}
function describeRules(p){const relation=p.pair_gap===0?'放量与红柱同日':`放量与红柱相距 ≤ ${p.pair_gap} 日`;$('ruleDescription').textContent=`${p.previous_volume?'此前 ':''}${p.volume_n} 日均量 × ${p.volume_mult} · ${relation} · 最近 ${p.lookback} 个交易日${p.include_secondary?' · 包含仅红柱的第二优先':''}`;}
function busyControls(){const busy=state.running||pending;['scanBtn','applyBtn','defaultBtn','importBtn'].forEach(id=>$(id).disabled=busy);$('cancelBtn').hidden=!state.running;$('cancelBtn').disabled=pending;}
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
  const search=$('search').value.trim().toUpperCase();if(search)rows=rows.filter(r=>`${r.symbol} ${r.name}`.toUpperCase().includes(search));
  for(const [id,key] of [['sectorFilter','sectors'],['indexFilter','indices']]){const v=$(id).value;if(v)rows=rows.filter(r=>v==='__unknown'?!(r[key]||[]).length:(r[key]||[]).includes(v));}
  rows=[...rows].sort((a,b)=>($('sortBy').value!=='signal'?(a.market_cap==null?(b.market_cap==null?0:1):b.market_cap==null?-1:$('sortBy').value==='cap_desc'?b.market_cap-a.market_cap:a.market_cap-b.market_cap):0)||Number(b.matched)-Number(a.matched)||(a.priority||99)-(b.priority||99)||(b.signal_date||'').localeCompare(a.signal_date||''));
  $('resultRows').innerHTML=rows.map(r=>{
    const valid=['ok','insufficient','stale'].includes(r.status);
    const reason=r.matched?(r.priority===2?'<span class="signal-pill red">第二优先 · BBUY ↑</span><span class="signal-note">缺少放量确认</span>':'<span class="signal-pill">第一优先 · 黄色放量</span><span class="signal-pill red">BBUY ↑</span>'):`<span class="signal-note" title="${esc(r.error||'本窗口无组合信号')}">${esc(r.error||(r.latest_heavy?'最新日放量 · 暂无组合':r.latest_bbuy?'最新日红柱 · 暂无组合':'本窗口无组合信号'))}</span>`;
    return `<tr data-symbol="${esc(r.symbol)}" class="${selected===r.symbol?'selected':''}"><td><div class="ticker">${esc(r.symbol.replace(/^US\./,''))}${r.stale?'<span class="stale-tag">缓存待更新</span>':''}</div><div class="company">${esc(r.name)}</div></td><td class="classification-cell"><span class="num" title="${esc(r.market_cap_at||'市值未知')}">${r.market_cap==null?'—':fmt(r.market_cap/1e8)+' 亿'}</span><small title="${esc((r.sectors||[]).join(' / '))}">${esc((r.sectors||[]).slice(0,3).join(' / ')||'未分类')}${(r.sectors||[]).length>3?' 等 '+r.sectors.length+' 个板块':''}</small><small>${esc((r.indices||[]).join(' / ')||'无所选指数归属')}</small></td><td class="price-cell"><span class="num">${valid?fmt(r.close):'—'}</span><small class="${tone(r.change)}">${valid?signed(r.change):''}</small></td><td class="num">${esc(r.signal_date||'—')}</td><td class="num ${r.matched?'accent':''}">${fmt(r.volume_ratio??r.latest_volume_ratio)}×</td><td class="num ${tone(r.vwap_distance)}">${signed(r.vwap_distance)}</td><td>${reason}</td></tr>`;
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
  if(!initialized){writeRules(status.settings);$('symbols').value=status.symbols.map(x=>x.replace(/^US\./,'')).join(', ');describeRules(status.settings);poolCount();initialized=true;}
  const wasRunning=state.running;state=results;
  $('dataDate').textContent=`已收盘 ${status.cutoff}`;
  const op=status.opend;$('connectionDot').className='dot '+(op.connected?'green':op.checking?'':'error');$('connectionText').textContent=op.connected?'OpenD 连接已验证':op.checking?'检查 OpenD…':'OpenD 未连接';$('connectionText').title=op.error||(op.checked_at?'上次验证 '+new Date(op.checked_at).toLocaleString():'');
  $('quota').textContent=op.remain==null?'—':op.remain.toLocaleString();$('quotaNote').textContent=op.used==null?'等待连接状态':`剩余股票数 · 已用 ${op.used}`;
  if(firstPoll||resultsChanged)render();
  if(!selected&&state.results.some(r=>r.status==='ok')){const first=state.results.find(r=>r.matched)||state.results.find(r=>r.status==='ok');selectStock(first.symbol);}
  if(wasRunning&&!state.running){toast(state.cancelled?'已取消剩余扫描':`扫描完成：${state.results.filter(r=>r.matched).length} 只候选，${state.failed} 只失败`);if(selected)await selectStock(selected);}
}catch(error){$('connectionDot').className='dot error';$('connectionText').textContent='本机服务未连接';$('statusNotice').hidden=false;$('statusNotice').textContent='无法连接本机服务，请运行项目中的“启动筛选器.command”。';}finally{polling=false;}}
$('ruleForm').addEventListener('submit',async e=>{e.preventDefault();if(!e.target.reportValidity())return;pending=true;busyControls();try{const p=readRules();await api('/api/settings',{settings:p,symbols:$('symbols').value});describeRules(p);chartSerial++;await poll();if(selected)await selectStock(selected);toast('条件已应用，使用缓存重算；缺少缓存的股票需要扫描。');}catch(err){toast(err.message,true);}finally{pending=false;busyControls();}});
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
