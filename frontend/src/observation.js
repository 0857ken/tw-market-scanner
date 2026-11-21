// Presentation restriction, not a replacement or modification of strategy rules.
export function observationSignals(signals) {
  const latest=signals.latest.map(s=>({...s,change:signals.daily.datesAligned?s.change:null,ma20:null,ma60:null,ma120:null,ma240:null,
    breakout20:false,breakout60:false,breakout120:false,breakout240:false,breakoutEligible:false,volRatio:null}));
  return {...signals,latest,hits:[],breakoutEligible:0,credit:[],creditNow:null,futures:null,
    alerts:[],marginRisk:[],regime:{state:'停用',ret:null,vol:null},breadth:[],
    coverage:{...signals.coverage,ma:{20:0,60:0,120:0,240:0},breakout240:0}};
}

export async function fetchApprovedMarket(url, expectedSha256, validate) {
  const target=new URL(url,globalThis.location.href);
  if(target.origin!==globalThis.location.origin||!/^([a-f0-9]{64})$/.test(expectedSha256))throw new Error('候選版只允許本站核准快照');
  target.searchParams.set('scanner_check',String(Date.now()));
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
  try {
    const response=await fetch(target,{cache:'no-store',credentials:'omit',signal:controller.signal});
    if(!response.ok)throw new Error(`讀取失敗：HTTP ${response.status}`);
    const bytes=await response.arrayBuffer();
    const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    if(digest!==expectedSha256)throw new Error('核准資料 SHA256 不符；拒絕其他版本／舊快取');
    const payload=validate(JSON.parse(new TextDecoder().decode(bytes)));
    if(payload.mode!=='live'||payload.observationProfile?.profile!=='observation-only')throw new Error('缺少核准盤後觀察 profile');
    return payload;
  } finally {clearTimeout(timer);}
}

// A separately approved frontend can follow validated immutable daily manifests.
// Same-origin HTTPS + protected release workflow is the trust boundary; a manifest
// digest is an integrity check, not an independent signature or strategy approval.
export async function fetchDailyMarket(url, frontendId, validate) {
  const target=new URL(url,globalThis.location.href);
  if(target.origin!==globalThis.location.origin)throw new Error('每日版本僅允許本站');
  const manifestUrl=new URL('release-manifest.json',target);
  manifestUrl.searchParams.set('scanner_check',String(Date.now()));
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
  try {
    const response=await fetch(manifestUrl,{cache:'no-store',credentials:'omit',signal:controller.signal});
    if(!response.ok)throw new Error(`manifest 讀取失敗：HTTP ${response.status}`);
    const manifest=await response.json();
    const disabled=['moving-averages','breakouts','credit-strategy','twse-t86','adjusted-prices','historical-backtest','intraday','institutional-streaks'];
    if(manifest.frontendId!==frontendId||manifest.profile!=='observation-only'||manifest.strategyComplete!==false||
       !disabled.every(k=>manifest.disabled?.includes(k))||manifest.assets?.['market.json']!==manifest.publishedDataSha256||
       !/^[a-f0-9]{64}$/.test(manifest.publishedDataSha256||''))throw new Error('每日 manifest／固定前端不符');
    const payload=await fetchApprovedMarket(url,manifest.publishedDataSha256,validate);
    if(payload.asOf!==manifest.asOf||payload.observationProfile.version!==manifest.version||
       payload.creditHistory.length||payload.futures.length||payload.indexHistory.length||
       !disabled.every(k=>payload.observationProfile.disabled?.includes(k))||
       payload.stocks.some(s=>s.margin||s.intraday||s.market==='TWSE'&&s.institutional?.length||s.history.some(r=>r.adjustedClose!=null)))throw new Error('每日資料日期／版本／停用範圍不符');
    for(const [module,source] of Object.entries(manifest.sourceVersions||{})) {
      if(source.sha256!==payload.sources[module]?.sha256||source.asOf!==payload.sources[module]?.asOf)throw new Error('manifest 來源版本不符');
    }
    return {...payload,releaseIntegrity:{dataSha256:manifest.publishedDataSha256,runId:manifest.runId,frontendId}};
  } finally {clearTimeout(timer);}
}
