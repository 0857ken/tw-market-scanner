import copy,json,tempfile,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from pipeline.common import ROOT,TPE,read_json,get_json
from pipeline.daily_release import gate,target_day,project,bundle,verify_bundle,sha,encoded,controlled,STATIC_ID
from pipeline.package_daily import package
from pipeline.daily_state import commit,restore
from pipeline.release_check import check as strict_check
class DailyReleaseTests(unittest.TestCase):
 def setUp(self):
  self.p=read_json(ROOT/'data/market.json');self.now=datetime(2026,10,14,9,tzinfo=TPE)
 def test_idempotent_and_weekend_noop(self):
  self.assertEqual(gate(self.p,self.p,'2026-10-13'),'no-op-identical')
  self.assertEqual(gate(self.p,self.p,'2026-10-18'),'no-op-closed')
 def test_successful_new_session_against_real_older_fixture(self):
  from tests.test_daily import DailyTests
  fixture=DailyTests();fixture.setUp();self.addCleanup(fixture.doCleanups)
  self.assertEqual(gate(self.p,read_json(fixture.root/'market.json'),'2026-10-13'),'candidate')
 def test_holiday_noop(self):
  p=copy.deepcopy(self.p);p['calendar']['rows'].append({'date':'2026-10-14','closed':True})
  self.assertEqual(gate(p,self.p,'2026-10-14'),'no-op-closed')
 def test_source_delay_and_new_year_never_invent_date(self):
  for target in ('2026-10-14','2027-01-04'):
   with self.assertRaises(ValueError):gate(self.p,self.p,target)
 def test_cross_day_target_preserved(self):
  self.assertEqual(target_day(self.now,'2026-10-13'),'2026-10-13')
  for day in ('2026-10-14','2026-10-12'):
   with self.assertRaises(ValueError):target_day(self.now,day)
  self.assertEqual(target_day(datetime(2027,1,1,1,tzinfo=TPE),'2026-12-31'),'2026-12-31')
 def test_revision_unknown_license_source_failure_and_url(self):
  for key,value in [('sha256','a'*64),('fetchStatus','error'),('url','https://evil.invalid/'),('licenseStatus','pending')]:
   p=copy.deepcopy(self.p);p['sources']['quotes'][key]=value
   with self.assertRaises(ValueError):gate(p,self.p,'2026-10-13')
 def test_market_date_mismatch_and_regression(self):
  for day in ('2026-10-12','2026-10-14'):
   p=copy.deepcopy(self.p);p['sources']['tpexQuotes']['asOf']=day
   with self.assertRaises(ValueError):gate(p,self.p,'2026-10-13')
 def test_coverage_anomaly(self):
  p=copy.deepcopy(self.p)
  for s in p['stocks'][:500]:
   for r in s['history']:
    if r['date']=='2026-10-13':r.update(close=None,rawClose=None,status='no-trade')
  with self.assertRaises(ValueError):gate(p,self.p,'2026-10-13')
 def test_official_403_and_429_never_retry(self):
  for code in (403,429):
   with patch('pipeline.common.urlopen',side_effect=HTTPError('https://www.tpex.org.tw/',code,'refused',{},None)) as request:
    with self.assertRaises(HTTPError):get_json('https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes')
    self.assertEqual(request.call_count,1)
 def test_local_overlapping_attempt_stops(self):
  with tempfile.TemporaryDirectory() as t:
   (Path(t)/'.lock').touch()
   with self.assertRaises(FileExistsError):controlled(ROOT/'data',t,'2026-10-13',self.now,'test')
 def test_failed_update_never_changes_baseline(self):
  before=(ROOT/'data/market.json').read_bytes()
  with tempfile.TemporaryDirectory() as t,patch('pipeline.daily_release.run_daily',return_value=2):
   with self.assertRaises(ValueError):controlled(ROOT/'data',t,'2026-10-13',self.now,'failure',True)
   self.assertTrue((Path(t)/'failure.json').exists())
  self.assertEqual(before,(ROOT/'data/market.json').read_bytes())
 def test_immutable_bundle_new_sha_static_bytes_and_restore(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);seed=root/'seed';seed.mkdir();(seed/'index.html').write_text('fixture');(seed/'.nojekyll').touch()
   pin={'frontendId':STATIC_ID,'assets':{n:sha((seed/n).read_bytes()) for n in ('index.html','.nojekyll')}}
   (seed/'frontend-pin.json').write_bytes(encoded(pin))
   body,report=project(self.p,'123',self.now)
   self.assertFalse(report['strategyComplete']);self.assertFalse(report['deploymentAuthorized'])
   receipt=bundle(body,report,seed,root/'old.zip');self.assertTrue(verify_bundle(root/'old.zip',receipt,seed))
   candidate=root/'candidate';candidate.mkdir();(candidate/'gate.json').write_bytes(encoded({'decision':'candidate','runId':'123'}));(candidate/'candidate-market.json').write_bytes(body);(candidate/'candidate-report.json').write_bytes(encoded(report))
   packed=package(candidate,root/'old.zip',receipt['zipSha256'],root/'packed');self.assertTrue(verify_bundle(root/'packed/daily-release.zip',packed,seed))
   (candidate/'gate.json').write_bytes(encoded({'decision':'no-op-identical','runId':'123'}))
   with self.assertRaises(ValueError):package(candidate,root/'old.zip',receipt['zipSha256'],root/'noop')
   receipt2=bundle(body,{**report,'runId':'124'},seed,root/'new.zip')
   self.assertNotEqual(receipt['zipSha256'],receipt2['zipSha256'])
   store=root/'ledger';commit(store,root/'old.zip',receipt,seed)
   with self.assertRaises(ValueError):commit(store,root/'new.zip',receipt2,seed)
   commit(store,root/'new.zip',receipt2,seed,receipt['zipSha256'])
   restore(store,receipt['zipSha256'],seed,receipt2['zipSha256'])
   self.assertEqual(read_json(store/'current.json')['zipSha256'],receipt['zipSha256'])
   self.assertEqual(receipt['dataSha256'],receipt2['dataSha256'])
   self.assertEqual(receipt['frontendPinSha256'],receipt2['frontendPinSha256'])
   with self.assertRaises(FileExistsError):bundle(body,report,seed,root/'old.zip')
   with self.assertRaises(ValueError):verify_bundle(root/'new.zip',receipt,seed)
   (seed/'index.html').write_text('tampered')
   with self.assertRaises(ValueError):bundle(body,report,seed,root/'bad.zip')
 def test_strict_strategy_gate_stays_closed(self):
  with self.assertRaisesRegex(ValueError,'calendar'):strict_check(self.p,self.now)
 def test_credit_t86_adjusted_never_projected(self):
  for kind in ('t86','credit','adjusted'):
   p=copy.deepcopy(self.p)
   if kind=='t86':next(s for s in p['stocks'] if s['market']=='TWSE')['institutional']=[{'date':'2026-10-13','foreignShares':0,'trustShares':0,'dealerShares':0,'totalShares':0}]
   elif kind=='credit':p['creditRule']['status']='verified'
   else:p['stocks'][0]['history'][-1]['adjustedClose']=100
   with self.assertRaises(ValueError):project(p,'test',self.now)
