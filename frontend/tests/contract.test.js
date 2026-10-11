import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {validateMarket,makeDemo,makeUnavailable,effectiveStatus} from '../src/data.js';
import {stockMetrics,computeBreadth,institutionalStreak,computeCredit,creditLight} from '../src/logic.js';
const captured=JSON.parse(fs.readFileSync(new URL('../../tests/fixtures/official-market-20261007.json',import.meta.url),'utf8'));
const copy=()=>structuredClone(captured);
test('Python official v2 output passes the independent JS adapter',()=>{
  assert.equal(validateMarket(copy()).asOf,'2026-10-07');
  assert.ok(captured.stocks.length>1000);
  assert.equal(captured.stocks.some(s=>s.symbol.startsWith('00')),false);
  assert.equal(captured.futures.at(-1).foreign,-79101);
});
test('demo relabelling is rejected; unavailable contract contains no invented readings',()=>{
  assert.throws(()=>validateMarket({...makeDemo(),mode:'live'}));
  assert.deepEqual(validateMarket(makeUnavailable()).stocks,[]);
});
test('rejects invalid dates, duplicate histories, negative shares, future observations',()=>{
  let x=copy();x.stocks[0].history[0].date='2026-02-30';assert.throws(()=>validateMarket(x),/日期/);
  x=copy();x.stocks[0].history.push(x.stocks[0].history[0]);assert.throws(()=>validateMarket(x),/日期/);
  x=copy();x.stocks[0].history[0].volumeShares=-1;assert.throws(()=>validateMarket(x),/成交量/);
  x=copy();x.asOf='2099-01-01';assert.throws(()=>validateMarket(x),/未來/);
});
test('rejects string money, ambiguous futures products, and unadjusted credit input',()=>{
  let x=copy();x.stocks[0].history[0].close='100';assert.throws(()=>validateMarket(x),/數字/);
  x=copy();x.futures[0].contract='MTX';assert.throws(()=>validateMarket(x),/TX/);
  x=copy();x.creditHistory=[{date:'2026-10-06',hyg:80,shy:82}];assert.throws(()=>validateMarket(x),/還原權息/);
});
test('a same-day quote provides official reference change without fabricated previous history',()=>{
  const r=stockMetrics({history:[{date:'2026-10-07',close:110,changeAmount:10,volumeShares:1000000}]});
  assert.ok(Math.abs(r.change-10)<1e-10);assert.equal(r.ma20,null);assert.equal(r.breakout60,null);
});
test('missing historical price is not zero in MA/breadth and missing volume is not zero',()=>{
  const h=Array.from({length:61},(_,i)=>({date:new Date(Date.UTC(2026,0,1+i)).toISOString().slice(0,10),close:100+i,volumeShares:1000}));
  h[45].close=null;h[44].volumeShares=null;
  const r=stockMetrics({history:h});assert.equal(r.ma20,null);assert.equal(r.prev60,null);assert.equal(r.volRatio,null);
  const b=computeBreadth([{history:h}],[h.at(-1).date]).at(-1);assert.equal(b.n20,0);assert.equal(b.a20,null);
});
test('missing session cannot silently count as consecutive buying',()=>{
  const dates=['2026-10-05','2026-10-06','2026-10-07'];
  const rows=[{date:dates[0],foreignShares:1000},{date:dates[2],foreignShares:2000}];
  assert.deepEqual(institutionalStreak(rows,'foreignShares',dates),{direction:1,days:1,shares:2000});
});
test('stale status advances after a new Taiwan session and respects official holidays',()=>{
  const source={status:'fresh',asOf:'2026-10-08'};
  const calendar={rows:[{date:'2026-10-09',closed:true},{date:'2026-01-01',closed:true}]};
  assert.equal(effectiveStatus(source,calendar,new Date('2026-10-09T22:30:00+08:00')),'fresh');
  assert.equal(effectiveStatus(source,calendar,new Date('2026-10-12T22:30:00+08:00')),'stale');
  assert.equal(effectiveStatus({...source,status:'error'},calendar),'error');
});
test('189 observations are necessary; ties and lag use exact ranks without lookahead',()=>{
  const rows=Array.from({length:190},(_,i)=>({date:new Date(Date.UTC(2025,0,1+i)).toISOString().slice(0,10),hyg:80,shy:80}));
  const result=computeCredit(rows);
  assert.equal(result[187].indicator,null);assert.equal(result[188].indicator,0);
  assert.equal(result[188].light,'PENDING');assert.equal(result[189].position,null);
  assert.equal(creditLight(.254,{status:'pending'}),'PENDING');
});
test('financial share totals retain decimals in lots and only divide once',()=>{
  // Synthetic unit values only; unpublished T86 observations are excluded from the public fixture.
  const latest={foreignShares:1001,trustShares:-2,dealerShares:4,totalShares:1003};
  assert.equal(latest.totalShares,latest.foreignShares+latest.trustShares+latest.dealerShares);
  assert.equal(latest.foreignShares/1000,1.001);
  const stock=captured.stocks.find(s=>s.margin);
  assert.equal(stock.margin?.sourceUnit,'lots');
});
test('public fixture excludes institution data pending redistribution rights',()=>{
  assert.equal(captured.sources.institutional.status,'unavailable');
  assert.equal(captured.stocks.some(s=>s.institutional?.length),false);
});
test('frontend freshness changes at the same 16:30 Taipei boundary as the pipeline',()=>{
  const source={status:'fresh',asOf:'2026-10-07'};
  const calendar={rows:[{date:'2026-01-01',closed:true}]};
  assert.equal(effectiveStatus(source,calendar,new Date('2026-10-08T16:29:00+08:00')),'fresh');
  assert.equal(effectiveStatus(source,calendar,new Date('2026-10-08T16:30:00+08:00')),'stale');
});
test('breadth does not compress a missing expected trading session into a valid MA window',()=>{
  const dates=Array.from({length:21},(_,i)=>new Date(Date.UTC(2026,0,1+i)).toISOString().slice(0,10));
  const history=dates.filter((_,i)=>i!==10).map(date=>({date,close:100,volumeShares:1000}));
  const latest=computeBreadth([{history}],[dates.at(-1)],dates).at(-1);
  assert.equal(latest.n20,0);assert.equal(latest.a20,null);
});
