import { numeric, round } from './logic.js';
const NAMES = [
 ['2330','台積電','半導體',2000],['2317','鴻海','電子代工',600],['2454','聯發科','半導體',750],['2308','台達電','電子零組件',390],
 ['2382','廣達','電子代工',260],['2303','聯電','半導體',50],['3711','日月光投控','半導體',165],['2891','中信金','金融',36],
 ['2882','國泰金','金融',68],['2881','富邦金','金融',90],['2886','兆豐金','金融',40],['2603','長榮','航運',230],
 ['2609','陽明','航運',69],['2615','萬海','航運',81],['2002','中鋼','鋼鐵',23],['1301','台塑','塑化',51],
 ['1303','南亞','塑化',48],['6505','台塑化','塑化',48],['2412','中華電','電信',126],['3008','大立光','光學',2480],
 ['3231','緯創','電子代工',115],['2357','華碩','電子',550],['2376','技嘉','電子',280],['3034','聯詠','半導體',390],
 ['2379','瑞昱','半導體',550],['3661','世芯-KY','半導體',2600],['3443','創意','半導體',1300],['2327','國巨','被動元件',560],
 ['2345','智邦','網通',680],['4938','和碩','電子代工',90],['1815','富喬','電子材料',66],['2368','金像電','PCB',420],
 ['6213','聯茂','PCB',122],['3715','定穎投控','PCB',93],['5439','高技','PCB',260],['1477','聚陽','紡織',310],
 ['2408','南亞科','記憶體',59],['2344','華邦電','記憶體',22],['3037','欣興','PCB',175],['8046','南電','PCB',156],
];
function rng(seed) { return () => { seed |= 0; seed = seed + 0x6d2b79f5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
function normal(rand) { return Math.sqrt(-2 * Math.log(Math.max(rand(), 1e-9))) * Math.cos(2 * Math.PI * rand()); }
function weekdays(end, n) {
  const days = [], d = new Date(`${end}T12:00:00Z`);
  while (days.length < n) { if (![0,6].includes(d.getUTCDay())) days.unshift(d.toISOString().slice(0,10)); d.setUTCDate(d.getUTCDate() - 1); }
  return days;
}
export function makeDemo() {
  // Frozen, explicitly fictitious test fixture: dates are intentionally historical.
  const dates = weekdays('2026-06-30', 280), rand = rng(119);
  let idx = 21200;
  const indexHistory = dates.map((date, i) => { idx *= 1 + (i > 235 ? -0.0004 : 0.0005) + normal(rand) * 0.010; return { date, close: round(idx), volumeShares: 0 }; });
  const stocks = NAMES.map(([symbol, name, sector, start], j) => {
    const r = rng(j * 119 + 8), beta = 0.4 + r() * 0.8;
    let price = start * (0.7 + r() * 0.6);
    const history = dates.map((date, i) => {
      price = Math.max(2, price * (1 + (indexHistory[i].close / (indexHistory[i-1]?.close || indexHistory[i].close) - 1) * beta + normal(r) * 0.014));
      return { date, close: round(price), volumeShares: Math.round((700000 + r() * 8500000) * (1 + Math.abs(normal(r)) * 0.4)) };
    });
    const institutional = dates.slice(-35).map(date => ({ date, foreignShares: Math.round(normal(r) * 1250000), trustShares: Math.round(normal(r) * 440000), dealerShares: Math.round(normal(r) * 190000) }));
    return { symbol, name, sector, marketCapM: Math.round(start * (30 + r() * 350)), history, institutional,
      margin: { usagePct: round(9 + r() * 85, 1), balanceShares: Math.round(500000 + r() * 13000000) },
      intraday: { asOf: '2026-06-30T11:00:00+08:00', cumulativeVolumeShares: Math.round(history.at(-1).volumeShares * (0.35 + r() * 0.35)) } };
  });
  const futures = dates.slice(-30).map((date, i) => ({ date, foreign: Math.round(-18000 + Math.sin(i / 4) * 8500 + normal(rand) * 1100), trust: Math.round(1500 + normal(rand) * 500), dealer: Math.round(-2500 + normal(rand) * 800) }));
  let hyg = 80, shy = 82, spy = 500;
  const creditHistory = dates.map((date, i) => {
    hyg *= 1 + (i > 230 ? -0.0011 : 0.0005) + normal(rand) * 0.009;
    shy *= 1 + 0.00006 + normal(rand) * 0.001;
    spy *= 1 + (i > 230 ? -0.0005 : 0.0007) + normal(rand) * 0.012;
    return { date, hyg: round(hyg, 4), shy: round(shy, 4), spy: round(spy, 2) };
  });
  return { schemaVersion: 2, mode: 'demo', asOf: '2026-06-30', generatedAt:'2026-06-30T16:30:00+08:00',
    sources:{quotes:{name:'固定虛構測試',status:'demo',asOf:'2026-06-30'},credit:{name:'固定虛構測試',status:'demo',asOf:'2026-06-30'}},
    creditRule:{status:'pending',window:189}, source: '固定隨機種子／虛構示範市場', universe: '40 檔示範觀察池（非全部上市櫃）', indexHistory, stocks, futures, creditHistory };
}

export function makeUnavailable() {
  return {schemaVersion:2, mode:'unavailable', asOf:null, generatedAt:new Date().toISOString(),
    source:'等待官方盤後資料', universe:'尚未載入市場母體', stocks:[],indexHistory:[],futures:[],creditHistory:[],
    sources:{quotes:{name:'TWSE 價量',status:'unavailable',asOf:null,reason:'尚未載入'}},creditRule:{status:'pending',window:189}};
}
const isDate = value => typeof value==='string' && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
  Number.isFinite(Date.parse(`${value}T00:00:00Z`)) && new Date(`${value}T00:00:00Z`).toISOString().slice(0,10)===value;
function history(rows, fields, label, positive=[]) {
  if(!Array.isArray(rows)) throw new Error(`${label} 必須是陣列`);
  let previous='';
  for(const row of rows){
    if(!isDate(row?.date)||row.date<=previous) throw new Error(`${label} 日期須有效、遞增且不重複`);
    previous=row.date;
    for(const field of fields) if(row[field]!=null&&!numeric(row[field])) throw new Error(`${label} ${field} 必須是數字或 null`);
    for(const field of positive) if(row[field]!=null&&row[field]<=0) throw new Error(`${label} ${field} 必須大於零`);
  }
}
export function validateMarket(payload) {
  if(!payload||payload.schemaVersion!==2) throw new Error('需要 schemaVersion: 2；舊格式須由資料管線轉換，不能只改 mode');
  if(!['live','unavailable'].includes(payload.mode)) throw new Error('mode 必須是 live 或 unavailable；拒絕 DEMO/範例冒充正式資料');
  if(!Number.isFinite(Date.parse(payload.generatedAt))||!/(Z|[+-]\d{2}:\d{2})$/.test(payload.generatedAt)) throw new Error('generatedAt 需包含時區');
  if(payload.asOf!=null&&(!isDate(payload.asOf)||payload.asOf>payload.generatedAt.slice(0,10)||payload.asOf>new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Taipei'}))) throw new Error('asOf 日期錯誤或在未來');
  if(!Array.isArray(payload.stocks)||!payload.sources||typeof payload.sources!=='object') throw new Error('需要 stocks 及逐模組 sources');
  const seen=new Set();
  for(const stock of payload.stocks){
    if(!/^\d{4}$/.test(stock.symbol)||seen.has(stock.symbol)||typeof stock.name!=='string') throw new Error('股票代號/名稱錯誤或重複');
    seen.add(stock.symbol);
    history(stock.history,['close','volumeShares','changeAmount'],stock.symbol,['close']);
    if(stock.history.some(r=>r.date>payload.asOf||r.volumeShares!=null&&r.volumeShares<0)) throw new Error('股票日期或成交量不合法');
    history(stock.institutional||[],['foreignShares','trustShares','dealerShares','totalShares'],`${stock.symbol} 法人`);
    if(stock.margin){
      if(!isDate(stock.margin.date)) throw new Error('融資需要獨立資料日');
      for(const k of ['balanceShares','limitShares','usagePct']) if(stock.margin[k]!=null&&(!numeric(stock.margin[k])||stock.margin[k]<0)) throw new Error('融資單位或數值不合法');
    }
  }
  history(payload.indexHistory||[],['close'],'指數',['close']);
  history(payload.creditHistory||[],['hyg','shy','spy'],'信用',['hyg','shy','spy']);
  if((payload.creditHistory||[]).some(r=>!numeric(r.hyg)||r.hyg<=0||!numeric(r.shy)||r.shy<=0)) throw new Error('信用價格須完整配對且大於零');
  history(payload.futures||[],['foreign','trust','dealer'],'期貨');
  if((payload.futures||[]).some(r=>r.contract!=='TX'||r.unit!=='contracts'||['foreign','trust','dealer'].some(k=>!Number.isInteger(r[k])))) throw new Error('期貨須明確為 TX 淨未平倉，單位口');
  for(const [key,source] of Object.entries(payload.sources)){
    if(!['fresh','stale','error','unknown','unavailable','imported'].includes(source.status)) throw new Error('來源品質狀態不合法');
    if(source.asOf!=null&&!isDate(source.asOf)) throw new Error('來源日期不合法');
    if(source.fetchedAt&&(!Number.isFinite(Date.parse(source.fetchedAt))||!/(Z|[+-]\d{2}:\d{2})$/.test(source.fetchedAt))) throw new Error('來源抓取時間不合法');
    if(key!=='calendar'&&source.asOf>payload.generatedAt.slice(0,10)) throw new Error('來源資料日不能在未來');
    for(const k of ['url','license']) if(source[k]){try{const u=new URL(source[k]);if(u.protocol!=='https:'||u.username||u.password)throw new Error();}catch{throw new Error('來源及授權連結須為無憑證 HTTPS')}}
  }
  if(payload.mode==='live'&&(!isDate(payload.asOf)||!payload.stocks.length||payload.sources.quotes?.asOf!==payload.asOf||!/^([a-f0-9]{64})$/.test(payload.sources.quotes?.sha256||''))) throw new Error('live 需要可追溯的正式價量快照，不能把 DEMO 換標籤');
  if(payload.creditHistory?.length&&payload.sources.credit?.priceBasis!=='adjusted-total-return') throw new Error('信用資料必須明確為還原權息價');
  return payload;
}
export async function fetchMarket(url) {
  const res=await fetch(url,{cache:'no-store'});
  if(!res.ok) throw new Error(`讀取失敗：HTTP ${res.status}`);
  return validateMarket(await res.json());
}

export function effectiveStatus(source, calendar, now=new Date()) {
  if(!source||['error','unavailable','demo'].includes(source.status)) return source?.status||'unavailable';
  if(!source.asOf||!calendar?.rows?.length) return source.status;
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(now);
  const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));
  let day=new Date(`${p.year}-${p.month}-${p.day}T00:00:00Z`);
  if(Number(p.hour)<16 || Number(p.hour)===16 && Number(p.minute)<30) day.setUTCDate(day.getUTCDate()-1);
  const closed=new Set(calendar.rows.filter(r=>r.closed).map(r=>r.date));
  while([0,6].includes(day.getUTCDay())||closed.has(day.toISOString().slice(0,10))) day.setUTCDate(day.getUTCDate()-1);
  const expected=day.toISOString().slice(0,10);
  if(!calendar.rows.some(r=>r.date.slice(0,4)===expected.slice(0,4)))return 'unknown';
  return source.asOf<expected?'stale':source.status;
}
