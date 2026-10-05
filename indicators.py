"""Price-only translations of the supplied Futu formulas; no look-ahead."""
import math
import numpy as np
import pandas as pd

DEFAULTS = dict(volume_n=20, volume_mult=1.5, previous_volume=False,
                vwap_n=30, sigma=1.5, lookback=5, pair_gap=0,
                bullish_only=False, require_vwap=False, require_rising=False,
                require_macd=False, require_bottom=False, include_secondary=True)


def _smooth(values, alpha):
    result, prev = [], float('nan')
    for value in values:
        value = float(value) if value is not None else float('nan')
        if math.isfinite(value):
            prev = value if not math.isfinite(prev) else alpha * value + (1-alpha) * prev
            result.append(prev)
        else:
            result.append(float('nan'))
    return result


def ema(values, n):
    return _smooth(values, 2/(n+1))


def sma(values, n, m=1):
    return _smooth(values, m/n)


def cross(a, b):
    a, b = list(a), list(b)
    return [False] + [bool(a[i] > b[i] and a[i-1] <= b[i-1]) for i in range(1, len(a))] if a else []


def _div(a, b):
    return a / b.replace(0, np.nan)


def _divergence(price, oscillator, crosses, bottom=True):
    result, previous = [], None
    for i, event in enumerate(crosses):
        found = False
        if event:
            if previous is not None:
                found = (price.iloc[i] < price.iloc[previous] and oscillator.iloc[i] > oscillator.iloc[previous]) if bottom else (price.iloc[i] > price.iloc[previous] and oscillator.iloc[i] < oscillator.iloc[previous])
            previous = i
        result.append(bool(found))
    return result


def enrich(bars, settings=None):
    if not bars:
        return []
    p = dict(DEFAULTS, **(settings or {}))
    f = pd.DataFrame(bars).copy().reset_index(drop=True)
    c, h, l, o, v = [f[k].astype(float) for k in ('close', 'high', 'low', 'open', 'volume')]
    S = lambda values: pd.Series(values, index=f.index, dtype=float)
    E = lambda x, n: S(ema(x, n))
    A = lambda x, n, m=1: S(sma(x, n, m))
    low = lambda x, n: x.rolling(n, min_periods=1).min()
    high = lambda x, n: x.rolling(n, min_periods=1).max()
    mean = lambda x, n: x.rolling(n, min_periods=n).mean()
    X = lambda a, b: pd.Series(cross(a, b), index=f.index)
    src = (h+l+c)/3
    rv = v.rolling(p['vwap_n'], min_periods=1).sum()
    vwap = _div((src*v).rolling(p['vwap_n'], min_periods=1).sum(), rv).where(rv > 0, src)
    variance = (_div((src*src*v).rolling(p['vwap_n'], min_periods=1).sum(), rv) - vwap*vwap).clip(lower=0)
    sd = variance.pow(.5).where(rv > 0, 0)
    vm = mean(v.shift(1) if p['previous_volume'] else v, p['volume_n'])
    heavy = v > vm*p['volume_mult']
    f['vwap'], f['upper'], f['lower'] = vwap, vwap+p['sigma']*sd, vwap-p['sigma']*sd
    f['volume_mean'], f['volume_ratio'] = vm, _div(v, vm)
    f['heavy'] = heavy
    f['vwap_up'], f['vwap_down'] = X(c, vwap)&heavy, X(vwap, c)&heavy
    rsv = _div(c-low(l,9), high(h,9)-low(l,9))*100
    inv = _div(high(h,9)-c, high(h,9)-low(l,9))*100
    k, d = A(rsv,3), A(A(rsv,3),3)
    f['k'], f['d'], f['j'] = k, d, 3*k-2*d
    topbottom = d-A(inv,9)+50
    var4 = 100-E(_div(c-low(l,330), high(h,210)-low(l,330))*100,10)
    trend = 100-(.191*var4.shift(1)+.809*var4)
    f['trend_line'] = trend
    # Later STICKLINE calls overwrite earlier ones at identical coordinates.
    background = pd.Series(0, index=f.index)
    background[topbottom > topbottom.shift(1)] = 1
    background[topbottom < topbottom.shift(1)] = -1
    background[(trend > trend.shift(1)) & (topbottom < topbottom.shift(1))] = 1
    background[(trend < trend.shift(1)) & (topbottom > topbottom.shift(1))] = -1
    f['background'] = background
    var6b = d-A(inv-70,9)
    step = (var6b-45).clip(lower=0)
    f['step'], f['step_rising'] = step, step>step.shift(1)
    d2 = E(src,6)
    f['bbuy'] = X(d2,E(d2,5))
    trend25 = A(A(_div(c-low(l,25),high(h,25)-low(l,25))*100,3),3)
    power = A(trend25,3)
    f['trend25'], f['power'] = trend25, power
    f['low_buy'], f['sold'] = X(trend25,power)&(trend25<25), X(power,trend25)&(power>80)
    delta = c.diff()
    rsi = lambda n: _div(A(delta.clip(lower=0),n),A(delta.abs(),n))*100
    rsi1, rsi2 = rsi(6), rsi(12)
    f['rsi'] = rsi1
    f['run'] = X(pd.Series(82.,index=f.index), rsi1)
    diff, dea = E(c,12)-E(c,26), E(E(c,12)-E(c,26),9)
    macd = 2*(diff-dea)
    f['diff'], f['dea'], f['macd'] = diff, dea, macd
    pairs = [('macd',diff,dea), ('kdj',k,d), ('rsi',rsi1,rsi2)]
    obv = (np.sign(delta.fillna(0))*v).cumsum()
    pairs.append(('obv',obv,mean(obv,34)))
    for name, a, b in pairs:
        f[name+'_bottom'] = _divergence(c,a,X(a,b))
        f[name+'_top'] = _divergence(c,a,X(b,a),False)
    dy = l.diff()
    q = -pd.Series(np.where(l<=low(l,17), _div(A(dy.abs(),17),A(dy.clip(lower=0),17,2)), -3),index=f.index)
    f['strong_pull'] = X(q,pd.Series(0.,index=f.index))
    q1 = _div(c-mean(c,40),mean(c,40))*100
    f['extra_pull'] = X(q1,pd.Series(-24.,index=f.index))
    var22 = E(E(E((2*c+h+l)/4,4),4),4)
    earth = _div(var22-var22.shift(1),var22.shift(1))*100
    f['half_buy'] = (earth>mean(earth,2))&(earth<0)
    v3 = _div(A(dy.abs(),3),A(dy.clip(lower=0),3))*100
    # IF(CLOSE*1.3, ...) uses truthiness, not a price comparison.
    v4 = E(v3*10,3)
    flame = E(pd.Series(np.where(l<=low(l,30),(v4+high(v4,30)*2)/2,0)),3)/999
    flame = flame.where(mean(c,58).notna(),0).clip(upper=100)
    f['flame'] = (flame*1.2).where((flame>0)&(flame>flame.shift(1)),0)
    double, count, positive_sum = [], 0, 0
    gold = X(diff,dea)
    for i in range(len(f)):
        if diff.iloc[i] >= 0:
            count, positive_sum = 0, 0
        else:
            count += int(gold.iloc[i])
            positive_sum += max(macd.iloc[i],0)
        double.append(bool(gold.iloc[i] and diff.iloc[i]<0 and count>=2 and positive_sum>1))
    f['double_gold'] = double
    records = []
    for row in f.to_dict('records'):
        records.append({key: (None if isinstance(val,(float,np.floating)) and not math.isfinite(val) else val.item() if isinstance(val,np.generic) else val) for key,val in row.items()})
    return records


