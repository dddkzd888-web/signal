"""Refresh the authorized US exchange/index universe at a USD market-cap floor."""
import csv,json,time,urllib.request
from pathlib import Path
from datetime import datetime,timezone
import futu as ft
ROOT=Path(__file__).parent
def main():
    base='http://127.0.0.1:8765'
    status=json.load(urllib.request.urlopen(base+'/api/status'))
    if status['scan']['running']:raise RuntimeError('扫描进行中，暂不能更新股票池')
    ctx=ft.OpenQuoteContext(host='127.0.0.1',port=11111)
    def call(fn,*a,**kw):
        ret,data=fn(*a,**kw)
        if ret!=ft.RET_OK:raise RuntimeError(str(data))
        time.sleep(3.2)
        return data
    try:
        f=ft.SimpleFilter();f.stock_field=ft.StockField.MARKET_VAL;f.filter_min=25000000000;f.is_no_filter=False;f.sort=ft.SortDir.DESCEND
        stocks=[];begin=0
        while True:
            last,total,batch=call(ctx.get_stock_filter,ft.Market.US,[f],begin=begin,num=200)
            stocks+=batch;begin+=len(batch)
            if last or begin>=total:break
            if not batch:raise RuntimeError('分页返回为空')
        caps={s.stock_code:dict(name=s.stock_name,market_cap_usd=s.market_val) for s in stocks}
        index_names={'US..IXIC':'纳斯达克综合指数','US..SPX':'标普500指数','US..NDX':'纳斯达克100指数'}
        members={}
        for code,name in index_names.items():
            for stock in call(ctx.get_plate_stock,code).code:
                members.setdefault(stock,[]).append(name)
        codes=[s for s in caps if s in members]
        selected=[]
        for start in range(0,len(codes),200):
            data=call(ctx.get_stock_basicinfo,ft.Market.US,ft.SecurityType.STOCK,codes[start:start+200])
            for r in data.to_dict('records'):
                if r['stock_type']=='STOCK' and r['exchange_type'] in ('US_NYSE','US_NASDAQ') and not r['delisting']:
                    selected.append(dict(code=r['code'],**caps[r['code']],exchange_type=r['exchange_type'],stock_type=r['stock_type'],delisting=False,indices=' / '.join(members[r['code']])))
        selected.sort(key=lambda r:r['market_cap_usd'],reverse=True)
        kept=['US.SPY','US.QQQ','US.SOXX','US.IWM','US.DIA','US.SMH']
        pool=[r['code'] for r in selected]
        pool+= [s for s in kept if s not in pool]
        req=urllib.request.Request(base+'/api/settings',data=json.dumps(dict(settings=status['settings'],symbols=pool)).encode(),headers={'Content-Type':'application/json'})
        json.load(urllib.request.urlopen(req,timeout=120))
        with (ROOT/'观察池-三条件.csv').open('w',encoding='utf-8-sig',newline='') as out:
            writer=csv.DictWriter(out,fieldnames=list(selected[0]));writer.writeheader();writer.writerows(selected)
        (ROOT/'观察池-股票代码.txt').write_text('\n'.join(s.removeprefix('US.') for s in pool),encoding='utf-8')
        info=dict(retrieved_at=datetime.now(timezone.utc).isoformat(),source='Futu OpenD 127.0.0.1:11111',minimum_market_cap_usd=25000000000,exchanges=['US_NYSE','US_NASDAQ'],index_union=list(index_names),qualifying_count=len(selected),retained_previous_symbols=kept,pool_total=len(pool),note='按当前OpenD市值重建观察池，保留6只ETF；市值门槛为闭区间≥250亿美元，扫描使用保存股票池。')
        (ROOT/'观察池-来源说明.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(dict(stock_count=len(selected),pool_total=len(pool),added=sorted(set(pool)-set(status['symbols'])),removed=sorted(set(status['symbols'])-set(pool))),ensure_ascii=False))
    finally:ctx.close()
if __name__=='__main__':main()
