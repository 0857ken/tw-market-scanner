"""Synthetic only: tamper, deletion, seal pin and PIT-block invariants."""
import json
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

from capture_seal import verify_local_seal
from forward_capture import collect


def synthetic_fetch(url):
    price='MI_5MINS_HIST' in url
    columns = (['日期','開盤指數','最高指數','最低指數','收盤指數'] if price else
               ['日期','成交股數','成交金額','成交筆數','發行量加權股價指數','漲跌點數'])
    row = (['115/11/18','100','110','90','105'] if price else
           ['115/11/18','1000','900000','500','105','5'])
    body=json.dumps({'stat':'OK','date':'20261118','fields':columns,'data':[row]}).encode()
    stamp='2026-11-18T13:00:00+00:00'
    return body,{
        'status':200,'url':url,'effective_url':url,
        'started_at_utc':stamp,'completed_at_utc':stamp,
        'bytes':len(body),'sha256':sha256(body).hexdigest(),
    }


class CaptureSealTests(unittest.TestCase):
    def make(self, root):
        return collect(root,'2026-11-18','2026-11-19','a'*64,synthetic_fetch)

    def test_local_capsule_seal_passes_but_pit_stays_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            folder,gate=self.make(root)
            self.assertEqual(gate['status'],'BLOCKED')
            self.assertFalse(gate['pit_qualified'])
            self.assertTrue((folder/'SEAL.json').is_file())
            result=verify_local_seal(folder,gate['local_seal_sha256'])
            self.assertEqual(result['integrity'],'PASS')
            self.assertEqual(result['files'],5)
            self.assertFalse(result['pit_qualified'])
            self.assertEqual(result['time_attestation'],'NOT_ESTABLISHED')
            self.assertFalse(any(p.name.startswith('.pending') for p in folder.parent.iterdir()))

    def test_tampered_body_detected(self):
        with tempfile.TemporaryDirectory() as root:
            folder,gate=self.make(root)
            (folder/'ohlc.body').write_bytes(b'{}')
            with self.assertRaises(ValueError):
                verify_local_seal(folder,gate['local_seal_sha256'])

    def test_tampered_status_detected(self):
        with tempfile.TemporaryDirectory() as root:
            folder,gate=self.make(root)
            p=folder/'status.json'
            status=json.loads(p.read_text())
            status['pit_qualified']=True
            p.write_text(json.dumps(status))
            with self.assertRaises(ValueError):
                verify_local_seal(folder)

    def test_missing_receipt_or_extra_file_detected(self):
        with tempfile.TemporaryDirectory() as root:
            folder,gate=self.make(root)
            receipt=folder/'turnover.receipt.json'
            receipt.unlink()
            with self.assertRaises(ValueError):
                verify_local_seal(folder,gate['local_seal_sha256'])
        with tempfile.TemporaryDirectory() as root:
            folder,gate=self.make(root)
            (folder/'extra.txt').write_text('injected')
            with self.assertRaises(ValueError):
                verify_local_seal(folder)

    def test_wrong_external_pin_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder,gate=self.make(root)
            with self.assertRaises(ValueError):
                verify_local_seal(folder,'0'*64)

    def test_self_signed_local_manifest_is_not_external_anchor(self):
        with tempfile.TemporaryDirectory() as root:
            folder,gate=self.make(root)
            seal=json.loads((folder/'SEAL.json').read_text())
            self.assertEqual(seal['status'],'LOCAL_INTEGRITY_ONLY_PIT_BLOCKED')
            self.assertIsNone(seal['external_time_anchor'])
            self.assertFalse(gate['prospective_candidate'])


if __name__=='__main__':
    unittest.main()
