"""Archive-only validation. Reuse the frozen processor; no source requests."""
import copy
from datetime import datetime
import json
from pathlib import Path
from .publication_contract import canonical, require

SOURCE_FIELDS = set(('name url asOf status fetchStatus fetchedAt lastAttemptAt license licenseEvidence '
                     'licenseStatus sha256 rowCount snapshotAction lastResponseSha256 reason error httpStatus priceBasis').split())
QUALITY_FIELDS = set('generatedAt asOf mode stockCount quoteDays sources coverage freshCritical warnings'.split())
ATTEMPT_FIELDS = set(('attemptedAt modules attemptedModules historicalRequests scheduleEnabled sources '
                      'status expectedTWSE coverage').split())


def fields(value, allowed, label):
    require(isinstance(value, dict) and set(value) <= set(allowed), 'Unknown archive fields: '+label)


def source_map(sources, label):
    from .acquisition_state import ROWS
    fields(sources, set(ROWS) | {'credit', 'institutional'}, label)
    for module, source in sources.items():
        fields(source, SOURCE_FIELDS, label+'.'+module)
        require(all(not isinstance(v, (dict, list)) for v in source.values()), 'Nested source metadata not approved')


def metadata(files, payload):
    """Cover non-raw files too; JSON schema's permissive extras cannot grant rights."""
    from .daily import quality
    source_map(payload['sources'], 'market.sources')
    state = json.loads(files['source-state.json'])
    fields(state, {'sources'}, 'source-state')
    source_map(state['sources'], 'source-state.sources')
    expected_coverage = quality(payload)
    for name, allowed in [('quality.json', QUALITY_FIELDS), ('daily-attempt.json', ATTEMPT_FIELDS)]:
        if name not in files:
            continue
        value = json.loads(files[name]); fields(value, allowed, name)
        if 'sources' in value:
            source_map(value['sources'], name+'.sources')
        if 'coverage' in value:
            fields(value['coverage'], expected_coverage, name+'.coverage')
            for market, record in value['coverage'].items():
                fields(record, expected_coverage[market], name+'.coverage.'+market)
                require(all(not isinstance(v, (dict, list)) for v in record.values()), 'Nested coverage metadata not approved')
        for key, item in value.items():
            if key in ('sources', 'coverage'):
                continue
            if key in ('warnings', 'modules', 'attemptedModules'):
                require(isinstance(item, list) and all(isinstance(x, str) for x in item), 'Metadata string list required')
                if key != 'warnings':
                    from .daily import MODULES
                    require(set(item) <= set(MODULES), 'Unapproved attempted module')
            else:
                require(not isinstance(item, (dict, list)), 'Nested archive metadata not approved')
        if name == 'daily-attempt.json':
            require(value.get('historicalRequests') == 0 and value.get('scheduleEnabled') is False,
                    'Archive cannot authorize historical requests or scheduling')


def replay(payload, root):
    """Rebuild ALL observations, including null/missing rows, from parsed snapshots.

    Internal market is an assertion to compare, never a seed for stock/history data.
    Source metadata and the recorded generation time are explicit non-price inputs.
    """
    from .run import build, snapshots
    from .research import integrate
    root = Path(root)
    calendars = snapshots(root, 'calendar')
    require(calendars, 'Missing calendar dependency for independent replay')
    actual = integrate(build(root, copy.deepcopy(payload['sources']), calendars[-1]['rows'], [],
                             datetime.fromisoformat(payload['generatedAt'])), root)
    require(canonical(actual) == canonical(payload), 'Complete acquisition replay differs from parsed sources')
    return actual
