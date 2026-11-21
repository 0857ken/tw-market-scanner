"""Offline plan and pre-outcome decision records. No external attestation or PIT grant."""
import argparse
from datetime import datetime, time
from hashlib import sha256
import json
from pathlib import Path
import re

from capture_seal import verify_local_seal
from evidence_schema import iso_date, unique_json
from forward_capture import verify_frozen_archive
from pit_guard import FROZEN_END, TZ, as_utc
from series import frozen, price_month
from study import HORIZONS


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':'), allow_nan=False) + '\n').encode()


def pinned_json(path, expected):
    body = Path(path).read_bytes()
    if not re.fullmatch('[a-f0-9]{64}', str(expected)) or sha256(body).hexdigest() != expected:
        raise ValueError('independently supplied expected hash mismatch')
    record = unique_json(body)
    if body != canonical(record):
        raise ValueError('reviewed JSON must use the canonical serialization')
    return record


def make_plan(archive_sha, first_session, registered_utc):
    if not re.fullmatch('[a-f0-9]{64}', str(archive_sha)):
        raise ValueError('invalid frozen archive digest')
    first = iso_date(first_session)
    registered = as_utc(registered_utc)
    if first <= FROZEN_END or registered.astimezone(TZ).date() > first:
        raise ValueError('plan must precede prospective observation')
    return {'schema_version': 1, 'instrument': 'TAIEX',
            'first_session': first_session, 'registered_utc': registered.isoformat(),
            'frozen_archive_sha256': archive_sha, 'horizons': list(HORIZONS),
            'selection': 'ALL_REVIEWED_SESSIONS_NO_THRESHOLD_SELECTION',
            'outcome_basis': 'EVENT_CLOSE_TO_FUTURE_SESSION_CLOSE',
            'pit_qualified': False, 'external_time_attestation': 'NOT_ESTABLISHED'}


def validate_calendar(record):
    if record.get('schema_version') != 1 or record.get('market') != 'TWSE':
        raise ValueError('wrong calendar schema or market')
    seen = []
    for row in record.get('days', []):
        day = iso_date(row['date'])
        if row.get('state') not in ('TRADING_SESSION', 'CLOSED'):
            raise ValueError('calendar has unresolved day')
        if not re.fullmatch('[a-f0-9]{64}', str(row.get('source_sha256'))):
            raise ValueError('calendar row lacks reference evidence hash')
        seen.append(day)
    if not seen or seen != sorted(set(seen)):
        raise ValueError('calendar dates must be nonempty, unique and sorted')
    for a, b in zip(seen, seen[1:]):
        if (b-a).days != 1:
            raise ValueError('calendar must account for every civil date')
    return [row['date'] for row in record['days'] if row['state'] == 'TRADING_SESSION']


