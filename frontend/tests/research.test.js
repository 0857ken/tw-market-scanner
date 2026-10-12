import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {alignedPrices,researchMetrics,researchBreadth,coverage,memberOn,suspendedOn,windowCheck} from '../src/research.js';
import {validateMarket} from '../src/data.js';
import {getSignals} from '../src/logic.js';
const days=Array.from({length:301},(_,i)=>new Date(Date.UTC(2025,0,1+i)).toISOString().slice(0,10));
const anchor=days.at(-1);
const meta={asOf:anchor,sessions:days,calendarStatus:'verified',calendarFrom:days[0],calendarTo:anchor,targetSessions:300};
const fixture=(market='TWSE')=>({symbol:'1234',securityId:`${market}:1234`,name:'synthetic',market,
  lifecycle:{listedOn:days[0],delistedOn:null,suspensions:[]},
  adjustment:{status:'verified',method:'backward-total-return',version:'TEST_ONLY'},
  eventCoverage:{status:'verified',from:days[0],to:anchor},events:[],
  history:days.map((date,i)=>({date,close:100+i,rawClose:100+i,adjustedClose:50+i/2,adjustmentVersion:'TEST_ONLY',volumeShares:1000,changeAmount:1}))});
test('MA240 and 240-day breakout use 240 and 241 complete observations, without lookahead',()=>{
  const s=fixture();let m=researchMetrics(s,meta,'adjusted',anchor);
  assert.equal(m.ma240,(s.history.at(-240).adjustedClose+s.history.at(-1).adjustedClose)/2);
  assert.equal(m.breakouts[240].hit,true);
  const short={...meta,sessions:days.slice(-240)};
  assert.equal(researchMetrics(s,short,'raw',anchor).breakouts[240].eligible,false);
  assert.equal(researchMetrics(s,{...meta,sessions:days.slice(-239)},'raw',anchor).ma240,null);
  const before=researchMetrics(s,meta,'adjusted',days.at(-2));s.history.at(-1).adjustedClose=99999;
  assert.equal(researchMetrics(s,meta,'adjusted',days.at(-2)).ma240,before.ma240);
});
test('adjusted gap/version mismatch never falls back to raw; basis selection is global',()=>{
  const s=fixture();s.history.at(-1).adjustedClose=null;
  assert.equal(alignedPrices(s,meta,'adjusted',anchor).at(-1).close,null);
  assert.equal(researchMetrics(s,meta,'adjusted',anchor).ma20,null);
  assert.ok(researchMetrics(s,meta,'raw',anchor).ma20>0);
  s.history.at(-1).adjustedClose=200;s.history.at(-1).adjustmentVersion='OTHER';
  assert.equal(researchMetrics(s,meta,'adjusted',anchor).ma20,null);
});
test('unadjusted dividend/split/reduction event or unknown event coverage suppresses breakout',()=>{
  for(const kind of ['cash-dividend','split','capital-reduction','ex-reference-price']){
    const s=fixture();s.events=[{date:anchor,kind}];s.history.at(-1).rawClose=99999;s.history.at(-1).close=99999;
    assert.equal(researchMetrics(s,meta,'raw',anchor).breakouts[240].hit,null);
  }
  const s=fixture();s.eventCoverage.status='unknown';
  assert.equal(researchMetrics(s,meta,'raw',anchor).breakouts[20].eligible,false);
});
test('holidays excluded by sessions; missing expected day/suspension stays null and warms up again',()=>{
  const s=fixture();s.history=s.history.filter(r=>r.date!==days.at(-5));
  assert.equal(researchMetrics(s,meta,'raw',anchor).ma20,null);
  assert.ok(researchMetrics(s,{...meta,sessions:days.filter(d=>d!==days.at(-5))},'raw',anchor).ma20>0);
  s.lifecycle.suspensions=[{from:days.at(-3),to:null}];
  assert.equal(suspendedOn(s,anchor),true);assert.equal(researchMetrics(s,meta,'raw',anchor).ma20,null);
});
test('IPO, transfer and delisting boundaries do not stitch market windows or double count',()=>{
  const old=fixture('TPEx'),next=fixture('TWSE');old.lifecycle.delistedOn=days.at(-10);next.lifecycle.listedOn=days.at(-10);
  assert.equal(memberOn(old,days.at(-10)),false);assert.equal(memberOn(next,days.at(-10)),true);
  assert.equal(researchMetrics(next,meta,'raw',anchor).ma20,null);
  assert.equal(researchMetrics(old,meta,'raw',anchor).ma20,null);
});
test('combined breadth adds eligible numerators/denominators, never averages market percentages',()=>{
  const a=fixture(),b=fixture('TPEx'),c=fixture('TPEx');c.symbol='5678';
  b.history=b.history.map((r,i)=>({...r,close:500-i,rawClose:500-i}));
  const market={research:{markets:{TWSE:meta,TPEx:meta}}};
  const combined=researchBreadth([a,b,c],market,'raw',[anchor]).at(-1);
  assert.equal(combined.n240,3);assert.ok(Math.abs(combined.a240-200/3)<1e-9);
  market.research.markets.TPEx={...meta,asOf:days.at(-2)};b.history.pop();c.history.pop();
  assert.equal(researchBreadth([a,b,c],market,'raw',[anchor]).at(-1).n240,1);
});
test('calendar uncertainty and partial event range fail closed',()=>{
  const s=fixture();assert.equal(windowCheck(s,{...meta,calendarStatus:'partial'},'raw',240,anchor).valid,false);
  s.eventCoverage.from=days.at(-20);assert.equal(researchMetrics(s,meta,'raw',anchor).breakouts[240].eligible,false);
});
test('production Stage3B contract and actual coverage are explicit; payload cannot self-approve',()=>{
  const p=JSON.parse(fs.readFileSync(new URL('../../data/market.json',import.meta.url),'utf8'));
  validateMarket(p);
  assert.equal(p.researchVersion,1);assert.ok(p.stocks.some(s=>s.market==='TPEx'));
  assert.equal(p.stocks.filter(s=>s.market==='TWSE').some(s=>s.institutional?.length),false);
  assert.ok(p.stocks.filter(s=>s.market==='TPEx').some(s=>s.institutional?.length));
  const a=getSignals(p,'TWSE','raw'),b=getSignals(p,'TPEx','raw'),all=getSignals(p,'ALL','raw');
  assert.equal(all.coverage.total,a.coverage.total+b.coverage.total);
  assert.equal(all.coverage.quotes,a.coverage.quotes+b.coverage.quotes);
  assert.equal(all.coverage.ma[240],0);assert.equal(all.coverage.adjusted,0);
  assert.equal(all.coverage.breakout240,0);
  for(const mutate of [x=>x.stocks[0].history[0].adjustedClose=1,x=>x.stocks[0].history[0].rawClose=1,x=>x.research.markets.TPEx.calendarStatus='verified',x=>x.stocks[0].adjustment.status='verified']){
    const x=structuredClone(p);mutate(x);assert.throws(()=>validateMarket(x));
  }
});

const contractCases=JSON.parse(fs.readFileSync(new URL('../../tests/fixtures/research-contract-cases.json',import.meta.url),'utf8'));
for(const c of contractCases)test(`research contract: ${c.name}`,()=>{
  const p=JSON.parse(fs.readFileSync(new URL('../../data/market.json',import.meta.url),'utf8'));
  for(const [,path,value] of c.ops){const parent=path.slice(0,-1).reduce((o,k)=>o[k],p);parent[path.at(-1)]=value;}
  if(c.valid)assert.doesNotThrow(()=>validateMarket(p));else assert.throws(()=>validateMarket(p));
});
