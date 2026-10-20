import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {fetchDailyMarket} from '../src/observation.js';
import {validateMarket} from '../src/data.js';
const original=JSON.parse(fs.readFileSync(new URL('../../data/market.json',import.meta.url)));
const profile=JSON.parse(fs.readFileSync(new URL('../../config/observation-release.json',import.meta.url)));
function fixture(version){
 const p=structuredClone(original);p.observationProfile={...profile,version};p.indexHistory=[];p.futures=[];p.creditHistory=[];
 p.stocks.forEach(s=>s.margin=null);
 const body=JSON.stringify(p),digest=crypto.createHash('sha256').update(body).digest('hex');
 return {body,manifest:{frontendId:'observation-daily-v1',profile:'observation-only',strategyComplete:false,version,asOf:p.asOf,publishedDataSha256:digest,assets:{'market.json':digest},disabled:profile.disabled,runId:'unit-fixture'}};
}
async function run(f,change=()=>{}){
 const before=globalThis.fetch,location=globalThis.location;globalThis.location={href:'https://example.test/tw-market-scanner/',origin:'https://example.test'};
 change(f);
 globalThis.fetch=async url=>new Response(String(url).includes('release-manifest.json')?JSON.stringify(f.manifest):f.body,{status:200});
 try{return await fetchDailyMarket('./market.json','observation-daily-v1',validateMarket)}finally{globalThis.fetch=before;globalThis.location=location}
}
test('daily loader verifies a new SHA per version with identical frontend',async()=>{
 const a=await run(fixture('day-a')),b=await run(fixture('day-b'));
 assert.notEqual(a.releaseIntegrity.dataSha256,b.releaseIntegrity.dataSha256);assert.equal(b.observationProfile.version,'day-b');
});
test('manifest/data hash, scope, version and frontend mismatch rejected',async()=>{
 for(const mutate of [f=>f.body='{}',f=>f.manifest.frontendId='other',f=>f.manifest.disabled=[],f=>f.manifest.version='wrong',f=>f.manifest.sourceVersions={quotes:{sha256:'a'.repeat(64),asOf:'2026-10-13'}}])await assert.rejects(run(fixture('day-a'),mutate));
});
