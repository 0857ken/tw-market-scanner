// Pure calculations, shared by UI and tests. No invented current readings.
export const CREDIT = Object.freeze({ window: 189, center: 0.30, buffer: 0.05 });
export const COLORS = Object.freeze({ red: '#fb6373', green: '#2ec995', yellow: '#f2b84b', blue: '#78a9ff' });
export const round = (n, d = 2) => Number(Number(n).toFixed(d));
export const numeric = (v) => typeof v === 'number' && Number.isFinite(v);
export const format = (v, digits = 0) => numeric(v) ? v.toLocaleString('zh-TW', { minimumFractionDigits: digits, maximumFractionDigits: digits }) : '—';
export const signed = (v, digits = 2) => numeric(v) ? `${v > 0 ? '+' : ''}${format(v, digits)}%` : '—';
export const avg = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null;
export function lastMA(history, period, to = history.length - 1) {
  if (to < period - 1) return null;
  const values = history.slice(to + 1 - period, to + 1).map(r => r.close);
  return values.every(numeric) ? avg(values) : null;
}
export function creditLight(indicator) {
  if (!numeric(indicator)) return 'UNKNOWN';
  if (indicator < CREDIT.center - CREDIT.buffer) return 'GREEN';
  if (indicator >= CREDIT.center + CREDIT.buffer) return 'RED';
  return 'YELLOW';
}
export function computeCredit(raw, windowSize = CREDIT.window) {
  if (!Array.isArray(raw)) return [];
  const rows = raw.filter(r => r && typeof r.date === 'string' && numeric(r.hyg) && r.hyg > 0 && numeric(r.shy) && r.shy > 0)
    .map(r => ({ date: r.date, hyg: r.hyg, shy: r.shy, ratio: r.hyg / r.shy, spy: numeric(r.spy) ? r.spy : null }))
    .sort((a, b) => a.date.localeCompare(b.date));
  return rows.map((r, i) => {
    if (i + 1 < windowSize) return { ...r, indicator: null, light: 'UNKNOWN', position: null };
    const win = rows.slice(i + 1 - windowSize, i + 1);
    // Higher HYG/SHY rank means lower indicator (= less credit stress).
    const below = win.filter(x => x.ratio <= r.ratio).length;
    const indicator = round(1 - below / windowSize, 5);
    const prev = i ? rows.slice(i - windowSize, i) : [];
    const prevIndicator = prev.length === windowSize ? round(1 - prev.filter(x => x.ratio <= rows[i - 1].ratio).length / windowSize, 5) : null;
    return { ...r, indicator, light: creditLight(indicator), position: prevIndicator === null ? null : Number(prevIndicator < CREDIT.center) };
  });
}
export function rollingVol(history, period = 20) {
  if (history.length < period + 1) return null;
  const sub = history.slice(-period - 1);
  const rets = sub.slice(1).map((r, i) => r.close / sub[i].close - 1);
  if (!rets.every(numeric)) return null;
  const mean = avg(rets);
  const variance = rets.reduce((acc, r) => acc + (r - mean) ** 2, 0) / (rets.length - 1);
  return Math.sqrt(variance) * Math.sqrt(252) * 100;
}
export function detectRegime(history, period = 20) {
  if (history.length <= period) return { state: '資料不足', ret: null, vol: null };
  const h = history.slice(-period - 1), ret = (h.at(-1).close / h[0].close - 1) * 100;
  const vol = rollingVol(history, period);
  return { state: vol > 22 ? '高波動' : ret > 2.5 ? '趨勢多頭' : ret < -2.5 ? '趨勢空頭' : '盤整', ret, vol };
}
export function stockMetrics(stock) {
  const h = stock?.history || [];
  const latest = h.at(-1), previous = h.at(-2);
  const ma20 = lastMA(h, 20), ma60 = lastMA(h, 60), ma120 = lastMA(h, 120);
  const change = previous?.close > 0 ? (latest.close / previous.close - 1) * 100 : null;
  const prev60 = h.length >= 61 ? Math.max(...h.slice(-61, -1).map(r => r.close)) : null;
  const mean20Volume = h.length >= 21 ? avg(h.slice(-21, -1).map(r => r.volumeShares)) : null;
  const volRatio = mean20Volume > 0 ? latest.volumeShares / mean20Volume : null;
  return { ...stock, close: latest?.close ?? null, date: latest?.date ?? null, change, ma20, ma60, ma120,
    prev60, breakout60: numeric(prev60) && latest.close > prev60, volRatio, volumeShares: latest?.volumeShares ?? null };
}
export function computeBreadth(stocks, dates) {
  if (!Array.isArray(stocks) || !Array.isArray(dates)) return [];
  const result = dates.map(date => ({ date, a20: 0, a60: 0, a120: 0, n20: 0, n60: 0, n120: 0, up: 0, down: 0 }));
  const dateIndex = new Map(dates.map((d, i) => [d, i]));
  for (const stock of stocks) {
    const h = stock.history || [];
    let sums = { 20: 0, 60: 0, 120: 0 };
    for (let i = 0; i < h.length; i++) {
      const price = h[i].close;
      for (const n of [20, 60, 120]) {
        sums[n] += price;
        if (i >= n) sums[n] -= h[i - n].close;
      }
      const ri = dateIndex.get(h[i].date);
      if (ri == null) continue;
      const r = result[ri];
      for (const n of [20, 60, 120]) {
        if (i + 1 < n) continue;
        r[`n${n}`]++;
        if (price > sums[n] / n) r[`a${n}`]++;
      }
      if (i > 0) {
        if (price > h[i - 1].close) r.up++;
        if (price < h[i - 1].close) r.down++;
      }
    }
  }
  return result.map(r => {
    for (const n of [20, 60, 120]) r[`a${n}`] = r[`n${n}`] ? round(r[`a${n}`] / r[`n${n}`] * 100, 1) : null;
    return r;
  });
}

