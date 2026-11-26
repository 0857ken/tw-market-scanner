"""Offline, descriptive-only T+1 reconciliation of a separately sealed day_drop3 record.

Neither the event ZIP nor the outcome capsule is a trusted-time PIT attestation.
This is not a backtest and does not join the 15-rule R3.6 frozen population.
"""
import argparse
from datetime import datetime, time
from decimal import Context, Decimal, localcontext
from email.utils import parsedate_to_datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import tempfile
from zipfile import ZipFile, BadZipFile

from capture_seal import DATA_FILES, MAX_FILE_BYTES, verify_local_seal
from evidence_schema import iso_date, unique_json, verify_source_endpoints
from pit_guard import TZ, as_utc, verify_receipt
from series import price_month


EXPECTED_ZIP_MEMBERS = (
    {'decision.json', 'verification_scope.json', 'capsule/SEAL.json'} |
    {'capsule/' + name for name in DATA_FILES}
)


def _valid_pin(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def pct(numerator, denominator):
    if denominator <= 0:
        raise ValueError('nonpositive index base')
    return str(((numerator / denominator - Decimal(1)) * 100).quantize(Decimal('0.000001')))


def _read_zip(path, label):
    path = Path(path)
    if not path.is_file():
        raise ValueError(label + ' ZIP missing')
    with path.open('rb') as archive:
        raw = archive.read(MAX_FILE_BYTES + 1)
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError(label + ' ZIP too large')
    return raw


def _check_members(archive, expected, label, *, max_total):
    infos = archive.infolist()
    if (len(infos) != len(expected) or {info.filename for info in infos} != expected or
            sum(info.file_size for info in infos) > max_total or
            any(info.file_size > MAX_FILE_BYTES or
                ((info.external_attr >> 16) & 0o170000) not in (0, 0o100000)
                for info in infos)):
        raise ValueError(label + ' ZIP has missing, extra or unsafe members')


def read_signal_archive(archive, approved_sha256):
    """Verify original ZIP bytes and contents; never rewrite the source archive."""
    return _read_signal_bytes(_read_zip(archive, 'event'), approved_sha256)


def _read_signal_bytes(raw, approved_sha256, *, exact_prices=False):
    if not _valid_pin(approved_sha256):
        raise ValueError('independent event ZIP pin is required')
    if sha256(raw).hexdigest() != approved_sha256:
        raise ValueError('original event ZIP SHA256 mismatch')
    try:
        with ZipFile(BytesIO(raw)) as z:
            _check_members(z, EXPECTED_ZIP_MEMBERS, 'event',
                           max_total=len(EXPECTED_ZIP_MEMBERS) * MAX_FILE_BYTES)
            decision = unique_json(z.read('decision.json'))
            scope = unique_json(z.read('verification_scope.json'))
            if (not isinstance(decision, dict) or not isinstance(scope, dict) or
                    decision.get('signal') != 'day_drop3' or
                    decision.get('observation_only') is not True or
                    decision.get('pit_qualified') is not False or
                    scope.get('frozen_rule_archive_bytes_verified') is not False or
                    not _valid_pin(decision.get('capsule_seal_sha256'))):
                raise ValueError('event is not an unqualified day_drop3 observation')
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp)
                for name in DATA_FILES:
                    (folder / name).write_bytes(z.read('capsule/' + name))
                (folder / 'SEAL.json').write_bytes(z.read('capsule/SEAL.json'))
                seal_check = verify_local_seal(folder, decision['capsule_seal_sha256'])
                status = unique_json((folder / 'status.json').read_bytes())
                if (decision.get('session') != status['session'] or
                        status.get('frozen_rule_archive_bytes_verified') is not False or
                        status.get('frozen_rule_members_verified') != 0 or
                        status.get('pit_qualified') is not False):
                    raise ValueError('event state and seal do not agree')
                session, next_session = status['session'], status['next_session']
                day = iso_date(session)
                next_day = iso_date(next_session)
                if (day >= next_day or
                        as_utc(status['completed_utc']) >=
                        datetime.combine(next_day, time(9), tzinfo=TZ)):
                    raise ValueError('event capture not before declared next open')
                prices = price_month((folder / 'ohlc.body').read_bytes(),
                                     session[:7], 'ohlc', exact=exact_prices)
                turns = price_month((folder / 'turnover.body').read_bytes(),
                                    session[:7], 'turnover', exact=exact_prices)
                prior = [d for d in prices if d < day and d in turns]
                if not prior:
                    raise ValueError('official two-source previous close unavailable')
                previous = max(prior)
                if prices[previous]['close'] != turns[previous]['close']:
                    raise ValueError('previous close two sources disagree')
                prior_close = Decimal(str(prices[previous]['close']))
                close = Decimal(str(prices[day]['close']))
                calculated = (close / prior_close - 1) * 100
                if (Decimal(str(decision.get('previous_close'))) != prior_close or
                        Decimal(str(decision.get('close'))) != close or
                        Decimal(str(decision.get('threshold_pct'))) != Decimal('-3') or
                        abs(Decimal(str(decision.get('change_pct'))) - calculated) > Decimal('0.0000001') or
                        (calculated <= -3) is not (decision.get('triggered') is True)):
                    raise ValueError('event decision does not agree with official evidence')
                if decision.get('triggered') is not True:
                    raise ValueError('no day_drop3 signal to evaluate')
                return {
                    'signal_date': session, 'next_session_claim': next_session,
                    'previous_session': previous.isoformat(),
                    'previous_close': str(prior_close), 'signal_close': str(close),
                    'signal_drop_pct': pct(close, prior_close),
                    'event_archive_sha256': approved_sha256,
                    'event_seal_sha256': seal_check['manifest_sha256'],
                    'claimed_frozen_archive_sha256': status['frozen_rule_archive_sha256'],
                }
    except (BadZipFile, KeyError, TypeError, ArithmeticError, ValueError, UnicodeDecodeError) as exc:
        raise ValueError('original signal evidence invalid: ' + str(exc)) from exc


