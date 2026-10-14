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
