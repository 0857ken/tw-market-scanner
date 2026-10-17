"""A Pages deployment ID is not a Run ID, artifact ID, or generic Deployment ID."""
from .publication_contract import require, require_remote

PENDING = {'deployment_queued', 'queued', 'in_progress', 'building', 'syncing_files', 'updating_pages', 'waiting_for_approval'}
FAILED = {'failed', 'cancelled', 'deployment_failed'}


def normalize(raw):
    if raw == 'succeed':
        return 'success'
    if raw in PENDING:
        return 'pending'
    if raw in FAILED:
        return 'failure'
    return 'unknown'


class PagesRejected(RuntimeError):
    """Transport can prove the create request was rejected without acceptance."""


class FakePages:
    offline = True

    def __init__(self, checkpoint=lambda _: None, on_create=lambda _: None):
        self.checkpoint = checkpoint; self.on_create = on_create; self.creates = []
        self.statuses = {}; self.serial = 0

    def create_once(self, transaction, persist_id, capability=None):
        self.checkpoint('pages.create.before')
        self.serial += 1; did = 'offline-pages-'+str(self.serial)
        self.creates.append({'id': did, 'key': transaction['key'], 'buildVersion': transaction['key'][:40]})
        self.statuses[did] = 'succeed'; self.on_create(transaction)
        self.checkpoint('pages.create.after')
        persist_id(did)
        return did

    def status(self, deployment_id):
        self.checkpoint('pages.status')
        raw = self.statuses[deployment_id]
        return {'id': deployment_id, 'rawStatus': raw, 'status': normalize(raw)}


class GitHubPages:
    offline = False

    def __init__(self, api):
        self.api = api

    def create_once(self, transaction, persist_id, capability=None):
        require_remote(capability)
        require(transaction['phase'] == 'DEPLOY_REQUESTED' and transaction['deploymentId'] is None, 'Missing durable dispatch intent')
        # No retry helper: any ambiguous POST response must become UNKNOWN.
        result = self.api('POST', '/pages/deployments', {
            'artifact_id': transaction['pagesArtifactId'], 'pages_build_version': transaction['key'][:40],
            'oidc_token': capability.oidc_token})
        did = str(result['id']); require(did, 'Pages deployment ID missing')
        persist_id(did)
        return did

    def status(self, deployment_id):
        from urllib.parse import quote
        require(isinstance(deployment_id, str) and deployment_id, 'Exact Pages deployment ID required')
        raw = self.api('GET', '/pages/deployments/'+quote(deployment_id, safe=''))
        return {'id': deployment_id, 'rawStatus': raw['status'], 'status': normalize(raw['status'])}
