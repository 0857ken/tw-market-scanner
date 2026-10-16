"""Consume an independently validated candidate and a pinned frontend ZIP; no build/network."""
import argparse,json,tempfile,zipfile
from pathlib import Path
from .common import read_json,write_json
from .daily_release import sha,encoded,bundle,verify_bundle,safe_name,STATIC_ID
from .candidate_io import candidate_destination, exclusive_lock, publish_directory
from . import daily_policy

def _package(candidate,seed_zip,expected_seed_sha,output):
 daily_policy.check_seed(expected_seed_sha)
 candidate,output=Path(candidate),Path(output);output.mkdir(parents=True,exist_ok=True)
 if (candidate/'failure.json').exists():raise ValueError('Failure evidence cannot be packaged')
 gate=read_json(candidate/'gate.json');report=read_json(candidate/'candidate-report.json');body=(candidate/'candidate-market.json').read_bytes()
 if gate['decision']!='candidate':raise ValueError('No-op/revision/failure cannot be published')
 if sha(body)!=report['publishedDataSha256'] or report['runId']!=gate['runId']:raise ValueError('Candidate data/run mismatch')
 if gate.get('candidatePolicySha256')!=daily_policy.digest() or report.get('candidatePolicySha256')!=daily_policy.digest():raise ValueError('Candidate policy binding mismatch')
 if gate.get('target')!=report['asOf']:raise ValueError('Candidate target binding mismatch')
 if sha(Path(seed_zip).read_bytes())!=expected_seed_sha:raise ValueError('Pinned frontend ZIP digest mismatch')
 with tempfile.TemporaryDirectory() as t:
  seed=Path(t)
  with zipfile.ZipFile(seed_zip) as z:
   names=z.namelist()
   if len(names)!=len(set(names)) or not all(safe_name(n) for n in names) or sum(i.file_size for i in z.infolist())>12*1024*1024:raise ValueError('Unsafe frontend seed')
   manifest=json.loads(z.read('release-manifest.json'));assets=manifest['frontendAssets']
   if manifest['frontendId']!=STATIC_ID:raise ValueError('Wrong frontend seed')
   for n,digest in assets.items():
    if not safe_name(n) or n in ('market.json','release-manifest.json'):raise ValueError('Unsafe static seed asset')
    b=z.read(n)
    if sha(b)!=digest:raise ValueError('Static seed digest mismatch')
    (seed/n).parent.mkdir(parents=True,exist_ok=True);(seed/n).write_bytes(b)
   write_json(seed/'frontend-pin.json',{'frontendId':STATIC_ID,'assets':assets})
  receipt=bundle(body,report,seed,output/'daily-release.zip')
  verify_bundle(output/'daily-release.zip',receipt,seed)
  write_json(output/'receipt.json',receipt)
 return receipt
def package(candidate,seed_zip,expected_seed_sha,output):
 output=candidate_destination(candidate,output)
 with exclusive_lock(output.parent/('.'+output.name+'.lock')),tempfile.TemporaryDirectory(prefix='.package-',dir=output.parent) as t:
  candidate_destination(candidate,output)
  staged=Path(t)/'result'
  receipt=_package(candidate,seed_zip,expected_seed_sha,staged)
  publish_directory(staged,output)
  return receipt
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',required=True);p.add_argument('--seed-zip',required=True);p.add_argument('--seed-sha256',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(package(a.candidate,a.seed_zip,a.seed_sha256,a.output)))
