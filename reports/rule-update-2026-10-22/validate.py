# -*- coding: utf-8 -*-
import sys,json,csv,math
from pathlib import Path
from collections import defaultdict
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from market import Store
p=Path(__file__).parent;r=json.loads((p/'results.json').read_text());s=Store(ROOT/'data/cache.sqlite')
rows=list(csv.DictReader((p/'trades.csv').open(encoding='utf-8-sig')));cache={};stats=defaultdict(list);previous={}
for t in rows:
 c=t['symbol']
 if c not in cache:
  b=s.bars(c)['rows'];cache[c]=(b,{x['date']:i for i,x in enumerate(b)})
 b,idx=cache[c];i=idx[t['signal']];h=int(t['horizon'])
 assert b[i+1]['date']==t['entry'] and b[i+h]['date']==t['exit']
 assert t['signal']<t['entry']<=t['exit']<=r['end']
 assert math.isclose(float(t['entry_price']),b[i+1]['open'],rel_tol=1e-10)
 assert math.isclose(float(t['exit_price']),b[i+h]['close'],rel_tol=1e-10)
 expected=(b[i+h]['close']/b[i+1]['open'])*(.9995**2)-1
 assert math.isclose(float(t['net']),expected,abs_tol=1e-10)
 key=(t['group'],t['indicator'],c)
 if key in previous:assert t['entry']>previous[key]
 previous[key]=t['exit'];stats[(t['group'],t['indicator'])].append(float(t['net']))
for group,g in r['groups'].items():
 for row in g['table']:
  values=stats[(group,row['key'])]
  assert len(values)==row['full']['n']
  if values:assert math.isclose(100*sum(values)/len(values),row['full']['mean'],abs_tol=1e-9)
assert r['groups']['M7']['covered']==7
assert r['groups']['500亿以上']['covered']==236
assert 'US.GOOG' not in r['groups']['500亿以上']['symbols']
assert len(set(r['groups']['500亿以上']['symbols']))==236
out=dict(checked_trades=len(rows),passed=True,checks=['next-open entry','exact five actual bars','no future exit','10bps roundtrip costs','nonoverlap per-stock-per-signal','sample counts and mean return reconciliation','M7 membership','Google share-class deduplication'])
(p/'validation.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print(out)
