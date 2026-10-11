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
  return { schemaVersion: 1, mode: 'demo', asOf: '2026-06-30', source: '固定隨機種子／虛構示範市場', universe: '40 檔示範觀察池（非全部上市櫃）', indexHistory, stocks, futures, creditHistory };
}
function validHistory(rows) { return Array.isArray(rows) && rows.every(r => typeof r.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(r.date) && numeric(r.close) && r.close > 0 && (r.volumeShares == null || numeric(r.volumeShares))); }
export function validateMarket(payload) {
  if (!payload || payload.schemaVersion !== 1) throw new Error('資料格式不相容：需要 schemaVersion: 1；Claude 的 market.json 欄位必須先對應，不可直接假設相容。');
  if (payload.mode !== 'live') throw new Error('匯入正式資料須標記 mode: live；範例與模擬行情不可以當成正式資料。');
  if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.asOf || '')) throw new Error('缺少合法 asOf (YYYY-MM-DD)。');
  if (!Array.isArray(payload.stocks)) throw new Error('stocks 必須是陣列。');
  const seen = new Set();
  for (const stock of payload.stocks) {
    if (typeof stock.symbol !== 'string' || !/^\d{4}[A-Z]?$/i.test(stock.symbol) || seen.has(stock.symbol)) throw new Error(`代號錯誤或重複：${String(stock.symbol)}`);
    seen.add(stock.symbol);
    if (!validHistory(stock.history)) throw new Error(`${stock.symbol} 缺少有效 history：每筆需 date、close、可選 volumeShares。`);
    if (!stock.history.every((r, i, arr) => i === 0 || arr[i - 1].date < r.date)) throw new Error(`${stock.symbol} 的 history 日期必須遞增且不重複。`);
    if (stock.institutional && (!Array.isArray(stock.institutional) || !stock.institutional.every(r => typeof r.date === 'string' && ['foreignShares','trustShares','dealerShares'].every(k => r[k] == null || numeric(r[k]))))) throw new Error(`${stock.symbol} institutional 欄位或單位錯誤（應為股數）。`);
  }
  if (payload.indexHistory && !validHistory(payload.indexHistory)) throw new Error('indexHistory 格式錯誤。');
  if (payload.creditHistory && !payload.creditHistory.every(r => typeof r.date === 'string' && numeric(r.hyg) && numeric(r.shy))) throw new Error('creditHistory 格式錯誤。');
  if (payload.futures && !payload.futures.every(r => typeof r.date === 'string' && ['foreign','trust','dealer'].every(k => r[k] == null || numeric(r[k])))) throw new Error('futures 格式錯誤：單位應為口。');
  // Does not alter or create data; optional features stay unavailable until supplied.
  return { ...payload, mode: 'live', source: payload.source || '使用者匯入資料', universe: payload.universe || `${payload.stocks.length} 檔匯入標的` };
}
export async function fetchMarket(url) {
  const res = await fetch(url, { cache: 'no-store' });
  if (!res.ok) throw new Error(`讀取失敗：HTTP ${res.status}`);
  return validateMarket(await res.json());
}
