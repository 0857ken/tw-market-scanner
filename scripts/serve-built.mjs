// Local verification server. Serves the production artifact under the Pages repository subpath.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),process.env.SCANNER_RC==='true'?'../frontend/dist-rc':'../frontend/dist');
const prefix='/tw-market-scanner/';
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript','.css':'text/css','.json':'application/json','.svg':'image/svg+xml'};
http.createServer((req,res)=>{
  const url=new URL(req.url,'http://localhost');
  if(!url.pathname.startsWith(prefix)){res.writeHead(302,{Location:prefix});res.end();return;}
  const relative=decodeURIComponent(url.pathname.slice(prefix.length))||'index.html';
  const file=path.resolve(root,relative);
  if(!file.startsWith(root+path.sep)||!fs.existsSync(file)||!fs.statSync(file).isFile()){res.writeHead(404);res.end('Not found');return;}
  res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream','Cache-Control':'no-store'});
  fs.createReadStream(file).pipe(res);
}).listen(4173,'127.0.0.1',()=>console.log('Preview: http://127.0.0.1:4173/tw-market-scanner/'));
