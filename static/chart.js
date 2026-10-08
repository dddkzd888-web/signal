/* All panels share the same trading-bar axis. No remote scripts or data. */
class SignalChart {
  constructor(canvas, tooltip) {
    this.canvas=canvas; this.ctx=canvas.getContext('2d'); this.tooltip=tooltip;
    this.rows=[]; this.count=100; this.end=0; this.hover=null; this.showKdj=false;
    this.drag=null; this.focusIndex=null;
    new ResizeObserver(()=>this.draw()).observe(canvas.parentElement);
    canvas.addEventListener('pointerdown',e=>{this.drag={x:e.clientX,end:this.end};canvas.setPointerCapture(e.pointerId);});
    canvas.addEventListener('pointerup',()=>{this.drag=null;});
    canvas.addEventListener('pointercancel',()=>{this.drag=null;});
    canvas.addEventListener('pointermove',e=>this.move(e));
    canvas.addEventListener('pointerleave',()=>{if(!this.drag){this.hover=null;tooltip.hidden=true;this.draw();}});
    canvas.addEventListener('wheel',e=>{if(!e.ctrlKey)return;e.preventDefault();this.zoom(e.deltaY>0?1.15:.85);},{passive:false});
  }
  setData(data){this.rows=data.rows;this.events=data.events;this.end=this.rows.length;this.count=Math.min(100,this.rows.length);this.focusIndex=null;this.hover=null;this.tooltip.hidden=true;this.draw();}
  reset(){this.end=this.rows.length;this.count=Math.min(100,this.rows.length);this.focusIndex=null;this.draw();}
  focus(index){this.count=Math.min(90,this.rows.length);this.end=Math.min(this.rows.length,Math.max(this.count,index+Math.floor(this.count*.7)));this.focusIndex=index;this.draw();}
  zoom(factor){this.count=Math.max(Math.min(20,this.rows.length),Math.min(this.rows.length,Math.round(this.count*factor)));this.end=Math.max(this.count,Math.min(this.rows.length,this.end));this.draw();}
  move(e){if(!this.rows.length)return;const rect=this.canvas.getBoundingClientRect();const x=e.clientX-rect.left;
    if(this.drag){const delta=Math.round((e.clientX-this.drag.x)/this.step);this.end=Math.max(this.count,Math.min(this.rows.length,this.drag.end-delta));this.hover=null;this.tooltip.hidden=true;this.draw();return;}
    const index=Math.floor((x-this.left)/this.step)+this.start;
    if(index<this.start||index>=this.end){this.hover=null;this.tooltip.hidden=true;this.draw();return;}
    this.hover=index;const r=this.rows[index];const n=v=>v==null?'—':Number(v).toFixed(2);
    this.tooltip.replaceChildren();
    const lines=[r.date,`开 ${n(r.open)}  高 ${n(r.high)}`,`低 ${n(r.low)}  收 ${n(r.close)}`,`成交量 ${this.volume(r.volume)} · 均量 ${n(r.volume_ratio)}×`,`VWAP ${n(r.vwap)}`,`DIF ${n(r.diff)} · DEA ${n(r.dea)}`,`${r.heavy?'黄色放量 K 线 ✓':'未放量'}  ${r.bbuy?'BBUY 红柱 ↑':'无 BBUY 红柱'}`];
    lines.forEach((text,i)=>{const d=document.createElement('div');d.textContent=text;if(i===0)d.style.color='#f3bf62';this.tooltip.append(d);});
    this.tooltip.style.left=x>this.width*.55?'20px':'auto';this.tooltip.style.right=x>this.width*.55?'auto':'75px';this.tooltip.hidden=false;this.draw();
  }
  volume(v){return v>=1e9?(v/1e9).toFixed(2)+'B':v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'K':String(Math.round(v));}
  text(text,x,y,color='#8090a5',size=10,align='left'){const c=this.ctx;c.fillStyle=this.light?({'#b8c5d5':'#475569','#8090a5':'#64748b','#a5b4c8':'#526175'}[color]||color):color;c.font=`${size}px -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif`;c.textAlign=align;c.fillText(text,x,y);}
  line(x1,y1,x2,y2,color,width=1,dash=[]){const c=this.ctx;c.beginPath();c.strokeStyle=this.light?({'#23303c':'#e6ebf2','#202b38':'#e6ebf2','#293442':'#dfe6ef','#25303e':'#e6ebf2','#344154':'#d7e0ea'}[color]||color):color;c.lineWidth=width;c.setLineDash(dash);c.moveTo(x1,y1);c.lineTo(x2,y2);c.stroke();c.setLineDash([]);}
  arrow(x,y,color,up=true){const c=this.ctx;const a=up?-1:1;c.fillStyle=color;c.beginPath();c.moveTo(x,y+a*6);c.lineTo(x-5,y-a);c.lineTo(x-2,y-a);c.lineTo(x-2,y-a*7);c.lineTo(x+2,y-a*7);c.lineTo(x+2,y-a);c.lineTo(x+5,y-a);c.closePath();c.fill();}
  draw(){
    const width=this.canvas.parentElement.clientWidth-18;
    if(width<=0)return;const height=this.showKdj?786:680;
    this.canvas.style.height=height+'px';const dpr=window.devicePixelRatio||1;
    this.canvas.width=Math.round(width*dpr);this.canvas.height=Math.round(height*dpr);
    this.light=document.documentElement.dataset.theme==='light';
    const c=this.ctx;c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,width,height);
    this.width=width;this.left=10;this.right=width-64;
    if(!this.rows.length){this.text('等待行情…',width/2,height/2,'#8090a5',12,'center');return;}
    this.end=Math.max(1,Math.min(this.end,this.rows.length));this.count=Math.min(this.count,this.end);
    this.start=Math.max(0,this.end-this.count);this.step=(this.right-this.left)/this.count;
    const rows=this.rows.slice(this.start,this.end);const x=i=>this.left+(i-this.start+.5)*this.step;
    const bw=Math.max(1,Math.min(12,this.step*.62));
    const panels=[{id:'price',label:'日线 · 前复权',top:0,h:290},{id:'volume',label:'成交量',top:290,h:85},{id:'indicator',label:'NEW7 · 自定义副图',top:375,h:155},{id:'macd',label:'MACD',top:530,h:125}];
    if(this.showKdj)panels.push({id:'kdj',label:'KDJ',top:655,h:106});
    const bottom=height-25;
    const visible=this.hover==null?this.end-1:this.hover;
    const current=this.rows[visible];const f=v=>v==null?'—':v.toFixed(2);
    panels.forEach(p=>{
      this.line(this.left,p.top,this.width,p.top,'#293442');
      this.text(p.label,this.left+5,p.top+17,'#b8c5d5',10);
      const plotTop=p.top+29,plotBottom=p.top+p.h-9;
      let min,max;
      if(p.id==='price'){
        const vals=rows.flatMap(r=>[r.low,r.high,r.vwap,r.lower,r.upper]).filter(v=>v!=null&&Number.isFinite(v));
        min=Math.min(...vals);max=Math.max(...vals);const pad=(max-min||max*.02||1)*.08;min-=pad;max+=pad;
      }else if(p.id==='volume'){min=0;max=Math.max(1,...rows.map(r=>r.volume))*1.15;}
      else if(p.id==='indicator'){min=0;max=Math.max(110,...rows.map(r=>r.step||0));}
      else if(p.id==='macd'){const vals=rows.flatMap(r=>[r.diff,r.dea,r.macd]).filter(v=>v!=null);min=Math.min(0,...vals);max=Math.max(0,...vals);let pad=(max-min||1)*.15;min-=pad;max+=pad;}
      else{min=Math.min(-5,...rows.map(r=>r.j==null?0:r.j));max=Math.max(105,...rows.map(r=>r.j||0));}
      const y=value=>plotBottom-(value-min)/(max-min)*(plotBottom-plotTop);
      const ticks=p.id==='indicator'?[0,20,50,80,100]:[0,1,2,3,4].map(i=>min+(max-min)*i/4);
      ticks.forEach(v=>{this.line(this.left,y(v),this.right,y(v),'#23303c',.6,[3,4]);this.text(p.id==='volume'?this.volume(v):v.toFixed(p.id==='price'?2:p.id==='macd'?1:0),this.right+7,y(v)+3,'#64768a',9);});
      for(let i=0;i<=6;i++){const xx=this.left+(this.right-this.left)*i/6;this.line(xx,plotTop,xx,plotBottom,'#202b38',.6);}
      const poly=(field,color,lineWidth=1.3)=>{c.strokeStyle=this.light?({'#23303c':'#e6ebf2','#202b38':'#e6ebf2','#293442':'#dfe6ef','#25303e':'#e6ebf2','#344154':'#d7e0ea'}[color]||color):color;c.lineWidth=lineWidth;c.beginPath();let started=false;for(let i=this.start;i<this.end;i++){const v=this.rows[i][field];if(v==null||!Number.isFinite(v)){started=false;continue;}if(!started){c.moveTo(x(i),y(v));started=true;}else c.lineTo(x(i),y(v));}c.stroke();};
      c.save();c.beginPath();c.rect(this.left,plotTop,this.right-this.left,plotBottom-plotTop);c.clip();
      if(p.id==='price'){
        poly('upper','#548aff',1);poly('lower','#548aff',1);
        for(let i=this.start+1;i<this.end;i++){const a=this.rows[i-1],b=this.rows[i];if(a.vwap==null||b.vwap==null)continue;this.line(x(i-1),y(a.vwap),x(i),y(b.vwap),b.close>=b.vwap?'#28bd96':'#e56ecb',2);}
        for(let i=this.start;i<this.end;i++){const r=this.rows[i],xx=x(i),up=r.close>=r.open,color=up?'#f75868':'#28bd96';this.line(xx,y(r.high),xx,y(r.low),color,1);c.fillStyle=r.heavy?'#f3bf62':color;c.fillRect(xx-bw/2,Math.min(y(r.open),y(r.close)),bw,Math.max(1,Math.abs(y(r.open)-y(r.close))));if(r.heavy){c.strokeStyle=this.light?({'#23303c':'#e6ebf2','#202b38':'#e6ebf2','#293442':'#dfe6ef','#25303e':'#e6ebf2','#344154':'#d7e0ea'}[color]||color):color;c.lineWidth=.8;c.strokeRect(xx-bw/2,Math.min(y(r.open),y(r.close)),bw,Math.max(1,Math.abs(y(r.open)-y(r.close))));}if(r.vwap_up)this.arrow(xx,y(r.low)+13,'#f75868');if(r.vwap_down)this.arrow(xx,y(r.high)-13,'#28bd96',false);}
        this.line(this.left,y(rows[rows.length-1].close),this.right,y(rows[rows.length-1].close),'#8296b566',.7,[2,5]);
      }else if(p.id==='volume'){
        for(let i=this.start;i<this.end;i++){const r=this.rows[i];c.fillStyle=r.heavy?'#f3bf62':r.close>=r.open?'#f7586866':'#28bd9666';c.fillRect(x(i)-bw/2,y(r.volume),bw,plotBottom-y(r.volume));}poly('volume_mean','#f3bf62',1);
      }else if(p.id==='indicator'){
        const fillBand=(a,b,color)=>{c.fillStyle=color;c.fillRect(this.left,y(b),this.right-this.left,y(a)-y(b));};
        fillBand(90,100,'#97c8ff');fillBand(80,90,'#46a3ff');fillBand(10,20,'#0072e3');fillBand(0,10,'#0066cc');
        for(let i=this.start;i<this.end;i++){const r=this.rows[i];if(r.background){c.fillStyle=r.background>0?'#d7fca5':'#f09b9c';c.fillRect(x(i)-this.step/2,y(80),this.step+.4,y(20)-y(80));}if(r.flame>0){c.fillStyle='#c07ab8';c.fillRect(x(i)-bw/2,y(r.flame),bw,y(0)-y(r.flame));}if(r.low_buy){c.fillStyle='#f75868';c.fillRect(x(i)-2,y(20),4,y(0)-y(20));}if(r.strong_pull){c.fillStyle='#ffe15b';c.fillRect(x(i)-1,y(20),2,y(2)-y(20));}if(r.extra_pull){c.fillStyle='#fff';c.fillRect(x(i)-1,y(50),2,y(0)-y(50));}if(r.half_buy){c.fillStyle='#88c6ff';c.fillRect(x(i)-2,y(20),4,y(0)-y(20));}}
        this.line(this.left,y(50),this.right,y(50),'#2cbe46',1,[4,4]);poly('trend_line','#4f91ec',3);
        for(let i=this.start+1;i<this.end;i++){const r=this.rows[i],prev=this.rows[i-1];if(r.step!=null&&prev.step!=null){c.fillStyle=r.step_rising?'#24e622':'#fa4f30';c.fillRect(x(i)-bw/2,Math.min(y(r.step),y(prev.step)),bw,Math.max(2,Math.abs(y(r.step)-y(prev.step))));}}
        poly('step','#2eead7',1);
        c.beginPath();c.strokeStyle='#17202a';c.lineWidth=2;for(let i=this.start;i<this.end;i++){const yy=y(this.rows[i].sold?85:100);if(i===this.start)c.moveTo(x(i),yy);else c.lineTo(x(i),yy);}c.stroke();
        for(let i=this.start;i<this.end;i++){const r=this.rows[i],xx=x(i);if(r.bbuy){c.fillStyle='#ef3349';c.fillRect(xx-3,y(60),6,y(0)-y(60));this.arrow(xx,y(70),'#e8293f');}if(r.macd_bottom)this.text('M底',xx,y(65),'#17212d',8,'center');if(r.kdj_bottom)this.text('K底',xx,y(35),'#17212d',8,'center');if(r.rsi_bottom)this.text('R底',xx,y(50),'#17212d',8,'center');if(r.macd_top)this.text('M顶',xx,y(70),'#17212d',8,'center');if(r.run)this.text('RUN',xx,y(25),'#ffe35a',8,'center');if(r.double_gold){c.fillStyle='#ffd34d';c.beginPath();c.arc(xx,y(20),4,0,Math.PI*2);c.fill();}}
      }else if(p.id==='macd'){
        this.line(this.left,y(0),this.right,y(0),'#64768a',.7);
        for(let i=this.start;i<this.end;i++){const r=this.rows[i];if(r.macd==null)continue;c.fillStyle=r.macd>0?'#f75868':'#28bd96';c.fillRect(x(i)-Math.max(1,bw*.2),Math.min(y(r.macd),y(0)),Math.max(1,bw*.4),Math.max(1,Math.abs(y(r.macd)-y(0))));}poly('diff','#ff9b48',1.5);poly('dea','#38c2ee',1.5);
      }else{poly('k','#ff9b48',1.3);poly('d','#38c2ee',1.3);poly('j','#e972ed',1.3);}
      c.restore();
      if(p.id==='price')this.text(`VWAP ${f(current.vwap)}  上轨 ${f(current.upper)}  下轨 ${f(current.lower)}`,this.left+112,p.top+17,'#6f95c9',9);
      if(p.id==='volume')this.text(`${this.volume(current.volume)}   ${f(current.volume_ratio)} × 均量`,this.left+65,p.top+17,'#f3bf62',9);
      if(p.id==='indicator')this.text(`BBUY ${current.bbuy?'↑ 红柱':'—'}   阶梯 ${f(current.step)}   趋势 ${f(current.trend_line)}`,this.left+142,p.top+17,'#8ab997',9);
      if(p.id==='macd')this.text(`DIF ${f(current.diff)}   DEA ${f(current.dea)}   MACD ${f(current.macd)}`,this.left+65,p.top+17,'#a896cc',9);
      if(p.id==='kdj')this.text(`K ${f(current.k)}   D ${f(current.d)}   J ${f(current.j)}`,this.left+65,p.top+17,'#a896cc',9);
      if(this.focusIndex!=null&&this.focusIndex>=this.start&&this.focusIndex<this.end){c.fillStyle='#f3bf6212';c.fillRect(x(this.focusIndex)-this.step/2,plotTop,this.step,plotBottom-plotTop);this.line(x(this.focusIndex),plotTop,x(this.focusIndex),plotBottom,'#f3bf62',.8,[3,3]);}
      if(this.hover!=null&&this.hover>=this.start&&this.hover<this.end)this.line(x(this.hover),plotTop,x(this.hover),plotBottom,'#aabbd0',.8,[3,3]);
    });
    for(let j=0;j<7;j++){const i=this.start+Math.round((this.count-1)*j/6);this.text(this.rows[i].date,x(i),bottom+16,'#6e8299',9,j===0?'left':j===6?'right':'center');}
  }
}
window.SignalChart=SignalChart;
