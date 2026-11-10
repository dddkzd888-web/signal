# -*- coding: utf-8 -*-
"""Read-only cache study. Fixed rules, 5-session next-open entries, chronological validation."""
import sys,json,csv,math,hashlib,html
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from market import Store,calendar
from indicators import enrich,cross
from opportunity import assess
OUT=Path(__file__).parent;store=Store(ROOT/'data/cache.sqlite')
END='2026-10-20';START='2024-10-20';FEE=.0005
m7=['US.AAPL','US.MSFT','US.AMZN','US.GOOGL','US.META','US.NVDA','US.TSLA']
metadata=store.get('stock_metadata',{})
large=[c for c in store.get('symbols') if (metadata.get(c,{}).get('market_cap') or 0)>=50e9 and c!='US.GOOG']
sessions=[x.strftime('%Y-%m-%d') for x in calendar().sessions_in_range(START,END) if x.strftime('%Y-%m-%d')!='2025-01-09'] # NYSE Carter national mourning closure, absent from bundled calendar
SPLIT=sessions[int(len(sessions)*.7)]
LABELS={'baseline':'无条件5日轮换（基准）','heavy':'黄色放量（2倍）','bbuy':'BBUY红柱','pair':'黄K＋BBUY同日','vwap_up':'放量上穿VWAP','vol_warning':'波动率变盘预警','vol_panic_buy':'波动率恐慌回落箭头','capital_up':'主力资金上穿零轴','capital_strength':'主力资金为正且抬升','macd_cross':'MACD金叉','macd_recover':'MACD绿柱缩短','kdj_cross':'KDJ低位金叉（K＜50）','step_rising':'NEW7绿色阶梯抬升','divergence':'任一底背离','early':'稳健左侧条件','full':'当前全套规则','no_warning':'全套去掉变盘预警','no_early':'全套去掉稳健左侧'}
DEFS={'heavy':'VOL > MA(VOL,20)×2，均量含当天','bbuy':'CROSS(EMA(HLC3,6),EMA(EMA(HLC3,6),5))','pair':'heavy AND bbuy 同一日','vwap_up':'heavy AND CROSS(CLOSE,滚动VWAP30)','vol_warning':'VOLINDEX < LLV(VOLINDEX,60)×1.1 AND CROSS(VOLINDEX,VOLMA5)','vol_panic_buy':'HHV(VOLINDEX,20)=REF(VOLINDEX,1) AND CROSS(VOLMA,VOLINDEX) AND CLOSE<MA20','capital_up':'价格推算主力资金 CROSS(值,0)，不是实际资金流','capital_strength':'价格推算主力资金>0 且高于前一日','macd_cross':'CROSS(DIF12/26,DEA9)','macd_recover':'MACD<0 且高于前一日','kdj_cross':'CROSS(K,D) 且 K<50','step_rising':'NEW7 step_rising 原公式状态','divergence':'MACD/KDJ/RSI 任一底背离','early':'当前7项低位、止跌、动能、防追高、流动性条件全部满足','full':'近5日BBUY＋近5日波动率预警＋当日稳健左侧；原配置允许第二优先，因此放量不是必需','no_warning':'近5日BBUY＋当日稳健左侧','no_early':'近5日BBUY＋近5日波动率预警','baseline':'每股固定间隔5交易日持有5日，不检查指标，独立对照'}
LABELS={'baseline':'无条件5日轮换','full':'旧版全套（含预警）','no_warning':'删除预警后的基础组合','confirmed':'新版：基础组合＋底背离或MACD金叉确认'}
DEFS['confirmed']='近5日BBUY＋当日稳健左侧＋近5日底背离或MACD金叉，不使用波动率预警'
allrows={};flags={};excluded=[];source=[]
for num,c in enumerate(sorted(set(large+m7+['US.SPY']))):
    d=store.bars(c)
    if not d:excluded.append(dict(symbol=c,reason='无缓存'));continue
    bars=[r for r in d['rows'] if r['date']<=END]
    first=next((i for i,r in enumerate(bars) if r['date']>=sessions[0]),len(bars))
    if first<121 or not bars or bars[-1]['date']<END:
        excluded.append(dict(symbol=c,reason='两年历史或122根预热不足',first=bars[0]['date'] if bars else None));continue
    if [r['date'] for r in bars[first:]]!=sessions:
        excluded.append(dict(symbol=c,reason='研究窗口内缺交易日'));continue
    rows=enrich(bars,dict(volume_n=20,volume_mult=2,previous_volume=False,vwap_n=30,sigma=1.5))
    mac=cross([r['diff'] for r in rows],[r['dea'] for r in rows]);kdj=cross([r['k'] for r in rows],[r['d'] for r in rows])
    ff={k:[] for k in LABELS}
    for i,r in enumerate(rows):
        b=any(x['bbuy'] for x in rows[max(0,i-4):i+1]);w=any(x['vol_warning'] for x in rows[max(0,i-4):i+1]);early=assess(rows[max(0,i-1):i+1])['early_ok']
        values=dict(baseline=True,heavy=r['heavy'],bbuy=r['bbuy'],pair=r['heavy'] and r['bbuy'],vwap_up=r['vwap_up'],vol_warning=r['vol_warning'],vol_panic_buy=r['vol_panic_buy'],capital_up=r['capital_up'],capital_strength=r['capital_value'] is not None and r['capital_value']>0 and r['capital_rising'],macd_cross=mac[i],macd_recover=i>0 and r['macd']<0 and r['macd']>rows[i-1]['macd'],kdj_cross=kdj[i] and r['k'] is not None and r['k']<50,step_rising=r['step_rising'],divergence=any(r[k] for k in ['macd_bottom','kdj_bottom','rsi_bottom']),early=early,full=b and w and early,no_warning=b and early,no_early=b and w)
        confirm=any(mac[j] or any(rows[j][k] for k in ['macd_bottom','kdj_bottom','rsi_bottom']) for j in range(max(0,i-4),i+1))
        values['confirmed']=b and early and confirm
        for k in LABELS:ff[k].append(bool(values[k]))
    allrows[c]=rows;flags[c]=ff
    source.append(dict(symbol=c,first=bars[0]['date'],last=bars[-1]['date'],n=len(bars),fetched=d['fetched'],market_cap=metadata.get(c,{}).get('market_cap'),sha256=hashlib.sha256(json.dumps(bars,sort_keys=True).encode()).hexdigest()))
    if num%40==0:print('Enriched',num,flush=True)
