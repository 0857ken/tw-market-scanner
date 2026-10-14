import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {fetchMarket} from '../src/data.js';
const payload=JSON.parse(fs.readFileSync(new URL('../../data/market.json',import.meta.url),'utf8'));
test('Stage3D data refresh bypasses browser cache, omits credentials and preserves validation',async()=>{
  const original=globalThis.fetch,calls=[];
  globalThis.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>payload};};
  try{assert.equal((await fetchMarket('./market.json')).asOf,payload.asOf);assert.equal(calls[0].options.cache,'no-store');assert.equal(calls[0].options.credentials,'omit');assert.ok(new URL(calls[0].url).searchParams.has('scanner_check'));assert.ok(calls[0].options.signal instanceof AbortSignal);}finally{globalThis.fetch=original;}
});
test('Stage3D unapproved remote origin or embedded credentials never reach fetch',async()=>{
  const original=globalThis.fetch;let calls=0;globalThis.fetch=async()=>{calls++;};
  try{for(const url of ['https://example.org/market.json','https://user:password@raw.githubusercontent.com/file','data:application/json,{}'])await assert.rejects(()=>fetchMarket(url));assert.equal(calls,0);}finally{globalThis.fetch=original;}
});
test('Stage3D approved GitHub origin still rejects HTTP failures and forged rules',async()=>{
  const original=globalThis.fetch;
  try{globalThis.fetch=async()=>({ok:false,status:503});await assert.rejects(()=>fetchMarket('https://raw.githubusercontent.com/0857ken/tw-market-scanner/market-data/data/market.json'),/HTTP 503/);
    globalThis.fetch=async()=>({ok:true,json:async()=>({...payload,creditRule:{status:'confirmed',window:189}})});await assert.rejects(()=>fetchMarket('./market.json'),/信用規則/);
  }finally{globalThis.fetch=original;}
});
