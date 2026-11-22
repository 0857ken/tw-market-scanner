"""Offline synthetic tests only; no retrospective market data or performance claims."""
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
import tempfile
import unittest
from zipfile import ZipFile

from forward_capture import collect
from single_signal_outcome import read_signal_archive, reconcile_t1


FROZEN = 'a' * 64
SIGNAL = '2026-11-20'
NEXT = '2026-11-23'


def fetch(session):
    def make(url):
        price = 'MI_5MINS_HIST' in url
        if session == SIGNAL:
            if price:
                rows = [
                    ['115/11/19', '39,000', '39,100', '38,400', '38,426.89'],
                    ['115/11/20', '37,646.13', '37,646.13', '35,738.68', '36,033.29']]
            else:
                rows = [
                    ['115/11/19', '1000', '1000000', '100', '38,426.89', '-100'],
                    ['115/11/20', '1000', '1000000', '100', '36,033.29', '-2393.60']]
            stamp = '2026-11-21T13:05:00+00:00'
        else:
            if price:
                rows = [['115/11/23', '36,500', '37,100', '36,300', '37,000']]
            else:
                rows = [['115/11/23', '1000', '1000000', '100', '37,000', '966.71']]
            stamp = '2026-11-23T06:00:00+00:00'
        fields = (['日期', '開盤指數', '最高指數', '最低指數', '收盤指數'] if price else
                  ['日期', '成交股數', '成交金額', '成交筆數', '發行量加權股價指數', '漲跌點數'])
        body = json.dumps({'stat':'OK', 'date':session.replace('-', ''), 'fields':fields,
                           'data':rows}).encode()
        return body, {'status':200, 'url':url, 'effective_url':url,
                      'started_at_utc':stamp, 'completed_at_utc':stamp,
                      'bytes':len(body), 'sha256':sha256(body).hexdigest()}
    return make


def fixture(root):
    root = Path(root)
    signal_dir, signal_gate = collect(root / 'signal', SIGNAL, NEXT, FROZEN, fetch(SIGNAL))
    outcome_dir, outcome_gate = collect(root / 'outcome', NEXT, '2026-11-24',
                                        FROZEN, fetch(NEXT))
    decision = {
        'signal':'day_drop3', 'session':SIGNAL,
        'previous_close':'38426.89', 'close':'36033.29',
        'threshold_pct':'-3',
        'change_pct':str((Decimal('36033.29')/Decimal('38426.89')-1)*100),
        'triggered':True, 'observation_only':True,
        'pit_qualified':False,
        'capsule_seal_sha256':signal_gate['local_seal_sha256'],
    }
    scope = {'frozen_rule_archive_bytes_verified':False}
    archive = root / 'single-signal.zip'
    with ZipFile(archive,'w') as z:
        z.writestr('decision.json',json.dumps(decision))
        z.writestr('verification_scope.json',json.dumps(scope))
        for file in signal_dir.iterdir():
            z.write(file, 'capsule/'+file.name)
    return archive, sha256(archive.read_bytes()).hexdigest(), outcome_dir, outcome_gate['local_seal_sha256']


class DayDropOutcomeTests(unittest.TestCase):
    def test_t1_dual_source_reconciled_but_never_pit(self):
        with tempfile.TemporaryDirectory() as t:
            a,p,o,s=fixture(t)
            r=reconcile_t1(a,p,o,s)
            self.assertEqual(r['status'],'DESCRIPTIVE_ONLY_PIT_BLOCKED')
            self.assertFalse(r['pit_qualified'])
            self.assertEqual(r['outcome_date'],NEXT)
            self.assertEqual(r['previous_session'],'2026-11-19')
            self.assertEqual(r['signal_close'],'36033.29')
            self.assertEqual(r['next_open_to_close_pct'],'1.369863')
            self.assertIs(r['rule_zip_bytes_verified'],False)
            self.assertEqual(r['remaining_horizons'],[3,5,10,20,40,60])

    def test_event_and_outcome_require_separately_retained_pins(self):
        with tempfile.TemporaryDirectory() as t:
            a,p,o,s=fixture(t)
            with self.assertRaises(ValueError):
                reconcile_t1(a,'0'*64,o,s)
            with self.assertRaises(ValueError):
                reconcile_t1(a,p,o,'0'*64)
            with self.assertRaises(ValueError):
                reconcile_t1(a,p,o,None)

    def test_future_data_absence_is_not_a_zero_return(self):
        with tempfile.TemporaryDirectory() as t:
            a,p,o,s=fixture(t)
            with self.assertRaises(ValueError):
                reconcile_t1(a,p,Path(t)/'not-yet-collected',s)

    def test_original_event_decision_checked_beyond_matching_zip_sha(self):
        with tempfile.TemporaryDirectory() as t:
            a,p,o,s=fixture(t)
            bad=Path(t)/'tampered-event.zip'
            with ZipFile(a) as src, ZipFile(bad,'w') as dst:
                for name in src.namelist():
                    value=src.read(name)
                    if name=='decision.json':
                        j=json.loads(value);j['previous_close']='40000'
                        value=json.dumps(j).encode()
                    dst.writestr(name,value)
            new_pin=sha256(bad.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'event decision'):
                reconcile_t1(bad,new_pin,o,s)

    def test_changed_future_market_body_cannot_use_old_seal(self):
        with tempfile.TemporaryDirectory() as t:
            a,p,o,s=fixture(t)
            (o/'ohlc.body').write_bytes(b'{}')
            with self.assertRaises(ValueError):
                reconcile_t1(a,p,o,s)

    def test_wrong_outcome_session_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            a,p,o,s=fixture(t)
            future,gate=collect(Path(t)/'future','2026-11-24','2026-11-25',FROZEN,
                                fetch(NEXT))
            with self.assertRaises(ValueError):
                reconcile_t1(a,p,future,gate['local_seal_sha256'])

    def test_do_not_allow_full_frozen_rule_claim_without_original_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            a,p,o,s=fixture(t)
            bad=Path(t)/'falsely-qualified.zip'
            with ZipFile(a) as src, ZipFile(bad,'w') as dst:
                for name in src.namelist():
                    value=src.read(name)
                    if name=='verification_scope.json':
                        value=json.dumps({'frozen_rule_archive_bytes_verified':True}).encode()
                    dst.writestr(name,value)
            with self.assertRaises(ValueError):
                read_signal_archive(bad,sha256(bad.read_bytes()).hexdigest())


if __name__=='__main__':
    unittest.main()
