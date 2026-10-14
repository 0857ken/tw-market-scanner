// Price-basis selection is global and explicit. Never fill adjusted gaps with raw prices.
const num=v=>typeof v==='number'&&Number.isFinite(v);
const isoDay=d=>typeof d==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(d)&&Number.isFinite(Date.parse(d+'T00:00:00Z'))&&new Date(d+'T00:00:00Z').toISOString().slice(0,10)===d;
export const MARKET_NAMES={TWSE:'上市',TPEx:'上櫃',ALL:'上市櫃合併'};
export const BASIS_NAMES={adjusted:'經驗證還原價（研究目標）',raw:'未還原價（暫行研究）'};
export const securityKey=s=>s.securityId||`${s.market||'TWSE'}:${s.symbol}`;
export function memberOn(s,date){const l=s.lifecycle||{};return (!l.listedOn||l.listedOn<=date)&&(!l.delistedOn||date<l.delistedOn);}
export function suspendedOn(s,date){return (s.lifecycle?.suspensions||[]).some(r=>r.from<=date&&(!r.to||date<r.to));}
export function marketMeta(market,exchange){
  return market.research?.markets?.[exchange]||{asOf:exchange==='TWSE'?market.asOf:null,sessions:exchange==='TWSE'?(market.quoteSessions||[]):[],calendarStatus:'partial',targetSessions:300};
}
export function alignedPrices(s,meta,basis,anchor){
  const map=new Map((s.history||[]).map(r=>[r.date,r]));
  const dates=[...new Set([...(meta.sessions||[]),...(anchor?[anchor]:[])])].filter(d=>(!anchor||d<=anchor)&&memberOn(s,d)).sort();
  return dates.map(date=>{const r=map.get(date),raw=r?.rawClose??r?.close??null;
    const verified=s.adjustment?.status==='verified'&&r?.adjustmentVersion===s.adjustment.version;
    const close=suspendedOn(s,date)?null:basis==='raw'?raw:verified?r?.adjustedClose??null:null;
    return {date,close:num(close)&&close>0?close:null,rawClose:raw,volumeShares:r?.volumeShares??null,changeAmount:r?.changeAmount??null};
  });
}
export function windowCheck(s,meta,basis,n,anchor,{breakout=false}={}){
  const h=alignedPrices(s,meta,basis,anchor).slice(-n);
  const fail=reason=>({rows:h,reason,valid:false});
  if(!memberOn(s,anchor))return fail('非該日市場成員');
  if(suspendedOn(s,anchor))return fail('停牌');
  if(basis==='adjusted'&&s.adjustment?.status!=='verified')return fail('還原價格尚未驗證');
  if(h.length<n)return fail(`暖機：需要 ${n} 個交易日`);
  if(meta.calendarStatus!=='verified'||!meta.calendarFrom||meta.calendarFrom>h[0].date||!meta.calendarTo||meta.calendarTo<anchor)return fail('交易日曆覆蓋未驗證');
  if(h.some(r=>!num(r.close)||r.close<=0))return fail('窗口有缺價或停牌');
  if(basis==='raw'&&breakout){
    const c=s.eventCoverage||{};
    if(c.status!=='verified'||!c.from||c.from>h[0].date||!c.to||c.to<anchor)return fail('公司事件覆蓋未驗證，停止突破判定');
    if((s.events||[]).some(e=>e.date>=h[0].date&&e.date<=anchor))return fail('窗口含除權息／資本事件，停止未還原突破判定');
  }
  return {rows:h,reason:null,valid:true};
}
export function researchMetrics(s,meta,basis,anchor){
  const out={indicatorBasis:basis,indicatorHistory:alignedPrices(s,meta,basis,anchor),maReasons:{},breakouts:{}};
  for(const n of [20,60,120,240]){
    const win=windowCheck(s,meta,basis,n,anchor);
    out[`ma${n}`]=win.valid?win.rows.reduce((a,r)=>a+r.close,0)/n:null;out.maReasons[n]=win.reason;
    const b=windowCheck(s,meta,basis,n+1,anchor,{breakout:true});
    const high=b.valid?Math.max(...b.rows.slice(0,-1).map(r=>r.close)):null;
    const close=b.valid?b.rows.at(-1).close:null;
    out.breakouts[n]={eligible:b.valid,reason:b.reason,high,dist:b.valid?(close/high-1)*100:null,hit:b.valid?close>high:null};
  }
  out.breakout60=out.breakouts[60].hit;out.breakoutEligible=out.breakouts[60].eligible;out.prev60=out.breakouts[60].high;
  return out;
}
export function researchBreadth(stocks,market,basis,dates){
  const result=dates.map(date=>{const r={date,up:0,down:0,flat:0,nChange:0};for(const n of [20,60,120,240]){r[`n${n}`]=0;r[`a${n}`]=null;r[`above${n}`]=0;}return r;});
  const indices=new Map(dates.map((d,i)=>[d,i])),anchor=dates.at(-1);
  for(const s of stocks){
    const meta=marketMeta(market,s.market||'TWSE'),h=alignedPrices(s,meta,basis,anchor);
    const sums=[0],missing=[0],raw=new Map(s.history.map(r=>[r.date,r]));
    for(let i=0;i<h.length;i++){
      const v=h[i].close,valid=num(v)&&v>0;
      sums.push(sums.at(-1)+(valid?v:0));missing.push(missing.at(-1)+(valid?0:1));
      const ri=indices.get(h[i].date);if(ri==null||!memberOn(s,h[i].date)||suspendedOn(s,h[i].date))continue;
      const r=result[ri],q=raw.get(h[i].date);
      if(num(q?.close)&&num(q?.changeAmount)){r.nChange++;if(q.changeAmount>0)r.up++;else if(q.changeAmount<0)r.down++;else r.flat++;}
      for(const n of [20,60,120,240]){
        const from=i+1-n;
        if(from<0||missing[i+1]!==missing[from]||meta.calendarStatus!=='verified'||!meta.calendarFrom||meta.calendarFrom>h[from].date||!meta.calendarTo||meta.calendarTo<h[i].date||basis==='adjusted'&&s.adjustment?.status!=='verified')continue;
        r[`n${n}`]++;if(v>(sums[i+1]-sums[from])/n)r[`above${n}`]++;
      }
    }
  }
  for(const r of result)for(const n of [20,60,120,240]){if(r[`n${n}`])r[`a${n}`]=r[`above${n}`]/r[`n${n}`]*100;delete r[`above${n}`];}
  return result;
}