def reconcile_t1(signal_zip, signal_sha256, outcome_capsule, outcome_seal_sha256):
    signal = read_signal_archive(signal_zip, signal_sha256)
    if not _valid_pin(outcome_seal_sha256):
        raise ValueError('separate outcome seal pin is required')
    outcome = Path(outcome_capsule)
    if not outcome.is_dir() or outcome.is_symlink():
        raise ValueError('outcome capsule missing or not a directory')
    validated = verify_local_seal(outcome, outcome_seal_sha256)
    status = unique_json((outcome / 'status.json').read_bytes())
    if (status.get('session') != signal['next_session_claim'] or
            status.get('frozen_rule_archive_sha256') !=
            signal['claimed_frozen_archive_sha256'] or
            status.get('frozen_rule_archive_bytes_verified') is not False or
            status.get('pit_qualified') is not False):
        raise ValueError('outcome session or unverified rule reference differs')
    day = iso_date(status['session'])
    closes = price_month((outcome / 'ohlc.body').read_bytes(),
                         status['session'][:7], 'ohlc')
    totals = price_month((outcome / 'turnover.body').read_bytes(),
                         status['session'][:7], 'turnover')
    if (day not in closes or day not in totals or
            closes[day]['close'] != totals[day]['close']):
        raise ValueError('outcome session absent or dual-source close mismatch')
    opening = Decimal(str(closes[day]['open']))
    closing = Decimal(str(closes[day]['close']))
    return {**_report(signal, opening, closing),
            'outcome_seal_sha256': validated['manifest_sha256']}


def _report(signal, opening, closing):
    return {
        'schema_version': 1,
        'status': 'DESCRIPTIVE_ONLY_PIT_BLOCKED',
        'pit_qualified': False,
        'external_time_attestation': 'NOT_ESTABLISHED',
        'calendar_authenticity_verified': False,
        'source_publication_verified': False,
        'rule_zip_bytes_verified': False,
        'outcome_horizon': 'FIRST_DECLARED_NEXT_SESSION_ONLY',
        'signal': 'day_drop3',
        **signal,
        'outcome_date': signal['next_session_claim'],
        'index_open': str(opening),
        'index_close': str(closing),
        'next_open_to_close_pct': pct(closing, opening),
        'signal_close_to_next_close_pct': pct(closing, Decimal(signal['signal_close'])),
        'remaining_horizons': [3, 5, 10, 20, 40, 60],
        'caution': ('Index point changes are observational, not executable strategy returns. '
                    'Official dates and publication timestamps require independent review. '
                    'This single-signal record cannot join the full 15-signal study.'),
    }


