import atexit
import csv
import io
import json
import threading
import time
import argparse
from pathlib import Path
from urllib.parse import urlsplit
from flask import Flask, request, jsonify, Response
from indicators import DEFAULTS, enrich, match_signals
from market import Store, Gateway, DEFAULT_SYMBOLS, normalize_symbols, validate_settings, last_closed_session

ROOT = Path(__file__).resolve().parent


class ScanManager:
    def __init__(self,store,gateway):
        self.store,self.gateway = store,gateway
        self.lock = threading.RLock()
        self.thread = None
        self.cancel = threading.Event()
        self.state = dict(running=False,total=0,completed=0,failed=0,current=None,cancelled=False,results=[],cutoff=None,error=None)
        saved = store.get('last_scan')
        if saved:
            self.state.update(saved,running=False,current=None)
        self.settings = validate_settings(store.get('settings',DEFAULTS))
        self.symbols = normalize_symbols(store.get('symbols',DEFAULT_SYMBOLS))
        self.chart_cache = {}

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state,allow_nan=False))

    def start(self,symbols,settings,force=False):
        with self.lock:
            if self.state['running']:
                raise RuntimeError('已有扫描正在运行')
            self.cancel.clear()
            self.settings,self.symbols = settings,symbols
            self.store.set('settings',settings)
            self.store.set('symbols',symbols)
            self.state = dict(running=True,total=len(symbols),completed=0,failed=0,current=None,cancelled=False,results=[],cutoff=None,error=None)
            self.thread = threading.Thread(target=self.run,args=(symbols,settings,force),daemon=True)
            self.thread.start()

    def evaluate(self,symbol,bars,name,settings,cutoff):
        bars = [r for r in bars if r['date']<=cutoff]
        if not bars:
            raise RuntimeError('没有已收盘日线')
        rows = enrich(bars,settings)
        signal = match_signals(rows,settings)
        latest = rows[-1]
        minimum = max(30,settings['volume_n']+int(settings['previous_volume']))
        sufficient = len(rows)>=minimum
        result = dict(symbol=symbol,name=name,status='ok' if sufficient else 'insufficient',error=None if sufficient else f'历史不足：需要至少 {minimum} 根日线',
                      close=latest['close'],date=latest['date'],bars=len(rows),
                      change=(latest['close']/rows[-2]['close']-1)*100 if len(rows)>1 else None,
                      latest_volume_ratio=latest['volume_ratio'],
                      vwap_distance=(latest['close']/latest['vwap']-1)*100 if latest['vwap'] else None,
                      long_history=len(rows)>=330,**{k:v for k,v in signal.items() if k!='events'})
        if not sufficient:
            result['matched'] = False
        result['historical_count'] = len(signal['events'])
        result['latest_heavy'],result['latest_bbuy'] = latest['heavy'],latest['bbuy']
        events = [{**e,'since_signal':(latest['close']/e['signal_close']-1)*100} for e in signal['events']]
        with self.lock:
            self.chart_cache[symbol] = dict(symbol=symbol,name=name,rows=rows,events=events,settings=settings,cutoff=cutoff,long_history=len(rows)>=330)
        return result

    def run(self,symbols,settings,force=False):
        with self.lock:
            self.state.update(running=True,total=len(symbols),completed=0,failed=0,current=None,cancelled=False,results=[],error=None)
            self.settings,self.symbols = settings,symbols
        try:
            cutoff = last_closed_session()
            with self.lock:
                self.state['cutoff'] = cutoff
            for symbol in symbols:
                if self.cancel.is_set():
                    break
                with self.lock:
                    self.state['current'] = symbol
                try:
                    bars,name = self.gateway.history(symbol,cutoff,force)
                    result = self.evaluate(symbol,bars,name,settings,cutoff)
                except Exception as exc:
                    result = dict(symbol=symbol,name=symbol,status='error',matched=False,error=str(exc))
                with self.lock:
                    self.state['results'].append(result)
                    self.state['completed'] += 1
                    self.state['failed'] += int(result['status']=='error')
        except Exception as exc:
            with self.lock:
                self.state['error'] = str(exc)
        finally:
            with self.lock:
                self.state.update(running=False,current=None,cancelled=self.cancel.is_set())
                self.store.set('last_scan',self.state)
            self.cancel.clear()

    def recompute(self,settings,symbols):
        with self.lock:
            if self.state['running']:
                raise RuntimeError('请先等待扫描结束或取消扫描')
            if self.thread and self.thread.is_alive():
                raise RuntimeError('扫描正在结束，请稍后重试')
            self.settings,self.symbols = settings,symbols
            self.store.set('settings',settings)
            self.store.set('symbols',symbols)
            cutoff = last_closed_session()
            results=[]
            for symbol in symbols:
                cached = self.store.bars(symbol)
                if not cached:
                    results.append(dict(symbol=symbol,name=symbol,status='uncached',matched=False,error='尚无缓存，请扫描更新'))
                else:
                    result = self.evaluate(symbol,cached['rows'],cached['name'],settings,cutoff)
                    result['stale'] = cached['asof']!=cutoff
                    results.append(result)
            self.state.update(results=results,total=len(symbols),completed=sum(r['status']!='uncached' for r in results),failed=0,cutoff=cutoff,cancelled=False,error=None)
            self.store.set('last_scan',self.state)

    def chart(self,symbol):
        with self.lock:
            cached_chart = self.chart_cache.get(symbol)
            if cached_chart and cached_chart['settings']==self.settings and cached_chart['cutoff']==last_closed_session():
                return cached_chart
            settings = dict(self.settings)
        cached = self.store.bars(symbol)
        if not cached:
            raise ValueError('暂无该证券缓存，请先扫描')
        cutoff = last_closed_session()
        self.evaluate(symbol,cached['rows'],cached['name'],settings,cutoff)
        with self.lock:
            result = dict(self.chart_cache[symbol])
        result['stale'] = cached['asof']!=cutoff
        return result


