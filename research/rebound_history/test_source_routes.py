"""Fail-closed TWSE route acceptance, including approved RWD redirect compatibility."""
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from evidence_schema import official_source_url, twse_urls, verify_source_endpoints
from forward_capture import collect
from capture_seal import verify_local_seal
from forward_review import make_plan
from test_capture_seal import synthetic_fetch

SESSION = '2026-11-18'
LEGACY = 'https://www.twse.com.tw/indicesReport/MI_5MINS_HIST?response=json&date=20261101'
RWD = 'https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date=20261118&response=json'
TURNOVER = 'https://www.twse.com.tw/exchangeReport/FMTQIK?response=json&date=20261101'


class SourceRouteTests(unittest.TestCase):
    def test_reviewed_routes_accept_legacy_and_rwd_only(self):
        for kind, url in [('ohlc', LEGACY), ('ohlc', RWD),
                          ('ohlc', RWD.replace('20261118', '20261101')),
                          ('turnover', TURNOVER),
                          ('ohlc', RWD.replace('date=20261118&response=json',
                                               'response=json&date=20261118'))]:
            with self.subTest(url=url):
                self.assertTrue(official_source_url(SESSION,kind,url))
        verify_source_endpoints(SESSION,'ohlc',LEGACY,RWD)
        verify_source_endpoints(SESSION,'ohlc',RWD,RWD)

    def test_reject_unknown_hosts_paths_mismatched_dates_and_query_injection(self):
        bad = [
            RWD.replace('https://','http://'),
            RWD.replace('www.twse.com.tw','www.twse.com.tw.attacker.org'),
            RWD.replace('www.twse.com.tw','www.twse.com.tw:443'),
            RWD.replace('www.twse.com.tw','bad@www.twse.com.tw'),
            RWD.replace('/rwd/zh/TAIEX/','/rwd/zh/afterTrading/'),
            RWD.replace('20261118','20261018'),
            RWD.replace('20261118','20261119'),
            RWD.replace('20261118','20261117'),
            RWD.replace('20261118','2026111'),
            RWD.replace('MI_5MINS_HIST','MI_5MINS_HIST/extra'),
            RWD.replace('response=json','response=html'),
            RWD+'&date=20261118',
            RWD+'&page=1',
            RWD+'#fragment',
            RWD.replace('MI_5MINS_HIST','%4dI_5MINS_HIST'),
            RWD.replace('date=20261118','date=20261118%26response%3Djson'),
        ]
        for url in bad:
            with self.subTest(url=url):
                self.assertFalse(official_source_url(SESSION,'ohlc',url))
                with self.assertRaises(ValueError):
                    verify_source_endpoints(SESSION,'ohlc',LEGACY,url)
        self.assertFalse(official_source_url(SESSION,'turnover',RWD))
        self.assertFalse(official_source_url(SESSION,'ohlc',TURNOVER))
        self.assertFalse(official_source_url(SESSION,'turnover',TURNOVER.replace('20261101','20261118')))

    def test_official_rwd_redirect_accepted_and_sealed_with_original_receipt(self):
        def old_redirects(url):
            body,receipt=synthetic_fetch(url)
            if 'MI_5MINS_HIST' in url:
                receipt['effective_url']=RWD
            return body,receipt
        with tempfile.TemporaryDirectory() as root:
            folder,gate=collect(root,SESSION,'2026-11-19','a'*64,old_redirects)
            receipt=json.loads((folder/'ohlc.receipt.json').read_text())
            self.assertEqual(receipt['url'],LEGACY)
            self.assertEqual(receipt['effective_url'],RWD)
            result=verify_local_seal(folder,gate['local_seal_sha256'])
            self.assertEqual(result['integrity'],'PASS')
            self.assertFalse(result['pit_qualified'])

    def test_direct_rwd_capture_accepted_and_unknown_redirect_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            routes=twse_urls(SESSION)
            routes['ohlc']=RWD
            with patch('forward_capture.source_urls',return_value=routes):
                folder,gate=collect(root,SESSION,'2026-11-19','a'*64,synthetic_fetch)
            self.assertEqual(verify_local_seal(folder,gate['local_seal_sha256'])['integrity'],'PASS')
            self.assertFalse(gate['pit_qualified'])
        with tempfile.TemporaryDirectory() as root:
            def hijack(url):
                body,receipt=synthetic_fetch(url)
                receipt['effective_url']='https://www.twse.com.tw/rwd/zh/TAIEX/other?date=20261118&response=json'
                return body,receipt
            with self.assertRaises(ValueError):
                collect(root,SESSION,'2026-11-19','a'*64,hijack)
            self.assertFalse(list(Path(root).rglob('SEAL.json')))

    def test_different_frozen_archive_never_joins_existing_capture(self):
        from test_evidence_hardening import DecisionTests
        with tempfile.TemporaryDirectory() as root:
            fixture=DecisionTests()
            plan,calendar,capsules,archive=fixture.fixture(root)
            different=Path(root)/'different.zip'
            different.write_bytes(archive.read_bytes())
            with ZipFile(different,'a') as z:
                z.writestr('unrelated-legal-file.txt','new archive version')
            other_pin=sha256(different.read_bytes()).hexdigest()
            self.assertNotEqual(plan['frozen_archive_sha256'],other_pin)
            plan=make_plan(other_pin,plan['first_session'],plan['registered_utc'])
            with self.assertRaisesRegex(ValueError,'different frozen-rule'):
                fixture.build(plan,calendar,capsules,different)


if __name__ == '__main__':
    unittest.main()
