"""Read-only incident/restore plans. Never clears reservations or dispatches Pages."""
import argparse
import json
from .publication_contract import require, sha
from .candidate_package import verify_closure


def reconcile(coordinator):
    snap = coordinator.store.read(); tx = snap.state['activeTransaction']
    plan = {'mode': 'read-only', 'stateHead': snap.head, 'expectedCurrent': snap.state['successfulPointer'],
            'halted': snap.state['control']['halted'], 'transaction': tx, 'actions': [],
            'missingEvidence': [], 'remoteMutationAuthorized': False}
    if not tx:
        return plan
    if not tx['deploymentId']:
        plan['missingEvidence'].append('Unique Pages deployment ID/acceptance status; do not resubmit')
        return plan
    try:
        status = coordinator.pages.status(tx['deploymentId']); plan['pages'] = status
        if status['status'] == 'success':
            files, _ = coordinator.archive.load(tx['archive'])
            plan['live'] = coordinator.verifier.verify(files['site.zip'])
            plan['actions'].append('finalize-existing-no-deploy requires separate exact owner authorization')
        elif status['status'] == 'failure':
            old, _ = coordinator.archive.load(tx['baselineArchive'])
            plan['live'] = coordinator.verifier.verify(old['site.zip'])
            plan['actions'].append('close-failed-safe after proving old worker terminated and no in-flight write')
        else:
            plan['missingEvidence'].append('Deployment not uniquely terminal')
    except Exception as exc:
        plan['missingEvidence'].append(str(exc))
    return plan


def restore_verified_version(coordinator, baseline, prior_archive, authorization=None):
    snap = coordinator.store.read(); files, _ = coordinator.archive.load(prior_archive); r = verify_closure(files)
    require(snap.head == baseline.state_head and snap.state['successfulPointer'] == baseline.pointer, 'Restore expectedCurrent differs')
    require(not snap.state['control']['halted'] and snap.state['activeTransaction'] is None, 'Resolve UNKNOWN/in-flight worker before restore')
    plan = {'mode': 'restore-plan', 'targetZipSha256': sha(files['site.zip']), 'receiptSha256': sha(files['candidate-receipt.json']),
            'seedZipSha256': r['frontend']['seedZipSha256'], 'expectedCurrent': baseline.binding,
            'requires': ['single owner approval', 'old writers terminated', 'no in-flight deployment'], 'willDeploy': True}
    if authorization is None:
        return plan
    return coordinator.prepare_publication(baseline, prior_archive, authorization, kind='manual-restore')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps({'mode': 'read-only', 'status': 'NOT_AUTHORIZED',
                      'reason': 'Remote initialization and real Pages authority are not installed in 4C-2B'}))
