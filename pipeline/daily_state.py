"""Local-only atomic release ledger used by the dry-run, never a Pages deployment.
Immutable complete bundles; compare-and-swap prevents retries/stale workers overwriting.
"""
import os,shutil
from pathlib import Path
from .common import read_json,write_json
from .daily_release import sha,verify_bundle

def commit(store,archive,receipt,seed,expected_current=None):
 store=Path(store);store.mkdir(parents=True,exist_ok=True)
 fd=os.open(store/'.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 try:
  current=read_json(store/'current.json',{})
  if current.get('zipSha256')!=expected_current:raise ValueError('Stale release worker; CAS rejected')
  verify_bundle(archive,receipt,seed)
  digest=receipt['zipSha256'];destination=store/(digest+'.zip')
  if destination.exists():
   if sha(destination.read_bytes())!=digest:raise ValueError('Stored immutable bundle corrupted')
  else:
   with destination.open('xb') as out:out.write(Path(archive).read_bytes())
  ledger=store/(digest+'.json')
  entry={**receipt,'previousZipSha256':expected_current,'production':False}
  if ledger.exists() and read_json(ledger)!=entry:raise ValueError('Immutable ledger conflict')
  if not ledger.exists():write_json(ledger,entry)
  write_json(store/'current.json',entry)
  return entry
 finally:os.close(fd);(store/'.lock').unlink()

def restore(store,prior_sha,seed,expected_current):
 store=Path(store);receipt=read_json(store/(prior_sha+'.json'))
 if not receipt:raise ValueError('No verified previous complete version')
 # Restore is a rehearsal in a local store only; production requires separate authority.
 verify_bundle(store/(prior_sha+'.zip'),receipt,seed)
 fd=os.open(store/'.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 try:
  if read_json(store/'current.json',{}).get('zipSha256')!=expected_current:raise ValueError('Stale restore CAS rejected')
  write_json(store/'current.json',receipt)
 finally:os.close(fd);(store/'.lock').unlink()
 return receipt
