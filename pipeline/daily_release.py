"""Isolated daily observation gate and immutable bundles. Never deploys."""
import argparse,copy,hashlib,io,json,os,re,shutil,tempfile,zipfile
from datetime import date,datetime,timedelta
from pathlib import Path
from .common import ROOT,TPE,read_json,write_json
from .daily import MODULES,quality,run_daily
from .observation_release import check as observation_check
from .run import SOURCES
from .current_csv import URL as CSV_URL
from .schema import validate
from .candidate_io import atomic_bytes, atomic_json, candidate_destination, exclusive_lock, publish_directory
from . import daily_policy
STATIC_ID='observation-daily-v1'
DISABLED={'moving-averages','breakouts','credit-strategy','twse-t86','adjusted-prices','historical-backtest','intraday','institutional-streaks'}
def sha(b):return hashlib.sha256(b).hexdigest()
def encoded(v):return (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
def identity(p):return sha(encoded({k:{f:p['sources'][k].get(f) for f in ('asOf','sha256','url')} for k in MODULES}))
def target_day(now,requested):
 local=now.astimezone(TPE);latest=local.date() if (local.hour,local.minute)>=(16,30) else local.date()-timedelta(days=1)
 target=date.fromisoformat(requested)
 if target>latest or (local.date()-target).days>1:raise ValueError('Target outside completed EOD window; retain original target for delayed runs')
 return target.isoformat()
def gate(p,baseline,target,policy=None):
 limits=daily_policy.load()
 validate(p);validate(baseline);policy=policy or read_json(ROOT/'config/source-publication.json')['modules']
 td=date.fromisoformat(target)
 for market,module in [('TWSE','quotes'),('TPEx','tpexQuotes')]:
  d=p['sources'][module]['asOf'];old=baseline['sources'][module]['asOf']
  if d<old:raise ValueError(market+': date regressed')
  if d>target:raise ValueError(market+': unexpected target date')
 dates=[p['sources'][m]['asOf'] for m in ('quotes','tpexQuotes')]
 if len(set(dates))!=1:raise ValueError('Markets unsynchronized')
 for module in MODULES:
  s=p['sources'][module];allowed={SOURCES[module][1]}|({CSV_URL} if module=='quotes' else set())
  if policy[module]['status']!='verified-open-data' or s.get('licenseStatus')!='verified-open-data':raise ValueError(module+': license missing')
  if s.get('url') not in allowed or not re.fullmatch('[a-f0-9]{64}',s.get('sha256','')):raise ValueError(module+': unapproved source/version')
  if s.get('fetchStatus')!='ok' or s.get('status') in ('error','unavailable','imported'):raise ValueError(module+': source failed')
  if module!='calendar' and s['asOf']>target:raise ValueError(module+': future source')
 if p['mode']!='live' or p['creditHistory'] or p['creditRule']['status']!='pending':raise ValueError('Real data and frozen credit required')
 q,oldq=quality(p),quality(baseline)
 for market in ('TWSE','TPEx'):
  x,old=q[market],oldq[market]
  if not x['total'] or not old['total'] or x['coveragePct']<limits['minimumPriceCoveragePct'] or x['coveragePct']<old['coveragePct']-limits['maximumCoverageDropPercentagePoints']:raise ValueError(market+': coverage abnormal')
  delta=limits['maximumRosterRelativeChange']
  if not 1-delta<=x['total']/old['total']<=1+delta:raise ValueError(market+': roster size abnormal')
 unchanged=identity(p)==identity(baseline)
 closed=td.weekday()>=5 or any(r['date']==target and r['closed'] for r in p['calendar']['rows'])
 if closed:
  if dates[0]==target or not unchanged:raise ValueError('Closed-day data change requires review')
  return 'no-op-closed'
 if target[:4] not in {r['date'][:4] for r in p['calendar']['rows']}:
  raise ValueError('Calendar year unknown; do not guess cross-year sessions')
 if dates[0]!=target:raise ValueError('Sources delayed; not a closure certification')
 if p['sources']['tpexInstitutional']['asOf']!=target:raise ValueError('TPEx institutional date mismatch')
 for m in ('companies','tpexCompanies'):
  if (td-date.fromisoformat(p['sources'][m]['asOf'])).days>limits['maximumRosterAgeCalendarDays']:raise ValueError('Roster older than configured calendar-day limit')
 if dates[0]==baseline['sources']['quotes']['asOf']:
  if not unchanged:raise ValueError('Same-day revision requires separate review')
  return 'no-op-identical'
 return 'candidate'
def project(p,run_id,now):
 daily_policy.load()
 a=copy.deepcopy(read_json(ROOT/'config/observation-release.json'))
 if not DISABLED<=set(a['disabled']):raise ValueError('Frozen features missing')
 body=encoded(p);a.update(approvedInputSha256=sha(body),approvedAsOf=p['asOf'],version=f"eod-{p['asOf']}-{identity(p)[:12]}")
 published,r=observation_check(body,a,now=now)
 r.update(frontendId=STATIC_ID,runId=str(run_id),sourceIdentitySha256=identity(p),licensePolicySha256=sha((ROOT/'config/source-publication.json').read_bytes()),processorCommit=os.environ.get('RC_COMMIT_SHA',os.environ.get('GITHUB_SHA','local-uncommitted-dry-run')),releaseKind='daily-observation-dry-run')
 r.update(candidatePolicySha256=daily_policy.digest(),productionBaselineVerified=False)
 return published,r
def verify_snapshot_links(p,data_dir):
 """Parsed snapshots and exported current prices must refer to the same version."""
 snapshots={}
 for module in MODULES:
  source=p['sources'][module]
  snap=read_json(Path(data_dir)/'raw'/f"{module}_{source['asOf']}.json")
  if not snap or snap['sha256']!=source['sha256'] or snap['url']!=source['url']:
   raise ValueError(module+': snapshot provenance mismatch')
  snapshots[module]=snap
 maps={m:{r['symbol']:r for r in snapshots[m]['rows']} for m in ('quotes','tpexQuotes')}
 for stock in p['stocks']:
  module='quotes' if stock['market']=='TWSE' else 'tpexQuotes';day=p['sources'][module]['asOf']
  raw=maps[module].get(stock['symbol']);row=next((r for r in stock['history'] if r['date']==day),None)
  if raw and (not row or any(row.get(k)!=raw.get(k) for k in ('close','volumeShares','changeAmount'))):
   raise ValueError(stock['symbol']+': current price differs from licensed snapshot')
  if not raw and row and row.get('close') is not None:raise ValueError('Invented missing price')
def safe_name(n):return n in ('index.html','.nojekyll','market.json','release-manifest.json') or bool(re.fullmatch(r'assets/[A-Za-z0-9_.-]+\.(js|css)',n))
def bundle(body,report,seed,destination):
 daily_policy.load()
 seed,destination=Path(seed),Path(destination);pin=read_json(seed/'frontend-pin.json');files={}
 if pin['frontendId']!=STATIC_ID:raise ValueError('Frontend identity mismatch')
 for n,digest in pin['assets'].items():
  if not safe_name(n) or n in ('market.json','release-manifest.json'):raise ValueError('Unsafe frontend inventory')
  b=(seed/n).read_bytes()
  if sha(b)!=digest:raise ValueError('Frontend asset changed')
  files[n]=b
 if not {'index.html','.nojekyll'}<=files.keys():raise ValueError('Incomplete frontend')
 files['market.json']=body
 m={**report,'frontendAssets':pin['assets'],'frontendPinSha256':sha(encoded(pin)),'assets':{n:sha(b) for n,b in files.items()}}
 files['release-manifest.json']=encoded(m)
 buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as z:
  for n,b in sorted(files.items()):
   i=zipfile.ZipInfo(n,(2020,1,1,0,0,0));i.compress_type=zipfile.ZIP_DEFLATED;z.writestr(i,b)
 archive=buffer.getvalue()
 receipt={'zipSha256':sha(archive),'manifestSha256':sha(files['release-manifest.json']),'dataSha256':sha(body),'version':report['version'],'runId':report['runId'],'frontendPinSha256':m['frontendPinSha256'],'deploymentAuthorized':False}
 # Validate before making the final ZIP name visible, including frozen data scope.
 verify_bundle_bytes(archive,receipt,seed)
 atomic_bytes(destination,archive,immutable=True)
 return receipt
def verify_bundle(path,receipt,seed):
 return verify_bundle_bytes(Path(path).read_bytes(),receipt,seed)
def verify_bundle_bytes(body,receipt,seed):
 daily_policy.load()
 if sha(body)!=receipt['zipSha256'] or len(body)>16*1024*1024:raise ValueError('ZIP digest/size mismatch')
 with zipfile.ZipFile(io.BytesIO(body)) as z:
  names=z.namelist()
  if len(names)!=len(set(names)) or not all(safe_name(n) for n in names) or sum(i.file_size for i in z.infolist())>12*1024*1024:raise ValueError('Unsafe ZIP')
  mb=z.read('release-manifest.json');m=json.loads(mb);pin=read_json(Path(seed)/'frontend-pin.json')
  if sha(mb)!=receipt['manifestSha256'] or set(names)!=set(m['assets'])|{'release-manifest.json'}:raise ValueError('Manifest mismatch')
  if m['frontendAssets']!=pin['assets'] or m['frontendPinSha256']!=sha(encoded(pin)):raise ValueError('Frontend pin mismatch')
  for n,digest in m['assets'].items():
   if sha(z.read(n))!=digest:raise ValueError('Asset digest mismatch')
  for n,digest in pin['assets'].items():
   if m['assets'].get(n)!=digest:raise ValueError('Static frontend changed')
  if any(m[k]!=receipt[v] for k,v in [('publishedDataSha256','dataSha256'),('version','version'),('runId','runId')]):raise ValueError('Ledger mismatch')
  b=z.read('market.json');p=json.loads(b);validate(p)
  if m.get('candidatePolicySha256')!=daily_policy.digest():raise ValueError('Candidate policy changed; review again')
  if m['licensePolicySha256']!=sha((ROOT/'config/source-publication.json').read_bytes()):raise ValueError('License policy changed; review again')
  policy=read_json(ROOT/'config/source-publication.json')['modules']
  for module in MODULES:
   s=p['sources'][module]
   if policy[module]['status']!='verified-open-data' or s.get('licenseStatus')!='verified-open-data' or s.get('fetchStatus')!='ok':raise ValueError('Source authorization/status failed')
   if s.get('url') not in {SOURCES[module][1]}|({CSV_URL} if module=='quotes' else set()):raise ValueError('Source URL failed')
   if m['sourceVersions'][module]['sha256']!=s['sha256'] or m['sourceVersions'][module]['asOf']!=s['asOf']:raise ValueError('Source manifest mismatch')
  if sha(b)!=receipt['dataSha256'] or p['asOf']!=m['asOf'] or p['mode']!='live':raise ValueError('Data digest/date mismatch')
  if p['creditHistory'] or p['futures'] or p['indexHistory'] or p['creditRule']['status']!='pending':raise ValueError('Frozen scope violated')
  if not DISABLED<=set(p['observationProfile']['disabled']):raise ValueError('Disabled features missing')
  if any(s.get('margin') or s.get('intraday') for s in p['stocks']):raise ValueError('Non-observation stock data')
  if any(s.get('institutional') for s in p['stocks'] if s['market']=='TWSE') or any(r.get('adjustedClose') is not None for s in p['stocks'] for r in s['history']):raise ValueError('Unapproved data')
  if m.get('productionBaselineVerified') is not False:raise ValueError('Candidate cannot certify a production baseline')
  if m['strategyComplete'] is not False or m['deploymentAuthorized'] is not False:raise ValueError('Unexpected release permission')
 return True
def controlled(data_dir,output,target,now,run_id,fetch_current=False):
 daily_policy.load()
 output=candidate_destination(data_dir,output)
 with exclusive_lock(output.parent/('.'+output.name+'.lock')), tempfile.TemporaryDirectory(prefix='.controlled-',dir=output.parent) as t:
  candidate_destination(data_dir,output)
  work=Path(t);evidence=work/'evidence';evidence.mkdir()
  try:
   baseline=read_json(Path(data_dir)/'market.json');stage=Path(data_dir)
   if fetch_current:
    stage=work/'updated-data'
    code=run_daily(data_dir,now,twse_current_csv=True,stop_on_failure=True,output_dir=stage)
    attempt=read_json(stage/'daily-attempt.json') if code==0 else read_json(stage.with_name(stage.name+'.attempt.json'))
    write_json(evidence/'update-attempt.json',attempt)
    if code:raise ValueError('Official update failed; no fallback or publication')
   p=read_json(stage/'market.json');verify_snapshot_links(p,stage);decision=gate(p,baseline,target)
   b,r=project(p,run_id,now)
   write_json(evidence/'gate.json',{'decision':decision,'target':target,'observedDates':{m:p['sources'][k]['asOf'] for m,k in [('TWSE','quotes'),('TPEx','tpexQuotes')]},'coverage':quality(p),'runId':str(run_id),'productionUnchanged':True,'baselineInputSha256':sha((Path(data_dir)/'market.json').read_bytes()),'candidatePolicySha256':daily_policy.digest(),'productionBaselineVerified':False})
   (evidence/'candidate-market.json').write_bytes(b);write_json(evidence/'candidate-report.json',r)
  except Exception as exc:
   # A failed attempt never retains a previous success gate or half-written candidate.
   for name in ('gate.json','candidate-market.json','candidate-report.json'):
    (evidence/name).unlink(missing_ok=True)
   write_json(evidence/'failure.json',{'error':str(exc),'runId':str(run_id),'productionUnchanged':True})
   publish_directory(evidence,output)
   raise
  publish_directory(evidence,output)
  return decision
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-dir',type=Path,default=ROOT/'data');p.add_argument('--output',type=Path,required=True);p.add_argument('--target-date',required=True);p.add_argument('--run-id',required=True);p.add_argument('--fetch-current',action='store_true');a=p.parse_args();now=datetime.now(TPE)
 controlled(a.data_dir,a.output,target_day(now,a.target_date),now,a.run_id,a.fetch_current)
