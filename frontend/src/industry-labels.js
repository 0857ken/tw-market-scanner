// Display-only dictionary. Official references and market differences:
// docs/INDUSTRY_LABELS_ACCEPTANCE.md. Never use these labels as grouping keys.
const common = Object.freeze({
  '02':'食品工業','03':'塑膠工業','04':'紡織纖維','05':'電機機械','06':'電器電纜',
  '08':'玻璃陶瓷','10':'鋼鐵工業','11':'橡膠工業','14':'建材營造','15':'航運業',
  '16':'觀光餐旅','20':'其他','21':'化學工業','22':'生技醫療業','23':'油電燃氣業',
  '24':'半導體業','25':'電腦及週邊設備業','26':'光電業','27':'通信網路業',
  '28':'電子零組件業','29':'電子通路業','30':'資訊服務業','31':'其他電子業',
  '35':'綠能環保','36':'數位雲端','37':'運動休閒','38':'居家生活'
});
const names = Object.freeze({
  TWSE:Object.freeze({...common,'01':'水泥工業','09':'造紙工業','12':'汽車工業','17':'金融保險','18':'貿易百貨','19':'綜合'}),
  TPEx:Object.freeze({...common,'17':'金融業','32':'文化創意業','33':'農業科技業','80':'管理股票'})
});
const codeOf = raw => /^(?:產業\s+)?(\d{1,2})$/.exec(String(raw ?? '').trim())?.[1].padStart(2,'0');
const unknown = raw => `${raw || '未分類'}（分類未確認）`;

export function industryLabel(row) {
  const raw=String(row.sector ?? '').trim();
  const code=codeOf(row.sectorCode ?? raw);
  if(!code) return raw && !/^產業(?:\s|$)/.test(raw) ? raw : unknown(raw);
  const label=names[row.market]?.[code];
  return label ? `${label}（${code}）` : unknown(raw || `產業 ${row.sectorCode ?? code}`);
}

export function industryGroupLabel(raw, rows) {
  const code=codeOf(raw);
  if(!code) return /^產業(?:\s|$)/.test(raw ?? '') ? unknown(raw) : (raw || '未分類');
  const markets=[...new Set(rows.map(r=>r.market))].sort();
  if(!markets.length || markets.some(m=>!names[m]?.[code])) return unknown(raw);
  // Existing ALL-market groups stay intact even where official names differ.
  const labels=[...new Set(markets.map(m=>names[m][code]))];
  return `${labels.join('／')}（${code}）`;
}
