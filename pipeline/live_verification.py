"""Read-only, two-round exact site verification with manifest sandwich reads."""
from datetime import datetime, timezone
import gzip
import io
import time
from urllib.parse import urlsplit, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from .publication_contract import canonical, sha, require, site_files

BASE_URL = 'https://0857ken.github.io/tw-market-scanner/'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect rejected during exact live verification')


def https_fetch(url, timeout):
    require(url.startswith(BASE_URL), 'Fixed production origin/path required')
    req = Request(url, headers={'Cache-Control': 'no-cache, no-store', 'Accept-Encoding': 'identity'})
    with build_opener(NoRedirect()).open(req, timeout=timeout) as r:
        body = r.read(12*1024*1024+1)
        require(len(body) <= 12*1024*1024, 'Live response compressed/body budget')
        encoding = r.headers.get('Content-Encoding', 'identity').lower()
        if encoding == 'gzip':
            with gzip.GzipFile(fileobj=io.BytesIO(body)) as compressed:
                body = compressed.read(12*1024*1024+1)
        else:
            require(encoding in ('identity',''), 'Unsupported content encoding')
        require(len(body) <= 12*1024*1024, 'Live decoded body budget')
        return {'status': r.status, 'url': r.url, 'body': body, 'headers': dict(r.headers)}


class LiveVerifier:
    def __init__(self, fetch=https_fetch, *, clock=lambda: datetime.now(timezone.utc), sleep=time.sleep):
        self.fetch = fetch; self.clock = clock; self.sleep = sleep

    def verify(self, site_zip):
        files = site_files(site_zip)
        started = self.clock(); rounds = []; requests = 0
        public = {n: b for n, b in files.items() if n not in ('.nojekyll', 'release-manifest.json')}

        def read(name, expected):
            nonlocal requests
            require((self.clock()-started).total_seconds() <= 240, 'Live verification deadline')
            requests += 1
            require(requests <= 2*(len(public)+2), 'Live request budget')
            url = BASE_URL+quote(name, safe='/')+'?scanner_check='+str(time.time_ns())
            response = self.fetch(url, 15)
            got = urlsplit(response['url']); base = urlsplit(BASE_URL)
            require(got.scheme == 'https' and got.netloc == base.netloc and got.path == base.path+name,
                    'Live origin/path redirect')
            require(response['status'] == 200 and len(response['body']) <= 12*1024*1024 and
                    response['body'] == expected, 'Live status/bytes mismatch: '+name)
            headers = {k.lower(): v for k, v in response.get('headers', {}).items()}
            return {'path': name, 'status': response['status'], 'bytes': len(expected), 'sha256': sha(expected),
                    'at': self.clock().isoformat(), 'cacheHeaders': {k: headers[k] for k in
                        ('cache-control', 'etag', 'last-modified', 'age', 'date', 'content-type') if k in headers}}

        for i in range(2):
            before = read('release-manifest.json', files['release-manifest.json'])
            inventory = [read(n, b) for n, b in sorted(public.items())]
            after = read('release-manifest.json', files['release-manifest.json'])
            rounds.append({'manifestBefore': before, 'files': inventory, 'manifestAfter': after})
            if i == 0:
                self.sleep(15)
        require((self.clock()-started).total_seconds() <= 240, 'Live verification exceeded deadline')
        return {'schemaVersion': 1, 'siteZipSha256': sha(site_zip), 'verifiedAt': self.clock().isoformat(),
                'baseUrl': BASE_URL, 'rounds': rounds, 'requests': requests,
                'excluded': {'.nojekyll': 'Pages platform control file; verified in ZIP, not a public HTTP resource'}}


def validate_evidence(evidence, site_zip, now):
    require(evidence['siteZipSha256'] == sha(site_zip) and evidence['baseUrl'] == BASE_URL and
            len(evidence['rounds']) == 2 and evidence['excluded'] == {
                '.nojekyll': 'Pages platform control file; verified in ZIP, not a public HTTP resource'}, 'Live evidence scope')
    age = (now-datetime.fromisoformat(evidence['verifiedAt'])).total_seconds()
    require(0 <= age <= 60, 'Live evidence expired/future')
    files = site_files(site_zip); public = set(files)-{'.nojekyll', 'release-manifest.json'}
    for round in evidence['rounds']:
        require({r['path'] for r in round['files']} == public and len(round['files']) == len(public), 'Incomplete live evidence')
        records = [round['manifestBefore'], *round['files'], round['manifestAfter']]
        require(round['manifestBefore']['path'] == round['manifestAfter']['path'] == 'release-manifest.json', 'Manifest sandwich missing')
        for r in records:
            require(r['status'] == 200 and r['sha256'] == sha(files[r['path']]) and r['bytes'] == len(files[r['path']]), 'Evidence hash mismatch')
            require(not {'authorization', 'cookie', 'set-cookie'} & set(r['cacheHeaders']), 'Sensitive evidence headers')
    return evidence
