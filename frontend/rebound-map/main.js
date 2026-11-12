import publicSnapshot from './public-snapshot.json';

const $ = id => document.getElementById(id);
const snapshot = $('snapshot');
const status = $('import-status');
const approvedDigest = 'd1eb19e5c0d15d355b775200dd9c210dfae2994e6787ec9704076b6114e5fe0e';
const approvedSize = 477674;

snapshot.addEventListener('change', async () => {
  const file = snapshot.files[0];
  if (!file) return;
  snapshot.disabled = true;
  $('show-public').disabled = true;
  try {
    if (file.size !== approvedSize) throw new Error('Unexpected file size');
    const bytes = await file.arrayBuffer();
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    const hex = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('');
    if (hex !== approvedDigest) throw new Error('Unexpected SHA256');
    const html = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    const payload = html.match(/<script id="r35-data" type="application\/json">([\s\S]*?)<\/script>/);
    if (!payload) throw new Error('Missing snapshot data');
    renderSnapshot(JSON.parse(payload[1]), false);
    status.textContent = '已核對並開啟 R3.6 歷史快照。關閉或重新整理分頁即可清除。';
  } catch {
    status.textContent = '無法開啟。請選取原始 R3.6 交付包內的 site/index.html，並使用 HTTPS 或本機預覽。';
  } finally {
    snapshot.value = '';
    snapshot.disabled = false;
    $('show-public').disabled = false;
  }
});


const standardWindows = [...$('window').options].map(option => [option.value, option.textContent]);
const sourceLinks = $('source-links');
for (const source of publicSnapshot.sources) {
  const item = document.createElement('li');
  const link = (url, text) => {
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.textContent = text;
    return anchor;
  };
  item.append(`${source.agency}（${source.origin}） · `,
    link(source.dataset_url, source.name), ' · ', link(source.raw_url, '官方 CSV'),
    ' · ', link(source.license.url, source.license.name));
  sourceLinks.append(item);
}

$('show-public').onclick = () => {
  status.textContent = '';
  renderSnapshot(publicSnapshot, true);
};

const fmt = (value, decimals = 2) => Number(value).toLocaleString('zh-TW', {
  minimumFractionDigits: decimals, maximumFractionDigits: decimals,
});
const metrics = [
  ['close', '收盤指數'], ['ma20', 'MA20'], ['ma60', 'MA60'], ['ma120', 'MA120'],
  ['k', 'KD · K'], ['d', 'KD · D'], ['rsi14', 'RSI14'], ['drawdown20', '20 日回檔 %'],
];
const calendarLabels = {
  SCHEDULED_OPEN: '預定交易日', EMERGENCY_CLOSED: '臨時休市',
  HOLIDAY_CLOSED: '國定假日／市場休市', WEEKEND: '週末', TRADING_DATA_AVAILABLE: '已有交易資料',
  FUTURE_SESSION: '未來日期', AWAITING_PUBLICATION: '等待發布',
  MISSING_EXPECTED_SESSION_REVIEW_REQUIRED: '缺資料，需查核', CLOSED_DAY_HAS_DATA: '來源衝突',
};

function createCard(label, value) {
  const card = document.createElement('div');
  card.className = 'card';
  const caption = document.createElement('div');
  caption.className = 'label';
  caption.textContent = label;
  card.append(caption, value);
  return card;
}

function renderPrivateDetails(data, isPublic) {
  $('chip-gaps').replaceChildren();
  $('calendar').replaceChildren();
  $('scope').textContent = '';
  if (isPublic) return;
  const chipLabels = {margin_100m: '融資', foreign_net_100m: '外資現貨', foreign_futures_net_short: '外資臺股期貨'};
  for (const [key, label] of Object.entries(chipLabels)) {
    const series = data.chip_gaps?.[key];
    const item = document.createElement('li');
    const gaps = series?.missing_since_latest ?? [];
    item.textContent = series?.latest_saved_date
      ? `${label}保存至 ${series.latest_saved_date}。${gaps.length ? `缺漏日期 ${gaps.join('、')}。` : ''}`
      : `${label}覆蓋紀錄待驗證。`;
    $('chip-gaps').append(item);
  }
  for (const row of data.calendar.days) {
    const tr = document.createElement('tr');
    for (const value of [row.date, calendarLabels[row.category], calendarLabels[row.data_state]]) {
      const cell = document.createElement('td');
      cell.textContent = value ?? '未知';
      tr.append(cell);
    }
    $('calendar').append(tr);
  }
  const {first_date, last_date, sessions} = data.coverage;
  $('scope').textContent = `本次官方回應涵蓋 ${first_date} 至 ${last_date}，共 ${sessions} 日。已保留並逐欄核對 R3.4 的 15 日資料。`;
}