def create_app(manager):
    app = Flask(__name__,static_folder=str(ROOT/'static'),static_url_path='/static')
    app.config['MAX_CONTENT_LENGTH'] = 500000

    @app.before_request
    def local_only():
        host = request.host.split(':')[0]
        if host not in ('127.0.0.1','localhost'):
            return jsonify(error='只允许本机访问'),403
        origin = request.headers.get('Origin')
        if origin and origin!=request.host_url.rstrip('/'):
            return jsonify(error='拒绝跨站请求'),403
        if request.method=='POST' and request.headers.get('Sec-Fetch-Site')=='cross-site':
            return jsonify(error='拒绝跨站请求'),403

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='no-referrer'
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'self'; base-uri 'self'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control']='no-store'
        return response

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error)),400

    @app.errorhandler(RuntimeError)
    def busy(error):
        return jsonify(error=str(error)),409

    @app.get('/')
    def index():
        return app.send_static_file('index.html')

    @app.get('/api/status')
    def status():
        return jsonify(opend=manager.gateway.status,scan={k:v for k,v in manager.snapshot().items() if k!='results'},settings=manager.settings,symbols=manager.symbols,cutoff=last_closed_session(),cached=len(manager.store.cached_symbols()))

    @app.post('/api/connect')
    def connect():
        if manager.state['running']:
            raise RuntimeError('扫描中，结束后可重新检查连接')
        threading.Thread(target=manager.gateway.probe,daemon=True).start()
        return jsonify(ok=True)

    @app.post('/api/settings')
    def settings():
        body = request.get_json()
        if not isinstance(body,dict):
            raise ValueError('请求格式错误')
        p = validate_settings(body.get('settings',{}))
        symbols = normalize_symbols(body.get('symbols',manager.symbols))
        manager.recompute(p,symbols)
        return jsonify(ok=True,settings=p,symbols=symbols)

    @app.post('/api/scan')
    def scan():
        body = request.get_json()
        if not isinstance(body,dict):
            raise ValueError('请求格式错误')
        p = validate_settings(body.get('settings',manager.settings))
        symbols = normalize_symbols(body.get('symbols',manager.symbols))
        force = body.get('force',False)
        if not isinstance(force,bool):
            raise ValueError('force 必须为开关值')
        manager.start(symbols,p,force)
        return jsonify(ok=True),202

    @app.post('/api/scan/cancel')
    def cancel():
        if manager.state['running']:
            manager.cancel.set()
        return jsonify(ok=True)

    @app.get('/api/results')
    def results():
        return jsonify(manager.snapshot())

    @app.get('/api/chart/<symbol>')
    def chart(symbol):
        codes = normalize_symbols([symbol])
        return jsonify(manager.chart(codes[0]))

    @app.get('/api/export')
    def export():
        snapshot = manager.snapshot()
        output = io.StringIO()
        output.write('\ufeff')
        writer = csv.writer(output)
        writer.writerow(['代码','名称','状态','命中','收盘日期','收盘价','放量日期','红柱日期','组合完成日期','放量倍数','信号后涨幅%','错误','规则参数','数据截止'])
        only = request.args.get('matched','1')=='1'
        for r in snapshot['results']:
            if only and not r.get('matched'):
                continue
            values = [r.get(k,'') for k in ('symbol','name','status','matched','date','close','volume_date','bbuy_date','signal_date','volume_ratio','since_signal','error')]
            values = ["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in values]
            writer.writerow(values+[json.dumps(manager.settings,ensure_ascii=False),snapshot.get('cutoff')])
        return Response(output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename="screener-results.csv"'})

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    args = parser.parse_args()
    store = Store(ROOT/'data'/'cache.sqlite')
    gateway = Gateway(store)
    manager = ScanManager(store,gateway)
    atexit.register(gateway.close)
    threading.Thread(target=gateway.probe,daemon=True).start()
    create_app(manager).run(host='127.0.0.1',port=args.port,debug=False,use_reloader=False,threaded=True)
