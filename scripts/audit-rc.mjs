// No network. Verifies the exact artifact and its non-publication boundaries.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {validateMarket} from '../frontend/src/data.js';
import {getSignals} from '../frontend/src/logic.js';
import {observationSignals} from '../frontend/src/observation.js';
const dist=path.resolve('frontend/dist-rc');
const manifest=JSON.parse(fs.readFileSync(path.join(dist,'release-manifest.json')));
for(const [relative,expected] of Object.entries(manifest.assets)){
  assert.ok(!relative.includes('..')&&!path.isAbsolute(relative));
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(dist,relative))).digest('hex'),expected);
}
assert.equal(manifest.publishedDataSha256,manifest.assets['market.json']);
assert.equal(manifest.deploymentAuthorized,false);
const data=validateMarket(JSON.parse(fs.readFileSync(path.join(dist,'market.json'))));
assert.equal(data.mode,'live');
assert.equal(data.observationProfile.profile,'observation-only');
assert.equal(data.creditHistory.length,0);
assert.ok(data.stocks.filter(s=>s.market==='TWSE').every(s=>!s.institutional.length));
assert.ok(!/(?:ghp_|github_pat_|AKIA)[A-Za-z0-9]{16,}/.test(fs.readFileSync(path.join(dist,'market.json'),'utf8')));
for(const scope of ['ALL','TWSE','TPEx']){
  const s=observationSignals(getSignals(data,scope,'adjusted'));
  assert.equal(s.hits.length,0);assert.equal(s.creditNow,null);
  assert.ok(s.latest.every(r=>r.ma240===null&&r.breakout240===false));
}
for(const workflow of ['ci.yml','deploy.yml']){
  const body=fs.readFileSync(`.github/workflows/${workflow}`,'utf8');
  assert.ok(!/^\s+schedule:/m.test(body));
  assert.ok(!/uses:\s*actions\/(?:deploy-pages|configure-pages|upload-pages-artifact)@/.test(body));
  assert.ok(!/pages:\s*write|id-token:\s*write/.test(body));
}
console.log('RC inventory, no secrets matching token patterns, approved profile, frozen signals and no-publication workflow audit passed. Pattern scan is not a guarantee of absence of all secrets.');
