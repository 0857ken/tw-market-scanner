"""Synthetic tests for the original six-member archive format."""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from evidence_schema import RWD_SOURCE_PATHS, official_source_url
from forward_capture import collect
from series import PRICE, TURN
from single_signal_outcome import MAX_FILE_BYTES, main, reconcile_t1_archive

SIGNAL = '2026-11-16'
OUTCOME = '2026-11-17'
FROZEN = 'a' * 64
ORIGINAL = 'original/REBOUND-PROSPECTIVE-20261116.zip'


def digest(body):
    return sha256(body).hexdigest()


def encode(obj):
    return json.dumps(obj).encode()


def source(kind, session):
    dates = ['115/11/13', '115/11/16', '115/11/17']
    prices = ['1000.00', '950.00', '975.00']
    width = 3 if session == OUTCOME else 2
    if kind == 'ohlc':
        rows = [[day, opening, '1030.00', '920.00', close]
                for day, opening, close in zip(dates, ['995.00', '990.00', '960.00'], prices)]
    else:
        rows = [[day, '2000', '2000000', '200', close, '5'] for day, close in zip(dates, prices)]
    return {'stat': 'OK', 'date': session.replace('-', ''),
            'fields': PRICE if kind == 'ohlc' else TURN, 'data': rows[:width]}


def receipt(kind, session, body):
    url = 'https://www.twse.com.tw' + RWD_SOURCE_PATHS[kind] + '?date=' + session.replace('-', '')
    url += '&response=json'
    return {'url': url, 'effective_url': url, 'status': 200,
            'http_date': datetime.fromisoformat(session).strftime('%a, %d %b %Y') + ' 06:00:01 GMT',
            'started_at_utc': session + 'T06:00:00+00:00',
            'completed_at_utc': session + 'T06:00:02+00:00', 'sha256': digest(body)}


def event_archive(root):
    def fetch(url):
        kind = 'ohlc' if 'MI_5MINS_HIST' in url else 'turnover'
        raw = encode(source(kind, SIGNAL))
        data = receipt(kind, SIGNAL, raw)
        return raw, {**data, 'url': url, 'effective_url': url, 'bytes': len(raw)}

    folder, gate = collect(root / 'event', SIGNAL, OUTCOME, FROZEN, fetch)
    event = root / 'event.zip'
    with ZipFile(event, 'w') as archive:
        archive.writestr('decision.json', encode({
            'signal': 'day_drop3', 'session': SIGNAL, 'previous_close': '1000.00',
            'close': '950.00', 'change_pct': '-5', 'threshold_pct': '-3', 'triggered': True,
            'observation_only': True, 'pit_qualified': False,
            'capsule_seal_sha256': gate['local_seal_sha256'],
        }))
        archive.writestr('verification_scope.json', encode({'frozen_rule_archive_bytes_verified': False}))
        for path in folder.iterdir():
            archive.write(path, 'capsule/' + path.name)
    return event.read_bytes()


