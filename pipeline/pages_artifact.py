"""Bind the actual Pages tar, its Actions artifact and exact producer attempt."""
from datetime import datetime
import io
import tarfile
from .publication_contract import (REPOSITORY, REPOSITORY_ID, require, positive, digest,
                                   read_zip, safe_path, site_files, sha, file_inventory, canonical)


def validate_saved_proof(proof, expected_sha, receipt, *, publisher_sha):
    require(isinstance(proof, dict) and sha(canonical(proof)) == expected_sha and
            proof.get('schemaVersion') == 1, 'Persisted Pages artifact proof missing/corrupted')
    positive(proof['artifactId']); digest(proof['artifactArchiveSha256'])
    require(proof['siteZipSha256'] == receipt['output']['siteZipSha256'] and
            proof['producer']['headSha'] == publisher_sha, 'Saved artifact ZIP/code binding mismatch')
    expected = {**receipt['frontend']['assets'], 'market.json': receipt['output']['publicMarketSha256'],
                'release-manifest.json': receipt['output']['manifestSha256']}
    require(set(proof['files']) == set(expected) and all(proof['files'][n]['sha256'] == d for n,d in expected.items()),
            'Saved Pages artifact file inventory differs')
    return proof


def verify(api, artifact_id, site_zip, expected_run):
    positive(artifact_id); positive(expected_run['runId']); positive(expected_run['runAttempt'])
    digest(expected_run['headSha'], 40)
    require(expected_run['workflowPath'] in ('.github/workflows/ci.yml', '.github/workflows/package-daily.yml'),
            'Unapproved Pages artifact producer workflow')
    meta = api('GET', '/actions/artifacts/'+str(artifact_id))
    run = api('GET', '/actions/runs/'+str(expected_run['runId'])+'/attempts/'+str(expected_run['runAttempt']))
    require(meta['id'] == artifact_id and meta['name'] == 'github-pages' and meta['expired'] is False,
            'Pages artifact identity/retention mismatch')
    source = meta['workflow_run']
    require(source['id'] == run['id'] == expected_run['runId'] and
            source['repository_id'] == source['head_repository_id'] == run['repository']['id'] == REPOSITORY_ID and
            run['repository']['full_name'] == REPOSITORY and
            source['head_sha'] == run['head_sha'] == expected_run['headSha'] and
            run['run_attempt'] == expected_run['runAttempt'] and run['path'] == expected_run['workflowPath'] and
            run['status'] == 'completed' and run['conclusion'] == 'success', 'Pages artifact producer mismatch')
    created = datetime.fromisoformat(meta['created_at'].replace('Z', '+00:00'))
    start = datetime.fromisoformat(run['run_started_at'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(run['updated_at'].replace('Z', '+00:00'))
    require(start <= created <= end, 'Artifact not from the approved run attempt')
    body = api('GET', '/actions/artifacts/'+str(artifact_id)+'/zip', binary=True)
    require(len(body) == meta['size_in_bytes'] and meta['digest'] == 'sha256:'+sha(body), 'Pages artifact archive digest mismatch')
    outer = read_zip(body, lambda n: n == 'artifact.tar')
    require(set(outer) == {'artifact.tar'}, 'Pages artifact must contain exactly artifact.tar')
    expected = site_files(site_zip); actual = {}
    with tarfile.open(fileobj=io.BytesIO(outer['artifact.tar']), mode='r:') as archive:
        entries = archive.getmembers()
        require(len(entries) <= 1000 and sum(m.size for m in entries) <= 12*1024*1024, 'Pages tar budget exceeded')
        for member in entries:
            name = member.name.removeprefix('./').rstrip('/')
            if member.isdir():
                require(name in ('', '.', 'assets'), 'Unapproved Pages directory')
                continue
            require(member.isfile() and safe_path(name) and name in expected and name not in actual,
                    'Unsafe/extra/duplicate Pages tar entry')
            actual[name] = archive.extractfile(member).read()
    require(file_inventory(actual) == file_inventory(expected), 'Pages tar bytes differ from approved site ZIP')
    return {'schemaVersion': 1, 'artifactId': artifact_id, 'artifactArchiveSha256': sha(body),
            'artifactArchiveBytes': len(body), 'producer': dict(expected_run), 'siteZipSha256': sha(site_zip),
            'files': file_inventory(actual)}
