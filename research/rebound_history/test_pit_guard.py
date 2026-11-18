"""No-network regression tests for PIT source evidence."""
import json
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from pit_guard import audit_zip, prospective_gate, verify_receipt, classify


class PITGuardTests(unittest.TestCase):
    def receipt(self):
        stamp='2026-11-16T10:00:00+00:00'
        url='https://www.twse.com.tw/exchangeReport/FMTQIK?date=20261101'
        return {'status':200,'url':url,'effective_url':url,
                'sha256':sha256(b'{}').hexdigest(),'bytes':2,
                'started_at_utc':stamp,'completed_at_utc':stamp}

    def test_preopen_is_only_candidate_never_pit_pass(self):
        r=prospective_gate('2026-11-18','2026-11-19','2026-11-18T13:00:00Z',True,True,True)
        self.assertTrue(r['prospective_candidate'])
        self.assertFalse(r['pit_qualified'])

    def test_next_open_and_unanchored_fail_closed(self):
        late=prospective_gate('2026-11-18','2026-11-19','2026-11-19T02:00:00Z',True,True,True)
        self.assertFalse(late['prospective_candidate'])
        for flags in ((False,True,True),(True,False,True),(True,True,False)):
            r=prospective_gate('2026-11-18','2026-11-19','2026-11-18T13:00:00Z',*flags)
            self.assertEqual(r['status'],'BLOCKED')

    def test_pre_freeze_rejected(self):
        with self.assertRaises(ValueError):
            prospective_gate('2026-11-13','2026-11-16','2026-11-15T00:00:00Z',True,True,True)

    def test_raw_sha_redirect_and_time_validation(self):
        receipt=self.receipt()
        verify_receipt(receipt,b'{}')
        for changed in (
            dict(receipt,sha256='0'*64),
            dict(receipt,url='https://bad.example/path'),
            dict(receipt,completed_at_utc='2026-11-16T09:00:00Z'),
            dict(receipt,effective_url='https://bad.example/path'),
        ):
            with self.assertRaises(ValueError):
                verify_receipt(changed,b'{}')

    def test_legacy_incomplete_not_trusted(self):
        receipt=self.receipt()
        del receipt['started_at_utc']
        del receipt['effective_url']
        with self.assertRaises(ValueError):
            verify_receipt(receipt,b'{}')
        started,finished,legacy=verify_receipt(receipt,b'{}',allow_legacy=True)
        self.assertIsNone(started)
        self.assertTrue(legacy)

    def test_monthly_report_never_daily_pit(self):
        value=classify('ohlc','2026-11',datetime(2026,11,16,tzinfo=timezone.utc),
                       [date(2026,11,13)])
        self.assertEqual(value,'NOT_SESSION_SCOPED')

    def test_offline_zip_digest_and_status(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'private.zip'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('raw/turnover/2026-11.body',b'{}')
                z.writestr('raw/turnover/2026-11.json',json.dumps(self.receipt()))
                z.writestr('results/input_series.csv','date\n2026-11-13\n')
            summary,rows=audit_zip(path,sha256(path.read_bytes()).hexdigest())
            self.assertEqual(summary['receipt_n'],1)
            self.assertEqual(summary['pit_qualified_n'],0)
            self.assertEqual(rows[0]['timing_classification'],'NOT_SESSION_SCOPED')
            with self.assertRaises(ValueError):
                audit_zip(path,'0'*64)


if __name__=='__main__':
    unittest.main()
