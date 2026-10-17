"""Exact-ID Releases adapter. Filesystem implementation is an offline test backend."""
import json
from pathlib import Path
from urllib.parse import quote
from urllib.error import HTTPError
from .candidate_io import atomic_bytes, atomic_json
from .publication_contract import (REPOSITORY_ID, ASSETS, canonical, sha, require,
                                   positive, require_remote)
from .candidate_package import verify_closure


class FilesystemReleases:
    offline = True

    def __init__(self, root, checkpoint=lambda _: None):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
        self.checkpoint = checkpoint

    def by_tag(self, tag):
        for p in self.root.glob('*/release.json'):
            r = json.loads(p.read_bytes())
            if r['tag_name'] == tag:
                return r
        return None

    def get(self, release_id):
        return json.loads((self.root/str(positive(release_id))/'release.json').read_bytes())

    def create(self, tag, capability=None, *, target_commit=None):
        self.checkpoint('release.create.before')
        require(self.by_tag(tag) is None, 'Release tag exists')
        rid = int(sha(tag.encode())[:12], 16)
        from .publication_contract import digest
        digest(target_commit,40)
        r = {'id': rid, 'tag_name': tag, 'repositoryId': REPOSITORY_ID, 'draft': True, 'immutable': False,
             'target_commitish':target_commit,'tagCommitSha':target_commit,'assets': []}
        atomic_json(self.root/str(rid)/'release.json', r, immutable=True)
        self.checkpoint('release.create.after')
        return r

    def upload(self, rid, name, body, capability=None):
        self.checkpoint('release.upload.'+name+'.before')
        r = self.get(rid); require(r['draft'] and not r['immutable'], 'Frozen Release cannot change')
        require(not any(a['name'] == name for a in r['assets']), 'No asset clobber')
        aid = int(sha((str(rid)+name).encode())[:12], 16)
        atomic_bytes(self.root/str(rid)/str(aid), body, immutable=True)
        a = {'id': aid, 'name': name, 'state': 'uploaded', 'size': len(body), 'digest': 'sha256:'+sha(body)}
        r['assets'].append(a); atomic_json(self.root/str(rid)/'release.json', r)
        self.checkpoint('release.upload.'+name+'.after')
        return a

    def download(self, rid, aid):
        self.checkpoint('release.download')
        require(any(a['id'] == aid for a in self.get(rid)['assets']), 'Asset ID not in Release')
        return (self.root/str(rid)/str(positive(aid))).read_bytes()

    def freeze(self, rid, capability=None):
        self.checkpoint('release.freeze.before')
        r = self.get(rid); r.update(draft=False, immutable=True)
        atomic_json(self.root/str(rid)/'release.json', r)
        self.checkpoint('release.freeze.after')
        return r

    def total_bytes(self):
        return sum(a['size'] for p in self.root.glob('*/release.json') for a in json.loads(p.read_bytes())['assets'])


class GitHubReleases:
    """Injected authenticated API client; all real mutation gates remain closed."""
    offline = False

    def __init__(self, api):
        self.api = api
        self._releases = {}

    def get(self, rid):
        r = self.api('GET', '/releases/'+str(positive(rid)))
        require(r['id'] == rid, 'Release ID mismatch')
        r['repositoryId'] = REPOSITORY_ID
        tag = self.api('GET','/git/ref/tags/'+quote(r['tag_name'],safe=''))['object']
        for _ in range(5):
            if tag['type']=='commit': break
            require(tag['type']=='tag','Release tag does not reference a commit')
            tag=self.api('GET','/git/tags/'+tag['sha'])['object']
        require(tag['type']=='commit','Release tag chain exceeds budget')
        r['tagCommitSha']=tag['sha']
        # Explicit pagination, not only the first page of assets.
        assets, page = [], 1
        while True:
            batch = self.api('GET', '/releases/'+str(rid)+'/assets?per_page=100&page='+str(page))
            assets.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        r['assets'] = assets
        self._releases[rid] = r
        return r

    def by_tag(self, tag):
        try:
            return self.api('GET', '/releases/tags/'+quote(tag, safe=''))
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def create(self, tag, capability=None, *, target_commit=None):
        require_remote(capability)
        return self.api('POST', '/releases', {'tag_name': tag,'target_commitish':target_commit, 'draft': True, 'make_latest': 'false'})

    def upload(self, rid, name, body, capability=None):
        require_remote(capability)
        return self.api('POST', 'uploads:/releases/'+str(positive(rid))+'/assets?name='+quote(name, safe=''), body)

    def freeze(self, rid, capability=None):
        require_remote(capability)
        return self.api('PATCH', '/releases/'+str(positive(rid)), {'draft': False, 'make_latest': 'false'})

    def download(self, rid, aid):
        release=self._releases.get(rid)
        if release is None or not any(a['id']==aid for a in release['assets']):
            release=self.get(rid)
        require(any(a['id'] == aid for a in release['assets']), 'Asset belongs to another Release')
        return self.api('GET', '/releases/assets/'+str(positive(aid)), binary=True)

    def total_bytes(self):
        total, page = 0, 1
        while True:
            batch = self.api('GET', '/releases?per_page=100&page='+str(page))
            for release in batch:
                total += sum(a['size'] for a in self.get(release['id'])['assets'])
            if len(batch) < 100:
                return total
            page += 1