T1_REPORT_METADATA = {
    'session_basis': 'Consecutive rows in both official monthly trading reports',
    'archive_integrity': 'PASS; ZIP and five seal members plus seal hash matched',
    'independent_signed_timestamp': False,
    'original_frozen_zip_verified': False,
    'pit_qualified': False,
    'scope': 'Index observation only, no costs, not a tradable execution or strategy efficacy proof',
}
T1_RECEIPT_FIELDS = {
    'url', 'effective_url', 'status', 'http_date', 'started_at_utc',
    'completed_at_utc', 'sha256',
}


def _archive_source(archive, kind, day):
    raw = archive.read(kind + '.json')
    receipt = unique_json(archive.read(kind + '.receipt.json'))
    if (not isinstance(receipt, dict) or receipt.keys() != T1_RECEIPT_FIELDS or
            type(receipt['status']) is not int):
        raise ValueError('unexpected outcome HTTP receipt fields')
    verify_source_endpoints(day.isoformat(), kind, receipt['url'], receipt['effective_url'],
                            rwd_session_only=True)
    # This archive's receipt schema has a body hash but no recorded byte count.
    started, finished, _ = verify_receipt({**receipt, 'bytes': len(raw)}, raw)
    if started < datetime.combine(day, time(13, 30), tzinfo=TZ):
        raise ValueError('outcome HTTP request precedes session close')
    http_date = parsedate_to_datetime(receipt['http_date'])
    if (http_date.utcoffset() is None or
            not started.replace(microsecond=0) <= http_date <= finished):
        raise ValueError('outcome HTTP Date conflicts with receipt times')
    rows = price_month(raw, day.isoformat()[:7], kind,
                       response_date=day.strftime('%Y%m%d'), exact=True)
    if max(rows) != day:
        raise ValueError('outcome session missing or report contains later trade dates')
    return rows, {'receipt': receipt, 'body_bytes': len(raw)}


def _check_saved_result(saved, signal, opening, closing):
    signal_close = Decimal(signal['signal_close'])
    with localcontext(Context(prec=28)):
        numbers = {
            'signal_close': signal_close,
            'entry_index_open': opening,
            'exit_index_close': closing,
            'open_to_close_points': closing - opening,
            'open_to_close_pct': (closing / opening - 1) * 100,
            'signal_close_to_next_close_points': closing - signal_close,
            'signal_close_to_next_close_pct': (closing / signal_close - 1) * 100,
        }
    expected = {
        **T1_REPORT_METADATA,
        'signal_date': signal['signal_date'],
        'next_actual_session': signal['next_session_claim'],
        'original_zip_sha256': signal['event_archive_sha256'],
    }
    if (not isinstance(saved, dict) or saved.keys() != expected.keys() | numbers.keys() or
            any(type(saved[key]) is not type(value) or saved[key] != value
                for key, value in expected.items()) or
            any(not isinstance(saved[key], str) or Decimal(saved[key]) != value
                for key, value in numbers.items())):
        raise ValueError('saved T+1 result differs from verified scope, dates or calculations')


def _private_path(path):
    path = Path(path).resolve()
    # Check the tool's repository and any other local Git working tree.
    repo = Path(__file__).resolve().parents[2]
    if path.is_relative_to(repo) or any((parent / '.git').is_file() or
                                      (parent / '.git' / 'HEAD').is_file()
                                      for parent in path.parents):
        raise ValueError('private files must remain outside Git repositories')
    return path


