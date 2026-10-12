"""Synthetic research fixtures: no third-party unlicensed historical observations."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from pipeline.common import ROOT, read_json
from pipeline import parsers
from pipeline.research import ordinary,apply_lifecycle,member_on,suspended_on,adjusted_prices,checked_import,import_history,integrate
from pipeline.schema import validate

class ResearchTests(unittest.TestCase):
    def test_ordinary_requires_roster_identity_not_just_quote_symbol(self):
        self.assertTrue(ordinary('1234','示範-KY'))
        for code,name in [('0050','ETF'),('00411A','主動ETF'),('020001','ETN'),('12345','特別股'),('123456','權證'),('9103','示範-DR')]:
            self.assertFalse(ordinary(code,name))

    def test_tpex_projection_dates_shares_and_missing_values(self):
        d,rows=parsers.tpex_companies([{'Date':'1151008','SecuritiesCompanyCode':'1234','CompanyAbbreviation':'示範','SecuritiesIndustryCode':'01','DateOfListing':'20200101','IssueShares':'1000','Address':'PRIVATE TEST ONLY'}])
        self.assertEqual(d,'2026-10-08');self.assertEqual(rows[0]['listedOn'],'2020-01-01');self.assertNotIn('Address',rows[0])
        d,rows=parsers.tpex_quotes([{'Date':'1151008','SecuritiesCompanyCode':'1234','CompanyName':'示範','Close':'--','TradingShares':'0','Change':'--'}])
        self.assertIsNone(rows[0]['close']);self.assertEqual(rows[0]['volumeShares'],0)
        with self.assertRaises(ValueError):parsers.tpex_quotes([{'Date':'1151008','SecuritiesCompanyCode':'1234','CompanyName':'示範','Close':'10','TradingShares':'-1'}])

    def test_lifecycle_exclusive_exit_resume_and_transfer(self):
        s=apply_lifecycle({},[{'date':'2025-01-02','kind':'listed'},{'date':'2025-02-01','kind':'suspend'},{'date':'2025-02-05','kind':'resume'},{'date':'2025-03-01','kind':'transfer-out'}])
        self.assertFalse(member_on(s,'2025-01-01'));self.assertTrue(member_on(s,'2025-01-02'))
        self.assertTrue(suspended_on(s,'2025-02-04'));self.assertFalse(suspended_on(s,'2025-02-05'))
        self.assertTrue(member_on(s,'2025-02-28'));self.assertFalse(member_on(s,'2025-03-01'))
        with self.assertRaises(ValueError):apply_lifecycle({},[{'date':'2025-01-01','kind':'resume'}])
        with self.assertRaises(ValueError):apply_lifecycle({},[{'date':'2025-01-01','kind':'suspend'},{'date':'2025-01-01','kind':'resume'}])

    def test_backward_factor_is_independent_not_reference_price_or_raw_overwrite(self):
        raw=[{'date':'2025-01-01','rawClose':100},{'date':'2025-01-02','rawClose':50},{'date':'2025-01-03','rawClose':None}]
        out=adjusted_prices(raw,[{'effectiveDate':'2025-01-02','factor':.5,'kind':'split'}],method='backward-price',version='synthetic-v1')
        self.assertEqual([r['adjustedClose'] for r in out],[50,50,None]);self.assertEqual(out[0]['rawClose'],100)
        self.assertNotIn('adjustedClose',raw[0])
        with self.assertRaises(ValueError):adjusted_prices(raw,[{'effectiveDate':'2025-01-02','factor':.5,'kind':'ex-reference-price'}],method='backward-total-return',version='test')
        with self.assertRaises(ValueError):adjusted_prices(raw,[{'effectiveDate':'2025-01-02','factor':0}],method='backward-price',version='test')

    def test_import_requires_external_file_hash_license_and_version_not_self_declared(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'input.json';data={'kind':'histories','version':'synthetic-v1','verified':True,'rows':[{'market':'TPEx','symbol':'1234','name':'示範','date':'2025-01-02','rawClose':10,'volumeShares':0}]};p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):checked_import(p,'histories')
            digest=hashlib.sha256(p.read_bytes()).hexdigest();grant={'histories':{digest:{'status':'reviewed','version':'synthetic-v1','permitsRedistribution':True,'evidence':'https://example.org/SYNTHETIC-TEST-ONLY'}}}
            result=import_history(p,Path(tmp)/'out',grant)
            self.assertEqual(result['rows'],1);self.assertEqual(hashlib.sha256(Path(result['path']).read_bytes()).hexdigest(),digest)
            data['rows'][0]['rawClose']=999;p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):checked_import(p,'histories',grant)

    def test_public_sample_keeps_market_and_price_layers_separate(self):
        p=read_json(ROOT/'data/market.json');validate(p)
        self.assertEqual(p['researchVersion'],1)
        for s in p['stocks']:
            self.assertEqual(s['securityId'],s['market']+':'+s['symbol'])
            self.assertFalse(s['lifecycle']['pointInTimeVerified'])
            if s['market']=='TWSE':self.assertFalse(s['institutional'])
            for r in s['history']:
                self.assertEqual(r['rawClose'],r['close']);self.assertIsNone(r['adjustedClose'])
        self.assertTrue(any(s['market']=='TPEx' and s['institutional'] for s in p['stocks']))
        self.assertEqual(read_json(ROOT/'data/stage3b-sample-manifest.json')['bulkHistoricalPriceRequests'],0)

    def test_shared_research_contract_cases(self):
        base=read_json(ROOT/'data/market.json')
        for case in read_json(ROOT/'tests/fixtures/research-contract-cases.json'):
            with self.subTest(case=case['name']):
                p=copy.deepcopy(base)
                for op,path,value in case['ops']:
                    parent=p
                    for key in path[:-1]:parent=parent[key]
                    parent[path[-1]]=value
                if case['valid']:validate(p)
                else:
                    with self.assertRaises(ValueError):validate(p)
