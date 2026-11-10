import unittest
import math
from indicators import ema, sma, cross, enrich, match_signals, DEFAULTS


def bar(i, close=10, volume=100):
    return dict(date=f'2026-01-{i+1:02d}', open=close, high=close, low=close,
                close=close, volume=volume)


class IndicatorTests(unittest.TestCase):
    def test_recursive_smoothing_is_not_simple_mean(self):
        self.assertEqual(ema([1, 2, 3], 3), [1, 1.5, 2.25])
        values = sma([1, 2, 3], 3, 1)
        self.assertAlmostEqual(values[1], 4/3)
        self.assertAlmostEqual(values[2], 17/9)

    def test_cross_requires_previous_not_above_and_current_strictly_above(self):
        self.assertEqual(cross([1, 1, 2, 3, 1], [1]*5), [False, False, True, False, False])

    def test_weighted_price_and_standard_deviation(self):
        rows = enrich([bar(0, 1, 1), bar(1, 2, 1), bar(2, 3, 2)], dict(DEFAULTS, vwap_n=3))
        self.assertAlmostEqual(rows[-1]['vwap'], 2.25)
        self.assertAlmostEqual(rows[-1]['upper'], 2.25 + 1.5 * math.sqrt(.6875))

    def test_previous_volume_average_changes_the_actual_signal(self):
        bars = [bar(i) for i in range(20)] + [bar(20, volume=3000)]
        a = enrich(bars, dict(DEFAULTS, volume_mult=15))[-1]
        b = enrich(bars, dict(DEFAULTS, volume_mult=15, previous_volume=True))[-1]
        self.assertFalse(a['heavy'])
        self.assertTrue(b['heavy'])
        self.assertAlmostEqual(b['volume_ratio'], 30)

    def test_red_column_uses_bbuy_not_positive_macd(self):
        bars = [bar(i) for i in range(20)] + [bar(20, 9), bar(21, 12)]
        rows = enrich(bars, DEFAULTS)
        self.assertFalse(rows[-2]['bbuy'])
        self.assertTrue(rows[-1]['bbuy'])
        self.assertFalse(rows[-1]['macd_bottom'])

    def test_flat_prices_do_not_generate_divergence_or_invalid_numbers(self):
        rows = enrich([bar(i) for i in range(20)], DEFAULTS)
        self.assertFalse(any(r['macd_bottom'] or r['kdj_bottom'] or r['rsi_bottom'] for r in rows))
        self.assertIsNone(rows[-1]['k'])

    def test_same_day_pair_requires_both_signals(self):
        rows = [dict(date='2026-01-01', close=10, heavy=True, bbuy=False),
                dict(date='2026-01-02', close=11, heavy=False, bbuy=True)]
        self.assertFalse(match_signals(rows, dict(DEFAULTS, include_secondary=False))['matched'])
        rows[-1]['heavy'] = True
        self.assertTrue(match_signals(rows, DEFAULTS)['matched'])

    def test_nearby_pair_uses_completion_date_and_trading_bars(self):
        rows = [dict(date='2026-01-02', close=10, heavy=True, bbuy=False),
                dict(date='2026-01-05', close=11, heavy=False, bbuy=True)]
        match = match_signals(rows, dict(DEFAULTS, pair_gap=1, lookback=1))
        self.assertTrue(match['matched'])
        self.assertEqual(match['signal_date'], '2026-01-05')
        self.assertEqual(match['volume_date'], '2026-01-02')
        self.assertEqual(match['bbuy_date'], '2026-01-05')
        self.assertFalse(match_signals(rows[:1], dict(DEFAULTS, pair_gap=1))['matched'])

    def test_old_pair_does_not_pass_freshness(self):
        rows = [dict(date='2026-01-01', close=10, heavy=True, bbuy=True)]
        rows += [dict(date=f'2026-01-0{i}', close=10, heavy=False, bbuy=False) for i in range(2, 5)]
        self.assertFalse(match_signals(rows, dict(DEFAULTS, lookback=2))['matched'])

    def test_optional_bullish_candle_is_applied_to_volume_day(self):
        rows = [dict(date='2026-01-01', close=9, open=10, heavy=True, bbuy=True)]
        self.assertFalse(match_signals(rows, dict(DEFAULTS, bullish_only=True))['matched'])

    def test_red_only_is_second_priority_without_inventing_volume_date(self):
        rows = [dict(date='2026-01-01', close=10, heavy=False, bbuy=True)]
        result = match_signals(rows, DEFAULTS)
        self.assertTrue(result['matched'])
        self.assertEqual(result['priority'], 2)
        self.assertIsNone(result['volume_date'])
        self.assertEqual(result['bbuy_date'], '2026-01-01')
        self.assertFalse(match_signals(rows, dict(DEFAULTS, include_secondary=False))['matched'])

    def test_primary_wins_over_newer_secondary(self):
        rows = [dict(date='2026-01-01', close=10, heavy=True, bbuy=True),
                dict(date='2026-01-02', close=11, heavy=False, bbuy=True)]
        result = match_signals(rows, DEFAULTS)
        self.assertEqual(result['priority'], 1)
        self.assertEqual(result['signal_date'], '2026-01-01')

    def test_secondary_obeys_freshness_and_volume_only_is_excluded(self):
        rows = [dict(date='2026-01-01', close=10, heavy=False, bbuy=True),
                dict(date='2026-01-02', close=11, heavy=True, bbuy=False)]
        self.assertFalse(match_signals(rows, dict(DEFAULTS, lookback=1))['matched'])
        self.assertFalse(match_signals(rows, dict(DEFAULTS, require_vwap=True))['matched'])

    def test_removed_volatility_warning_cannot_block_a_candidate(self):
        rows=[dict(date='2026-01-01',close=10,heavy=False,bbuy=True)]
        self.assertTrue(match_signals(rows,dict(require_vol_warning=True))['matched'])

    def test_confirmation_window_and_grades_do_not_use_old_or_future_signals(self):
        rows=[dict(date=str(i),close=10,heavy=False,bbuy=i==8,macd_cross=i==4) for i in range(10)]
        self.assertFalse(match_signals(rows,dict(require_confirmation=True))['matched'])
        rows[5]['macd_cross']=True
        b=match_signals(rows,dict(require_confirmation=True))
        self.assertTrue(b['matched'])
        self.assertEqual(b['confirmation_grade'],'B')
        rows[8]['heavy']=True
        self.assertEqual(match_signals(rows,dict(require_confirmation=True))['confirmation_grade'],'A')
        rows[4]['macd_cross']=False;rows[5]['macd_cross']=False;rows[9]['macd_bottom']=True
        self.assertTrue(match_signals(rows,dict(require_confirmation=True))['matched'])
        self.assertFalse(match_signals(rows[:9],dict(require_confirmation=True))['matched'])

    def test_capital_indicator_matches_supplied_formula_without_future_data(self):
        closes=[100+.1*i+3*math.sin(i/3) for i in range(160)]
        rows=enrich([bar(i,close=c) for i,c in enumerate(closes)])
        self.assertIsNone(rows[120]['capital_value'])
        deviation=[None if i<119 else closes[i]/(sum(closes[i-119:i+1])/120)-1 for i in range(len(closes))]
        expected=[]
        for i in range(121,len(closes)):
            var1=closes[i]/(1+deviation[i]-sum(deviation[i-2:i+1])/3)
            value=(closes[i]/var1-1)*100
            expected.append(value)
            self.assertAlmostEqual(rows[i]['capital_value'],value,places=10)
            if i>121:
                self.assertEqual(rows[i]['capital_up'],value>0 and expected[-2]<=0)
                self.assertEqual(rows[i]['capital_down'],value<0 and expected[-2]>=0)
        self.assertEqual(enrich([bar(i,close=c) for i,c in enumerate(closes[:140])]),rows[:140])

    def test_capital_flat_price_is_zero_and_never_crosses(self):
        rows=enrich([bar(i) for i in range(140)])
        self.assertTrue(all(r['capital_value']==0 for r in rows[121:]))
        self.assertFalse(any(r['capital_up'] or r['capital_down'] for r in rows))

    def test_volindex_matches_constant_log_returns_and_warmup(self):
        bars = [dict(date=str(i),open=100*math.exp(.01*i),high=100*math.exp(.01*i),low=100*math.exp(.01*i),close=100*math.exp(.01*i),volume=100) for i in range(80)]
        rows=enrich(bars,DEFAULTS)
        self.assertIsNone(rows[59]['volindex'])
        self.assertAlmostEqual(rows[60]['volindex'],math.sqrt(252),places=8)
        self.assertIsNone(rows[63]['volma'])
        self.assertAlmostEqual(rows[64]['volma'],math.sqrt(252),places=8)
        flat = enrich([dict(b,open=100,high=100,low=100,close=100) for b in bars])
        self.assertFalse(any(r['vol_panic_buy'] or r['vol_warning'] for r in flat))
        self.assertEqual(enrich(bars[:70]), rows[:70])


if __name__ == '__main__':
    unittest.main()