class T1ArchiveTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.event = event_archive(self.root)
        self.event_pin = digest(self.event)
        self.members = {ORIGINAL: self.event}
        for kind in ('ohlc', 'turnover'):
            body = encode(source(kind, OUTCOME))
            self.members[kind + '.json'] = body
            self.members[kind + '.receipt.json'] = encode(receipt(kind, OUTCOME, body))
        self.result = {
            'session_basis': 'Consecutive rows in both official monthly trading reports',
            'archive_integrity': 'PASS; ZIP and five seal members plus seal hash matched',
            'scope': 'Index observation only, no costs, not a tradable execution or strategy efficacy proof',
            'independent_signed_timestamp': False, 'original_frozen_zip_verified': False,
            'pit_qualified': False, 'signal_date': SIGNAL, 'next_actual_session': OUTCOME,
            'original_zip_sha256': self.event_pin, 'signal_close': '950.00',
            'entry_index_open': '960.00', 'exit_index_close': '975.00',
            'open_to_close_points': '15.00', 'open_to_close_pct': '1.5625',
            'signal_close_to_next_close_points': '25.00',
            'signal_close_to_next_close_pct': '2.631578947368421052631578900',
        }
        self.members['result.json'] = encode(self.result)

    def archive(self, *, extra=None):
        path = self.root / 't1.zip'
        with ZipFile(path, 'w', compression=ZIP_DEFLATED) as archive:
            for member, body in self.members.items():
                archive.writestr(member, body)
            if extra is not None:
                archive.writestr(*extra)
        return path, digest(path.read_bytes())

    def verify(self, *, extra=None):
        path, pin = self.archive(extra=extra)
        return reconcile_t1_archive(path, pin, self.event_pin)

    def change_receipt(self, kind, **values):
        member = kind + '.receipt.json'
        self.members[member] = encode({**json.loads(self.members[member]), **values})

    def change_body(self, kind, obj):
        raw = encode(obj)
        self.members[kind + '.json'] = raw
        self.change_receipt(kind, sha256=digest(raw))

    def change_result(self, **values):
        self.members['result.json'] = encode({**self.result, **values})

    def test_original_archive_read_only_and_descriptive(self):
        path, pin = self.archive()
        with patch('socket.socket', side_effect=AssertionError('network disabled')):
            report = reconcile_t1_archive(path, pin, self.event_pin)
        self.assertEqual(digest(path.read_bytes()), pin)
        self.assertEqual(report['outcome_zip_sha256'], pin)
        self.assertEqual(report['event_archive_sha256'], self.event_pin)
        self.assertEqual(report['status'], 'DESCRIPTIVE_ONLY_PIT_BLOCKED')
        self.assertEqual(report['outcome_date'], OUTCOME)
        self.assertEqual(Decimal(report['index_open']), Decimal('960'))
        self.assertEqual(Decimal(report['index_close']), Decimal('975'))
        self.assertEqual(report['next_open_to_close_pct'], '1.562500')
        self.assertEqual(report['signal_close_to_next_close_pct'], '2.631579')
        self.assertEqual(report['claimed_frozen_archive_sha256'], FROZEN)
        self.assertFalse(report['pit_qualified'])
        self.assertFalse(report['full_15_signal_oos_qualified'])
        self.assertFalse(report['rule_zip_bytes_verified'])
        self.assertNotIn('outcome_seal_sha256', report)
        for kind, validated in report['outcome_sources'].items():
            self.assertEqual(validated['receipt'], json.loads(self.members[kind + '.receipt.json']))
            self.assertEqual(validated['body_bytes'], len(self.members[kind + '.json']))

    def test_pin_refers_to_complete_zip_even_if_members_unchanged(self):
        path, pin = self.archive()
        with path.open('ab') as archive:
            archive.write(b'trailing bytes')
        with self.assertRaisesRegex(ValueError, r'T\+1 ZIP SHA256 mismatch'):
            reconcile_t1_archive(path, pin, self.event_pin)

    def test_event_requires_its_own_pin(self):
        path, pin = self.archive()
        for event_pin in (None, pin):
            with self.subTest(event_pin=event_pin), self.assertRaisesRegex(ValueError, 'event ZIP'):
                reconcile_t1_archive(path, pin, event_pin)

    def test_changed_raw_body_rejected_even_with_new_outer_pin(self):
        self.members['ohlc.json'] += b' '
        with self.assertRaisesRegex(ValueError, 'raw SHA256'):
            self.verify()

    def test_edited_receipt_rejected_even_with_new_outer_pin(self):
        self.change_receipt('turnover', status=307)
        with self.assertRaisesRegex(ValueError, 'invalid status'):
            self.verify()

    def test_unknown_routes_and_queries_rejected_on_both_receipt_urls(self):
        good = json.loads(self.members['turnover.receipt.json'])
        url = good['url']
        for wrong in (url.replace('https:', 'http:'), url.replace('www.twse.com.tw', 'other.example'),
                      url.replace('www.twse.com.tw', 'www.twse.com.tw:443'),
                      url.replace('FMTQIK', 'MI_MARGN'), url.replace('/rwd/zh/afterTrading/', '/exchangeReport/'),
                      url.replace('20261117', '20261116'), url.replace('20261117', '20261101'),
                      url.replace('20261117', '20261017'), url + '&page=1', url + '&response=json',
                      url + '#', url + '\t'):
            for field in ('url', 'effective_url'):
                with self.subTest(url=wrong, field=field):
                    self.members['turnover.receipt.json'] = encode({**good, field: wrong})
                    with self.assertRaisesRegex(ValueError, 'endpoint or query'):
                        self.verify()

    def test_http_date_and_retrieval_order_must_agree(self):
        good = json.loads(self.members['ohlc.receipt.json'])
        for changes, error in (
            ({'started_at_utc': OUTCOME + 'T06:00:03+00:00'}, 'time order'),
            ({'started_at_utc': OUTCOME + 'T04:00:00+00:00'}, 'session close'),
            ({'http_date': 'Tue, 17 Nov 2026 06:01:00 GMT'}, 'HTTP Date'),
        ):
            with self.subTest(changes=changes):
                self.members['ohlc.receipt.json'] = encode({**good, **changes})
                with self.assertRaisesRegex(ValueError, error):
                    self.verify()

    def test_duplicate_member_rejected(self):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with self.assertRaisesRegex(ValueError, 'unsafe members'):
                self.verify(extra=('ohlc.json', self.members['ohlc.json']))

    def test_extra_path_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unsafe members'):
            self.verify(extra=('../ohlc.json', self.members['ohlc.json']))

    def test_symlink_member_rejected(self):
        body = self.members.pop('ohlc.json')
        member = ZipInfo('ohlc.json')
        member.create_system = 3
        member.external_attr = 0o120777 << 16
        with self.assertRaisesRegex(ValueError, 'unsafe members'):
            self.verify(extra=(member, body))

    def test_uncompressed_total_bounded(self):
        self.members['ohlc.json'] = b' ' * MAX_FILE_BYTES
        with self.assertRaisesRegex(ValueError, 'unsafe members'):
            self.verify()

    def test_missing_report_rejected(self):
        del self.members['turnover.json']
        with self.assertRaisesRegex(ValueError, 'missing'):
            self.verify()

    def test_wrong_response_day_schema_and_values_rejected(self):
        for field, value, error in (
            ('date', '20261116', 'wrong month'),
            ('fields', PRICE[::-1], 'wrong month'),
            ('stat', 'Error', 'wrong month'),
            ('data', [['115/11/17', '3', '1', '2', '3']], 'invalid OHLC bounds'),
            ('data', [['115/11/017', '1', '4', '1', '3']], 'unexpected or duplicate trade date'),
        ):
            with self.subTest(field=field, value=value):
                self.change_body('ohlc', {**source('ohlc', OUTCOME), field: value})
                with self.assertRaisesRegex(ValueError, error):
                    self.verify()

    def test_two_outcome_closes_must_match_exactly(self):
        obj = source('turnover', OUTCOME)
        obj['data'][-1][4] = '975.00000000000001'
        self.change_body('turnover', obj)
        with self.assertRaisesRegex(ValueError, 'dual-source close mismatch'):
            self.verify()

    def test_outcome_history_must_agree_with_sealed_signal_close(self):
        obj = source('ohlc', OUTCOME)
        obj['data'][-2][-1] = '951.00'
        self.change_body('ohlc', obj)
        with self.assertRaisesRegex(ValueError, 'original signal close'):
            self.verify()

    def test_dates_must_be_consecutive_in_each_source(self):
        obj = source('ohlc', OUTCOME)
        obj['data'].pop(-2)
        self.change_body('ohlc', obj)
        with self.assertRaisesRegex(ValueError, 'not consecutive'):
            self.verify()

    def test_future_source_row_rejected(self):
        obj = source('ohlc', OUTCOME)
        obj['data'].append(['115/11/18', *obj['data'][-1][1:]])
        self.change_body('ohlc', obj)
        with self.assertRaisesRegex(ValueError, 'later trade dates'):
            self.verify()

    def test_saved_date_and_both_calculations_recomputed(self):
        for change in ({'next_actual_session': '2026-11-18'}, {'signal_date': '2026-11-13'},
                       {'entry_index_open': '959.00'}, {'exit_index_close': '974.00'},
                       {'signal_close_to_next_close_pct': '1.5625'}, {'open_to_close_pct': '0'},
                       {'open_to_close_points': '1.5625'}, {'signal_close_to_next_close_points': None}):
            with self.subTest(change=change):
                self.change_result(**change)
                with self.assertRaisesRegex(ValueError, r'saved T\+1 result differs'):
                    self.verify()

    def test_result_cannot_upgrade_pit_time_or_rule_verification(self):
        for key in ('pit_qualified', 'independent_signed_timestamp', 'original_frozen_zip_verified'):
            with self.subTest(key=key):
                self.change_result(**{key: True})
                with self.assertRaisesRegex(ValueError, 'verified scope'):
                    self.verify()

    def test_frozen_reference_cannot_be_replaced_by_outcome_result(self):
        for change in ({'frozen_rule_archive_sha256': 'b' * 64}, {'original_zip_sha256': 'b' * 64}):
            with self.subTest(change=change):
                self.change_result(**change)
                with self.assertRaisesRegex(ValueError, 'verified scope'):
                    self.verify()

    def test_embedded_event_cannot_be_changed_under_original_pin(self):
        self.members[ORIGINAL] += b' '
        with self.assertRaisesRegex(ValueError, 'original event ZIP SHA256 mismatch'):
            self.verify()

    def test_resealed_event_with_swapped_frozen_reference_fails_original_pin(self):
        updated = BytesIO()
        with ZipFile(BytesIO(self.event)) as original, ZipFile(updated, 'w') as edited:
            members = {name: original.read(name) for name in original.namelist()}
            status = json.loads(members['capsule/status.json'])
            status['frozen_rule_archive_sha256'] = 'b' * 64
            status_bytes = encode(status)
            seal = json.loads(members['capsule/SEAL.json'])
            seal['files']['status.json'] = {'bytes': len(status_bytes), 'sha256': digest(status_bytes)}
            seal_bytes = encode(seal)
            decision = json.loads(members['decision.json'])
            decision['capsule_seal_sha256'] = digest(seal_bytes)
            members.update({'capsule/status.json': status_bytes, 'capsule/SEAL.json': seal_bytes,
                            'decision.json': encode(decision)})
            for name, body in members.items():
                edited.writestr(name, body)
        self.members[ORIGINAL] = updated.getvalue()
        self.change_result(original_zip_sha256=digest(self.members[ORIGINAL]))
        with self.assertRaisesRegex(ValueError, 'original event ZIP SHA256 mismatch'):
            self.verify()

    def test_rwd_turnover_allowlist_preserves_legacy_route(self):
        url = json.loads(self.members['turnover.receipt.json'])['url']
        self.assertTrue(official_source_url(OUTCOME, 'turnover', url))
        legacy = url.replace('/rwd/zh/afterTrading/', '/exchangeReport/')
        self.assertFalse(official_source_url(OUTCOME, 'turnover', legacy))
        self.assertTrue(official_source_url(OUTCOME, 'turnover', legacy.replace('20261117', '20261101')))

    def test_cli_creates_private_report_exclusively(self):
        path, pin = self.archive()
        output = self.root / 'report.json'
        with patch('sys.argv', ['single_signal_outcome.py', 'archive', str(path),
                                pin, self.event_pin, str(output)]), patch('builtins.print'):
            main()
            saved = output.read_bytes()
            with self.assertRaises(FileExistsError):
                main()
        self.assertEqual(output.read_bytes(), saved)
        self.assertEqual(json.loads(saved)['outcome_date'], OUTCOME)

    def test_input_in_a_git_tree_is_rejected(self):
        path, pin = self.archive()
        (self.root / '.git').mkdir()
        (self.root / '.git' / 'HEAD').touch()
        with self.assertRaisesRegex(ValueError, 'outside Git repositories'):
            reconcile_t1_archive(path, pin, self.event_pin)


if __name__ == '__main__':
    unittest.main()