def build_decision(plan, calendar, capsules, archive, decision_utc):
    if plan != make_plan(plan.get('frozen_archive_sha256'),
                         plan.get('first_session'), plan.get('registered_utc')):
        raise ValueError('plan differs from fixed study specification')
    sessions = validate_calendar(calendar)
    cutoff = as_utc(decision_utc)
    if as_utc(plan['registered_utc']) > cutoff:
        raise ValueError('decision precedes plan')
    verify_frozen_archive(archive, plan['frozen_archive_sha256'])
    rules, manifest = frozen(Path(archive), plan['frozen_archive_sha256'])
    rows, pins = [], []
    for item in capsules:
        folder = Path(item['directory'])
        expected = item.get('seal_sha256')
        if not re.fullmatch('[a-f0-9]{64}', str(expected)):
            raise ValueError('each capsule needs a separately retained hash')
        check = verify_local_seal(folder, expected)
        status = unique_json((folder/'status.json').read_bytes())
        session = check['session']
        if iso_date(session) > cutoff.astimezone(TZ).date():
            raise ValueError('future data date at decision cutoff')
        close = datetime.combine(iso_date(session), time(13, 30), tzinfo=TZ)
        if cutoff < close:
            raise ValueError('same-session intraday decision')
        if as_utc(status['completed_utc']) > cutoff:
            raise ValueError('capture finished after decision')
        if status['frozen_rule_archive_sha256'] != plan['frozen_archive_sha256']:
            raise ValueError('capture uses a different frozen-rule reference')
        ohlc = price_month((folder/'ohlc.body').read_bytes(), session[:7], 'ohlc')
        turnover = price_month((folder/'turnover.body').read_bytes(), session[:7], 'turnover')
        day = iso_date(session)
        position = sessions.index(session) if session in sessions else -1
        if position < 0 or position + 1 >= len(sessions) or status['next_session'] != sessions[position+1]:
            raise ValueError('next session differs from reviewed calendar')
        if status.get('retrieval_before_next_open') is not True:
            raise ValueError('capture is outside the prospective observation window')
        if not rows:
            for kind in ('ohlc', 'turnover'):
                receipt = unique_json((folder/(kind+'.receipt.json')).read_bytes())
                if as_utc(plan['registered_utc']) > as_utc(receipt['started_at_utc']):
                    raise ValueError('plan registered after first capture began')
        rows.append({'date': session, **ohlc[day], 'turnover': turnover[day]['turnover'],
                     'margin_100m': None, 'foreign_net_100m': None,
                     'foreign_futures_net_short': None})
        pins.append({'session': session, 'seal_sha256': expected})
    if not rows or [r['date'] for r in rows] != sorted({r['date'] for r in rows}):
        raise ValueError('capsules must be unique and in session order')
    first, last = rows[0]['date'], rows[-1]['date']
    expected = [s for s in sessions if plan['first_session'] <= s <= last]
    if first != plan['first_session'] or [r['date'] for r in rows] != expected:
        raise ValueError('missing approved session or disallowed retrospective warmup')
    if not calendar['days'][0]['date'] <= first <= last <= calendar['days'][-1]['date']:
        raise ValueError('calendar does not cover observations')
    if as_utc(plan['registered_utc']) > datetime.combine(iso_date(first), time(13, 30), tzinfo=TZ):
        raise ValueError('plan registered after first signal close')
    next_day = iso_date(sessions[sessions.index(last)+1])
    if cutoff >= datetime.combine(next_day, time(9), tzinfo=TZ):
        raise ValueError('decision must precede next-session opening')
    enriched = rules['indicators'](rows)
    signals = rules['signals'](enriched, len(enriched)-1)
    if len(rows) < 5:
        signals['down4'] = None
    return {'schema_version': 1, 'session': last, 'decision_utc': cutoff.isoformat(),
            'plan_sha256': sha256(canonical(plan)).hexdigest(),
            'calendar_sha256': sha256(canonical(calendar)).hexdigest(),
            'frozen_archive_sha256': plan['frozen_archive_sha256'],
            'frozen_basis_as_of': manifest['basis_as_of'], 'capsules': pins,
            'history_sessions': len(rows), 'signals': signals,
            'horizons': list(HORIZONS), 'outcomes': None,
            'source_publication_verified': False, 'calendar_authenticity_verified': False,
            'time_attestation': 'NOT_ESTABLISHED', 'pit_qualified': False,
            'status': 'PRE_OUTCOME_LOCAL_RECORD_REVIEW_REQUIRED'}


def write_new(path, record):
    """Exclusive file create, so revisions require a separately named version."""
    with Path(path).open('xb') as output:
        output.write(canonical(record))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plan', type=Path)
    parser.add_argument('plan_sha256')
    parser.add_argument('calendar', type=Path)
    parser.add_argument('calendar_sha256')
    parser.add_argument('capsule_list', type=Path)
    parser.add_argument('capsule_list_sha256')
    parser.add_argument('frozen_archive', type=Path)
    parser.add_argument('decision_utc')
    parser.add_argument('out', type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    if args.out.resolve().is_relative_to(repo):
        parser.error('private decision must be outside public repository')
    plan = pinned_json(args.plan, args.plan_sha256)
    calendar = pinned_json(args.calendar, args.calendar_sha256)
    capsules = pinned_json(args.capsule_list, args.capsule_list_sha256)
    record = build_decision(plan, calendar, capsules, args.frozen_archive, args.decision_utc)
    write_new(args.out, record)
    print(json.dumps({'sha256': sha256(args.out.read_bytes()).hexdigest(),
                      'status': record['status'], 'pit_qualified': False}))


if __name__ == '__main__':
    main()
