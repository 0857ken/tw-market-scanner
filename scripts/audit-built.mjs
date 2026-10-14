// Read-only readiness measurements. This script cannot merge, publish or fetch finance data.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import assert from 'node:assert/strict';
import {performance} from 'node:perf_hooks';
import {validateMarket} from '../frontend/src/data.js';
import {getSignals} from '../frontend/src/logic.js';
const dist=path.resolve('frontend/dist'),html=fs.readFileSync(path.join(dist,'index.html'),'utf8');
const body=fs.readFileSync(path.join(dist,'market.json'));
const payload=validateMarket(JSON.parse(body));
assert.ok(html.includes('Content-Security-Policy')&&html.includes("object-src 'none'"));
assert.ok(fs.existsSync(path.join(dist,'.nojekyll')));
const urls=[...html.matchAll(/(?:src|href)="([^"#]+)"/g)].map(m=>m[1]);
for(const url of urls){assert.ok(url.startsWith('./'),'Assets must stay within the repository subpath');assert.ok(fs.existsSync(path.join(dist,url)));}
const js=fs.readdirSync(path.join(dist,'assets')).filter(f=>f.endsWith('.js'));
const jsGzip=js.reduce((n,f)=>n+zlib.gzipSync(fs.readFileSync(path.join(dist,'assets',f))).length,0);
const timings={};
for(const scope of ['TWSE','TPEx','ALL']){const start=performance.now();const s=getSignals(payload,scope,'adjusted');timings[scope]=Math.round((performance.now()-start)*100)/100;assert.equal(s.hits.length,0);assert.equal(s.coverage.adjusted,0);}
assert.ok(body.length<8*1024*1024,'Observation snapshot exceeded 8 MiB budget');
assert.ok(jsGzip<300*1024,'JavaScript gzip exceeded 300 KiB budget');
assert.ok(Math.max(...Object.values(timings))<2000,'Signal computation exceeded 2 s budget');
const result={type:'offline-build-readiness',asOf:payload.asOf,stockCount:payload.stocks.length,marketBytes:body.length,marketGzipBytes:zlib.gzipSync(body).length,javascriptGzipBytes:jsGzip,signalMs:timings,relativeAssets:urls.length,cspMeta:true,nojekyll:true,actualPagesHeadersVerified:false,deployAuthorized:false};
fs.mkdirSync('test-results',{recursive:true});fs.writeFileSync('test-results/stage3d-build-audit.json',JSON.stringify(result,null,2));
console.log(JSON.stringify(result));