function drawChart(rows) {
  const width = 960, height = 380, pad = 48;
  const averages = [['ma20', '#ffd166'], ['ma60', '#8bc5ff'], ['ma120', '#c5a3ff']];
  const values = rows.flatMap(r => [r.high, r.low, ...averages.map(([key]) => r[key])]).filter(v => v != null);
  const lo = Math.min(...values) * .996, hi = Math.max(...values) * 1.004;
  const y = value => height-pad-(value-lo)/(hi-lo)*(height-2*pad);
  const x = i => pad+(i+.5)*(width-2*pad)/rows.length;
  const w = Math.max(2, (width-2*pad)/rows.length*.65);
  let svg = '';
  for (let i = 0; i < 5; i++) {
    const value = lo+(hi-lo)*i/4, yy = y(value);
    svg += `<line x1="${pad}" x2="${width-pad}" y1="${yy}" y2="${yy}" stroke="#344454"/><text x="4" y="${yy}" fill="#a8bacb" font-size="14">${Math.round(value)}</text>`;
  }
  rows.forEach((row, i) => {
    const color = row.close >= row.open ? '#ff8589' : '#6bdfb1';
    const top = Math.min(y(row.open), y(row.close));
    const body = Math.max(1, Math.abs(y(row.open)-y(row.close)));
    svg += `<line x1="${x(i)}" x2="${x(i)}" y1="${y(row.high)}" y2="${y(row.low)}" stroke="${color}"/>`;
    svg += `<rect x="${x(i)-w/2}" y="${top}" width="${w}" height="${body}" fill="${color}"/>`;
  });
  for (const [key, color] of averages) {
    const points = rows.flatMap((row, i) => row[key] == null ? [] : [`${x(i)},${y(row[key])}`]).join(' ');
    if (points) svg += `<polyline fill="none" stroke="${color}" stroke-width="2" points="${points}"/>`;
  }
  $('chart').innerHTML = svg;
}

function renderSnapshot(data, isPublic) {
  const {rows} = data;
  $('workspace').hidden = false;
  $('show-public').hidden = isPublic;
  $('public-sources').hidden = !isPublic;
  $('private-calendar').hidden = isPublic;
  $('private-scope').hidden = isPublic;
  $('asof').textContent = data.price_as_of;
  $('summary-date').textContent = data.price_as_of;
  $('chip').textContent = data.chip_as_of ?? '資料不足';
  $('status').textContent = isPublic
    ? `截至 ${data.price_as_of.replaceAll('-', '/')} 的歷史研究快照 · ${rows.length} 個交易日`
    : `私人 R3.6 歷史研究快照 · 行情保存至 ${data.price_as_of}。日曆核對範圍 ${data.calendar.coverage_start} 至 ${data.calendar.coverage_end}。`;
  $('backtest-note').textContent = 'DESCRIPTIVE_ONLY · 正式 PIT BLOCKED · 歷史合格 PIT 樣本 0。' + (data.backtest_status ?? '');
  renderPrivateDetails(data, isPublic);

  const latest = isPublic ? rows.at(-1) : data.latest;
  $('metrics').replaceChildren(...metrics.map(([key, label]) => {
    const value = document.createElement('div');
    value.className = 'value';
    value.dataset.metric = key;
    const number = latest[key];
    value.textContent = number == null ? '資料不足' : fmt(number * (key === 'drawdown20' ? 100 : 1));
    return createCard(label, value);
  }));

  const windows = isPublic ? [[String(rows.length), `全部 ${rows.length} 日`]] : standardWindows;
  $('window').replaceChildren(...windows.map(([value, label]) => new Option(label, value)));
  $('window').value = isPublic ? String(rows.length) : '60';
  $('date').replaceChildren(...rows.map((row, i) => new Option(row.date, i)));
  $('cursor').min = 0;
  $('cursor').max = rows.length - 1;
  $('date').value = rows.length - 1;

  function draw() {
    const i = Number($('date').value);
    const row = rows[i];
    drawChart(rows.slice(Math.max(0, i-Number($('window').value)+1), i+1));
    $('quote').textContent = `${row.date}　開 ${fmt(row.open)}　高 ${fmt(row.high)}　低 ${fmt(row.low)}　收 ${fmt(row.close)}`;
    $('turnover').textContent = row.turnover == null ? '成交金額：資料不足' : `成交金額：NT$ ${fmt(row.turnover, 0)}`;
    $('cursor').value = i;
    $('signal-date').textContent = row.date;
    $('signals').replaceChildren(...Object.entries(data.signal_labels).map(([key, label]) => {
      const value = document.createElement('div');
      value.dataset.signal = key;
      const state = data.signals[i][key];
      value.textContent = state == null ? '資料不足（UNKNOWN）' : state ? '符合研究條件' : '未符合';
      return createCard(key === 'high_turnover_fall' ? '下跌且成交額 > 前20日均額 1.4倍' : label, value);
    }));
  }

  $('date').onchange = draw;
  $('window').onchange = draw;
  $('cursor').oninput = () => {
    $('date').value = $('cursor').value;
    draw();
  };
  draw();
}

renderSnapshot(publicSnapshot, true);
