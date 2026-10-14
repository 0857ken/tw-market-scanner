"""Financial unit/date/error tests. Synthetic parser cases never enter market.json."""
import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from pipeline import parsers
from pipeline.common import ROOT, calendar_rows, expected_session, iso_date, number, read_json, write_json
from pipeline.run import collect, build, import_credit, sessions_between, record_failure
from pipeline.schema import validate
from pipeline.release_check import check

NOW = datetime(2026, 10, 8, 21, 30, tzinfo=ZoneInfo('Asia/Taipei'))


class PipelineTests(unittest.TestCase):
    def test_shared_contract_cases(self):
        baseline=read_json(ROOT/'tests/fixtures/official-market-20261007.json')
        for case in read_json(ROOT/'tests/fixtures/contract-cases.json'):
            with self.subTest(case=case['name']):
                value=copy.deepcopy(baseline)
                for op in case['ops']:
                    parent=value
                    for key in op[1][:-1]: parent=parent[key]
                    if op[0]=='delete': del parent[op[1][-1]]
                    else: parent[op[1][-1]]=op[2]
                if case['valid']: validate(value, NOW)
                else:
                    with self.assertRaises(ValueError): validate(value, NOW)

    def test_cross_year_requires_both_calendar_years(self):
        now=datetime(2027,1,1,18,tzinfo=ZoneInfo('Asia/Taipei'))
        rows=[{'date':'2027-01-01','closed':True}]
        self.assertEqual(expected_session(now,rows),('2026-12-31',False))
        rows.append({'date':'2026-01-01','closed':True})
        self.assertEqual(expected_session(now,rows),('2026-12-31',True))

    def test_roc_and_gregorian_dates_are_validated(self):
        self.assertEqual(iso_date('1151007'), '2026-10-07')
        self.assertEqual(iso_date('20261007'), '2026-10-07')
        self.assertEqual(iso_date('115/10/7'), '2026-10-07')
        with self.assertRaises(ValueError): iso_date('1150230')

    def test_missing_and_nonfinite_are_not_zero(self):
        for value in ('--', '', None, 'NaN', 'Infinity', True): self.assertIsNone(number(value))
        self.assertEqual(number('0'), 0)
        self.assertEqual(number('-1,234'), -1234)

    def test_quotes_preserve_shares_and_missing_prices(self):
        raw=[{'Date':'1151007','Code':'2330','Name':'台積電','ClosingPrice':'--','TradeVolume':'--','Change':'--'}]
        d,r=parsers.quotes(raw)
        self.assertEqual(d,'2026-10-07');self.assertIsNone(r[0]['close']);self.assertIsNone(r[0]['volumeShares'])
        self.assertEqual(r[0]['status'],'no_trade')

    def test_quotes_reject_mixed_dates_duplicates_and_negative_volume(self):
        row={'Date':'1151007','Code':'2330','Name':'台積電','ClosingPrice':'100','TradeVolume':'1000'}
        for rows in ([row,row], [row,{**row,'Code':'2317','Date':'1151008'}], [{**row,'TradeVolume':'-1'}]):
            with self.assertRaises(ValueError):parsers.quotes(rows)

    def test_t86_exact_categories_and_official_total(self):
        raw={'stat':'OK','date':'20261007','fields':['證券代號','外陸資買賣超股數(不含外資自營商)','投信買賣超股數','自營商買賣超股數','自營商買賣超股數(自行買賣)','自營商買賣超股數(避險)','三大法人買賣超股數'],
             'data':[['2330','1,001','-2','4','7','-3','1,003']]}
        _,rows=parsers.t86(raw,'2026-10-07');self.assertEqual(rows[0]['totalShares'],1003)
        self.assertEqual(rows[0]['dealerShares'],4);self.assertEqual(rows[0]['foreignShares'],1001)
        bad=copy.deepcopy(raw);bad['data'][0][-1]='1004'
        with self.assertRaises(ValueError):parsers.t86(bad,'2026-10-07')

    def test_t86_unknown_category_stays_null(self):
        raw={'stat':'OK','date':'20261007','fields':['證券代號','外陸資買賣超股數(不含外資自營商)','投信買賣超股數','自營商買賣超股數','自營商買賣超股數(自行買賣)','自營商買賣超股數(避險)','三大法人買賣超股數'],
             'data':[['2330','--','0','0','0','0','--']]}
        _,rows=parsers.t86(raw,'2026-10-07');self.assertIsNone(rows[0]['foreignShares']);self.assertEqual(rows[0]['trustShares'],0)

    def test_rwd_must_match_requested_day(self):
        with self.assertRaises(ValueError):parsers.rwd_date({'stat':'OK','date':'20261006'},'2026-10-07')
        with self.assertRaises(ValueError):parsers.rwd_date({'stat':'查無資料'},'2026-10-07')

    def test_margin_first_group_lot_conversion_and_next_session_limit(self):
        raw={'stat':'OK','date':'20261007','tables':[{'fields':['代號','今日餘額','次一營業日限額','今日餘額','次一營業日限額'],
                                                  'data':[['2330','1,234','10,000','999','1000']]}]}
        _,rows=parsers.margin(raw,'2026-10-07');r=rows[0]
        self.assertEqual(r['balanceShares'],1234000);self.assertEqual(r['limitShares'],10000000)
        self.assertAlmostEqual(r['usagePct'],12.34);self.assertEqual(r['usagePctBasis'],'today-balance/next-session-limit')
        raw['tables'][0]['data'][0][2]='0'
        self.assertIsNone(parsers.margin(raw,'2026-10-07')[1][0]['usagePct'])

    @staticmethod
    def tx_rows():
        return [{'Date':'20261007','ContractCode':'臺股期貨','Item':identity,'OpenInterest(Long)':'100','OpenInterest(Short)':'100','OpenInterest(Net)':'0'}
                for identity in ('外資及陸資','投信','自營商')]

    def test_taifex_english_fields_zero_is_valid_and_other_contracts_excluded(self):
        raw=self.tx_rows()+[{**self.tx_rows()[0],'ContractCode':'小型臺指期貨','OpenInterest(Net)':'-999'}]
        _,rows=parsers.futures(raw);self.assertEqual(rows[0]['foreign'],0);self.assertEqual(rows[0]['contract'],'TX')

    def test_taifex_requires_all_identities_one_date_and_consistent_oi(self):
        for raw in (self.tx_rows()[:2],self.tx_rows()+[self.tx_rows()[0]], [{**r,'Date':'20261006'} if i else r for i,r in enumerate(self.tx_rows())],
                    [{**r,'OpenInterest(Net)':'1'} for r in self.tx_rows()]):
            with self.assertRaises(ValueError):parsers.futures(raw)

    def test_official_calendar_start_days_and_holidays(self):
        rows=calendar_rows([{'Date':'1150102','Name':'開始交易日','Description':'開始交易'}, {'Date':'1151009','Name':'國慶補假','Description':'放假'},
                            {'Date':'1150212','Name':'市場無交易，僅辦理結算交割作業','Description':''}])
        self.assertFalse(rows[0]['closed']);self.assertTrue(rows[1]['closed']);self.assertTrue(rows[2]['closed'])
        expected,known=expected_session(datetime(2026,10,9,22,tzinfo=ZoneInfo('Asia/Taipei')),rows)
        self.assertEqual(expected,'2026-10-08');self.assertTrue(known)
        _,known=expected_session(datetime(2027,1,4,22,tzinfo=ZoneInfo('Asia/Taipei')),rows);self.assertFalse(known)

    def test_timezone_uses_taipei_even_when_now_is_utc(self):
        expected,_=expected_session(datetime(2026,10,8,9,tzinfo=ZoneInfo('UTC')),[{'date':'2026-01-01','closed':True}])
        self.assertEqual(expected,'2026-10-08')

    def test_gap_sessions_include_missing_trading_days(self):
        self.assertEqual(sessions_between('2026-10-05','2026-10-07',[]),['2026-10-05','2026-10-06','2026-10-07'])

    def test_failed_fetch_retains_prior_date_timestamp_and_never_zero_fills(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);write_json(root/'raw/quotes_2026-10-07.json',{'date':'2026-10-07','rows':[{'symbol':'2330','close':123}],
                                                                    'sha256':'f'*64,'fetchedAt':'2026-10-07T22:30:00+08:00'})
            sources={}
            with patch('pipeline.run.get_json',side_effect=RuntimeError('source outage')):
                snap=collect(root,sources,'quotes',parsers.quotes,NOW)
            self.assertEqual(snap['date'],'2026-10-07');self.assertEqual(snap['rows'][0]['close'],123)
            self.assertEqual(sources['quotes']['status'],'error');self.assertEqual(sources['quotes']['fetchedAt'],'2026-10-07T22:30:00+08:00')

    def test_missing_source_without_history_is_error_not_holiday(self):
        with tempfile.TemporaryDirectory() as tmp:
            sources={}
            with patch('pipeline.run.get_json',side_effect=RuntimeError('timeout')):
                self.assertIsNone(collect(Path(tmp),sources,'quotes',parsers.quotes,NOW))
            self.assertIsNone(sources['quotes']['asOf']);self.assertEqual(sources['quotes']['status'],'error')

    def test_canonical_real_dataset_and_explicit_price_basis(self):
        raw=read_json(ROOT/'tests/fixtures/official-market-20261007.json');validate(raw)
        self.assertGreater(len(raw['stocks']),1000);self.assertEqual(raw['asOf'],'2026-10-07')
        self.assertTrue(all(s['priceBasis']=='unadjusted' for s in raw['stocks']))
        self.assertEqual(raw['creditHistory'],[]);self.assertEqual(raw['creditRule']['status'],'pending')

    def test_schema_refuses_fabricated_modes_duplicates_and_missing_digest(self):
        raw=read_json(ROOT/'data/market.json')
        for mutate in (lambda r:r.update(mode='demo'),lambda r:r['stocks'].append(r['stocks'][0]),lambda r:r['sources']['quotes'].pop('sha256')):
            x=copy.deepcopy(raw);mutate(x)
            with self.assertRaises(ValueError):validate(x)

    def test_credit_requires_rights_adjusted_prices_and_completed_us_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'credit.json'
            write_json(p,{'priceBasis':'unadjusted','rows':[]})
            with self.assertRaises(ValueError):import_credit(p,{},NOW)
            write_json(p,{'priceBasis':'adjusted-total-return','license':{'permitsRedistribution':'false'},'rows':[]})
            with self.assertRaises(ValueError):import_credit(p,{},NOW)
            raw={'priceBasis':'adjusted-total-return','source':'Fixture only','license':{'permitsRedistribution':True,'url':'https://example.org/license'},
                 'rows':[{'date':'2026-10-08','hyg':80,'shy':82}]}
            write_json(p,raw)
            with self.assertRaises(ValueError):import_credit(p,{},NOW)  # US market is not closed yet at Taipei 21:30.

    def test_atomic_write_refuses_nan(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'market.json';write_json(p,{'close':123})
            with self.assertRaises(ValueError):write_json(p,{'close':float('nan')})
            self.assertEqual(read_json(p)['close'],123)

    def test_unverified_institutional_source_is_not_fetched_or_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            write_json(root/'raw/institutional_2026-10-07.json',{'date':'2026-10-07','rows':[{'symbol':'2330','foreignShares':1234}]})
            sources={}
            with patch('pipeline.run.get_json') as fetch:
                self.assertIsNone(collect(root,sources,'institutional',parsers.t86,NOW))
            fetch.assert_not_called()
            self.assertEqual(sources['institutional']['status'],'unavailable')

    def test_schema_rejects_wrong_futures_units_negative_margin_and_unadjusted_credit(self):
        raw=read_json(ROOT/'tests/fixtures/official-market-20261007.json')
        cases=[]
        x=copy.deepcopy(raw);x['futures'][0]['contract']='MTX';cases.append(x)
        x=copy.deepcopy(raw);next(s for s in x['stocks'] if s['margin'])['margin']['balanceShares']=-1;cases.append(x)
        x=copy.deepcopy(raw);x['creditHistory']=[{'date':'2026-10-07','hyg':80,'shy':82}];cases.append(x)
        for x in cases:
            with self.assertRaises(ValueError):validate(x)

    def test_release_rechecks_current_date_even_if_saved_status_says_fresh(self):
        raw=read_json(ROOT/'tests/fixtures/official-market-20261007.json')
        for source in raw['sources'].values():
            if source['status']=='stale':source['status']='fresh'
        with self.assertRaisesRegex(ValueError,'current expected session'):check(raw,NOW)

    def test_release_rejects_pending_redistribution_even_when_quotes_are_fresh(self):
        raw=read_json(ROOT/'tests/fixtures/official-market-20261007.json')
        raw['sources']['quotes']['status']='fresh';raw['sources']['companies']['status']='fresh'
        before_close=datetime(2026,10,8,15,tzinfo=ZoneInfo('Asia/Taipei'))
        self.assertEqual(check(raw,before_close),'2026-10-07')
        raw['sources']['institutional']['asOf']='2026-10-07'
        raw['stocks'][0]['institutional']=[{'date':'2026-10-07','foreignShares':1000}]
        with self.assertRaisesRegex(ValueError,'redistribution rights pending'):check(raw,before_close)

    def test_fatal_integration_failure_publishes_error_without_changing_observed_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);before=read_json(ROOT/'tests/fixtures/official-market-20261007.json')
            write_json(root/'market.json',before)
            self.assertEqual(record_failure(root,NOW,ValueError('invalid imported credit')),2)
            after=read_json(root/'market.json');validate(after)
            self.assertEqual(after['stocks'],before['stocks']);self.assertEqual(after['asOf'],before['asOf'])
            self.assertEqual(after['futures'],before['futures'])
            self.assertEqual(after['sources']['quotes']['fetchedAt'],before['sources']['quotes']['fetchedAt'])
            self.assertEqual(after['sources']['quotes']['status'],'error')
            self.assertFalse(read_json(root/'quality.json')['freshCritical'])


if __name__ == '__main__': unittest.main()
