"""Offline package -> verify -> simulated replacement -> restore exact prior bytes."""
import argparse,json,os,shutil,tempfile,zipfile
from datetime import datetime
from pathlib import Path
from pipeline.common import ROOT,TPE,read_json,write_json
from pipeline.daily_state import commit,restore
from pipeline.daily_release import project,bundle,verify_bundle,controlled
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'test-results/stage4c1')
out=parser.parse_args().output;out.mkdir(parents=True,exist_ok=False)
seed=ROOT/'frontend/dist-daily'
now=datetime.now(TPE)
p=read_json(ROOT/'data/market.json')
run_id='ci-fixture-'+os.environ.get('GITHUB_RUN_ID','local')
# Offline no-op rehearsal uses the fixture's source day, without claiming it is current.
controlled(ROOT/'data',out/'offline',p['asOf'],now,run_id)
body,report=project(p,run_id,now)
archive=out/'daily-preview.zip'
receipt=bundle(body,report,seed,archive);verify_bundle(archive,receipt,seed)
with tempfile.TemporaryDirectory(prefix='scanner-restore-') as t:
 previous=Path(t)/'previous';next_site=Path(t)/'next';restored=Path(t)/'restored'
 with zipfile.ZipFile(archive) as z:z.extractall(previous)
 # A different package version demonstrates data revisions without rebuilding assets.
 r2={**report,'runId':'offline-next-fixture'};new=Path(t)/'next.zip';receipt2=bundle(body,r2,seed,new);verify_bundle(new,receipt2,seed)
 store=Path(t)/'ledger';commit(store,archive,receipt,seed);commit(store,new,receipt2,seed,receipt['zipSha256']);restore(store,receipt['zipSha256'],seed,receipt2['zipSha256'])
 assert read_json(store/'current.json')['zipSha256']==receipt['zipSha256']
 with zipfile.ZipFile(new) as z:z.extractall(next_site)
 with zipfile.ZipFile(archive) as z:z.extractall(restored)
 assert {p.relative_to(previous).as_posix():p.read_bytes() for p in previous.rglob('*') if p.is_file()}=={p.relative_to(restored).as_posix():p.read_bytes() for p in restored.rglob('*') if p.is_file()}
 for n in report.get('frontendAssets',read_json(seed/'frontend-pin.json')['assets']):assert (previous/n).read_bytes()==(next_site/n).read_bytes()
for n in ('market.json','release-manifest.json'):
 with zipfile.ZipFile(archive) as z:(seed/n).write_bytes(z.read(n))
write_json(out/'receipt.json',receipt)
write_json(out/'dry-run.json',{'packaged':True,'allHashesVerified':True,'fixedFrontendReused':True,'restoreByteIdentical':True,'atomicCASLedgerAndPreviousBundle':True,'productionDeployed':False,'strategyComplete':False,'fixtureAsOf':p['asOf']})
print(json.dumps(receipt))
