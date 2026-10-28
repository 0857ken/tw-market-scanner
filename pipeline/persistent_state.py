"""Linear Git state: single-parent child plus non-force ref update. No lease fiction."""
import base64
import copy
import io
import hashlib
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import tempfile
import tarfile
from .publication_contract import (REPOSITORY_ID, STATE_BRANCH, canonical, sha, require,
                                   state_path, validate_state, require_remote)


class CASConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class StateSnapshot:
    head: str
    state: dict
    files: dict


class LocalGitState:
    """Real bare Git used by offline integration tests; accepts local paths only."""
    offline = True

    def __init__(self, path, checkpoint=lambda _: None):
        self.path = Path(path).resolve()
        require(self.path.is_dir() and self.path.is_absolute(), 'Existing local bare Git required')
        self.checkpoint = checkpoint
        require(self.git('rev-parse', '--is-bare-repository').strip() == b'true', 'Bare Git required')

    def git(self, *args, body=None, extra_env=None):
        env = {**os.environ, 'GIT_AUTHOR_NAME': 'offline-scanner-test', 'GIT_AUTHOR_EMAIL': 'offline@example.invalid',
               'GIT_COMMITTER_NAME': 'offline-scanner-test', 'GIT_COMMITTER_EMAIL': 'offline@example.invalid', **(extra_env or {})}
        r = subprocess.run(['git', '--git-dir', str(self.path), *args], input=body, capture_output=True, env=env)
        if r.returncode:
            raise CASConflict(r.stderr.decode(errors='replace'))
        return r.stdout

    def head(self):
        return self.git('rev-parse', 'refs/heads/'+STATE_BRANCH).decode().strip()

    def files(self, head):
        # Read one fixed commit in one process; do not spawn once per historical event.
        with tarfile.open(fileobj=io.BytesIO(self.git('archive', '--format=tar', head))) as archive:
            members = [m for m in archive.getmembers() if not m.isdir()]
            require(all(m.isfile() and not m.mode & 0o111 and state_path(m.name) for m in members), 'Executable/unapproved state paths')
            return {m.name: archive.extractfile(m).read() for m in members}

    def child(self, parent, files, message, capability=None):
        self.checkpoint('state.child.before')
        with tempfile.TemporaryDirectory() as t:
            env = {'GIT_INDEX_FILE': str(Path(t)/'index')}
            if parent is not None:
                self.git('read-tree', parent, extra_env=env)
            for name, body in files.items():
                require(state_path(name), 'Invalid state path')
                blob = self.git('hash-object', '-w', '--stdin', body=body).decode().strip()
                self.git('update-index', '--add', '--cacheinfo', '100644,'+blob+','+name, extra_env=env)
            tree = self.git('write-tree', extra_env=env).decode().strip()
            args = ['commit-tree', tree] + (['-p', parent] if parent is not None else [])
            commit = self.git(*args, body=message.encode(), extra_env=env).decode().strip()
        self.checkpoint('state.child.after')
        return commit

    def advance(self, expected, child, *, force=False, capability=None):
        require(force is False, 'Force prohibited')
        parents = self.git('show', '-s', '--format=%P', child).decode().strip().split()
        require(parents == [expected], 'Child must have exactly the read head as sole parent')
        self.checkpoint('state.ref.before')
        # Real receive-pack performs the fast-forward check under its ref lock.
        self.git('push', '--porcelain', str(self.path), child+':refs/heads/'+STATE_BRANCH)
        self.checkpoint('state.ref.after')

    def contains(self, ancestor, head):
        try:
            self.git('merge-base', '--is-ancestor', ancestor, head)
            return True
        except CASConflict:
            return False

    def initialize_offline(self, files):
        require(not any(self.path.glob('refs/heads/*')), 'Test genesis exists')
        c = self.child(None, files, 'offline-only genesis')
        self.git('update-ref', 'refs/heads/'+STATE_BRANCH, c)
        return c


