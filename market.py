import csv
import io
import json
import math
import re
import sqlite3
import threading
import time
from datetime import timedelta
from pathlib import Path
from functools import lru_cache
import pandas as pd
import exchange_calendars as xcals
from indicators import DEFAULTS

DEFAULT_SYMBOLS = 'SPY QQQ SOXX IWM DIA AAPL MSFT NVDA AMZN GOOGL META TSLA AMD AVGO MU INTC NFLX PLTR COIN SMH'


def normalize_symbols(text):
    if isinstance(text,list):
        tokens = text
    elif isinstance(text,str):
        if len(text)>200000:
            raise ValueError('导入内容过长')
        lines = text.strip().splitlines()
        first = [x.strip().lower() for x in next(csv.reader(lines),[])]
        if 'symbol' in first or 'code' in first:
            key = 'symbol' if 'symbol' in first else 'code'
            idx = first.index(key)
            tokens = [row[idx] for row in csv.reader(lines[1:]) if len(row)>idx and row[idx].strip()]
        else:
            tokens = re.split(r'[\s,;，；]+',text.strip())
    else:
        raise ValueError('股票池必须为代码文本或列表')
    result = []
    for token in tokens:
        if not isinstance(token,str):
            raise ValueError('股票代码必须是文字')
        symbol = token.strip().upper()
        if not symbol:
            continue
        if re.match(r'^(HK|SH|SZ|SG|JP)\.',symbol):
            raise ValueError('只支持美股，发现非美股代码：'+symbol)
        symbol = symbol[3:] if symbol.startswith('US.') else symbol
        if not re.fullmatch(r'[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)?',symbol) or len(symbol)>16:
            raise ValueError('无效美股代码：'+symbol)
        code = 'US.'+symbol
        if code not in result:
            result.append(code)
    if not result:
        raise ValueError('请至少输入一个美股代码')
    if len(result)>5000:
        raise ValueError('单次股票池最多 5000 只；实际覆盖受行情额度限制')
    return result


def validate_settings(settings):
    if not isinstance(settings,dict):
        raise ValueError('筛选设置格式错误')
    p = dict(DEFAULTS)
    if set(settings)-set(p):
        raise ValueError('未知筛选参数')
    p.update(settings)
    bounds = dict(volume_n=(2,120),volume_mult=(1.01,50),vwap_n=(2,120),sigma=(.1,5),lookback=(1,60),pair_gap=(0,5))
    for key,(lo,hi) in bounds.items():
        value = p[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not lo<=value<=hi:
            raise ValueError(f'{key} 必须在 {lo}–{hi} 之间')
        if key in ('volume_n','vwap_n','lookback','pair_gap') and int(value)!=value:
            raise ValueError(key+' 必须为整数')
        if key in ('volume_n','vwap_n','lookback','pair_gap'):
            p[key] = int(value)
    for key in set(p)-set(bounds):
        if not isinstance(p[key],bool):
            raise ValueError(key+' 必须为开关值')
    return p


@lru_cache(maxsize=1)
def calendar():
    return xcals.get_calendar('XNYS',start='1990-01-01',end='2035-12-31')


def last_closed_session(now=None):
    stamp = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz='UTC')
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize('UTC')
    stamp = stamp.tz_convert('UTC')
    cal = calendar()
    day = stamp.tz_convert('America/New_York').date().isoformat()
    session = cal.date_to_session(day,direction='previous')
    if stamp < cal.session_close(session):
        session = cal.previous_session(session)
    return session.strftime('%Y-%m-%d')


def merge_history(old,new):
    known = {r['date']:r for r in old}
    changed = any(r['date'] in known and any(not math.isclose(float(r[k]),float(known[r['date']][k]),rel_tol=1e-6,abs_tol=1e-5) for k in ('open','high','low','close','volume')) for r in new)
    known.update({r['date']:r for r in new})
    return [known[d] for d in sorted(known)],changed


