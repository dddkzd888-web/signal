import unittest
import tempfile
from unittest.mock import patch,Mock
from pathlib import Path
from types import SimpleNamespace
from market import normalize_symbols, validate_settings, last_closed_session, Store, merge_history


class MarketTests(unittest.TestCase):
    def test_old_warning_setting_is_discarded_without_changing_other_rules(self):
        old=dict(volume_mult=2,require_vol_warning=True)
        clean=validate_settings(old)
        self.assertNotIn('require_vol_warning',clean)
        self.assertEqual(clean['volume_mult'],2)
        self.assertTrue(old['require_vol_warning'])

    def test_opend_reconnection_wait_is_bounded(self):
        from market import Gateway
        with tempfile.TemporaryDirectory() as folder:
            ctx=Mock()
            with patch('futu.OpenQuoteContext',return_value=ctx):
                gateway=Gateway(SimpleNamespace(path=Path(folder)/'cache.sqlite'))
                self.assertIs(gateway._connect(),ctx)
                ctx.set_sync_query_connect_timeout.assert_called_once_with(15)

    def test_us_symbols_are_deduplicated_without_rewriting_foreign_codes(self):
        self.assertEqual(normalize_symbols('aapl, US.AAPL\nBRK.B QQQ'), ['US.AAPL','US.BRK.B','US.QQQ'])
        with self.assertRaises(ValueError):
            normalize_symbols('HK.00700')
        with self.assertRaises(ValueError):
            normalize_symbols('AAPL<script>')

    def test_early_close_and_weekend_cutoff(self):
        self.assertEqual(last_closed_session('2026-11-27T17:59:00Z'), '2026-11-25')
        self.assertEqual(last_closed_session('2026-11-27T18:01:00Z'), '2026-11-27')
        self.assertEqual(last_closed_session('2026-11-28T20:00:00Z'), '2026-11-27')

    def test_current_regular_session_is_excluded(self):
        self.assertEqual(last_closed_session('2026-10-05T15:00:00Z'), '2026-10-02')
        self.assertEqual(last_closed_session('2026-10-05T20:01:00Z'), '2026-10-05')

    def test_invalid_settings_cannot_create_unbounded_or_nan_computations(self):
        for settings in [dict(volume_mult=float('nan')), dict(volume_n=0),
                         dict(pair_gap=6), dict(lookback=61),dict(previous_volume='false'),dict(volume_n=2.5)]:
            with self.assertRaises(ValueError):
                validate_settings(settings)

    def test_adjustment_change_requires_full_refresh_not_mixed_history(self):
        old = [dict(date='2026-01-01',close=100,open=100,high=100,low=100,volume=10),
               dict(date='2026-01-02',close=110,open=110,high=110,low=110,volume=10)]
        changed = [dict(date='2026-01-02',close=55,open=55,high=55,low=55,volume=20)]
        merged, changed_flag = merge_history(old, changed)
        self.assertTrue(changed_flag)
        unchanged = [dict(old[-1]),dict(date='2026-01-03',close=120,open=120,high=120,low=120,volume=10)]
        merged, changed_flag = merge_history(old,unchanged)
        self.assertFalse(changed_flag)
        self.assertEqual([r['close'] for r in merged],[100,110,120])

    def test_cache_and_settings_survive_new_store_instance(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory+'/cache.sqlite')
            store.save_bars('US.QQQ',[dict(date='2026-01-01',close=10)],'2026-01-01','QQQ')
            store.set('settings',dict(volume_mult=2))
            other = Store(directory+'/cache.sqlite')
            self.assertEqual(other.bars('US.QQQ')['rows'][0]['close'],10)
            self.assertEqual(other.get('settings')['volume_mult'],2)


if __name__ == '__main__':
    unittest.main()
