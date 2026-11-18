"""Small deterministic tests; no network and no private study data."""
import unittest
from sensitivity import next_open_outcome, evaluate_next_open
from study import HORIZONS


class SensitivityTest(unittest.TestCase):
    def test_uses_next_open_not_signal_close(self):
        rows = [
            {'open': 98, 'close': 100},
            {'open': 120, 'close': 110},
            {'open': 140, 'close': 150},
        ]
        self.assertAlmostEqual(next_open_outcome(rows, 0, 1), 100*(110/120-1))
        self.assertAlmostEqual(next_open_outcome(rows, 0, 2), 25.0)

    def test_censor_and_invalid_prices_fail_closed(self):
        rows = [{'open':100,'close':110}, {'open':0,'close':120}]
        self.assertIsNone(next_open_outcome(rows, 0, 1))
        rows[1]['open']=115
        self.assertIsNone(next_open_outcome(rows, 1, 1))
        with self.assertRaises(ValueError):
            next_open_outcome(rows, 0, 0)

    def test_no_lookahead_and_unknown_excluded(self):
        labels = {'a':'signal A', 'b':'signal B'}
        def indicator(records):
            for row in records:
                row['day_return']=0.0
                row['drawdown20']=0.0
            return records
        def signals(rows,index):
            return {'a':index==0, 'b':None}
        rules = {'LABELS':labels,'indicators':indicator,'signals':signals}
        sessions = [
            {'segment':0,'date':'2024-01-02','open':100,'close':100},
            {'segment':0,'date':'2024-01-03','open':110,'close':105},
            {'segment':0,'date':'2024-01-04','open':111,'close':120},
        ]
        got=evaluate_next_open(sessions,rules)
        self.assertEqual(len(got),2*len(HORIZONS))
        case=next(r for r in got if r['signal']=='a' and r['horizon']==1)
        self.assertEqual(case['trigger_n'],1)
        self.assertEqual(case['n'],1)
        self.assertAlmostEqual(case['next_open_mean_pct'],100*(105/110-1))
        self.assertEqual(case['pit_qualified_n'],0)
        self.assertEqual(next(r for r in got if r['signal']=='b')['n'],0)

    def test_segment_boundary_does_not_advance_exit(self):
        def signals(rows,index):
            return {'a':True}
        rules={'LABELS':{'a':'signal A'},'indicators':lambda a:a,'signals':signals}
        rows=[
            {'segment':0,'date':'2024-01-02','open':100,'close':100},
            {'segment':1,'date':'2024-01-04','open':120,'close':130},
            {'segment':1,'date':'2024-01-05','open':140,'close':150},
        ]
        result=evaluate_next_open(rows,rules)
        first=next(r for r in result if r['horizon']==1)
        self.assertEqual(first['trigger_n'],3)
        self.assertEqual(first['n'],1)
        self.assertEqual(first['censored_or_gap'],2)


if __name__=='__main__':unittest.main()
