"""Local rehearsal ledger only. No production baseline/state/Pages integration."""
import re
from pathlib import Path
from .common import read_json
from .candidate_io import atomic_bytes, atomic_json, exclusive_lock
from .daily_release import sha, verify_bundle
from .daily_policy import load as load_policy


def commit(store, archive, receipt, seed, expected_current=None):
    load_policy()
    store = Path(store)
    with exclusive_lock(store / '.lock'):
        current = read_json(store / 'current.json', {})
        verify_bundle(archive, receipt, seed)
        digest = receipt['zipSha256']
        destination = store / (digest + '.zip')
        if current.get('zipSha256') == digest:
            if (any(current.get(k) != v for k, v in receipt.items()) or
                    expected_current not in (digest, current.get('previousZipSha256'))):
                raise ValueError('Conflicting repeated release')
            verify_bundle(destination, current, seed)
            return current
        if current.get('zipSha256') != expected_current:
            raise ValueError('Stale release worker; CAS rejected')
        if destination.exists():
            if sha(destination.read_bytes()) != digest:
                raise ValueError('Stored immutable bundle corrupted; explicit quarantine required')
        else:
            atomic_bytes(destination, Path(archive).read_bytes(), immutable=True)
        ledger = store / (digest + '.json')
        entry = {**receipt, 'previousZipSha256': expected_current, 'production': False}
        if ledger.exists() and read_json(ledger) != entry:
            raise ValueError('Immutable ledger conflict')
        if not ledger.exists():
            atomic_json(ledger, entry, immutable=True)
        atomic_json(store / 'current.json', entry)
        return entry


def restore(store, prior_sha, seed, expected_current):
    """Caller supplies the PRIOR version's seed, not the newest frontend seed."""
    load_policy()
    if not isinstance(prior_sha, str) or not re.fullmatch('[a-f0-9]{64}', prior_sha):
        raise ValueError('Exact prior ZIP SHA required')
    store = Path(store)
    with exclusive_lock(store / '.lock'):
        receipt = read_json(store / (prior_sha + '.json'))
        if not receipt or receipt.get('zipSha256') != prior_sha:
            raise ValueError('No verified previous complete version')
        verify_bundle(store / (prior_sha + '.zip'), receipt, seed)
        current = read_json(store / 'current.json', {})
        if current == receipt:
            return receipt
        if current.get('zipSha256') != expected_current:
            raise ValueError('Stale restore CAS rejected')
        atomic_json(store / 'current.json', receipt)
        return receipt
