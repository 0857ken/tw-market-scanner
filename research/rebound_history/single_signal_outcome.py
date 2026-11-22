"""Offline, descriptive-only T+1 reconciliation of a separately sealed day_drop3 record.

Neither the event ZIP nor the outcome capsule is a trusted-time PIT attestation.
This is not a backtest and does not join the 15-rule R3.6 frozen population.
"""
import argparse
from datetime import datetime, time
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
from zipfile import ZipFile, BadZipFile

from capture_seal import DATA_FILES, verify_local_seal
from evidence_schema import iso_date, unique_json
from pit_guard import TZ, as_utc
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


def read_signal_archive(archive, approved_sha256):
    """Verify original ZIP bytes and contents; never rewrite the source archive."""
    if not _valid_pin(approved_sha256):
        raise ValueError('independent event ZIP pin is required')
    path = Path(archive)
    if not path.is_file() or path.stat().st_size > 8_000_000:
        raise ValueError('event ZIP absent or too large')
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != approved_sha256:
        raise ValueError('original event ZIP SHA256 mismatch')
    try:
        with ZipFile(BytesIO(raw)) as z:
            infos = z.infolist()
            names = [item.filename for item in infos]
            if (len(names) != len(set(names)) or set(names) != EXPECTED_ZIP_MEMBERS
                    or any(info.file_size > 8_000_000 or
                           ((info.external_attr >> 16) & 0o170000) == 0o120000
                           for info in infos)):
                raise ValueError('event ZIP has missing, extra or unsafe members')
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
                                     session[:7], 'ohlc')
                turns = price_month((folder / 'turnover.body').read_bytes(),
                                    session[:7], 'turnover')
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
        'outcome_date': status['session'],
        'outcome_seal_sha256': validated['manifest_sha256'],
        'index_open': str(opening),
        'index_close': str(closing),
        'next_open_to_close_pct': pct(closing, opening),
        'signal_close_to_next_close_pct': pct(closing, Decimal(signal['signal_close'])),
        'remaining_horizons': [3, 5, 10, 20, 40, 60],
        'caution': ('Index point changes are observational, not executable strategy returns. '
                    'Official dates and publication timestamps require independent review. '
                    'This single-signal record cannot join the full 15-signal study.'),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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
    with args.private_out.open('xb') as output:
        output.write((json.dumps(report, ensure_ascii=False, indent=2,
                                 sort_keys=True, allow_nan=False) + '\n').encode())
    print(json.dumps({'report_sha256': sha256(args.private_out.read_bytes()).hexdigest(),
                      'status': report['status'], 'pit_qualified': False}))


if __name__ == '__main__':
    main()