spy={r['date']:r for r in allrows['US.SPY']}

def trade_sample(c,key,lo,hi,horizon=5):
    rows=allrows[c];nxt=0;out=[]
    for i,r in enumerate(rows):
        if i<nxt or r['date']<lo or r['date']>hi or i+horizon>=len(rows) or rows[i+horizon]['date']>hi:continue
        if not flags[c][key][i]:continue
        e=rows[i+1];z=rows[i+horizon];entry=e['open']
        gross=z['close']/entry-1;net=(1+gross)*(1-FEE)**2-1
        bench=spy[z['date']]['close']/spy[e['date']]['open']-1
        low=min(x['low'] for x in rows[i+1:i+horizon+1]);mae=min(0,low/entry-1)
        out.append(dict(symbol=c,signal=r['date'],entry=e['date'],exit=z['date'],i=i,horizon=horizon,entry_price=entry,exit_price=z['close'],gross=gross,net=net,excess=net-bench,spy=bench,mae=mae))
        nxt=i+horizon
    return out

def stats(trades,codes,lo,hi,portfolio=True):
    if not trades:return dict(n=0,stocks=0,dates=0,win=None,mean=None,gross=None,excess=None,mae=None,worst_mae=None,maxdd=None,total_return=None,ci_low=None,ci_high=None)
    avg=lambda k:float(np.mean([t[k] for t in trades]))*100
    # Monthly block resampling preserves same-month cross-stock dependence approximately.
    groups=defaultdict(list)
    for t in trades:groups[t['signal'][:7]].append(t['excess'])
    keys=sorted(groups);rng=np.random.default_rng(41);tot=np.array([sum(groups[k]) for k in keys]);counts=np.array([len(groups[k]) for k in keys])
    draws=rng.integers(0,len(keys),size=(1500,len(keys)));boot=tot[draws].sum(axis=1)/counts[draws].sum(axis=1)*100
    exposure=100*sum(t['horizon'] for t in trades)/(len(codes)*sum(lo<=d<=hi for d in sessions))
    result=dict(exposure=exposure,n=len(trades),stocks=len({t['symbol'] for t in trades}),dates=len({t['signal'] for t in trades}),months=len(keys),win=100*sum(t['net']>0 for t in trades)/len(trades),mean=avg('net'),gross=avg('gross'),excess=avg('excess'),mae=avg('mae'),worst_mae=min(t['mae'] for t in trades)*100,ci_low=float(np.percentile(boot,2.5)),ci_high=float(np.percentile(boot,97.5)),maxdd=None,total_return=None)
    if portfolio:
        days=[d for d in sessions if lo<=d<=hi];idx={d:j for j,d in enumerate(days)};equity=np.zeros(len(days));by=defaultdict(list)
        for t in trades:by[t['symbol']].append(t)
        for c in codes:
            curve=np.ones(len(days));factors=np.ones(len(days));rows=allrows[c]
            for t in by[c]:
                for j in range(t['i']+1,t['i']+t['horizon']+1):
                    day=rows[j]['date'];factor=rows[j]['close']/(t['entry_price'] if j==t['i']+1 else rows[j-1]['close'])
                    if j==t['i']+1:factor*=1-FEE
                    if j==t['i']+t['horizon']:factor*=1-FEE
                    factors[idx[day]]*=factor
            equity+=np.cumprod(factors)/len(codes)
        peaks=np.maximum.accumulate(np.r_[1.,equity]);dd=np.r_[1.,equity]/peaks-1
        result.update(maxdd=float(dd.min()*100),total_return=float((equity[-1]-1)*100))
    return result