def reconcile_t1_archive(outcome_zip, outcome_zip_sha256, signal_zip_sha256):
    """Check the original six-member archive in place, using two independent pins."""
    if not _valid_pin(outcome_zip_sha256) or not _valid_pin(signal_zip_sha256):
        raise ValueError('independent T+1 and event ZIP pins are required')
    raw = _read_zip(_private_path(outcome_zip), 'T+1')
    if sha256(raw).hexdigest() != outcome_zip_sha256:
        raise ValueError('original T+1 ZIP SHA256 mismatch')
    try:
        with ZipFile(BytesIO(raw)) as archive:
            embedded = [name for name in archive.namelist()
                        if re.fullmatch(r'original/REBOUND-PROSPECTIVE-\d{8}\.zip', name)]
            if len(embedded) != 1:
                raise ValueError('expected one original signal ZIP member')
            expected = {'result.json', 'ohlc.json', 'turnover.json',
                        'ohlc.receipt.json', 'turnover.receipt.json', embedded[0]}
            _check_members(archive, expected, 'T+1', max_total=MAX_FILE_BYTES)
            signal = _read_signal_bytes(archive.read(embedded[0]), signal_zip_sha256,
                                        exact_prices=True)
            signal_day = iso_date(signal['signal_date'])
            day = iso_date(signal['next_session_claim'])
            if embedded[0] != f'original/REBOUND-PROSPECTIVE-{signal_day:%Y%m%d}.zip':
                raise ValueError('embedded signal ZIP name disagrees with signal date')
            ohlc, ohlc_receipt = _archive_source(archive, 'ohlc', day)
            turnover, turnover_receipt = _archive_source(archive, 'turnover', day)
            # The saved result claims consecutive rows in both same-month reports.
            for rows in (ohlc, turnover):
                if signal_day not in rows or list(rows)[-2:] != [signal_day, day]:
                    raise ValueError('signal and outcome are not consecutive in both reports')
                if rows[signal_day]['close'] != Decimal(signal['signal_close']):
                    raise ValueError('outcome reports disagree with the original signal close')
            opening, closing = ohlc[day]['open'], ohlc[day]['close']
            if closing != turnover[day]['close']:
                raise ValueError('outcome dual-source close mismatch')
            _check_saved_result(unique_json(archive.read('result.json')),
                                signal, opening, closing)
    except (BadZipFile, KeyError, TypeError, AttributeError, ArithmeticError,
            ValueError, RuntimeError) as exc:
        raise ValueError('original T+1 evidence invalid: ' + str(exc)) from exc

    return {
        **_report(signal, opening, closing),
        'outcome_zip_sha256': outcome_zip_sha256,
        'full_15_signal_oos_qualified': False,
        'outcome_sources': {'ohlc': ohlc_receipt, 'turnover': turnover_receipt},
    }


def main():
    if sys.argv[1:2] == ['archive']:
        parser = argparse.ArgumentParser(description='Verify the original six-member T+1 ZIP offline.')
        parser.add_argument('outcome_zip', type=Path)
        parser.add_argument('outcome_zip_sha256')
        parser.add_argument('signal_zip_sha256')
        parser.add_argument('private_out', type=Path)
        args = parser.parse_args(sys.argv[2:])
        private_out = _private_path(args.private_out)
        report = reconcile_t1_archive(args.outcome_zip, args.outcome_zip_sha256,
                                      args.signal_zip_sha256)
        _write_report(private_out, report)
        return

    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='For the original six-member T+1 ZIP, use archive --help.')
    parser.add_argument('signal_zip', type=Path)
    parser.add_argument('signal_zip_sha256')
    parser.add_argument('outcome_capsule', type=Path)
    parser.add_argument('outcome_seal_sha256')
    parser.add_argument('private_out', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    if args.private_out.resolve().is_relative_to(repo):
        parser.error('output must remain outside public repository')
    report = reconcile_t1(args.signal_zip, args.signal_zip_sha256,
                          args.outcome_capsule, args.outcome_seal_sha256)
    _write_report(args.private_out, report)


def _write_report(private_out, report):
    with private_out.open('xb') as output:
        output.write((json.dumps(report, ensure_ascii=False, indent=2,
                                 sort_keys=True, allow_nan=False) + '\n').encode())
    print(json.dumps({'report_sha256': sha256(private_out.read_bytes()).hexdigest(),
                      'status': report['status'], 'pit_qualified': False}))


if __name__ == '__main__':
    main()