def match_signals(rows, settings=None):
    p = dict(DEFAULTS, **(settings or {}))
    events, seen = [], set()
    for vi, vol in enumerate(rows):
        if not vol.get('heavy'):
            continue
        if p['bullish_only'] and vol.get('close',0) <= vol.get('open',0):
            continue
        if p['require_vwap'] and not vol.get('vwap_up'):
            continue
        for bi in range(max(0,vi-p['pair_gap']),min(len(rows),vi+p['pair_gap']+1)):
            if not rows[bi].get('bbuy'):
                continue
            end = max(vi,bi)
            row = rows[end]
            if p['require_rising'] and not row.get('step_rising'):
                continue
            if p['require_macd'] and (row.get('macd') is None or row['macd']<=0):
                continue
            if p['require_bottom'] and not any(any(r.get(k) for k in ('macd_bottom','kdj_bottom','rsi_bottom')) for r in rows[max(0,end-4):end+1]):
                continue
            if (vi,bi) in seen:
                continue
            seen.add((vi,bi))
            events.append(dict(index=end,signal_date=row['date'],volume_date=vol['date'],
                               bbuy_date=rows[bi]['date'],signal_close=row['close'],
                               volume_ratio=vol.get('volume_ratio'),same_day=vi==bi,priority=1))
    events.sort(key=lambda x:(x['index'],x['bbuy_date'],x['volume_date']),reverse=True)
    secondary = []
    if p['include_secondary'] and not p['require_vwap']:
        for bi, row in enumerate(rows):
            if not row.get('bbuy'):
                continue
            nearby = rows[max(0,bi-p['pair_gap']):min(len(rows),bi+p['pair_gap']+1)]
            if any(r.get('heavy') for r in nearby):
                continue
            if p['bullish_only'] and row.get('close',0)<=row.get('open',0):
                continue
            if p['require_rising'] and not row.get('step_rising'):
                continue
            if p['require_macd'] and (row.get('macd') is None or row['macd']<=0):
                continue
            if p['require_bottom'] and not any(any(r.get(k) for k in ('macd_bottom','kdj_bottom','rsi_bottom')) for r in rows[max(0,bi-4):bi+1]):
                continue
            secondary.append(dict(index=bi,signal_date=row['date'],volume_date=None,
                                  bbuy_date=row['date'],signal_close=row['close'],
                                  volume_ratio=row.get('volume_ratio'),same_day=False,priority=2))
    events += secondary
    events.sort(key=lambda e:e['index'],reverse=True)
    recent = [e for e in events if e['index'] >= len(rows)-p['lookback']]
    recent.sort(key=lambda e:(e['priority'],-e['index']))
    chosen = recent[0] if recent else None
    result = dict(matched=bool(recent), events=events, recent_count=len(recent), priority=None)
    if chosen:
        result.update(chosen)
        result['since_signal'] = (rows[-1]['close']/chosen['signal_close']-1)*100 if chosen['signal_close'] else None
    return result
