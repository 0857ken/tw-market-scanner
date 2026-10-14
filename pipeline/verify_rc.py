"""Offline immutable RC ZIP verification. Never extracts, fetches or publishes."""
import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

from .schema import validate


def verify(path, zip_sha256, commit, data_sha256, as_of):
    if not re.fullmatch('[a-f0-9]{64}', zip_sha256) or not re.fullmatch('[a-f0-9]{64}', data_sha256) or not re.fullmatch('[a-f0-9]{40}', commit):
        raise ValueError('Exact approved SHA values required')
    body = Path(path).read_bytes()
    if len(body) > 16*1024*1024 or hashlib.sha256(body).hexdigest() != zip_sha256:
        raise ValueError('RC ZIP SHA mismatch or size exceeded')
    with zipfile.ZipFile(path) as archive:
        if any(i.is_dir() and i.filename != 'assets/' for i in archive.infolist()):
            raise ValueError('Unapproved ZIP directory')
        entries = [i for i in archive.infolist() if not i.is_dir()]
        names = [i.filename for i in entries]
        allowed = lambda n: n in ('index.html','market.json','release-manifest.json','.nojekyll') or bool(re.fullmatch(r'assets/[A-Za-z0-9_.-]+\.(?:js|css)', n))
        if len(names) != len(set(names)) or not all(allowed(n) for n in names):
            raise ValueError('Duplicate or unapproved ZIP resources')
        if sum(i.file_size for i in archive.infolist()) > 8*1024*1024 or any(stat.S_ISLNK(i.external_attr >> 16) for i in entries):
            raise ValueError('Unsafe archive size or symlink')
        manifest = json.loads(archive.read('release-manifest.json'))
        if manifest.get('candidateCommit') != commit or manifest.get('publishedDataSha256') != data_sha256 or manifest.get('asOf') != as_of:
            raise ValueError('Commit, data SHA or approved date mismatch')
        if manifest.get('profile') != 'observation-only' or manifest.get('strategyComplete') is not False or manifest.get('deploymentAuthorized') is not False or manifest.get('localTreeDirty') is not False:
            raise ValueError('Clean observation candidate required; no strategy/deployment permission')
        if set(names) != set(manifest['assets']) | {'release-manifest.json'}:
            raise ValueError('ZIP inventory differs from reviewed manifest')
        for name, digest in manifest['assets'].items():
            if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                raise ValueError('Asset SHA mismatch: '+name)
        market_body = archive.read('market.json')
        if hashlib.sha256(market_body).hexdigest() != data_sha256:
            raise ValueError('Market SHA mismatch')
        payload = json.loads(market_body)
        validate(payload)
        if payload['asOf'] != as_of or payload['mode'] != 'live' or payload.get('observationProfile',{}).get('profile') != 'observation-only':
            raise ValueError('Real approved observation date/profile required')
        if payload['creditHistory'] or payload['futures'] or payload['indexHistory'] or any(s.get('margin') or s.get('intraday') for s in payload['stocks']):
            raise ValueError('Non-observation data in candidate')
        if any(s.get('institutional') for s in payload['stocks'] if s['market']=='TWSE'):
            raise ValueError('TWSE T86 prohibited')
        html = archive.read('index.html').decode()
        if "connect-src 'self';" not in html or "object-src 'none'" not in html or 'raw.githubusercontent.com' in html:
            raise ValueError('Observation security policy missing')
    return {'verified':True,'candidateCommit':commit,'asOf':as_of,'dataSha256':data_sha256,
            'rcZipSha256':zip_sha256,'files':len(names),'publicationAuthorized':False,
            'note':'Integrity verification is not merge or Pages authorization.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('zip',type=Path)
    parser.add_argument('--zip-sha256',required=True)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--data-sha256',required=True)
    parser.add_argument('--as-of',required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.zip,args.zip_sha256,args.commit,args.data_sha256,args.as_of)))
