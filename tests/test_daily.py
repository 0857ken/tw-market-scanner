"""Offline replay tests. Synthetic changes stay in temporary data directories."""
import copy
import json
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from pipeline.common import ROOT,TPE,read_json,write_json,expected_session
from pipeline.daily import MODULES,run_daily,quality
from pipeline.run import SOURCES,collect,build
from pipeline.research import integrate
from pipeline import parsers

NOW=datetime(2026,10,12,23,30,tzinfo=TPE)

class DailyTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'data';shutil.copytree(ROOT/'data',self.root,ignore=shutil.ignore_patterns('institutional_*.json'))
        pinned={'calendar':'2026-12-25','companies':'2026-10-11','quotes':'2026-10-08','tpexCompanies':'2026-10-11','tpexQuotes':'2026-10-08','tpexInstitutional':'2026-10-08'}
        self.snaps={m:read_json(self.root/'raw'/f'{m}_{d}.json') for m,d in pinned.items()}
        for m,d in pinned.items():
            for path in (self.root/'raw').glob(m+'_*.json'):
                if path.stem.split('_')[-1]>d:path.unlink()
        sources=read_json(self.root/'source-state.json')['sources']
        for m,snap in self.snaps.items():
            sources[m].update(asOf=snap['date'],fetchedAt=snap['fetchedAt'],sha256=snap['sha256'],status='unknown',fetchStatus='ok')
        baseline=integrate(build(self.root,sources,self.snaps['calendar']['rows'],[],NOW),self.root)
        write_json(self.root/'market.json',baseline);write_json(self.root/'source-state.json',{'sources':sources})

    def replay(self, changes=None, fail=None, now=NOW):
        samples=copy.deepcopy(self.snaps)
        if changes: changes(samples)
        adapters={m:(lambda raw,m=m:(samples[m]['date'],samples[m]['rows'])) for m in MODULES}
        by_url={SOURCES[m][1]:m for m in MODULES}
        def fetch(url,params=None):
            self.assertIsNone(params);self.assertIn(url,by_url)
            m=by_url[url]
            if m==fail: raise RuntimeError('offline simulated outage')
            return {},samples[m]['sha256'],url
        with patch('pipeline.daily.PARSERS',adapters),patch('pipeline.run.get_json',side_effect=fetch) as network:
            code=run_daily(self.root,now)
            self.assertEqual(network.call_count,6)
            return code

    def test_rerun_does_not_duplicate_or_rewrite_snapshots(self):
        before={p.name:p.read_bytes() for p in (self.root/'raw').glob('*.json')}
        self.assertEqual(self.replay(),0);self.assertEqual(self.replay(),0)
        self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'raw').glob('*.json')})
        market=read_json(self.root/'market.json')
        for s in market['stocks']:self.assertEqual(len(s['history']),len({r['date'] for r in s['history']}))

    def test_failed_source_retains_market_state_and_raw_bytes(self):
        files=[self.root/'market.json',self.root/'source-state.json',*(self.root/'raw').glob('*.json')]
        before={str(p):p.read_bytes() for p in files}
        self.assertEqual(self.replay(fail='tpexQuotes'),2)
        self.assertEqual(before,{str(p):p.read_bytes() for p in files})
        self.assertEqual(read_json(self.root/'daily-attempt.json')['status'],'failed-last-valid-retained')

    def test_same_date_revision_and_regression_require_review(self):
        for mode in ('revision','regression'):
            def change(s):
                if mode=='revision':s['quotes']['rows'][0]['close']=1
                else:s['quotes']['date']='2026-10-06'
            before=(self.root/'market.json').read_bytes()
            self.assertEqual(self.replay(change),2);self.assertEqual((self.root/'market.json').read_bytes(),before)

    def test_holiday_replay_never_dates_prices_as_holiday(self):
        holiday=datetime(2026,10,18,21,tzinfo=TPE)
        self.assertEqual(self.replay(now=holiday),0)
        self.assertFalse((self.root/'raw/quotes_2026-10-18.json').exists())
        self.assertEqual(read_json(self.root/'market.json')['sources']['quotes']['asOf'],'2026-10-08')

    def test_known_closure_and_weekend_quote_rejected(self):
        for day in ('2026-10-09','2026-10-10'):
            def change(s):
                s['quotes']['date']=day
                for row in s['quotes']['rows']:row['date']=day
            self.assertEqual(self.replay(change),2)
            self.assertFalse((self.root/'raw'/f'quotes_{day}.json').exists())

    def test_cross_year_calendar_does_not_claim_verified(self):
        rows=[{'date':'2027-01-01','closed':True}]
        self.assertEqual(expected_session(datetime(2027,1,1,21,tzinfo=TPE),rows),('2026-12-31',False))
        self.assertEqual(self.replay(now=datetime(2027,1,4,21,tzinfo=TPE)),0)
        self.assertEqual(read_json(self.root/'market.json')['sources']['quotes']['status'],'unknown')

    def test_market_dates_mismatch_is_not_combined_daily_breadth(self):
        def change(s):
            s['quotes']['date']='2026-10-12'
            for row in s['quotes']['rows']:row['date']='2026-10-12'
        self.assertEqual(self.replay(change),0)
        q=read_json(self.root/'quality.json')['coverage']
        self.assertFalse(q['ALL']['sameDate']);self.assertIsNone(q['ALL']['up'])
        self.assertEqual(q['TPEx']['asOf'],'2026-10-08')
        self.assertEqual(read_json(self.root/'market.json')['sources']['tpexQuotes']['status'],'unknown')

    def test_quality_categories_partition_and_unknown_is_not_suspension(self):
        q=quality(read_json(self.root/'market.json'))
        for m in ('TWSE','TPEx'):
            x=q[m];self.assertEqual(x['total'],x['valid']+x['missingRow']+x['missingPriceUnknownReason']+x['confirmedSuspended'])
            self.assertEqual(x['valid'],x['changeEligible']+x['changeUnknownAmongValidPrices'])
            self.assertEqual(x['confirmedSuspended'],0)
            self.assertEqual(x['unknownReason'],x['missing'])

    def test_parsers_mixed_date_missing_price_and_zero_change(self):
        row={'Date':'1151008','SecuritiesCompanyCode':'1234','CompanyName':'TEST','Close':'--','TradingShares':'--','Change':'0'}
        _,rows=parsers.tpex_quotes([row]);self.assertIsNone(rows[0]['close']);self.assertEqual(rows[0]['changeAmount'],0)
        with self.assertRaises(ValueError):parsers.tpex_quotes([row,{**row,'SecuritiesCompanyCode':'1235','Date':'1151012'}])

    def test_csv_official_mapping_and_no_historical_parameters(self):
        from pipeline.current_csv import parse_twse_csv,fetch_twse_csv
        raw='日期,證券代號,證券名稱,收盤價,成交股數,漲跌價差\n1151012,2330,TEST,100,1000,0\n'.encode()
        d,rows=parsers.quotes(parse_twse_csv(raw));self.assertEqual(d,'2026-10-12');self.assertEqual(rows[0]['volumeShares'],1000)
        with self.assertRaises(ValueError):parse_twse_csv(b'<html>error</html>')
        with self.assertRaises(ValueError):fetch_twse_csv(params={'date':'20250101'})

    def test_csv_update_option_uses_licensed_current_adapter(self):
        samples=copy.deepcopy(self.snaps)
        adapters={m:(lambda raw,m=m:(samples[m]['date'],samples[m]['rows'])) for m in MODULES}
        by_url={SOURCES[m][1]:m for m in MODULES}
        def fetch(url,params=None):return {},samples[by_url[url]]['sha256'],url
        from pipeline.current_csv import URL
        with patch('pipeline.daily.PARSERS',adapters),patch('pipeline.run.get_json',side_effect=fetch) as api,patch('pipeline.daily.fetch_twse_csv',return_value=({},samples['quotes']['sha256'],URL)) as csv:
            self.assertEqual(run_daily(self.root,NOW,twse_current_csv=True),0)
            self.assertEqual(api.call_count,5);csv.assert_called_once()

    def test_preclose_same_day_eod_rejected_for_both_markets(self):
        def change(s):
            for module in ('quotes','tpexQuotes'):
                s[module]['date']='2026-10-12'
                for r in s[module]['rows']:r['date']='2026-10-12'
        self.assertEqual(self.replay(change,now=datetime(2026,10,12,12,0,tzinfo=TPE)),2)
        self.assertEqual(read_json(self.root/'market.json')['sources']['quotes']['asOf'],'2026-10-08')
