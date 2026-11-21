"""Self-contained parsed acquisition closure. No HTTP bodies or executable input."""
import json
from pathlib import Path
import re
from .common import ROOT
from .publication_contract import canonical, sha, require, read_zip, zip_bytes, file_inventory, verify_inventory
from .daily_release import verify_snapshot_links
from .schema import validate

ROWS = {
    'calendar': 'date closed name',
    'companies': 'date symbol name sector sectorCode issuedShares listedOn',
    'tpexCompanies': 'date symbol name sector sectorCode issuedShares listedOn',
    'quotes': 'date symbol name close volumeShares changeAmount status',
    'tpexQuotes': 'date symbol name close volumeShares changeAmount status',
    'tpexInstitutional': 'date symbol foreignShares trustShares dealerShares totalShares',
    'tpexEvents': 'date symbol kind status cashDividend previousClose referencePrice',
    'index': 'date close changePct', 'indexHistory': 'date close volumeShares',
    'futures': 'contract date dealer foreign scope trust unit',
    'margin': 'date symbol balanceShares limitShares lotSize sourceUnit usagePct usagePctBasis',
}
CODE_PATHS = ('pipeline/schema.py', 'pipeline/parsers.py', 'pipeline/research.py', 'pipeline/release_check.py',
              'pipeline/observation_release.py', 'frontend/src/logic.js', 'frontend/src/research.js')
POLICIES = ('daily-release.json', 'source-publication.json', 'observation-release.json', 'research-approvals.json', 'credit-rule.json')


def policy_files():
    return {n: (ROOT/'config'/n).read_bytes() for n in POLICIES}


def code_inventory():
    return {n: sha((ROOT/n).read_bytes()) for n in CODE_PATHS}


def allowed(name):
    return name in ('market.json', 'source-state.json', 'quality.json', 'daily-attempt.json', 'inventory.json') or bool(
        re.fullmatch(r'raw/[A-Za-z]+_\d{4}-\d{2}-\d{2}\.json', name))


def validate_files(files):
    require({'market.json', 'source-state.json'} <= files.keys(), 'Missing acquisition state')
    payload = json.loads(files['market.json']); validate(payload)
    from .acquisition_validation import metadata, replay
    metadata(files, payload)
    require(json.loads(files['source-state.json'])['sources'] == payload['sources'], 'Source-state differs from internal market')
    require(not payload['creditHistory'] and payload['creditRule']['status'] == 'pending', 'Unapproved credit closure')
    policy = json.loads(policy_files()['source-publication.json'])['modules']
    snapshots = {}
    for name, body in files.items():
        require(allowed(name), 'Unapproved acquisition dependency')
        if not name.startswith('raw/'):
            continue
        snap = json.loads(body); module = snap['module']
        snapshots[(module, snap['date'])] = snap
        require(module in ROWS and policy[module]['status'] == 'verified-open-data', 'Unapproved snapshot module')
        require(name == 'raw/' + module + '_' + snap['date'] + '.json', 'Snapshot filename binding')
        require(set(snap) == {'date', 'fetchedAt', 'license', 'module', 'rows', 'sha256', 'url'}, 'Unapproved snapshot metadata')
        require(all(set(r) <= set(ROWS[module].split()) for r in snap['rows']), 'Unapproved parsed fields, including contacts')
        require(all(not isinstance(v, (dict, list)) for r in snap['rows'] for v in r.values()),
                'Nested parsed fields not approved')
        from .run import SOURCES
        from .current_csv import URL
        official = 'https://www.tpex.org.tw/openapi/v1/tpex_exright_daily' if module == 'tpexEvents' else SOURCES[module][1]
        urls = {official} | ({URL} if module == 'quotes' else set())
        if module == 'margin':
            # Existing licensed parsed dependency only; this does not issue a request.
            urls.add(official+'?date='+snap['date'].replace('-', '')+'&selectType=ALL&response=json')
        require(snap['url'] in urls, 'Snapshot URL mismatch')
    for module, source in payload['sources'].items():
        if module in ROWS and source.get('asOf') and source.get('sha256'):
            snapshot = snapshots.get((module, source['asOf']))
            require(snapshot and snapshot['sha256'] == source['sha256'] and snapshot['url'] == source['url'],
                    'Missing source dependency: '+module)
    prices = {(m, d): {r['symbol']: r for r in s['rows']} for (m,d),s in snapshots.items() if m in ('quotes','tpexQuotes')}
    for stock in payload['stocks']:
        module = 'quotes' if stock['market'] == 'TWSE' else 'tpexQuotes'
        for row in stock['history']:
            if row['close'] is None:
                continue
            snap = snapshots.get((module, row['date'])); source = prices.get((module,row['date']), {}).get(stock['symbol'])
            require(snap and source and row['sourceVersion'] == snap['sha256'] and
                    all(row.get(k) == source.get(k) for k in ('close','volumeShares','changeAmount')), 'Historical parsed dependency mismatch')
    # Existing linkage validator operates only on the provided self-contained files.
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        for n, b in files.items():
            p = Path(t)/n; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
        verify_snapshot_links(payload, t)
        replay(payload, t)
    return payload


