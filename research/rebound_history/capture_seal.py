"""Offline integrity seal for a manual prospective observation.

This verifies that local artifacts remain unchanged relative to their
manifest. It does NOT prove when they existed or confer PIT approval.
"""
import argparse
import json
import re
from hashlib import sha256
from pathlib import Path

from pit_guard import TZ, as_utc, prospective_gate, verify_receipt
from series import price_month
from evidence_schema import iso_date, twse_urls, unique_json

DATA_FILES = ('ohlc.body', 'ohlc.receipt.json',
              'turnover.body', 'turnover.receipt.json', 'status.json')
SEALED_FILES = set(DATA_FILES) | {'SEAL.json'}
MAX_FILE_BYTES = 8_000_000


def digest(body):
    return sha256(body).hexdigest()


_unique_json = unique_json

def _read_artifact(directory, name):
    if name not in DATA_FILES and name != 'SEAL.json':
        raise ValueError('unapproved capsule path')
    path = directory / name
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('capsule file missing, symlinked or over size limit: ' + name)
    return path.read_bytes()


def _validate_contents(directory):
    status = _unique_json(_read_artifact(directory, 'status.json'))
    if not isinstance(status, dict) or status.get('pit_qualified') is not False or status.get('status') != 'BLOCKED':
        raise ValueError('prospective capsule must remain PIT_BLOCKED')
    session, nxt = status.get('session'), status.get('next_session')
    if not isinstance(session, str) or not isinstance(nxt, str):
        raise ValueError('session identifiers missing')
    day, next_day = iso_date(session), iso_date(nxt)
    for flag in ('prospective_candidate', 'independent_timestamp_anchor',
                 'calendar_verified_independently', 'publication_timestamp_verified',
                 'signal_frozen_before_outcome', 'outcome_matured'):
        if status.get(flag) is not False:
            raise ValueError('local capture cannot certify ' + flag)
    rows = {}
    completed = []
    for kind in ('ohlc', 'turnover'):
        raw = _read_artifact(directory, kind + '.body')
        receipt = _unique_json(_read_artifact(directory, kind + '.receipt.json'))
        started, finish, legacy = verify_receipt(receipt, raw)
        if legacy:
            raise ValueError('legacy receipt not permitted')
        expected = twse_urls(session)[kind]
        if receipt['url'] != expected or receipt.get('effective_url') != expected:
            raise ValueError('receipt endpoint or query differs from capsule source')
        if started.astimezone(TZ).date() < day:
            raise ValueError('receipt predates data session')
        completed.append(finish)
        parsed = price_month(raw, session[:7], kind)
        if day not in parsed:
            raise ValueError('missing session in ' + kind)
        rows[kind] = parsed[day]
    if rows['ohlc']['close'] != rows['turnover']['close']:
        raise ValueError('two sources disagree')
    if status.get('index_close') != rows['ohlc']['close']:
        raise ValueError('stored index close mismatch')
    if status.get('turnover_ntd') != rows['turnover']['turnover']:
        raise ValueError('stored turnover mismatch')
    if not re.fullmatch('[a-f0-9]{64}', str(status.get('frozen_rule_archive_sha256'))):
        raise ValueError('missing frozen-rule reference hash')
    if status.get('frozen_rule_archive_bytes_verified') is not True and status.get('frozen_rule_members_verified') != 0:
        raise ValueError('inconsistent frozen-rule verification state')
    latest = max(completed).isoformat()
    if as_utc(status.get('completed_utc')) != as_utc(latest):
        raise ValueError('stored completion time differs from receipts')
    gate = prospective_gate(session, nxt, latest,
                            anchored=False, crosschecked=True,
                            frozen=status.get('frozen_rule_archive_bytes_verified') is True)
    if status.get('retrieval_before_next_open') != gate['retrieval_before_next_open']:
        raise ValueError('window decision mismatch')
    return status


def write_local_seal(directory):
    """Seal validated five-file capsule, without external time attestation."""
    directory = Path(directory)
    actual = {p.name for p in directory.iterdir()}
    if actual != set(DATA_FILES):
        raise ValueError('unexpected or missing files before seal')
    status = _validate_contents(directory)
    manifest = {
        'schema_version': 1,
        'session': status['session'],
        'next_session': status['next_session'],
        'status': 'LOCAL_INTEGRITY_ONLY_PIT_BLOCKED',
        'external_time_anchor': None,
        'files': {name: {'bytes': len(body := _read_artifact(directory, name)),
                         'sha256': digest(body)} for name in DATA_FILES},
    }
    data = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')
    (directory / 'SEAL.json').write_bytes(data)
    return digest(data)


def verify_local_seal(directory, expected_seal_sha=None):
    """Reject changed files; optionally compare independently saved seal hash."""
    directory = Path(directory)
    actual = {p.name for p in directory.iterdir()}
    if actual != SEALED_FILES:
        raise ValueError('unexpected or missing files in sealed capsule')
    seal_body = _read_artifact(directory, 'SEAL.json')
    seal_hash = digest(seal_body)
    if expected_seal_sha is not None and (
        not re.fullmatch('[a-f0-9]{64}', expected_seal_sha) or
        seal_hash != expected_seal_sha
    ):
        raise ValueError('sealed manifest hash mismatch')
    seal = _unique_json(seal_body)
    if (seal.get('schema_version') != 1 or
        seal.get('status') != 'LOCAL_INTEGRITY_ONLY_PIT_BLOCKED' or
        seal.get('external_time_anchor') is not None or
        set(seal.get('files', {})) != set(DATA_FILES)):
        raise ValueError('unapproved seal schema')
    for name in DATA_FILES:
        body = _read_artifact(directory, name)
        detail = seal['files'][name]
        if not isinstance(detail, dict) or detail != {
            'bytes': len(body), 'sha256': digest(body)
        }:
            raise ValueError('capsule tamper detected: ' + name)
    status = _validate_contents(directory)
    if seal.get('session') != status['session'] or seal.get('next_session') != status['next_session']:
        raise ValueError('seal session mismatch')
    return {'manifest_sha256': seal_hash, 'session': status['session'],
            'files': len(DATA_FILES), 'integrity': 'PASS',
            'pit_qualified': False, 'time_attestation': 'NOT_ESTABLISHED'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('private_capsule_dir', type=Path)
    p.add_argument('--seal-sha256', help='exact externally retained seal hash (optional)')
    args = p.parse_args()
    print(json.dumps(verify_local_seal(args.private_capsule_dir, args.seal_sha256),
                     indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