class ReleaseArchive:
    def __init__(self, backend):
        self.backend = backend

    def _asset(self, rid, meta, expected, *, downloaded=None):
        require(meta['state'] == 'uploaded' and meta['size'] == len(expected) and
                meta.get('digest') == 'sha256:'+sha(expected), 'Starter/corrupt Release asset')
        require((self.backend.download(rid, meta['id']) if downloaded is None else downloaded) == expected, 'Asset read-back differs')

    def archive_candidate(self, files, capability=None):
        if not self.backend.offline:
            require_remote(capability)  # Before *any* remote mutation or create.
        r = verify_closure(files)
        tag = 'scanner-archive-{}-r{}-a{}-{}'.format(r['slot']['targetDate'], r['provenance']['sourceRunId'],
                    r['provenance']['runAttempt'], r['output']['siteZipSha256'][:12])
        release = self.backend.by_tag(tag)
        if release and release.get('immutable') is True and release['draft'] is False:
            meta=next(a for a in release['assets'] if a['name']=='package-index.json')
            ref={'repositoryId':REPOSITORY_ID,'releaseId':release['id'],'tag':tag,'indexAssetId':meta['id'],
                 'packageIndexSha256':meta['digest'].removeprefix('sha256:'),'receiptSha256':sha(files['candidate-receipt.json'])}
            require(self.load(ref)[0]==files,'Existing immutable archive differs')
            return ref
        total = self.backend.total_bytes()
        require(type(total) is int and total >= 0 and total + sum(map(len, files.values())) + 256*1024 <= 5*1024**3,
                'Unknown/exceeded archive capacity budget')
        if release is None:
            try:
                release = self.backend.create(tag, capability,target_commit=r['provenance']['processorCommit'])
            except TimeoutError:
                release = self.backend.by_tag(tag)
                require(release is not None, 'UNKNOWN Release create; no retry')
        rid = release['id']; positive(rid)
        index = {'schemaVersion': 1, 'repositoryId': REPOSITORY_ID, 'releaseId': rid, 'tag': tag, 'assets': {}}
        for name in ASSETS:
            release = self.backend.get(rid)
            matches = [a for a in release['assets'] if a['name'] == name]
            require(len(matches) <= 1, 'Duplicate Release asset')
            if not matches:
                try:
                    meta = self.backend.upload(rid, name, files[name], capability)
                except TimeoutError:
                    matches = [a for a in self.backend.get(rid)['assets'] if a['name'] == name]
                    require(len(matches) == 1, 'UNKNOWN asset upload; no retry/clobber')
                    meta = matches[0]
            else:
                meta = matches[0]
            self._asset(rid, meta, files[name])
            index['assets'][name] = {'id': meta['id'], 'bytes': len(files[name]), 'sha256': sha(files[name])}
        ib = canonical(index); release = self.backend.get(rid)
        matches = [a for a in release['assets'] if a['name'] == 'package-index.json']
        require(len(matches) <= 1, 'Duplicate index')
        if matches:
            im = matches[0]
        else:
            try:
                im = self.backend.upload(rid, 'package-index.json', ib, capability)
            except TimeoutError:
                matches = [a for a in self.backend.get(rid)['assets'] if a['name'] == 'package-index.json']
                require(len(matches) == 1, 'UNKNOWN index upload')
                im = matches[0]
        self._asset(rid, im, ib)
        if self.backend.get(rid)['draft']:
            try:
                self.backend.freeze(rid, capability)
            except TimeoutError:
                pass  # Exact read-back below decides; never repeat freeze automatically.
        ref = {'repositoryId': REPOSITORY_ID, 'releaseId': rid, 'tag': tag,
               'indexAssetId': im['id'], 'packageIndexSha256': sha(ib), 'receiptSha256': sha(files['candidate-receipt.json'])}
        self.load(ref)
        return ref

    def load(self, ref):
        require(ref['repositoryId'] == REPOSITORY_ID, 'Wrong archive repository')
        rid = ref['releaseId']; release = self.backend.get(rid)
        require(release['id'] == rid and release['repositoryId'] == REPOSITORY_ID and release['tag_name'] == ref['tag'] and
                release.get('immutable') is True and release['draft'] is False, 'Archive not immutable/exact')
        require(len(release['assets']) == 5 and {a['name'] for a in release['assets']} == set(ASSETS) | {'package-index.json'}, 'Incomplete/unexpected archive assets')
        im = next(a for a in release['assets'] if a['id'] == ref['indexAssetId'])
        require(im['name'] == 'package-index.json' and im['size'] <= 256*1024, 'Invalid/oversized index asset')
        ib = self.backend.download(rid, ref['indexAssetId'])
        require(sha(ib) == ref['packageIndexSha256'], 'Index digest mismatch')
        index = json.loads(ib)
        require(index['repositoryId'] == REPOSITORY_ID and index['releaseId'] == rid and index['tag'] == ref['tag'] and
                set(index['assets']) == set(ASSETS), 'Index identity mismatch')
        require(im['name'] == 'package-index.json', 'Wrong index asset ID'); self._asset(rid, im, ib,downloaded=ib)
        files = {}
        for name, record in index['assets'].items():
            meta = next(a for a in release['assets'] if a['id'] == record['id'])
            require(meta['name'] == name, 'Asset ID/name mismatch')
            budgets = {'site.zip':16*1024*1024, 'acquisition-state.zip':64*1024*1024, 'supporting-material.zip':64*1024*1024,
                       'candidate-receipt.json':256*1024}
            require(0 < record['bytes'] <= budgets[name] and meta['size'] == record['bytes'], 'Asset download budget exceeded')
            body = self.backend.download(rid, record['id'])
            require(len(body) == record['bytes'] and sha(body) == record['sha256'], 'Indexed asset mismatch')
            self._asset(rid, meta, body,downloaded=body); files[name] = body
        receipt=verify_closure(files, ref['receiptSha256'])
        require(release['tagCommitSha']==receipt['provenance']['processorCommit'],'Release tag/processor commit mismatch')
        return files, index
