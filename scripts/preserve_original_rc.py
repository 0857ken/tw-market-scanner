"""Verify the original approved RC and build a LOCAL portable import closure, never remote genesis."""
import argparse
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
from pipeline.common import ROOT
from pipeline.candidate_io import publish_directory, exclusive_lock
from pipeline.candidate_package import (LEGACY_ZIP, LEGACY_COMMIT, LEGACY_DATA, legacy_import_plan, verify_closure)
from pipeline.publication_contract import sha, canonical, site_files, safe_path, zip_bytes
from pipeline.acquisition_state import code_inventory
from pipeline.verify_rc import verify


def preserve(archive_path, output):
    output = Path(output).absolute()
    if output.exists(): raise FileExistsError('Choose a new evidence output; original bytes are never overwritten')
    original = Path(archive_path).read_bytes()
    verification = verify(archive_path, LEGACY_ZIP, LEGACY_COMMIT, LEGACY_DATA, '2026-10-13')
    output.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_lock(output.parent/('.'+output.name+'.lock')), tempfile.TemporaryDirectory(dir=output.parent) as t:
        temp = Path(t); data = temp/'input'; data.mkdir()
        archive = subprocess.check_output(['git', 'archive', LEGACY_COMMIT, 'data'], cwd=ROOT)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for item in tar.getmembers():
                if item.isdir(): continue
                if not item.isfile() or not safe_path(item.name) or not item.name.startswith('data/'):
                    raise ValueError('Unsafe original input material')
                p = data/item.name.removeprefix('data/'); p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(tar.extractfile(item).read())
        frozen = code_inventory()
        for name, digest in frozen.items():
            old = subprocess.check_output(['git', 'show', LEGACY_COMMIT+':'+name], cwd=ROOT)
            if sha(old) != digest: raise ValueError('Legacy frozen processor no longer identical: '+name)
        now = datetime.now(timezone.utc)
        provenance = {'sourceRunId':'38494657009', 'runAttempt':1, 'workflowPath':'.github/workflows/ci.yml',
            'status':'completed', 'conclusion':'success', 'codeSha':LEGACY_COMMIT, 'processorCommit':LEGACY_COMMIT,
            'evidenceKind':'original-approved-artifact-build; not a new acquisition run'}
        slot = {'timezone':'Asia/Taipei', 'targetDate':'2026-10-13', 'event':'legacy-import-plan',
                'slot':'original-existing-release', 'startedAt':now.isoformat(), 'deadline':(now+timedelta(hours=1)).isoformat()}
        closure = legacy_import_plan(original, data, provenance, slot)
        verify_closure(closure)
        public = site_files(original)
        proof = {'schemaVersion':1, 'scope':'original-byte preservation and offline legacy closure, not remote initialization/live acceptance',
            'originalArtifactId':11862513391, 'originalRunId':38494657009, 'originalPagesRunId':38496725153,
            'originalCommit':LEGACY_COMMIT, 'originalZipSha256':sha(original), 'originalZipBytes':len(original),
            'publicDataSha256':sha(public['market.json']), 'manifestSha256':sha(public['release-manifest.json']),
            'files':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in public.items()},
            'assets':{n:{'sha256':sha(b),'bytes':len(b)} for n,b in closure.items()},
            'frozenCodeInventory':frozen, 'projectionReproduced':True, 'responseBodiesArchived':False,
            'liveHttpsAcceptance':'BLOCKED: must be performed in separately authorized 4C-2C',
            'remoteReleasesInitialized':False, 'remoteStateInitialized':False, 'pagesDeployed':False}
        result = temp/'result'; result.mkdir()
        for n,b in closure.items(): (result/n).write_bytes(b)
        (result/'original-rc-proof.json').write_bytes(canonical(proof))
        (result/'portable-legacy-import.zip').write_bytes(zip_bytes({**closure,'original-rc-proof.json':canonical(proof)}))
        publish_directory(result, output)
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('original_zip', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(preserve(args.original_zip, args.output), ensure_ascii=False, indent=2))
