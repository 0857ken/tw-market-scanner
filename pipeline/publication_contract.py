"""Versioned archive contracts. Pure validation; never grants remote authority."""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

REPOSITORY = '0857ken/tw-market-scanner'
REPOSITORY_ID = 1412557806
STATE_BRANCH = 'scanner-release-state'
ENVIRONMENT = 'github-pages'
ASSETS = ('site.zip', 'acquisition-state.zip', 'supporting-material.zip', 'candidate-receipt.json')


class ContractError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ContractError(message)


def canonical(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':'), allow_nan=False) + '\n').encode()


def sha(body):
    return hashlib.sha256(body).hexdigest()


def digest(value, length=64):
    require(isinstance(value, str) and re.fullmatch('[a-f0-9]{%d}' % length, value), 'Exact digest required')
    return value


def positive(value, zero=False):
    require(type(value) is int and value >= (0 if zero else 1), 'Invalid integer identity')
    return value


def safe_path(name):
    p = PurePosixPath(name)
    return (isinstance(name, str) and bool(name) and not name.startswith('/') and
            '\\' not in name and str(p) == name and not any(x in ('..', '.') for x in p.parts))


def read_zip(body, allowed, *, compressed=64*1024*1024, expanded=256*1024*1024, entries=10000):
    require(len(body) <= compressed, 'ZIP compressed budget exceeded')
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        infos = z.infolist()
        names = [i.filename for i in infos]
        require(len(names) <= entries and len(names) == len(set(names)), 'ZIP duplicate/entry budget')
        require(sum(i.file_size for i in infos) <= expanded, 'ZIP expanded budget exceeded')
        for i in infos:
            # Legacy Actions ZIPs contain an explicit assets/ directory.
            name = i.filename[:-1] if i.is_dir() else i.filename
            mode = i.external_attr >> 16
            require(safe_path(name) and not stat.S_ISLNK(mode) and not i.flag_bits & 1,
                    'ZIP unsafe path, symlink or encryption')
            require(not mode or stat.S_IFMT(mode) in (0, stat.S_IFREG, stat.S_IFDIR), 'ZIP special file')
            require((i.is_dir() and name == 'assets') or (not i.is_dir() and allowed(name)), 'ZIP file not allowed')
        return {i.filename: z.read(i) for i in infos if not i.is_dir()}


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, body in sorted(files.items()):
            require(safe_path(name), 'Unsafe ZIP output')
            entry = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            z.writestr(entry, body)
    return buffer.getvalue()


def file_inventory(files):
    return {n: {'bytes': len(b), 'sha256': sha(b)} for n, b in sorted(files.items())}


def verify_inventory(files, inventory):
    require(file_inventory(files) == inventory, 'File inventory differs')


def site_files(body):
    from .daily_release import safe_name
    files = read_zip(body, safe_name, compressed=16*1024*1024, expanded=12*1024*1024)
    require({'index.html', '.nojekyll', 'market.json', 'release-manifest.json'} <= files.keys(), 'Incomplete site')
    manifest = json.loads(files['release-manifest.json'])
    require(set(files) == set(manifest['assets']) | {'release-manifest.json'}, 'Site inventory mismatch')
    require(all(sha(files[n]) == d for n, d in manifest['assets'].items()), 'Site asset mismatch')
    require(sha(files['market.json']) == manifest['publishedDataSha256'], 'Public data digest mismatch')
    require(manifest['profile'] == 'observation-only' and manifest['strategyComplete'] is False and
            manifest['deploymentAuthorized'] is False, 'Frozen candidate authority')
    return files


def operation_key(baseline, site_sha, target, kind='publish'):
    return sha(canonical({'repositoryId': REPOSITORY_ID, 'environment': ENVIRONMENT, 'kind': kind,
                          'generation': baseline['generation'], 'baselineZip': baseline['publishedZipSha256'],
                          'targetDate': target, 'candidateZip': site_sha}))


