import test from 'node:test';
import assert from 'node:assert/strict';
import { creditLight, computeCredit, rollingVol, institutionalStreak, lastMA, stockMetrics, computeBreadth } from '../src/logic.js';
import { makeDemo, validateMarket } from '../src/data.js';
function h(n=150) { return Array.from({length:n},(_,i)=>({date:new Date(Date.UTC(2025,0,1+i)).toISOString().slice(0,10),close:100+i,volumeShares:1000000})); }
const proposedRule={status:'confirmed',greenBelow:.25,redAtOrAbove:.35,positionBelow:.3};
test('explicit rule boundaries are exact; fixture does not freeze the original screenshot',()=>{
  assert.equal(creditLight(.254),'PENDING');
  assert.equal(creditLight(0.24999,proposedRule),'GREEN');
  assert.equal(creditLight(0.25,proposedRule),'YELLOW');
  assert.equal(creditLight(0.254,proposedRule),'YELLOW');
  assert.equal(creditLight(0.34999,proposedRule),'YELLOW');
  assert.equal(creditLight(0.35,proposedRule),'RED');
});
test('high ratio is low credit pressure; low ratio is high pressure',()=>{
  const data=Array.from({length:190},(_,i)=>({date:new Date(Date.UTC(2025,0,1+i)).toISOString().slice(0,10),hyg:70+i*.3,shy:80,spy:100+i}));
  const result=computeCredit(data,189,proposedRule);
  assert.equal(result.at(-1).indicator,0);
  assert.equal(result.at(-1).light,'GREEN');
  const reverse=computeCredit(data.map((r,i)=>({...r,hyg:100-i*.3})),189,proposedRule);
  assert.ok(reverse.at(-1).indicator>.99);
  assert.equal(reverse.at(-1).light,'RED');
});
test('historical price window insufficient => no MA or breakout',()=>{
  const stock={symbol:'2330',name:'example',history:h(20)};
  assert.equal(lastMA(stock.history,20),109.5);
  assert.equal(lastMA(stock.history,60),null);
  assert.equal(stockMetrics(stock).breakout60,null);
});
test('breadth excludes stocks with inadequate MA history',()=>{
  const dates=['2026-10-07','2026-10-08'];
  const stocks=[{history:[{date:dates[0],close:100},{date:dates[1],close:101}]}];
  const b=computeBreadth(stocks,dates);
  assert.equal(b.at(-1).n20,0);
  assert.equal(b.at(-1).a20,null);
  assert.equal(b.at(-1).up,1);
});
test('streak resets at zero',()=>{
  const data=[{foreignShares:1000},{foreignShares:0},{foreignShares:3000},{foreignShares:2000}];
  assert.deepEqual(institutionalStreak(data,'foreignShares'),{direction:1,days:2,shares:5000});
});
test('annualized vol is standard deviation of returns, not RMS',()=>{
  const rows=Array.from({length:22},(_,i)=>({close:100*Math.pow(1.01,i)}));
  assert.ok(rollingVol(rows,20)<0.00001);
});
test('demo fixture stable and honestly labeled',()=>{
  const a=makeDemo(),b=makeDemo();
  assert.equal(a.mode,'demo');assert.equal(a.asOf,'2026-06-30');
  assert.deepEqual(a.stocks[0].history.slice(-2),b.stocks[0].history.slice(-2));
  assert.equal(a.stocks.length,40);
});
test('adapter refuses undocumented schema and fake mode',()=>{
  assert.throws(()=>validateMarket({stocks:[]}),/schemaVersion/);
  assert.throws(()=>validateMarket({schemaVersion:2,mode:'demo',stocks:[],asOf:'2026-10-08'}),/mode/);
  assert.throws(()=>validateMarket({schemaVersion:2,mode:'live',stocks:[],asOf:'2026-10-08'}));
});

test('sample JSON is not importable as real market data', async()=>{
  const fs=await import('node:fs');
  const fixture=JSON.parse(fs.readFileSync(new URL('../public/market.example.json',import.meta.url),'utf8'));
  assert.throws(()=>validateMarket(fixture),/mode/);
});