export function institutionalStreak(rows, key) {
  const vals = (rows || []).map(r => r?.[key]);
  if (!vals.length || !numeric(vals.at(-1)) || vals.at(-1) === 0) return { direction: 0, days: 0, shares: 0 };
  const sign = Math.sign(vals.at(-1));
  let days = 0, shares = 0;
  for (let i = vals.length - 1; i >= 0 && Math.sign(vals[i]) === sign; i--) { days++; shares += vals[i]; }
  return { direction: sign, days, shares };
}
export function getSignals(market) {
  const stocks = market?.stocks || [];
  const latest = stocks.map(stockMetrics);
  const dates = [...new Set(stocks.flatMap(s => (s.history || []).map(x => x.date)))].sort().slice(-120);
  const breadth = computeBreadth(stocks, dates);
  const credit = computeCredit(market.creditHistory || []);
  const creditNow = credit.at(-1);
  const futures = (market.futures || []).at(-1);
  const regime = detectRegime(market.indexHistory || []);
  const hits = latest.filter(s => s.breakout60);
  const b = breadth.at(-1);
  const alerts = [];
  if (creditNow?.light === 'RED') alerts.push({ level: 'danger', page: '信用利差', msg: `信用壓力指標 ${format(creditNow.indicator, 4)}，進入紅燈區` });
  if (creditNow?.light === 'YELLOW') alerts.push({ level: 'warn', page: '信用利差', msg: `信用壓力指標 ${format(creditNow.indicator, 4)}，處於緩衝區` });
  if (numeric(b?.a20) && b.a20 < 30) alerts.push({ level: 'warn', page: '市場廣度', msg: `站上 MA20 比例 ${b.a20}%，廣度偏弱（不保證即將反轉）` });
  if (numeric(b?.a20) && b.a20 > 70) alerts.push({ level: 'info', page: '市場廣度', msg: `站上 MA20 比例 ${b.a20}%，注意追價風險` });
  if (numeric(futures?.foreign) && futures.foreign < -15000) alerts.push({ level: 'warn', page: '期貨籌碼', msg: `外資期貨淨部位 ${format(futures.foreign)} 口；需連同選擇權及避險部位判讀` });
  const marginRisk = latest.filter(s => numeric(s.margin?.usagePct) && s.margin.usagePct >= 80);
  if (marginRisk.length) alerts.push({ level: 'warn', page: '融資水位', msg: `${marginRisk.length} 檔達到自訂融資使用率觀察門檻 80%（非斷頭保證）` });
  return { latest, dates, breadth, credit, creditNow, regime, futures, hits, marginRisk, alerts };
}
