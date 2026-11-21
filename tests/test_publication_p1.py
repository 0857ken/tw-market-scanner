"""Real archive-boundary faults and regressions for the audited P1 gaps."""
import copy
from datetime import timedelta
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from pipeline.acquisition_state import unpack, validate_files
from pipeline.common import ROOT
from pipeline.publication_contract import canonical, sha, site_files, zip_bytes
from pipeline.pages_artifact import verify as verify_pages_artifact
from pipeline.persistent_state import StateSnapshot
from pipeline.verified_baseline import _success_chain
from tests.publication_fixture import Fixture, NOW, EXPIRES


def cases(*ids):
    def decorate(fn):
        fn.matrix_ids = ids
        return fn
    return decorate


CRASH_SCRIPT = r'''
import os,sys
from pathlib import Path
from unittest.mock import patch
from pipeline.acquisition_state import unpack,pack
from pipeline.daily_release import controlled
from pipeline.candidate_io import publish_directory
from pipeline.common import ROOT
from tests.publication_fixture import NOW
source,output,mode=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
def acquire(data_dir,now,**kwargs):
    unpack(source.read_bytes(),kwargs['output_dir'])
    return 0
def export(root):
    if mode=='before-pack':os._exit(91)
    return pack(root)
original_link=os.link
def link(src,dst,*args,**kwargs):
    if Path(dst).name=='acquisition-state.zip' and mode=='zip-before-link':os._exit(92)
    return original_link(src,dst,*args,**kwargs)
def publish(src,dst):
    if Path(dst)==output:
        if mode=='before-publish':os._exit(93)
        result=publish_directory(src,dst)
        if mode=='after-publish':os._exit(94)
        return result
    return publish_directory(src,dst)
with patch('socket.create_connection',side_effect=AssertionError('No network')), \
     patch('pipeline.daily_release.run_daily',side_effect=acquire), \
     patch('pipeline.acquisition_state.pack',side_effect=export), \
     patch('pipeline.candidate_io.os.link',side_effect=link), \
     patch('pipeline.daily_release.publish_directory',side_effect=publish):
    assert controlled(ROOT/'data',output,'2026-10-14',NOW,'1001',True)=='candidate'
'''


