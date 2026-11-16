"""Network-free checks. No private archive or historical data checked into Git."""
from datetime import date
from pathlib import Path
import json
import tempfile
import unittest

from capture import jobs
from series import annual_counts, calendar_year, futures_year, load_source, PRICE, price_month, sha
from study import describe, disjoint, excursion, holm, match_effect, stratum


class StudyTest(unittest.TestCase):
    def test_warmup_capture_plan_has_71_months(self):
        self.assertEqual(len(list(jobs('ohlc'))), 71)

    def test_wrong_month_and_duplicates_rejected(self):
        data={'stat':'OK','date':'20211101','fields':PRICE,
              'data':[['110/11/01','100','110','98','105']]}
        self.assertEqual(price_month(json.dumps(data), '2021-11','ohlc')[date(2021,11,1)]['close'],105)
        with self.assertRaises(ValueError):
            price_month(json.dumps(data),'2021-10','ohlc')
        data['data']*=2
        with self.assertRaises(ValueError):
            price_month(json.dumps(data),'2021-11','ohlc')
        data['data']=data['data'][:1];data['data'][0][2]='98'
        with self.assertRaises(ValueError):
            price_month(json.dumps(data),'2021-11','ohlc')

    def test_calendar_response_must_be_requested_year(self):
        raw=json.dumps({'fields':['日期','名稱','說明'],'queryYear':2027,'data':[]})
        with self.assertRaises(ValueError):
            calendar_year(raw,'2026')

    def test_factbook_counts_parse(self):
        rows=['<tr><td>'+str(y)+'</td><td>245</td>'+'<td>0</td>'*6+'</tr>' for y in range(2021,2026)]
        self.assertEqual(annual_counts((''.join(rows)).encode())['2021'],245)

    def test_txf_short_sign_and_scope(self):
        head='日期,商品名稱,身份別,多方未平倉口數,空方未平倉口數,多空未平倉口數淨額\n'
        body='2024/01/02,臺股期貨,外資及陸資,100,123,-23\n2024/01/02,小型臺指期貨,外資及陸資,23,15,8\n'
        self.assertEqual(futures_year((head+body).encode('cp950'),'2024'),{date(2024,1,2):23})
        with self.assertRaises(ValueError):
            futures_year((head+body.replace('-23','23')).encode(),'2024')

    def test_source_hash_tamper(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'ohlc').mkdir()
            path=root/'ohlc'/'2021-01'
            path.with_suffix('.body').write_bytes(b'value')
            path.with_suffix('.json').write_text(json.dumps({'status':200,'bytes':5,'sha256':sha(b'value')}))
            self.assertEqual(load_source(root,'ohlc','2021-01'),b'value')
            path.with_suffix('.body').write_bytes(b'other')
            with self.assertRaises(ValueError):
                load_source(root,'ohlc','2021-01')

    def test_censor_and_forward_excursion_exclude_signal_day(self):
        data=[{'close':100,'low':80,'high':160},{'close':110,'low':95,'high':120}]
        self.assertIsNone(excursion(data,1,1))
        ret,mae,mfe=excursion(data,0,1)
        self.assertAlmostEqual(ret,10);self.assertAlmostEqual(mae,-5);self.assertAlmostEqual(mfe,20)
        self.assertEqual(describe([(0,0,0)])['win_pct'],0)

    def test_disjoint_never_reuses_exit_day(self):
        self.assertEqual(disjoint([(0,1),(0,6),(0,7),(1,0)],5),[(0,1),(0,7),(1,0)])

    def test_match_no_cross_year_and_no_donor_gives_unknown(self):
        rows={(0,0):{'date':'2024-01-02','day_return':-.02,'drawdown20':-.05},
              (0,1):{'date':'2024-01-03','day_return':-.02,'drawdown20':-.05},
              (0,2):{'date':'2025-01-02','day_return':-.02,'drawdown20':-.05}}
        v={k:(r,0,0) for k,r in zip(rows,(2,1,9))}
        self.assertEqual(match_effect([(0,0)],[(0,1),(0,2)],rows,v)['mean_delta_pp'],1)
        self.assertIsNone(match_effect([(0,0)],[(0,2)],rows,v)['mean_delta_pp'])

    def test_matching_bins_are_not_defined_by_trigger_thresholds(self):
        def regime(daily, drawdown):
            return stratum({'date':'2024-01-02','day_return':daily,'drawdown20':drawdown})
        self.assertEqual(regime(-.031,-.101),regime(-.029,-.099))
        self.assertEqual(regime(-.031,-.071),regime(-.029,-.069))

    def test_holm_accounts_for_all_prelisted_slots(self):
        result=holm({'a':.001,'b':.002},105)
        self.assertAlmostEqual(result['a'],.105)
        self.assertAlmostEqual(result['b'],.208)


if __name__=='__main__':
    unittest.main()