def pack(data_dir):
    root = Path(data_dir)
    require(not any((root/n).exists() and any((root/n).iterdir()) for n in ('history', 'adjustments', 'lifecycles')),
            'Unapproved dependency closure cannot be silently excluded')
    files = {}
    for p in root.rglob('*'):
        require(not p.is_symlink(), 'Acquisition symlink')
        if p.is_file():
            name = p.relative_to(root).as_posix()
            require(allowed(name) or re.fullmatch(r'(runs/[^/]+|stage[0-9a-z-]+)\.json', name), 'Unknown input dependency cannot be silently excluded')
            if allowed(name) and p.name != 'inventory.json':
                files[name] = p.read_bytes()
    validate_files(files)
    records = file_inventory(files)
    frozen_code = code_inventory()
    license_policy_sha = sha(policy_files()['source-publication.json'])
    for n in records:
        if n.startswith('raw/'):
            s = json.loads(files[n])
            records[n].update(module=s['module'], date=s['date'], sourceUrl=s['url'],
                              responseSha256=s['sha256'], parsedSnapshotFileSha256=sha(files[n]), responseBodyArchived=False,
                              licensePolicySha256=license_policy_sha, parserSha256=frozen_code['pipeline/parsers.py'])
    files['inventory.json'] = canonical({'schemaVersion': 1, 'files': records,
        'excludedNonInputs': ['runs/*', 'stage*-*.json'], 'codeInventory': frozen_code})
    body = zip_bytes(files)
    unpack(body)
    return body


def unpack(body, destination=None):
    files = read_zip(body, allowed)
    inventory = json.loads(files.pop('inventory.json'))
    from .acquisition_validation import fields
    fields(inventory, {'schemaVersion', 'files', 'excludedNonInputs', 'codeInventory'}, 'inventory')
    require(inventory['schemaVersion'] == 1 and inventory['excludedNonInputs'] == ['runs/*','stage*-*.json'], 'Unknown acquisition inventory contract')
    records = inventory['files']
    verify_inventory(files, {n: {k: r[k] for k in ('bytes', 'sha256')} for n, r in records.items()})
    frozen_code = code_inventory()
    license_policy_sha = sha(policy_files()['source-publication.json'])
    require(inventory['codeInventory'] == frozen_code, 'Processor/parser contract changed; explicit migration needed')
    for n, r in records.items():
        fields(r, {'bytes', 'sha256'} | ({'module', 'date', 'sourceUrl', 'responseSha256',
               'parsedSnapshotFileSha256', 'responseBodyArchived', 'licensePolicySha256', 'parserSha256'}
               if n.startswith('raw/') else set()), 'inventory record')
        if n.startswith('raw/'):
            s = json.loads(files[n])
            require(r['parsedSnapshotFileSha256'] == sha(files[n]) and r['responseSha256'] == s['sha256'] and
                    r['responseBodyArchived'] is False and r['module'] == s['module'] and r['date'] == s['date'] and
                    r['sourceUrl'] == s['url'] and r['licensePolicySha256'] == license_policy_sha and
                    r['parserSha256'] == frozen_code['pipeline/parsers.py'], 'Parsed/response provenance mismatch')
    validate_files(files)
    if destination is not None:
        root = Path(destination); root.mkdir(parents=True, exist_ok=False)
        for n, b in files.items():
            p = root/n; p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(b)
    return files
