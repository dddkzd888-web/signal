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
        self.assertFalse(match_signals(rows, DEFAULTS)['matched'])
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


if __name__ == '__main__':
    unittest.main()