class Store:
    def __init__(self,path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS history (symbol TEXT PRIMARY KEY, rows TEXT NOT NULL, asof TEXT, name TEXT, fetched TEXT)')

    def connect(self):
        db = sqlite3.connect(self.path,timeout=20)
        db.row_factory = sqlite3.Row
        return db

    def get(self,key,default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?',(key,)).fetchone()
            return json.loads(row['value']) if row else default

    def set(self,key,value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(value,ensure_ascii=False,allow_nan=False)))

    def bars(self,symbol):
        with self.connect() as db:
            row = db.execute('SELECT * FROM history WHERE symbol=?',(symbol,)).fetchone()
            return dict(rows=json.loads(row['rows']),asof=row['asof'],name=row['name'],fetched=row['fetched']) if row else None

    def save_bars(self,symbol,rows,asof,name):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO history VALUES (?,?,?,?,?)',(symbol,json.dumps(rows,allow_nan=False),asof,name,pd.Timestamp.now(tz='UTC').isoformat()))

    def cached_symbols(self):
        with self.connect() as db:
            return [row['symbol'] for row in db.execute('SELECT symbol FROM history')]


class Gateway:
    def __init__(self,store):
        self.store = store
        self.lock = threading.RLock()
        self.ctx = None
        self.last_call = 0.
        self.used_codes = set()
        self.status = dict(connected=False,checking=True,error=None,used=None,remain=None)

    def _connect(self):
        import futu as ft
        if self.ctx is None:
            from futu.common.ft_logger import logger
            logger.log_path = str(Path(self.store.path).parent/'opend-logs')
            Path(logger.log_path).mkdir(exist_ok=True)
            self.ctx = ft.OpenQuoteContext(host='127.0.0.1',port=11111)
        return self.ctx

    def _call(self,func,*args,**kwargs):
        # All requests share one limiter; no subscription slots are consumed.
        time.sleep(max(0,1.2-(time.monotonic()-self.last_call)))
        self.last_call = time.monotonic()
        result = func(*args,**kwargs)
        return result

    def probe(self):
        with self.lock:
            self.status['checking'] = True
            try:
                ctx = self._connect()
                ret, state = self._call(ctx.get_global_state)
                if ret!=0 or not state.get('qot_logined'):
                    raise RuntimeError(str(state) if ret else 'OpenD 尚未登录行情')
                ret, quota = self._call(ctx.get_history_kl_quota,get_detail=True)
                if ret!=0:
                    raise RuntimeError(str(quota))
                self.used_codes = {r.get('code') for r in quota[2]}
                self.status = dict(connected=True,checking=False,error=None,used=int(quota[0]),remain=int(quota[1]),market=state.get('market_us'),checked_at=pd.Timestamp.now(tz='UTC').isoformat())
            except Exception as exc:
                self.status = dict(connected=False,checking=False,error=str(exc),used=None,remain=None)
                if self.ctx:
                    self.ctx.close()
                    self.ctx = None
            return dict(self.status)

    def _fetch(self,symbol,start,end):
        import futu as ft
        rows, key = [], None
        while True:
            ret,data,key = self._call(self.ctx.request_history_kline,symbol,start=start,end=end,ktype=ft.KLType.K_DAY,autype=ft.AuType.QFQ,max_count=1000,page_req_key=key,extended_time=False)
            if ret!=ft.RET_OK:
                raise RuntimeError(str(data))
            for r in data.to_dict('records'):
                day = str(r['time_key'])[:10]
                if day>end:
                    continue
                item = dict(date=day,**{k:float(r[k]) for k in ('open','high','low','close','volume')})
                if not all(math.isfinite(item[k]) for k in ('open','high','low','close','volume')) or item['close']<=0:
                    raise RuntimeError('行情包含无效价格或成交量')
                rows.append(item)
            if key is None:
                break
        return sorted({r['date']:r for r in rows}.values(),key=lambda r:r['date'])

    def history(self,symbol,cutoff,force=False):
        cached = self.store.bars(symbol)
        if cached and cached['asof']==cutoff and not force:
            return cached['rows'],cached['name']
        with self.lock:
            import futu as ft
            ctx = self._connect()
            if not self.status.get('connected'):
                status = self.probe()
                if not status['connected']:
                    raise RuntimeError(status['error'])
                ctx = self.ctx
            if symbol not in self.used_codes and self.status.get('remain',0)<=0:
                raise RuntimeError('未扫描：历史 K 线额度不足')
            ret, basic = self._call(ctx.get_stock_basicinfo,ft.Market.US,code_list=[symbol])
            if ret!=0 or basic.empty:
                raise RuntimeError('证券不存在或信息不可用：'+str(basic))
            info = basic.iloc[0]
            if str(info['stock_type']) not in ('STOCK','ETF'):
                raise RuntimeError('只支持美股股票和 ETF；该证券类型为 '+str(info['stock_type']))
            name = str(info['name'])
            start_full = (pd.Timestamp(cutoff)-pd.DateOffset(years=5)).date().isoformat()
            start = (pd.Timestamp(cached['rows'][-1]['date'])-timedelta(days=14)).date().isoformat() if cached and cached['rows'] and not force else start_full
            new = self._fetch(symbol,start,cutoff)
            if not new:
                raise RuntimeError('未返回历史日线')
            if cached and start!=start_full:
                merged,changed = merge_history(cached['rows'],new)
                if changed:
                    merged = self._fetch(symbol,start_full,cutoff)
                    if not merged:
                        raise RuntimeError('复权变化，完整历史刷新失败')
            else:
                merged = new
            self.store.save_bars(symbol,merged,cutoff,name)
            if symbol not in self.used_codes:
                self.used_codes.add(symbol)
                self.status['remain'] = max(0,self.status['remain']-1)
                self.status['used'] += 1
            return merged,name

    def refresh_metadata(self):
        from metadata import refresh_metadata
        with self.lock:
            return refresh_metadata(self.store,self._connect())

    def close(self):
        with self.lock:
            if self.ctx:
                self.ctx.close()
                self.ctx = None
