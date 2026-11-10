import unittest
from unittest.mock import patch
from opportunity import assess, backtest

class OpportunityTests(unittest.TestCase):
    def rows(self):
        prev=dict(close=100,ema5=98,macd=-1)
        current=dict(close=101,ema5=99,ema20=100,atr14=2,low30=95,low60=90,high60=120,macd=-.5,dollar_volume20=2e7)
        return [prev,current]

    def test_all_confirmations_and_no_chase(self):
        rows=self.rows()
        self.assertTrue(assess(rows)['early_ok'])
        rows[-1]['close']=119
        self.assertFalse(assess(rows)['early_ok'])
        self.assertIn('低位区域',assess(rows)['early_reason'])

    def test_downward_volatility_is_not_upward_confirmation(self):
        rows=self.rows()
        rows[-1].update(close=97,macd=-2,vol_warning=True)
        self.assertFalse(assess(rows)['early_ok'])

    def test_missing_history_is_not_zero_score(self):
        self.assertIsNone(assess([])['early_score'])

    def test_no_samples_reports_missing_evidence(self):
        class Store:
            def bars(self,symbol):return None
        r=backtest(Store(),['US.X'],{},'2026-10-09')
        self.assertEqual(r['evidence'],'证据不足')
        self.assertIsNone(r['test']['up_rate'])
        self.assertEqual(r['coverage'],0)

    def test_evaluation_uses_next_open_nonoverlap_and_time_split(self):
        rows=[dict(date=f'{i:03d}',open=100,close=110,low=90) for i in range(100)]
        class Store:
            def bars(self,symbol):return dict(rows=rows)
        with patch('opportunity.enrich',return_value=rows), patch('opportunity.assess',return_value={'early_ok':True}), patch('opportunity.match_signals',return_value={'matched':True}):
            r=backtest(Store(),['X'],{},'999')
        self.assertEqual(r['coverage'],0)  # under minimum 120 bars
        rows.extend(dict(date=f'{i:03d}',open=100,close=110,low=90) for i in range(100,140))
        with patch('opportunity.enrich',return_value=rows), patch('opportunity.assess',return_value={'early_ok':True}), patch('opportunity.match_signals',return_value={'matched':True}):
            r=backtest(Store(),['X'],{},'999')
        self.assertGreater(r['test']['n'],0)
        self.assertAlmostEqual(r['test']['mean_return'],10)
        self.assertAlmostEqual(r['test']['mean_drawdown'],-10)
        self.assertTrue(all(int(b['date'])-int(a['date'])>=6 for a,b in zip(r['samples'],r['samples'][1:])))
        self.assertTrue(all(s['exit_date']<'999' for s in r['samples']))
