"""Offline synthetic fixtures for prospective TWSE two-source capture."""
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from forward_capture import collect, source_urls


class ProspectiveCaptureTests(unittest.TestCase):
    def fake(self,mismatch=False):
        def fetch(url):
            price='MI_5MINS_HIST' in url
            fields=(['日期','開盤指數','最高指數','最低指數','收盤指數'] if price else
                    ['日期','成交股數','成交金額','成交筆數','發行量加權股價指數','漲跌點數'])
            row=(['115/11/18','100','110','90','105'] if price else
                 ['115/11/18','1000','900000','500','106' if mismatch else '105','5'])
            body=json.dumps({'stat':'OK','date':'20261118','fields':fields,'data':[row]}).encode()
            stamp='2026-11-18T13:00:00+00:00'
            return body,{'status':200,'url':url,'effective_url':url,
                         'started_at_utc':stamp,'completed_at_utc':stamp,
                         'bytes':len(body),'sha256':sha256(body).hexdigest()}
        return fetch

    def test_capture_requires_dual_close_and_never_pit_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            directory,report=collect(temp,'2026-11-18','2026-11-19','a'*64,self.fake())
            self.assertEqual(report['index_close'],105)
            self.assertTrue(report['retrieval_before_next_open'])
            self.assertFalse(report['pit_qualified'])
            self.assertFalse(report['frozen_rule_archive_bytes_verified'])
            self.assertEqual(report['status'],'BLOCKED')
            self.assertTrue((directory/'ohlc.body').exists())
            self.assertTrue((directory/'turnover.receipt.json').exists())
            self.assertTrue((directory/'status.json').exists())

    def test_bad_cross_source_close_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                collect(temp,'2026-11-18','2026-11-19','a'*64,self.fake(True))
            self.assertEqual(list(Path(temp).rglob('status.json')),[])

    def test_frozen_rule_bytes_checked_before_capture(self):
        with tempfile.TemporaryDirectory() as temp:
            archive=Path(temp)/'frozen.zip'
            archive.write_bytes(b'approved-archive-fixture')
            digest=sha256(archive.read_bytes()).hexdigest()
            path,report=collect(temp,'2026-11-18','2026-11-19',digest,
                                self.fake(),frozen_archive=archive)
            self.assertTrue(report['frozen_rule_archive_bytes_verified'])
            self.assertFalse(report['pit_qualified'])
            with self.assertRaises(ValueError):
                collect(temp,'2026-11-18','2026-11-19','a'*64,
                        self.fake(),frozen_archive=archive)

    def test_invalid_date_and_sha_rejected(self):
        with self.assertRaises(ValueError):
            source_urls('2026-11-13')
        with self.assertRaises(ValueError):
            collect('/tmp','2026-11-18','2026-11-19','invalid',self.fake())
        with self.assertRaises(ValueError):
            collect('/tmp','2026-11-18','2026-11-18','a'*64,self.fake())


if __name__=='__main__':
    unittest.main()
