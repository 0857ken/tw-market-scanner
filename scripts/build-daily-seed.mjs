// Build frontend once for candidate approval. Daily bundling never invokes Vite.
import fs from 'node:fs';
import crypto from 'node:crypto';
import {execFileSync} from 'node:child_process';
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const id='observation-daily-v1';
execFileSync(process.execPath,['node_modules/vite/bin/vite.js','build','--outDir','dist-daily'],{cwd:'frontend',stdio:'inherit',env:{...process.env,VITE_RELEASE_PROFILE:'observation-only',VITE_DAILY_FRONTEND_ID:id,VITE_RC_VERSION:'4c1-preview',VITE_RC_COMMIT:process.env.RC_COMMIT_SHA||execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),VITE_MARKET_URL:''}});
const root='frontend/dist-daily';
fs.writeFileSync(`${root}/.nojekyll`,'');
// Vite's public directory may include development fixture files: never pin them.
for(const name of fs.readdirSync(root))if(name!=='index.html'&&name!=='.nojekyll'&&name!=='assets')fs.rmSync(`${root}/${name}`,{recursive:true});
const assets={};for(const n of ['index.html','.nojekyll',...fs.readdirSync(`${root}/assets`).map(n=>`assets/${n}`)])assets[n]=sha(fs.readFileSync(`${root}/${n}`));
fs.writeFileSync(`${root}/frontend-pin.json`,JSON.stringify({frontendId:id,assets},null,2)+'\n');
