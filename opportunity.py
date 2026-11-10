"""Fixed low-position confirmation rules and chronological five-session evaluation."""
from indicators import enrich, match_signals

def assess(rows):
    r=rows[-1] if rows else {}
    fields=('ema5','ema20','atr14','low30','high60','low60','macd')
    if any(r.get(k) is None for k in fields) or len(rows)<2:
        return dict(early_ok=False,early_score=None,early_reason='历史不足：至少60根日线')
    c=r['close']; prev=rows[-2]
    checks=[
        ('低位区域', (c-r['low60'])/(r['high60']-r['low60'] or 1)<=.55),
        ('距30日低点不超过12%',c<=r['low30']*1.12),
        ('价格站上5日均线且均线抬升',c>r['ema5'] and r['ema5']>prev.get('ema5',r['ema5'])),
        ('收盘止跌',c>=prev['close']),
        ('MACD动能改善',prev.get('macd') is not None and r['macd']>prev['macd']),
        ('未远离20日均线',c-r['ema20']<=2*r['atr14']),
        ('20日平均成交额≥1000万美元',(r.get('dollar_volume20') or 0)>=1e7)]
    score=round(100*sum(ok for _,ok in checks)/len(checks))
    return dict(early_ok=all(ok for _,ok in checks),early_score=score,
                early_reason=' · '.join(name for name,ok in checks if not ok) or '低位、止跌、动能改善、流动性全部满足')

def summarize(samples):
    if not samples:return dict(n=0,up_rate=None,mean_return=None,mean_drawdown=None)
    return dict(n=len(samples),up_rate=100*sum(s['return']>0 for s in samples)/len(samples),
                mean_return=sum(s['return'] for s in samples)/len(samples),
                mean_drawdown=sum(s['drawdown'] for s in samples)/len(samples))

def backtest(store,symbols,settings,cutoff):
    samples=[]; dates=set(); available=0
    p=dict(settings,early_mode=True)
    for symbol in symbols:
        cached=store.bars(symbol)
        if not cached:continue
        bars=[r for r in cached['rows'] if r['date']<=cutoff]
        if len(bars)<120:continue
        available+=1
        rows=enrich(bars,p)
        start=max(60,len(rows)-500)
        dates.update(r['date'] for r in rows[start:-5])
        next_allowed=start
        for i in range(start,len(rows)-5):
            if i<next_allowed or not assess(rows[:i+1])['early_ok']:continue
            signal=match_signals(rows[max(0,i-60):i+1],p)
            if not signal['matched']:continue
            entry=rows[i+1]['open']
            if entry<=0:continue
            end=rows[i+5]
            samples.append(dict(symbol=symbol,date=rows[i]['date'],exit_date=end['date'],
                                return_value=(end['close']/entry-1)*100,
                                drawdown=(min(r['low'] for r in rows[i+1:i+6])/entry-1)*100))
            next_allowed=i+6
    ordered=sorted(dates)
    split=ordered[int(len(ordered)*.7)] if ordered else cutoff
    for s in samples:s['return']=s.pop('return_value')
    train=[s for s in samples if s['exit_date']<split]
    test=[s for s in samples if s['date']>=split]
    return dict(cutoff=cutoff,split=split,coverage=available,total=len(symbols),
                train=summarize(train),test=summarize(test),
                settings=dict(settings), symbols=list(symbols), evidence='证据不足' if len(test)<100 else '尚未证明预测优势；非个股上涨概率',
                methodology='固定规则；按日期前70%/后30%划分，中间排除跨界持仓；每股持仓不重叠；信号次日开盘进入、第5日收盘退出；未计费用、滑点；当前观察池存在幸存者偏差，同日股票样本相关。',samples=samples)
