import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from pipeline.common import ROOT
from pipeline.observation_release import check
from pipeline.verify_rc import verify


class VerifyRCTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'rc.zip'
        market, report = check((ROOT/'data/market.json').read_bytes())
        self.commit = 'a'*40
        self.data_sha = report['publishedDataSha256']
        self.day = report['asOf']
        self.files = {'index.html': b"connect-src 'self'; object-src 'none'", 'market.json':market,'.nojekyll':b''}
        manifest = {**report,'candidateCommit':self.commit,'localTreeDirty':False,
                    'assets':{n:hashlib.sha256(v).hexdigest() for n,v in self.files.items()}}
        self.files['release-manifest.json'] = json.dumps(manifest).encode()
        self.pack()

    def pack(self):
        with zipfile.ZipFile(self.path,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for n,b in self.files.items():z.writestr(n,b)
        self.zip_sha = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_valid_bundle_is_not_publication_permission(self):
        report = verify(self.path,self.zip_sha,self.commit,self.data_sha,self.day)
        self.assertTrue(report['verified'])
        self.assertFalse(report['publicationAuthorized'])

    def test_zip_commit_data_and_date_must_be_exact(self):
        expected = [self.zip_sha,self.commit,self.data_sha,self.day]
        for i,replacement in enumerate(('0'*64,'b'*40,'0'*64,'2000-01-01')):
            args = expected.copy();args[i] = replacement
            with self.assertRaises(ValueError):verify(self.path,*args)

    def test_unapproved_resource_or_path_is_rejected(self):
        for name in ('market.example.json','../outside.txt','../outside/'):
            self.files[name] = b'{}';self.pack()
            with self.assertRaises(ValueError):verify(self.path,self.zip_sha,self.commit,self.data_sha,self.day)
            del self.files[name]

    def test_changed_asset_requires_new_zip_and_inventory_review(self):
        self.files['index.html'] += b' altered';self.pack()
        with self.assertRaises(ValueError):verify(self.path,self.zip_sha,self.commit,self.data_sha,self.day)
