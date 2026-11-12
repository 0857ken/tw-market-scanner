const $ = id => document.getElementById(id);
const snapshot = $('snapshot');
const status = $('import-status');
const approvedDigest = 'd1eb19e5c0d15d355b775200dd9c210dfae2994e6787ec9704076b6114e5fe0e';
const approvedSize = 477674;

snapshot.addEventListener('change', async () => {
  const file = snapshot.files[0];
  if (!file) return;
  snapshot.disabled = true;
  try {
    if (file.size !== approvedSize) throw new Error('Unexpected file size');
    const bytes = await file.arrayBuffer();
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    const hex = Array.from(new Uint8Array(digest), value => value.toString(16).padStart(2, '0')).join('');
    if (hex !== approvedDigest) throw new Error('Unexpected SHA256');
    const html = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    const payload = html.match(/<script id="r35-data" type="application\/json">([\s\S]*?)<\/script>/);
    if (!payload) throw new Error('Missing snapshot data');
    renderSnapshot(JSON.parse(payload[1]));
    $('workspace').hidden = false;
    status.textContent = '已核對並開啟 R3.6 歷史快照。關閉或重新整理分頁即可清除。';
  } catch {
    snapshot.disabled = false;
    status.textContent = '無法開啟。請選取原始 R3.6 交付包內的 site/index.html，並使用 HTTPS 或本機預覽。';
  } finally {
    snapshot.value = '';
  }
});


function renderSnapshot(D) {
const rows=D.rows,fmt=(v,d=2)=>v==null?'未知':Number(v).toLocaleString('zh-TW',{minimumFractionDigits:d,maximumFractionDigits:d});
$('asof').textContent=D.price_as_of;$('summary-date').textContent=D.price_as_of;$('chip').textContent=D.chip_as_of;
const calendarRange = D.calendar.coverage_start + ' 至 ' + D.calendar.coverage_end;
$('status').textContent = '歷史研究快照。行情保存至 ' + D.price_as_of
  + '。日曆核對範圍 ' + calendarRange + '。後續資料狀態待驗證。';
const chipLabels = {margin_100m: '融資', foreign_net_100m: '外資現貨', foreign_futures_net_short: '外資臺股期貨'};
for (const [key, label] of Object.entries(chipLabels)) {
  const series = D.chip_gaps && D.chip_gaps[key];
  const item = document.createElement('li');
  if (series && series.latest_saved_date) {
    const gaps = series.missing_since_latest || [];
    item.textContent = label + '保存至 ' + series.latest_saved_date
      + (gaps.length ? '。缺漏日期 ' + gaps.join('、') : '') + '。';
  } else {
    item.textContent = label + '覆蓋紀錄待驗證。';
  }
  $('chip-gaps').append(item);
}
const fields=[['close','收盤指數'],['ma20','MA20'],['ma60','MA60'],['ma120','MA120'],['k','KD · K'],['d','KD · D'],['rsi14','RSI14'],['drawdown20','20 日回檔 %']];
for(const [k,label] of fields){const e=document.createElement('div');e.className='card';const l=document.createElement('div');l.className='label';l.textContent=label;const v=document.createElement('div');v.className='value';v.dataset.metric=k;v.textContent=D.latest[k]==null?'資料不足':fmt(D.latest[k]*(k==='drawdown20'?100:1));e.append(l,v);$('metrics').append(e)}
const labels={SCHEDULED_OPEN:'預定交易日',EMERGENCY_CLOSED:'臨時休市',HOLIDAY_CLOSED:'國定假日／市場休市',WEEKEND:'週末',TRADING_DATA_AVAILABLE:'已有交易資料',FUTURE_SESSION:'未來日期',AWAITING_PUBLICATION:'等待發布',MISSING_EXPECTED_SESSION_REVIEW_REQUIRED:'缺資料，需查核',CLOSED_DAY_HAS_DATA:'來源衝突'};
for(const r of D.calendar.days){const tr=document.createElement('tr');for(const v of [r.date,labels[r.category]||r.category,labels[r.data_state]||r.data_state]){const td=document.createElement('td');td.textContent=v;tr.append(td)}$('calendar').append(tr)}
$('scope').textContent='本次官方回應：'+D.coverage.first_date+' 至 '+D.coverage.last_date+'，共 '+D.coverage.sessions+' 日；已保留並逐欄核對 R3.4 的 15 日資料。';
rows.forEach((r,i)=>{const o=document.createElement('option');o.value=i;o.textContent=r.date;$('date').append(o)});
$('cursor').min=0;$('cursor').max=rows.length-1;$('cursor').value=rows.length-1;$('date').value=rows.length-1;
function draw(){const idx=+$('date').value,n=+$('window').value,a=rows.slice(Math.max(0,idx-n+1),idx+1),W=960,H=380,pad=48,values=a.flatMap(r=>[r.high,r.low,r.ma20,r.ma60,r.ma120].filter(v=>v!=null)),lo=Math.min(...values)*.996,hi=Math.max(...values)*1.004,y=v=>H-pad-(v-lo)/(hi-lo)*(H-2*pad),x=i=>pad+(i+.5)*(W-2*pad)/a.length;let s='';for(let i=0;i<5;i++){const v=lo+(hi-lo)*i/4,yy=y(v);s+=`<line x1="${pad}" x2="${W-pad}" y1="${yy}" y2="${yy}" stroke="#344454"/><text x="4" y="${yy}" fill="#a8bacb" font-size="14">${Math.round(v)}</text>`}a.forEach((r,i)=>{const c=r.close>=r.open?'#ff8589':'#6bdfb1',xx=x(i),w=Math.max(2,(W-2*pad)/a.length*.65);s+=`<line x1="${xx}" x2="${xx}" y1="${y(r.high)}" y2="${y(r.low)}" stroke="${c}"/><rect x="${xx-w/2}" y="${Math.min(y(r.open),y(r.close))}" width="${w}" height="${Math.max(1,Math.abs(y(r.open)-y(r.close)))}" fill="${c}"/>`});for(const [k,c] of [['ma20','#ffd166'],['ma60','#8bc5ff'],['ma120','#c5a3ff']]){const points=a.map((r,i)=>r[k]==null?'':`${x(i)},${y(r[k])}`).filter(Boolean).join(' ');s+=`<polyline fill="none" stroke="${c}" stroke-width="2" points="${points}"/>`}$('chart').innerHTML=s;const r=rows[idx];$('quote').textContent=r.date+'　開 '+fmt(r.open)+'　高 '+fmt(r.high)+'　低 '+fmt(r.low)+'　收 '+fmt(r.close);$('cursor').value=idx;renderSignals(idx)}
function renderSignals(idx){$('signals').textContent='';$('signal-date').textContent=rows[idx].date;$('backtest-note').textContent='DESCRIPTIVE_ONLY · 正式 PIT BLOCKED。'+D.backtest_status;for(const [key,label] of Object.entries(D.signal_labels)){const e=document.createElement('div');e.className='card';const t=document.createElement('div');t.className='label';t.textContent=key==='high_turnover_fall'?'下跌且成交額 > 前20日均額 1.4倍':label;const v=document.createElement('div');v.dataset.signal=key;const state=D.signals[idx][key];v.textContent=state==null?'資料不足／未知':state?'符合研究條件':'未符合';e.append(t,v);$('signals').append(e)}}
$('date').addEventListener('change',draw);$('window').addEventListener('change',draw);$('cursor').addEventListener('input',()=>{$('date').value=$('cursor').value;draw()});draw();
}
