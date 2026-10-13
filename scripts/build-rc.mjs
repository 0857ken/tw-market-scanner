// Offline, pinned-data build; never creates a release, branch, schedule or deployment.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
import {spawnSync,execFileSync} from 'node:child_process';
import zlib from 'node:zlib';
const root=path.resolve(import.meta.dirname,'..');
process.chdir(root);
const commit=process.env.RC_COMMIT_SHA||execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
assert.match(commit,/^[a-f0-9]{40}$/);
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'scanner-observation-'));
function run(command,args,options={}){const result=spawnSync(command,args,{stdio:'inherit',...options});if(result.status!==0)throw new Error(`${command} failed (${result.status})`);}
run(process.env.PYTHON||'python3',['-m','pipeline.observation_release','--output',temporary]);
const report=JSON.parse(fs.readFileSync(path.join(temporary,'observation-report.json')));
const publicFile=path.join(root,'frontend/public/market.json');
const original=fs.existsSync(publicFile)?fs.readFileSync(publicFile):null;
try {
  fs.copyFileSync(path.join(temporary,'market.json'),publicFile);
  run(process.execPath,['node_modules/vite/bin/vite.js','build','--outDir','dist-rc'],{cwd:path.join(root,'frontend'),env:{...process.env,VITE_RELEASE_PROFILE:'observation-only',VITE_MARKET_URL:'',VITE_APPROVED_DATA_SHA256:report.publishedDataSha256,VITE_RC_COMMIT:commit}});
} finally {
  if(original)fs.writeFileSync(publicFile,original);else fs.unlinkSync(publicFile);
}
const dist=path.join(root,'frontend/dist-rc');
const sha=body=>crypto.createHash('sha256').update(body).digest('hex');
assert.equal(sha(fs.readFileSync(path.join(dist,'market.json'))),report.publishedDataSha256);
const html=fs.readFileSync(path.join(dist,'index.html'),'utf8');
assert.ok(html.includes("connect-src 'self';"));
assert.ok(!html.includes('raw.githubusercontent.com'));
assert.ok(fs.existsSync(path.join(dist,'.nojekyll')));
for(const match of html.matchAll(/(?:src|href)="([^"#]+)"/g)){assert.ok(match[1].startsWith('./'));assert.ok(fs.existsSync(path.join(dist,match[1])));}
const assets={};
function inventory(directory){for(const entry of fs.readdirSync(directory,{withFileTypes:true})){const file=path.join(directory,entry.name);if(entry.isDirectory())inventory(file);else assets[path.relative(dist,file).split(path.sep).join('/')]=sha(fs.readFileSync(file));}}
inventory(dist);
const js=Object.keys(assets).filter(f=>f.endsWith('.js'));
const javascriptGzipBytes=js.reduce((n,f)=>n+zlib.gzipSync(fs.readFileSync(path.join(dist,f))).length,0);
assert.ok(javascriptGzipBytes<300*1024);
const manifest={...report,candidateCommit:commit,localTreeDirty:!!execFileSync('git',['status','--porcelain'],{encoding:'utf8'}).trim(),assets,javascriptGzipBytes,actualPagesHeadersVerified:false,actualSafariVerified:false};
fs.writeFileSync(path.join(dist,'release-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
fs.mkdirSync('test-results',{recursive:true});
fs.writeFileSync('test-results/stage4a-build-audit.json',JSON.stringify(manifest,null,2)+'\n');
console.log(`Observation RC ${commit}: approved data ${report.publishedDataSha256}; not deployed.`);