class PublicationP1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.network = patch('socket.create_connection', side_effect=AssertionError('OFFLINE: no real network'))
        cls.network_spy = cls.network.start()
        try:
            cls.fixture = Fixture()
        except BaseException:
            cls.network.stop(); raise

    @classmethod
    def tearDownClass(cls):
        try:
            cls.fixture.close()
            if cls.network_spy.call_count:
                raise AssertionError('Offline P1 tests attempted network')
        finally:
            cls.network.stop()

    @cases('B03', 'B05')
    def test_independent_replay_covers_full_history_institutions_index_margin_and_futures(self):
        original = unpack(self.fixture.old['acquisition-state.zip'])
        payload = json.loads(original['market.json'])
        targets = ['index', 'futures', 'institutional', 'margin', 'missing-price', 'omitted-history', 'market-cap']
        for target in targets:
            p = copy.deepcopy(payload)
            if target == 'index': p['indexHistory'][0]['close'] += 1
            elif target == 'futures': p['futures'][0]['foreign'] += 1
            elif target == 'institutional': next(s for s in p['stocks'] if s['market']=='TPEx' and s['institutional'])['institutional'][0]['foreignShares'] += 1
            elif target == 'margin': next(s for s in p['stocks'] if s['margin'])['margin']['usagePct'] += 1
            elif target == 'market-cap': next(s for s in p['stocks'] if s['marketCapM'])['marketCapM'] += 1
            else:
                stock = next(s for s in p['stocks'] if len(s['history'])>1 and s['history'][0]['close'] is not None)
                if target == 'omitted-history': stock['history'].pop(0)
                else: stock['history'][0].update(close=None,rawClose=None)
            files = {**original, 'market.json': canonical(p)}
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'Complete acquisition replay'):
                validate_files(files)

    @cases('A05', 'B07')
    def test_unknown_archive_fields_rejected_at_all_nonraw_levels(self):
        original = unpack(self.fixture.old['acquisition-state.zip'])
        for name in ('market.json', 'source-state.json', 'quality.json', 'daily-attempt.json'):
            value = json.loads(original[name]); value['contactEmail'] = 'private@example.invalid'
            with self.subTest(name=name), self.assertRaises(ValueError):
                validate_files({**original, name: canonical(value)})
        for name in ('market.json','source-state.json','quality.json','daily-attempt.json'):
            value = json.loads(original[name])
            next(iter(value['sources'].values()))['nestedContact'] = {'email':'private@example.invalid'}
            with self.subTest(nested=name), self.assertRaisesRegex(ValueError, 'Unknown archive fields'):
                validate_files({**original, name: canonical(value)})
        value = json.loads(original['quality.json']); value['coverage']['TWSE']['ownerContact'] = 'private'
        with self.assertRaisesRegex(ValueError, 'Unknown archive fields'):
            validate_files({**original, 'quality.json':canonical(value)})

    @cases('B01', 'B03')
    def test_success_requires_real_approval_bytes_and_exact_bindings(self):
        snap = self.fixture.store.read()
        success = json.loads(snap.files['successes/g0.json'])
        digest = success['approvalSha256']; path = 'approvals/'+digest+'.json'
        for mode in ('missing','corrupt','zip_sha','seed_sha','code_sha','deployment_id','expected_generation','expires_at','origin'):
            files = dict(snap.files); record = copy.deepcopy(success); state = copy.deepcopy(snap.state)
            if mode == 'missing': files.pop(path)
            elif mode == 'corrupt': files[path] += b'corruption'
            else:
                approval = json.loads(files[path])
                if mode == 'origin': approval['authorityKind'] = 'owner-reviewed'
                elif mode == 'expires_at': approval[mode] = (NOW-timedelta(seconds=1)).isoformat()
                elif mode == 'expected_generation': approval[mode] = 1
                else: approval[mode] = 'a'*(40 if mode=='code_sha' else 64)
                body = canonical(approval); record['approvalSha256'] = sha(body)
                files['approvals/'+sha(body)+'.json'] = body
                files['successes/g0.json'] = canonical(record)
                state['successfulPointer']['successRecordSha256'] = sha(canonical(record))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                _success_chain(StateSnapshot(snap.head,state,files), offline=True)
        with self.assertRaisesRegex(ValueError, 'Offline approval'):
            _success_chain(snap,offline=False)
        self.assertEqual(_success_chain(snap,offline=True)['kind'],'legacy-import')

    def artifact(self, *, altered=None):
        files = site_files(self.fixture.new['site.zip']); stream = io.BytesIO()
        if altered == 'bytes': files['index.html'] += b'tamper'
        if altered == 'extra': files['extra.json'] = b'{}'
        with tarfile.open(fileobj=stream,mode='w') as archive:
            for name,body in files.items():
                info=tarfile.TarInfo('./'+name);info.size=len(body);archive.addfile(info,io.BytesIO(body))
            if altered == 'link':
                info=tarfile.TarInfo('linked');info.type=tarfile.SYMTYPE;info.linkname='index.html';archive.addfile(info)
        body=zip_bytes({'artifact.tar':stream.getvalue()})
        producer={'runId':1001,'runAttempt':1,'headSha':self.fixture.commit,'workflowPath':'.github/workflows/package-daily.yml'}
        meta={'id':77,'name':'github-pages','expired':False,'size_in_bytes':len(body),'digest':'sha256:'+sha(body),
              'created_at':NOW.isoformat(),'workflow_run':{'id':1001,'repository_id':1412557806,'head_repository_id':1412557806,'head_sha':self.fixture.commit}}
        run={'id':1001,'run_attempt':1,'head_sha':self.fixture.commit,'path':producer['workflowPath'],
             'status':'completed','conclusion':'success','repository':{'id':1412557806,'full_name':'0857ken/tw-market-scanner'},
             'run_started_at':(NOW-timedelta(minutes=1)).isoformat(),'updated_at':(NOW+timedelta(minutes=1)).isoformat()}
        def api(method,path,payload=None,*,binary=False):
            self.assertEqual(method,'GET')
            return {'/actions/artifacts/77':meta,'/actions/runs/1001/attempts/1':run,'/actions/artifacts/77/zip':body}[path]
        return api,meta,run,producer

    @cases('P01', 'P03', 'B04')
    def test_pages_artifact_binds_approved_bytes_repository_and_attempt(self):
        api,meta,run,producer=self.artifact()
        proof=verify_pages_artifact(api,77,self.fixture.new['site.zip'],producer)
        self.assertEqual(proof['siteZipSha256'],sha(self.fixture.new['site.zip']))
        for mode in ('bytes','extra','link','digest','attempt','fork','time'):
            api,meta,run,producer=self.artifact(altered=mode)
            if mode=='digest':meta['digest']='sha256:'+'a'*64
            if mode=='attempt':run['run_attempt']=2
            if mode=='fork':meta['workflow_run']['head_repository_id']=1
            if mode=='time':meta['created_at']=(NOW-timedelta(days=1)).isoformat()
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                verify_pages_artifact(api,77,self.fixture.new['site.zip'],producer)

    def test_pure_genesis_requires_pinned_owner_approval_fresh_live_and_real_index_bindings(self):
        from pipeline.legacy_genesis import build
        from tests.publication_fixture import verifier
        closure = self.fixture.old; ref = self.fixture.old_ref
        index = self.fixture.archive.load(ref)[1]
        snap = self.fixture.store.read(); record = json.loads(snap.files['successes/g0.json'])
        approval = json.loads(snap.files['approvals/'+record['approvalSha256']+'.json'])
        approval['authorityKind']='owner-reviewed'; approval['reference']='synthetic-owner-record-only'
        approval['deployment_id']='original-offline-proof'
        ab=canonical(approval); live=verifier(self.fixture.live).verify(closure['site.zip'])
        deployment={'id':'original-offline-proof','rawStatus':'succeed','status':'success','runId':38496725153,
                    'jobId':115634120612,'pagesArtifactId':11864511360,'source':'verified-original-Pages-run','logsSha256':'a'*64}
        files=build(closure,ref,index,live,ab,sha(ab),deployment,NOW)
        self.assertEqual(json.loads(files['state.json'])['successfulPointer']['generation'],0)
        for mode in ('approval','stale-live','index','deployment'):
            wrong_index=copy.deepcopy(index); wrong_deployment=copy.deepcopy(deployment)
            if mode=='index':wrong_index['assets']['site.zip']['id']=ref['indexAssetId']
            if mode=='deployment':wrong_deployment['status']='pending'
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                build(closure,ref,wrong_index,live,ab,'b'*64 if mode=='approval' else sha(ab),wrong_deployment,
                      NOW+timedelta(seconds=61) if mode=='stale-live' else NOW)

    @cases('B08')
    def test_process_exit_at_real_closure_export_and_publication_boundaries(self):
        before={p.relative_to(ROOT/'data').as_posix():sha(p.read_bytes()) for p in (ROOT/'data').rglob('*') if p.is_file()}
        source=self.fixture.root/'package'/'acquisition-state.zip'
        for mode,code in [('before-pack',91),('zip-before-link',92),('before-publish',93),('after-publish',94),('normal',0)]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as t:
                output=Path(t)/'candidate'
                result=subprocess.run([sys.executable,'-c',CRASH_SCRIPT,str(source),str(output),mode],cwd=ROOT,capture_output=True,text=True,timeout=90)
                self.assertEqual(result.returncode,code,result.stderr)
                if mode in ('after-publish','normal'):
                    self.assertEqual(set(p.name for p in output.iterdir()), {'gate.json','candidate-market.json','candidate-report.json','acquisition-state.zip','update-attempt.json'})
                    # Fresh independent replay after the writer has exited.
                    restored=unpack((output/'acquisition-state.zip').read_bytes())
                    self.assertEqual(json.loads(restored['market.json'])['asOf'],'2026-10-14')
                else:self.assertFalse(output.exists())
                after={p.relative_to(ROOT/'data').as_posix():sha(p.read_bytes()) for p in (ROOT/'data').rglob('*') if p.is_file()}
                self.assertEqual(before,after)
