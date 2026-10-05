import unittest
import tempfile
import threading
import pandas as pd
from app import create_app, ScanManager
from market import Store
from indicators import DEFAULTS


class FakeGateway:
    """Only OpenD/network is replaced; real manager/store/filtering still run."""
    status = dict(connected=True,remain=10,used=0)
    def history(self, symbol, cutoff, force=False):
        if symbol == 'US.BAD':
            raise RuntimeError('无行情权限')
        return [dict(date=d.strftime('%Y-%m-%d'),open=10,close=10,high=11,low=9,volume=100) for d in pd.bdate_range(end=cutoff,periods=100)], symbol


class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name+'/cache.sqlite')
        self.manager = ScanManager(self.store,FakeGateway())
        self.client = create_app(self.manager).test_client()

    def tearDown(self):
        self.tmp.cleanup()

    def test_cross_origin_and_bad_host_cannot_mutate_local_state(self):
        r = self.client.post('/api/settings',json=dict(settings=DEFAULTS),headers={'Origin':'https://evil.example'})
        self.assertEqual(r.status_code,403)
        r = self.client.get('/api/status',headers={'Host':'evil.example'})
        self.assertEqual(r.status_code,403)

    def test_invalid_settings_are_rejected_and_valid_persist(self):
        self.assertEqual(self.client.post('/api/settings',json=dict(settings=dict(volume_n=0))).status_code,400)
        self.assertEqual(self.client.post('/api/settings',json=dict(settings=dict(DEFAULTS,volume_mult=2))).status_code,200)
        self.assertEqual(self.store.get('settings')['volume_mult'],2)

    def test_failure_is_not_reported_as_no_match(self):
        self.manager.run(['US.BAD'],DEFAULTS,False)
        result = self.manager.snapshot()
        self.assertEqual(result['failed'],1)
        self.assertEqual(result['results'][0]['status'],'error')
        self.assertIn('无行情权限',result['results'][0]['error'])

    def test_zero_candidates_still_returns_all_scanned_rows(self):
        self.manager.run(['US.QQQ'],DEFAULTS,False)
        result = self.manager.snapshot()
        self.assertEqual(result['completed'],1)
        self.assertEqual(result['results'][0]['matched'],False)
        self.assertEqual(result['results'][0]['status'],'ok')

    def test_busy_scan_is_rejected_and_cancel_allows_next_scan(self):
        entered, release = threading.Event(),threading.Event()
        original = self.manager.gateway.history
        def blocked(*args,**kwargs):
            entered.set(); release.wait(5)
            return original(*args,**kwargs)
        self.manager.gateway.history = blocked
        self.manager.start(['US.QQQ','US.AAPL'],DEFAULTS,False)
        self.assertTrue(entered.wait(2))
        self.assertEqual(self.client.post('/api/scan',json=dict(symbols='QQQ',settings=DEFAULTS)).status_code,409)
        self.client.post('/api/scan/cancel')
        release.set(); self.manager.thread.join(5)
        self.assertFalse(self.manager.snapshot()['running'])
        self.assertTrue(self.manager.snapshot()['cancelled'])
        self.assertEqual(self.manager.snapshot()['completed'],1)
        self.manager.gateway.history = original
        self.manager.run(['US.QQQ'],DEFAULTS,False)
        self.assertEqual(self.manager.snapshot()['completed'],1)

    def test_old_completed_pair_is_historical_not_a_current_candidate(self):
        bars=[dict(date=d.strftime('%Y-%m-%d'),open=10,close=10,high=10,low=10,volume=100) for d in pd.bdate_range(end='2026-09-01',periods=60)]
        bars[-2].update(open=9,close=9,high=9,low=9)
        bars[-1].update(open=12,close=12,high=12,low=12,volume=1000)
        self.store.save_bars('US.QQQ',bars,'2026-09-01','QQQ')
        self.manager.recompute(DEFAULTS,['US.QQQ'])
        result=self.manager.snapshot()['results'][0]
        self.assertFalse(result['matched'])
        self.assertTrue(result['stale'])
        self.assertGreater(result['historical_count'],0)
        for _ in range(2):
            detail=self.manager.chart('US.QQQ')
            self.assertTrue(detail['stale'])
            self.assertEqual(detail['data_date'],'2026-09-01')


if __name__ == '__main__':
    unittest.main()