def validate_receipt(r):
    require(r['schemaVersion'] == 2 and r['repository'] == REPOSITORY and
            r['repositoryId'] == REPOSITORY_ID and r['environment'] == ENVIRONMENT and
            r['profile'] == 'observation-only', 'Receipt identity mismatch')
    require(r['kind'] in ('publish', 'legacy-import'), 'Unsupported candidate kind')
    require(r['authority'] == {'deploymentAuthorized': False, 'rollbackAuthorized': False}, 'Receipt grants authority')
    for k in ('siteZipSha256', 'acquisitionZipSha256', 'supportZipSha256', 'internalMarketSha256',
              'publicMarketSha256', 'manifestSha256', 'sourceIdentitySha256','originalReceiptSha256'):
        digest(r['output'][k])
    for d in r['policies'].values():
        digest(d)
    for d in r['codeInventory'].values():
        digest(d)
    digest(r['frontend']['seedZipSha256']); digest(r['frontend']['frontendPinSha256'])
    for d in r['frontend']['assets'].values():
        digest(d)
    positive(r['provenance']['runAttempt'])
    require(r['provenance']['inputSchemaVersion'] == 2 and r['provenance']['parserSha256'] == r['codeInventory']['pipeline/parsers.py'] and
            r['provenance']['schemaSha256'] == r['codeInventory']['pipeline/schema.py'], 'Input schema/parser binding mismatch')
    require(str(r['provenance']['sourceRunId']).isdigit(), 'Exact source Run ID required')
    digest(r['provenance']['processorCommit'], 40)
    require(r['provenance']['workflowPath'] in ('.github/workflows/update-data.yml', '.github/workflows/ci.yml'), 'Wrong upstream workflow')
    require(r['provenance']['status'] == 'completed' and r['provenance']['conclusion'] == 'success' and
            r['provenance']['codeSha'] == r['provenance']['processorCommit'], 'Upstream not successful/same code')
    require(r['slot']['timezone'] == 'Asia/Taipei', 'Original slot timezone required')
    from datetime import date, datetime
    date.fromisoformat(r['slot']['targetDate'])
    require(r['slot']['event'] and r['slot']['slot'], 'Original event/slot required')
    for k in ('deadline', 'startedAt'):
        require(datetime.fromisoformat(r['slot'][k]).utcoffset() is not None, 'Aware slot time required')
    require(datetime.fromisoformat(r['slot']['startedAt']) <= datetime.fromisoformat(r['slot']['deadline']), 'Expired original slot')
    if r['kind'] == 'publish':
        b = r['baseline']
        positive(b['generation'], zero=True)
        for k in ('publishedZipSha256', 'receiptSha256', 'acquisitionZipSha256'):
            digest(b[k])
        digest(b['stateHead'], 40)
        require(r['gate']['decision'] == 'candidate' and r['slot']['targetDate'] == r['gate']['target'], 'Noncandidate receipt')
    else:
        require(r['baseline'] is None and r['gate']['decision'] == 'legacy-import', 'Legacy cannot invent a baseline')
    return r


def state_path(path):
    return safe_path(path) and (path == 'state.json' or path == 'README.md' or bool(re.fullmatch(
        r'(transactions/[a-f0-9]{64}/[0-9]+|successes/g[0-9]+|receipts/[a-f0-9]{64}|indexes/[a-f0-9]{64}|live-evidence/[a-f0-9]{64}|approvals/[a-f0-9]{64}|retired/[a-f0-9]{64})\.json', path)))


def validate_state(s):
    require(s['schemaVersion'] == 1 and s['repositoryId'] == REPOSITORY_ID, 'Wrong state identity')
    positive(s['stateRevision'], zero=True); positive(s['fenceCounter'], zero=True)
    require(type(s['control']['halted']) is bool, 'Missing halted state')
    p = s['successfulPointer']
    positive(p['generation'], zero=True)
    for k in ('publishedZipSha256', 'receiptSha256', 'acquisitionZipSha256', 'packageIndexSha256', 'successRecordSha256'):
        digest(p[k])
    require(len(canonical(s)) <= 64*1024, 'State budget exceeded')
    return s


def require_remote(capability=None):
    # A later reviewed 4C-2C/2D authority integration must replace this closed gate.
    # CLI booleans, payload flags and offline test approvals cannot arm real writes.
    raise PermissionError('Remote mutation NOT_AUTHORIZED in Stage 4C-2B')