result={};csvrows=[];trades_export=[]
for group,requested in [('M7',m7),('500亿以上',large)]:
    codes=[c for c in requested if c in allrows];table=[]
    for key in LABELS:
        partitions={}
        for name,lo,hi in [('full',sessions[0],END),('train',sessions[0],sessions[sessions.index(SPLIT)-1]),('test',SPLIT,END)]:
            trades=[t for c in codes for t in trade_sample(c,key,lo,hi)]
            partitions[name]=stats(trades,codes,lo,hi)
            if name=='full':trades_export.extend(dict(group=group,indicator=key,**{k:v for k,v in t.items() if k!='i'}) for t in trades)
        sens={}
        for h in [10,20]:
            tt=[t for c in codes for t in trade_sample(c,key,SPLIT,END,h)];sens[str(h)]=stats(tt,codes,SPLIT,END,False)
        table.append(dict(key=key,label=LABELS[key],definition=DEFS[key],**partitions,sensitivity=sens))
        for part in partitions:csvrows.append(dict(group=group,indicator=LABELS[key],partition=part,**partitions[part]))
    # Fixed training ordering, so validation results do not decide the selection order.
    threshold=20 if group=='M7' else 100
    ranked=sorted([r for r in table if r['key']!='baseline'],key=lambda r:(r['train']['n']>=threshold,r['train']['excess'] if r['train']['excess'] is not None else -999),reverse=True)
    for rank,r in enumerate(ranked,1):r['training_rank']=rank
    result[group]=dict(requested=len(requested),covered=len(codes),symbols=codes,table=table,ranking=[r['key'] for r in ranked],min_n=threshold)
    print(group,'complete',len(codes),flush=True)
report=dict(start=sessions[0],end=END,split=SPLIT,sessions=len(sessions),metadata_at=store.get('metadata_updated_at'),settings=store.get('settings'),groups=result,excluded=excluded,sources=source,cost_roundtrip_bps=10,created_at=pd.Timestamp.now(tz='UTC').isoformat(),limitations=['当前网站观察池内的当前市值筛选，不是全美股历史成分池；有幸存者与历史市值前视偏差','谷歌仅计GOOGL，排除GOOG双重计数；新上市或缺日线股票排除','按时间前70%探索、后30%验证；这是指标比较研究，重复比较存在多重检验和择优偏差，不是独立前瞻验证','单股同信号持仓不重叠，但不同股票/指标并不独立；月度块bootstrap为粗略敏感性区间，测试段月份少','前复权价格，非完整分红再投资总收益；假设可按次日开盘成交，每边5基点，无止损、无利息、无税费','组合最大回撤：每股初始等资金、盈利留在各自子账户、空仓现金不计息、逐日收盘估值；不等于单笔区间最低浮亏','所有条件使用信号日可见数据，进场次日，最后五个交易日未成熟信号不计入5日统计'])
(OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
for filename,rows in [('comparison.csv',csvrows),('trades.csv',trades_export)]:
    with (OUT/filename).open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
for group,g in result.items():
 print('\nGROUP',group,'covered',g['covered'])
 for r in sorted(g['table'],key=lambda r:r['test']['excess'] if r['test']['excess'] is not None else -999,reverse=True):print(r['key'],json.dumps(r['test'],ensure_ascii=False))