export function coverage(stocks,market,basis,anchor){
  const eligible=stocks.filter(s=>memberOn(s,anchor)), total=eligible.length;
  const quotes=eligible.filter(s=>s.history.some(r=>r.date===anchor&&num(r.rawClose??r.close)&&(r.rawClose??r.close)>0)&&!suspendedOn(s,anchor)).length;
  const result={total,quotes,quotePct:total?quotes/total*100:null,adjusted:0,ma:{},breakout240:0,minDays:0,maxDays:0};
  const days=eligible.map(s=>s.history.filter(r=>num(r.rawClose??r.close)&&(r.rawClose??r.close)>0&&r.date<=anchor).length);
  result.minDays=days.length?Math.min(...days):0;result.maxDays=days.length?Math.max(...days):0;
  for(const n of [20,60,120,240])result.ma[n]=0;
  for(const s of eligible){const meta=marketMeta(market,s.market||'TWSE');const m=researchMetrics(s,meta,basis,anchor);
    for(const n of [20,60,120,240])if(num(m[`ma${n}`]))result.ma[n]++;
    if(m.breakouts[240].eligible)result.breakout240++;
    if(s.adjustment?.status==='verified'&&s.history.some(r=>r.date===anchor&&num(r.adjustedClose)&&r.adjustmentVersion===s.adjustment.version))result.adjusted++;
  }
  return result;
}
export function validateResearch(payload){
  if(payload.researchVersion!==1||!payload.research?.markets)throw new Error('需要研究資料契約 v1');
  const markets=payload.research.markets;
  if(Object.keys(markets).sort().join(',')!=='TPEx,TWSE')throw new Error('需要上市與上櫃覆蓋紀錄');
  for(const [exchange,meta] of Object.entries(markets)){
    const source=payload.sources[exchange==='TWSE'?'quotes':'tpexQuotes'];
    if(meta.asOf!==source?.asOf||source?.asOf&&!/^[a-f0-9]{64}$/.test(source.sha256||''))throw new Error('市場日期／版本與來源不一致');
    if(meta.targetSessions!==300||meta.calendarStatus!=='partial')throw new Error('交易日曆版本未獨立核准');
    if(!Array.isArray(meta.sessions)||meta.sessions.some((d,i)=>!isoDay(d)||d>payload.asOf||i>0&&d<=meta.sessions[i-1]))throw new Error('市場交易日錯誤');
  }
  for(const s of payload.stocks){
    if(!['TWSE','TPEx'].includes(s.market)||s.securityId!==`${s.market}:${s.symbol}`||s.securityType!=='ordinary'||s.symbol.startsWith('00')||s.name.toUpperCase().includes('-DR'))throw new Error('普通股市場分類錯誤');
    if(s.priceBasis!=='unadjusted'||s.adjustment?.status!=='unavailable'||s.adjustment.method!==null||s.adjustment.version!==null)throw new Error('還原版本未獨立核准');
    if(s.eventCoverage?.status!=='unknown'||s.lifecycle?.pointInTimeVerified!==false)throw new Error('公司事件或歷史母體未獨立核准');
    const life=s.lifecycle;
    if(life.status!=='current-roster-only'||life.source!==(s.market==='TWSE'?'companies':'tpexCompanies')||['listedOn','delistedOn','rosterAsOf'].some(k=>life[k]!=null&&!isoDay(life[k])))throw new Error('成員日期或來源錯誤');
    if(life.listedOn&&life.delistedOn&&life.listedOn>=life.delistedOn)throw new Error('成員日期範圍錯誤');
    let previousEnd='';
    for(const span of life.suspensions||[]){if(!isoDay(span.from)||span.to!=null&&!isoDay(span.to)||previousEnd===null||span.from<previousEnd||span.to&&span.to<=span.from)throw new Error('停牌日期範圍錯誤');previousEnd=span.to;}
    for(const e of s.events||[]){if(!isoDay(e.date)||e.kind!=='ex-reference-price'||e.status!=='official-reference-only')throw new Error('公司事件未驗證');}
    const source=s.market==='TWSE'?'quotes':'tpexQuotes',day=payload.sources[source]?.asOf;
    for(const r of s.history){
      if(!Object.hasOwn(r,'rawClose')||r.rawClose!==r.close||r.adjustedClose!==null||r.adjustmentVersion!==null)throw new Error('價格基礎混用或未核准還原價');
      if(r.market!==s.market||r.source!==source||!/^[a-f0-9]{64}$/.test(r.sourceVersion||''))throw new Error('價格版本來源錯誤');
      if(r.close!==null&&r.date===day&&r.sourceVersion!==payload.sources[source].sha256)throw new Error('最新行情版本與來源不一致');
      if(r.close!==null&&(!day||r.date>day))throw new Error('價格超過所屬市場來源日期');
    }
  }
}

export function breakoutSelection(stocks,period,minVol=0,search=''){
  const eligible=stocks.filter(s=>s.breakouts?.[period]?.eligible===true);
  const rows=eligible.map(s=>({...s,dist:s.breakouts[period].dist,breakout:s.breakouts[period].hit===true}))
    .filter(s=>num(s.dist)&&(minVol===0||num(s.volRatio)&&s.volRatio>=minVol)&&`${s.symbol}${s.name}`.includes(search));
  return {eligible:eligible.length,rows,hits:rows.filter(s=>s.breakout).sort((a,b)=>b.dist-a.dist),near:rows.filter(s=>!s.breakout&&s.dist>=-3).sort((a,b)=>b.dist-a.dist)};
}
