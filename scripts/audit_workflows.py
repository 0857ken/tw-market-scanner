"""Audit EVERY workflow; only the byte-pinned legacy release may deploy.

Uses a real YAML parser, rejects duplicate keys/aliases and unknown workflows.
This is a repository guard, not proof of remote environment protection settings.
"""
import hashlib
from pathlib import Path
import re
import yaml
from pipeline.common import ROOT

LEGACY = 'pages-release.yml'
LEGACY_SHA256 = '07ec8e9cebcc239d92232663d52bb9f0f872cfa6a4b64b602d4fb317ae00a7ed'
EVENTS = {'ci.yml': {'push', 'pull_request', 'workflow_dispatch'},
          'deploy.yml': {'workflow_dispatch'}, 'update-data.yml': {'workflow_dispatch'},
          'package-daily.yml': {'workflow_dispatch'}, LEGACY: {'workflow_dispatch'}}


class UniqueLoader(yaml.BaseLoader):
    def construct_mapping(self, node, deep=False):
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in result:
                raise ValueError('Duplicate or non-scalar workflow key')
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def parse(body):
    if any(isinstance(event, yaml.AliasEvent) for event in yaml.parse(body)):
        raise ValueError('Workflow aliases are not permitted by the audit')
    document = yaml.load(body, Loader=UniqueLoader)
    if not isinstance(document, dict):
        raise ValueError('Workflow must be a mapping')
    return document


def audit(directory=ROOT / '.github/workflows'):
    directory = Path(directory)
    paths = sorted(p for p in directory.iterdir() if p.suffix.lower() in ('.yml', '.yaml'))
    if {p.name for p in paths} != set(EVENTS):
        raise ValueError('Workflow inventory changed; review explicit roles before accepting it')
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError('Workflow must be a regular file')
        body = path.read_bytes()
        document = parse(body)
        events = document.get('on')
        events = {events} if isinstance(events, str) else set(events or {})
        if events != EVENTS[path.name]:
            raise ValueError(path.name + ': event/schedule policy changed')
        if path.name == LEGACY:
            if hashlib.sha256(body).hexdigest() != LEGACY_SHA256:
                raise ValueError('Legacy Pages release must remain byte-identical')
        elif re.search(rb'\bsecrets\s*\.', body):
            raise ValueError('Candidate workflows cannot consume repository Secrets')
        jobs = document.get('jobs', {})
        if not isinstance(jobs, dict) or not jobs:
            raise ValueError('Workflow jobs required')
        top = document.get('permissions')
        if not isinstance(top, dict) or not top or any(v != 'read' for v in top.values()):
            raise ValueError(path.name + ': explicit read-only default permissions required')
        for name, job in jobs.items():
            permissions = job.get('permissions', top)
            legacy_deploy = path.name == LEGACY and name == 'deploy'
            if not isinstance(permissions, dict):
                raise ValueError('Unbounded permissions')
            if legacy_deploy:
                if permissions != {'pages': 'write', 'id-token': 'write'}:
                    raise ValueError('Legacy deployment permission boundary changed')
            elif any(value != 'read' for value in permissions.values()):
                raise ValueError(path.name + ': candidate job has write permissions')
            if path.name != LEGACY and ('environment' in job or 'uses' in job):
                raise ValueError('Candidate jobs cannot invoke deployment environments/reusable workflows')
            for step in job.get('steps', []):
                action = step.get('uses', '')
                if path.name != LEGACY and re.search(r'(?i)(deploy|configure-pages|upload-pages)', action):
                    raise ValueError('Candidate workflow invokes publication action')
    return [p.name for p in paths]


if __name__ == '__main__':
    print('Workflow permissions/events audit passed: ' + ', '.join(audit()))