class GitHubState:
    """Git Database REST adapter. Mutations remain gated pending remote approval."""
    offline = False

    def __init__(self, api):
        self.api = api
        self._blobs = {}

    def head(self):
        r = self.api('GET', '/git/ref/heads/'+STATE_BRANCH)
        require(r['ref'] == 'refs/heads/'+STATE_BRANCH and r['object']['type'] == 'commit', 'Wrong state ref')
        return r['object']['sha']

    def files(self, head):
        commit = self.api('GET', '/git/commits/'+head)
        tree = self.api('GET', '/git/trees/'+commit['tree']['sha']+'?recursive=1')
        require(tree['truncated'] is False, 'Truncated state tree')
        files = {}
        for e in tree['tree']:
            if e['type'] == 'tree':
                continue
            require(e['type'] == 'blob' and e['mode'] == '100644' and state_path(e['path']), 'Unsafe state blob')
            if e['sha'] not in self._blobs:
                blob = self.api('GET', '/git/blobs/'+e['sha'])
                require(blob['encoding'] == 'base64', 'Unexpected Git blob encoding')
                body = base64.b64decode(blob['content'])
                require(hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest() == e['sha'], 'Git blob content hash differs')
                self._blobs[e['sha']] = body
            files[e['path']] = self._blobs[e['sha']]
        return files

    def child(self, parent, files, message, capability=None):
        require_remote(capability)  # No orphan initialization exposed here.
        base = self.api('GET', '/git/commits/'+parent)
        require(all(state_path(n) for n in files), 'Unsafe state paths')
        entries = []
        for n, b in files.items():
            blob = self.api('POST', '/git/blobs', {'content': base64.b64encode(b).decode(), 'encoding': 'base64'})
            entries.append({'path': n, 'type': 'blob', 'mode': '100644', 'sha': blob['sha']})
        tree = self.api('POST', '/git/trees', {'base_tree': base['tree']['sha'], 'tree': entries})
        return self.api('POST', '/git/commits', {'message': message, 'tree': tree['sha'], 'parents': [parent]})['sha']

    def advance(self, expected, child, *, force=False, capability=None):
        require_remote(capability)
        require(force is False, 'Force prohibited')
        c = self.api('GET', '/git/commits/'+child)
        require([p['sha'] for p in c['parents']] == [expected], 'State child parent mismatch')
        self.api('PATCH', '/git/refs/heads/'+STATE_BRANCH, {'sha': child, 'force': False})

    def contains(self, ancestor, head):
        comparison = self.api('GET', '/compare/'+ancestor+'...'+head)
        return comparison['status'] in ('identical', 'ahead')


class StateStore:
    def __init__(self, backend):
        self.backend = backend

    def read(self):
        h = self.backend.head(); files = self.backend.files(h)
        require('state.json' in files and all(state_path(n) for n in files), 'Missing/unsafe state')
        for n, b in files.items():
            require(len(b) <= (64*1024 if n == 'state.json' else 256*1024), 'State file budget')
        return StateSnapshot(h, validate_state(json.loads(files['state.json'])), files)

    def cas_transition(self, expected_head, expected_generation, operation_key, fence, transition, capability=None):
        if not self.backend.offline:
            require_remote(capability)
        snap = self.read(); old = snap.state
        if snap.head != expected_head or old['successfulPointer']['generation'] != expected_generation:
            raise CASConflict('State head/generation changed')
        active = old['activeTransaction']
        if fence is not None and (not active or active['key'] != operation_key or active['fence'] != fence):
            raise CASConflict('Operation/fence changed')
        new, changes = transition(copy.deepcopy(old))
        require(new['stateRevision'] == old['stateRevision'] + 1, 'State revision must advance once')
        validate_state(new)
        if new['successfulPointer'] != old['successfulPointer']:
            p = new['successfulPointer']
            require(p['generation'] == expected_generation+1, 'Success generation must advance once')
            record = changes.get('successes/g'+str(p['generation'])+'.json')
            require(record and sha(record) == p['successRecordSha256'], 'Atomic SuccessRecord missing')
        for name, b in changes.items():
            require(state_path(name) and name != 'state.json' and len(b) <= 256*1024, 'Invalid evidence path/budget')
            require(name not in snap.files or snap.files[name] == b, 'Immutable state record overwrite')
        changes = {**changes, 'state.json': canonical(new)}
        child = self.backend.child(snap.head, changes, 'scanner-state '+operation_key+' r'+str(new['stateRevision']), capability=capability)
        try:
            self.backend.advance(snap.head, child, force=False, capability=capability)
        except TimeoutError:
            # Accepted response lost: read exact child/ancestry; never rebuild/rebase.
            h = self.backend.head()
            if not self.backend.contains(child, h):
                raise CASConflict('UNKNOWN state write; do not repeat')
        current = self.read()
        if not self.backend.contains(child, current.head):
            raise CASConflict('State write not observed')
        return current
