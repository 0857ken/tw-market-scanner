"""Additional synthetic attacks on prospective metadata and decision selection."""
from datetime import date
from urllib.parse import parse_qs, urlsplit
from capture import jobs
from series import calendar_year
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from capture_seal import write_local_seal
from evidence_schema import iso_date, unique_json
from forward_capture import collect, source_urls, verify_frozen_archive
from forward_review import build_decision, canonical, make_plan, pinned_json, validate_calendar, write_new
from test_capture_seal import synthetic_fetch


class MetadataTests(unittest.TestCase):
    def test_calendar_request_uses_the_official_form_date_parameter(self):
        for kind,year,urls in jobs('calendar'):
            query=parse_qs(urlsplit(urls[0]).query)
            self.assertEqual(query['date'],[year+'0101'])
            self.assertNotIn('queryYear',query)

    def test_settlement_only_note_overrides_copied_last_trading_label(self):
        payload={'queryYear':2022,'fields':['日期','名稱','說明'],
                 'data':[['2022-01-26','農曆春節前最後交易日','農曆春節前最後交易。1月27日市場無交易，僅辦理結算交割作業。'],
                         ['2022-01-27','農曆春節前最後交易日','1月27日市場無交易，僅辦理結算交割作業。']]}
        closed=calendar_year(json.dumps(payload),'2022')
        self.assertEqual(set(closed),{date(2022,1,27)})

    def test_noncanonical_dates_rejected(self):
        for value in ('20261118', '2026-W47-3', '2026-1-18', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                iso_date(value)
        self.assertEqual(iso_date('2026-11-18'), date(2026, 11, 18))

    def test_ambiguous_json_and_constants_rejected(self):
        for value in ('{"date":"a","date":"b"}','{"x":NaN}','{"x":Infinity}'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                unique_json(value)

    def test_same_host_wrong_endpoint_query_rejected(self):
        for url in ('https://www.twse.com.tw/other',
                    source_urls('2026-11-18')['ohlc'].replace('20261101','20261001')):
            with self.subTest(url=url), tempfile.TemporaryDirectory() as root:
                folder,_=collect(root,'2026-11-18','2026-11-19','a'*64,synthetic_fetch)
                (folder/'SEAL.json').unlink()
                p=folder/'ohlc.receipt.json'
                record=json.loads(p.read_text());record['url']=url;record['effective_url']=url
                p.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    write_local_seal(folder)

    def test_resealed_claim_cannot_upgrade_local_evidence(self):
        for flag in ('prospective_candidate','independent_timestamp_anchor',
                     'calendar_verified_independently','publication_timestamp_verified',
                     'signal_frozen_before_outcome','outcome_matured'):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as root:
                folder,_=collect(root,'2026-11-18','2026-11-19','a'*64,synthetic_fetch)
                (folder/'SEAL.json').unlink()
                p=folder/'status.json';record=json.loads(p.read_text())
                record[flag]=True;p.write_text(json.dumps(record))
                with self.assertRaises(ValueError):
                    write_local_seal(folder)

    def test_receipt_cannot_predate_market_session(self):
        def early(url):
            body,receipt=synthetic_fetch(url)
            receipt.update(started_at_utc='2026-11-17T13:00:00Z',
                           completed_at_utc='2026-11-17T13:01:00Z')
            return body,receipt
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
            collect(root,'2026-11-18','2026-11-19','a'*64,early)

    def test_duplicate_frozen_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'frozen.zip'
            with ZipFile(p,'w') as z:
                z.writestr('data/r25_frozen_rules.json','{"files_sha256":{},"files_sha256":{}}')
            with self.assertRaises(ValueError):
                verify_frozen_archive(p,sha256(p.read_bytes()).hexdigest())


class DecisionTests(unittest.TestCase):
    def fixture(self, root):
        archive=Path(root)/'synthetic-rules.zip'
        code=b'# synthetic integrity-only fixture'
        with ZipFile(archive,'w') as z:
            z.writestr('tools/backtest.py',code)
            z.writestr('data/r25_frozen_rules.json',json.dumps({
                'basis_as_of':'2026-10-16','signal_keys':['s'+str(i) for i in range(15)],
                'files_sha256':{'tools/backtest.py':sha256(code).hexdigest()}}))
        pin=sha256(archive.read_bytes()).hexdigest()
        folder,gate=collect(root,'2026-11-18','2026-11-19',pin,synthetic_fetch)
        plan=make_plan(pin,'2026-11-18','2026-11-18T00:00:00Z')
        calendar={'schema_version':1,'market':'TWSE','days':[
            {'date':'2026-11-18','state':'TRADING_SESSION','source_sha256':'c'*64},
            {'date':'2026-11-19','state':'TRADING_SESSION','source_sha256':'c'*64}]}
        capsules=[{'directory':str(folder),'seal_sha256':gate['local_seal_sha256']}]
        return plan,calendar,capsules,archive

    def build(self, plan, calendar, capsules, archive, cutoff='2026-11-18T14:00:00Z'):
        # Only test selection and evidence gates. No synthetic performance results.
        rules={'indicators':lambda rows:rows,'signals':lambda rows,i:{'down4':False}}
        with patch('forward_review.frozen',return_value=(rules,{'basis_as_of':'2026-10-16'})):
            return build_decision(plan,calendar,capsules,archive,cutoff)

    def test_preoutcome_decision_uses_explicit_pins_and_stays_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            record=self.build(*self.fixture(root))
            self.assertEqual(record['history_sessions'],1)
            self.assertIsNone(record['signals']['down4'])
            self.assertFalse(record['pit_qualified'])
            self.assertIsNone(record['outcomes'])

    def test_future_intraday_and_incomplete_capture_cutoffs_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            args=self.fixture(root)
            for cutoff in ('2026-11-17T14:00:00Z','2026-11-18T04:00:00Z','2026-11-18T12:59:59Z',
                           '2026-11-19T01:00:00Z'):
                with self.subTest(cutoff=cutoff), self.assertRaises(ValueError):
                    self.build(*args,cutoff=cutoff)

    def test_decision_uses_taipei_next_open_across_utc_date_boundary(self):
        with tempfile.TemporaryDirectory() as root:
            record=self.build(*self.fixture(root),cutoff='2026-11-18T16:30:00Z')
            self.assertEqual(record['session'],'2026-11-18')
            self.assertFalse(record['pit_qualified'])

    def test_missing_or_wrong_capsule_pin_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            plan,calendar,capsules,archive=self.fixture(root)
            for altered in ([],[{'directory':capsules[0]['directory']}],
                            [dict(capsules[0],seal_sha256='0'*64)]):
                with self.subTest(altered=altered), self.assertRaises(ValueError):
                    self.build(plan,calendar,altered,archive)

    def test_retrospective_registration_and_unresolved_calendar_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            plan,calendar,capsules,archive=self.fixture(root)
            late=dict(plan,registered_utc='2026-11-18T13:01:00+00:00')
            with self.assertRaises(ValueError):
                self.build(late,calendar,capsules,archive)
            calendar['days'][0]['state']='UNKNOWN'
            with self.assertRaises(ValueError):
                validate_calendar(calendar)

    def test_missing_calendar_day_and_wrong_market_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            _,calendar,_,_=self.fixture(root)
            calendar['market']='TPEx'
            with self.assertRaises(ValueError):
                validate_calendar(calendar)
            calendar['market']='TWSE';calendar['days'][-1]['date']='2026-11-20'
            with self.assertRaises(ValueError):
                validate_calendar(calendar)

    def test_changed_plan_or_archive_cannot_join_original_capture(self):
        with tempfile.TemporaryDirectory() as root:
            plan,calendar,capsules,archive=self.fixture(root)
            plan['horizons']=[1]
            with self.assertRaises(ValueError):
                self.build(plan,calendar,capsules,archive)
            with self.assertRaises(ValueError):
                make_plan('a'*64,'2026-11-13','2026-11-12T00:00:00Z')

    def test_pinned_plan_must_reference_its_exact_canonical_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'plan.json'
            p.write_bytes(b'{"a": 1}')
            with self.assertRaises(ValueError):
                pinned_json(p,sha256(p.read_bytes()).hexdigest())
            p.write_bytes(canonical({'a':1}))
            self.assertEqual(pinned_json(p,sha256(p.read_bytes()).hexdigest()),{'a':1})

    def test_versioned_decision_write_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'decision.json'
            write_new(path,{'version':1})
            with self.assertRaises(FileExistsError):
                write_new(path,{'version':2})
            self.assertEqual(path.read_bytes(),canonical({'version':1}))


if __name__ == '__main__':
    unittest.main()
