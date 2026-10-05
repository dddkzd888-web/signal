"""Source-backed stock classifications, independent of signal calculations."""
import math
import time
from datetime import datetime, timezone

INDEX_CODES={'纳斯达克综合':'US..IXIC','标普500':'US..SPX','纳斯达克100':'US..NDX'}

def build_metadata(codes, snapshots, owners, members):
    result={c:dict(market_cap=None,market_cap_at=None,sectors=[],indices=[]) for c in codes}
    for row in snapshots:
        if row['code'] not in result: continue
        value=row.get('total_market_val')
        if isinstance(value,(int,float)) and math.isfinite(value) and value>0:
            result[row['code']].update(market_cap=value,market_cap_at=row.get('update_time'))
    for row in owners:
        if row['code'] in result and row.get('plate_type') in ('INDUSTRY','CONCEPT'):
            names=result[row['code']]['sectors']
            if row['plate_name'] not in names:names.append(row['plate_name'])
    for name,codes_in_index in members.items():
        for code in codes_in_index:
            if code in result:result[code]['indices'].append(name)
    return result

def refresh_metadata(store, ctx):
    import futu as ft
    codes=store.get('symbols',[])
    snapshots,owners,members=[],[],{}
    def call(fn,*args):
        ret,data=fn(*args)
        if ret!=ft.RET_OK:raise RuntimeError(str(data))
        time.sleep(3.2)
        return data
    for name,code in INDEX_CODES.items():
        members[name]=call(ctx.get_plate_stock,code).code.tolist()
    for start in range(0,len(codes),200):
        batch=codes[start:start+200]
        snapshots+=call(ctx.get_market_snapshot,batch).to_dict('records')
        stocks=call(ctx.get_stock_basicinfo,ft.Market.US,ft.SecurityType.STOCK,batch)
        underlying=stocks.loc[stocks.stock_type=='STOCK','code'].tolist()
        if underlying:owners+=call(ctx.get_owner_plate,underlying).to_dict('records')
    data=build_metadata(codes,snapshots,owners,members)
    store.set('stock_metadata',data)
    store.set('metadata_updated_at',datetime.now(timezone.utc).isoformat())
    return data

if __name__=='__main__':
    from pathlib import Path
    from market import Store
    import futu as ft
    store=Store(Path(__file__).parent/'data/cache.sqlite')
    ctx=ft.OpenQuoteContext(host='127.0.0.1',port=11111)
    try:print('Updated',len(refresh_metadata(store,ctx)),'stocks')
    finally:ctx.close()
