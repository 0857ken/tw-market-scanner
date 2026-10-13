import {MARKET_NAMES,BASIS_NAMES,securityKey,memberOn,marketMeta,breakoutSelection} from './research.js';
import React, { useMemo, useRef, useState, useEffect } from 'react';
import {
  ResponsiveContainer, ComposedChart, LineChart, BarChart, Line, Bar, Cell, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, Treemap
} from 'recharts';
import { LayoutDashboard, Activity, Compass, TrendingUp, Menu, X, Search, Database, ChevronRight, ChevronDown,
  CheckCircle2, AlertTriangle, ShieldAlert, BarChart3, Layers, LineChart as LineIcon, RotateCcw,
  CalendarDays, Upload, Info, Star,
  BookOpen, Waves, Building2, FlaskConical, Radio,
  Zap, CircleHelp
} from 'lucide-react';
import { makeDemo, makeUnavailable, validateMarket, fetchMarket, effectiveStatus } from './data.js';
import { CREDIT, COLORS, numeric, format, signed, avg, stockMetrics, getSignals, detectRegime, rollingVol,
  institutionalStreak, creditLight, lastMA, round } from './logic.js';

const NAV = [
  { label: '核心', items: [['總覽', LayoutDashboard], ['資料健康', Database], ['我的關注', Star], ['信用利差', ShieldAlert], ['市場廣度', Waves], ['市場體制', Compass]] },
  { label: '市場掃描', items: [['台股熱力圖', Layers], ['美股熱力圖', Layers], ['高點突破', Zap], ['產業輪動', Building2], ['盤中量能', BarChart3]] },
  { label: '法人籌碼', items: [['法人買賣超', BarChart3], ['連續買賣超', TrendingUp], ['期貨籌碼', LineIcon], ['融資水位', BarChart3], ['券商分點', Building2]] },
  { label: '研究工具', items: [['盤前觀察', CalendarDays], ['研究週報', BookOpen], ['持股水位', Activity]] },
];
const LIGHTS = {
  GREEN: { cn: '綠燈', color: COLORS.green, desc: '信用風險相對較低（非保證安全）', action: '正常風險監控' },
  YELLOW: { cn: '黃燈', color: COLORS.yellow, desc: '指標位於閾值緩衝區', action: '觀察趨勢變化' },
  RED: { cn: '紅燈', color: COLORS.red, desc: '信用風險相對升高', action: '檢視槓桿與風險' },
  UNKNOWN: { cn: '資料不足', color: '#8da1bc', desc: '需要至少 189 個有效交易日', action: '等待資料' },
  PENDING: { cn: '規則待確認', color: '#b8a4ff', desc: '依原始截圖還原中；不啟用未確認的燈號與部位規則', action: '等待原始規則' },
};
const CV = { danger: COLORS.red, warn: COLORS.yellow, info: '#6fb3fa' };
const NAV_NAMES = NAV.flatMap(group => group.items.map(row => row[0]));
const tooltipProps = { contentStyle: { background: '#131f32', border: '1px solid #27364c', borderRadius: 10, color: '#e7edf6', fontSize: 12 }, labelStyle: { color: '#adbed2' } };
const axisProps = { tick: { fill: '#8093ae', fontSize: 10 }, tickLine: false, axisLine: false, minTickGap: 30 };
const sharesToLots = n => numeric(n) ? n / 1000 : null;
const getInst = (s, key) => s.institutional?.at(-1)?.[key] ?? null;
const candleColor = v => v > 0 ? COLORS.red : v < 0 ? COLORS.green : '#94a3b8'; // Taiwan red up
const readableDate = date => date || '—';
const lightDate = s => typeof s==='string' ? s.slice(5) : s?.date?.slice(5) || '';
const Help = ({ children }) => <span title={children} className="help"><CircleHelp size={13}/></span>;

function Panel({ title, subtitle, right, children, className = '' }) {
  return <section className={`panel ${className}`}>
    {(title || right) && <div className="panel-head"><div><h2>{title}</h2>{subtitle && <p className="muted tiny">{subtitle}</p>}</div>{right}</div>}
    {children}
  </section>;
}
function Pill({ children, tone = 'neutral' }) { return <span className={`pill pill-${tone}`}>{children}</span>; }
function Empty({ title, detail, icon: Icon = Database }) { return <div className="empty"><Icon size={28} strokeWidth={1.5}/><h3>{title}</h3><p>{detail}</p></div>; }
function Metric({ title, value, note, tone, onClick, icon: Icon }) {
  return <button type="button" className={`metric metric-${tone || 'normal'}`} onClick={onClick} disabled={!onClick}>
    <div className="metric-top"><span>{title}</span>{Icon && <Icon size={16}/>}</div><div className="metric-value">{value}</div><div className="metric-note">{note}</div>
  </button>;
}
function Percent({ value }) { return <span className="num" style={{ color: candleColor(value) }}>{signed(value)}</span>; }
function Toggle({ value, setValue, options }) { return <div className="segmented">{options.map(o => <button type="button" className={value === o ? 'sel' : ''} key={o} onClick={() => setValue(o)}>{o}</button>)}</div>; }
function DataGrid({ columns, rows, onRow, empty='暫無符合條件資料' }) {
  const [sort,setSort]=useState({key:null,descending:false});
  const ordered=useMemo(()=>!sort.key?rows:[...(rows||[])].sort((a,b)=>{
    const column=columns.find(c=>c.key===sort.key);
    const av=column?.sortValue?column.sortValue(a):a[sort.key],bv=column?.sortValue?column.sortValue(b):b[sort.key];
    if(av==null)return bv==null?0:1;if(bv==null)return -1;
    const c=numeric(av)&&numeric(bv)?av-bv:String(av).localeCompare(String(bv),'zh-TW',{numeric:true});
    return sort.descending?-c:c;
  }),[rows,sort,columns]);
  if (!rows?.length) return <Empty title={empty} detail="可以調整條件，或檢查目前是否有完整資料。" />;
  return <div className="table-scroll" tabIndex={0} aria-label="可左右捲動的資料表"><table><thead><tr>{columns.map(c => <th key={c.key} aria-sort={sort.key===c.key?(sort.descending?'descending':'ascending'):'none'} className={c.left ? 'align-left' : ''}><button type="button" disabled={!c.sortValue&&rows.every(r=>r[c.key]==null)} onClick={()=>setSort({key:c.key,descending:sort.key===c.key?!sort.descending:false})}>{c.name}{sort.key===c.key?(sort.descending?' ↓':' ↑'):''}</button></th>)}</tr></thead>
    <tbody>{ordered.map((row, idx) => <tr key={row.securityId || row.symbol || row.date || row.name || idx} tabIndex={onRow?0:undefined} onKeyDown={e=>{if(e.key==='Enter')onRow?.(row)}} className={onRow ? 'clickrow' : ''} onClick={() => onRow?.(row)}>{columns.map(c => <td key={c.key} className={c.left ? 'align-left' : ''}>{c.render ? c.render(row) : row[c.key] ?? '—'}</td>)}</tr>)}</tbody></table></div>;
}
const nameCol = { key: 'symbol', name: '股票', left: true, render: r => <div className="stockname"><b>{r.symbol}</b><span>{r.name}</span></div> };
const changeCol = { key: 'change', name: '漲跌幅', render: r => <Percent value={r.change}/> };
const stockCols = [nameCol, { key: 'close', name: '收盤價', render: r => <span className="num">{format(r.close, 2)}</span> }, changeCol];
function Spark({ rows, valueKey, color, height = 195, rightAxis = false, lineName = '指標', lines = [] }) {
  const valid = rows?.filter(r => numeric(r[valueKey]));
  if (!valid || valid.length < 2) return <Empty title="可繪製資料不足" detail="價格歷史至少需要 2 筆有效資料。"/>;
  return <div style={{ height }} className="chart-wrap"><ResponsiveContainer width="100%" height="100%">
    <ComposedChart data={valid} margin={{ top: 8, right: rightAxis ? 7 : 2, left: -22, bottom: 0 }}>
      <CartesianGrid stroke="#203046" vertical={false} strokeDasharray="3 4"/>
      <XAxis dataKey="date" {...axisProps} tickFormatter={lightDate}/><YAxis {...axisProps} domain={['auto','auto']}/>
      <Tooltip {...tooltipProps}/><Line type="monotone" name={lineName} dataKey={valueKey} stroke={color || '#7aa5f8'} dot={false} strokeWidth={2} isAnimationActive={false}/>
      {lines.map(line => <Line key={line.key} type="monotone" dataKey={line.key} name={line.name} stroke={line.color} dot={false} strokeWidth={1.4} connectNulls={false} isAnimationActive={false}/>)}
    </ComposedChart>
  </ResponsiveContainer></div>;
}
function Overview({ market, signals, go, onStock, watchlist }) {
  const { creditNow, futures, breadth, regime, hits, latest, alerts, marginRisk } = signals;
  const light = LIGHTS[market.creditRule?.status!=='confirmed'?'PENDING':creditNow?.light || 'UNKNOWN'], b = breadth.at(-1), idx = market.indexHistory?.at(-1);
  const bestStocks = [...latest].filter(s => numeric(s.change)).sort((a, b) => b.change - a.change).slice(0, 6);
  const newestDate = idx?.date || market.asOf;
  return <>
    <div className="dashboard-hero">
      <div className="hero-identity"><div className="eyebrow"><Radio size={13}/> MARKET PULSE <span className="hero-dot"/></div>
        <h1>市場盤後，一眼掌握。</h1>
        <p>信用風險、廣度、趨勢與籌碼，集中在同一個畫面。所有資料都標示來源與日期。</p>
        <div className="hero-tags"><Pill tone={market.mode === 'demo' ? 'warn' : 'neutral'}>{market.mode === 'demo' ? '虛構示範資料' : market.mode==='live'?'官方盤後快照':'尚未載入'}</Pill><span>{newestDate||'—'}</span><span>{market.universe}</span></div>
      </div>
      <div className="hero-signal" onClick={() => go('信用利差')} role="button" tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') go('信用利差'); }}>
        <div className="signal-label">信用壓力燈號 <ChevronRight size={16}/></div><div className="hero-signal-status" style={{ color: light.color }}><span className="signal-dot" style={{ background: light.color }}/>{light.cn}</div>
        <div className="signal-sub">指標 {format(creditNow?.indicator, 4)}　·　{light.action}</div>
      </div>
    </div>
    <div className="metrics-grid">
      <Metric title="加權指數" value={format(idx?.close, 0)} note={`資料日 ${idx?.date || '—'}`} icon={TrendingUp} />
      <Metric title="站上 20 日均線" value={numeric(b?.a20) ? `${format(b.a20, 1)}%` : '—'} note={b?.n20?`${b.n20} 檔有效標的`:'需 20 日有效歷史'} icon={Waves} onClick={() => go('市場廣度')}/>
      <Metric title="市場體制" value={regime.state} note={`年化波動 ${format(regime.vol, 1)}%`} icon={Compass} onClick={() => go('市場體制')}/>
      <Metric title="外資期貨淨部位" value={numeric(futures?.foreign) ? `${format(futures.foreign)} 口` : '—'} note={futures?.date || '尚未接入'} icon={LineIcon} onClick={() => go('期貨籌碼')}/>
      <Metric title="60 日高點突破" value={signals.breakoutEligible?`${hits.length} 檔`:'暖機中'} note={`需 61 個有效交易日 · 可用 ${signals.breakoutEligible} 檔`} icon={Zap} onClick={() => go('高點突破')}/>
      <Metric title="融資高水位" value={marginRisk.length ? `${marginRisk.length} 檔` : `${latest.filter(s=>numeric(s.margin?.usagePct)).length ? '0 檔' : '—'}`} note="自訂監控門檻 ≥80%" icon={ShieldAlert} onClick={() => go('融資水位')}/>
    </div>
    <div className="two-columns overview-columns">
      <Panel title="市場風險雷達" subtitle="條件警示，不是交易指令" right={<Pill tone={alerts.length ? 'warn' : 'good'}>{alerts.length} 則警示</Pill>}>
        {alerts.length ? <div className="alert-list">{alerts.map((a, i) => <button className="alert-item" key={`${a.page}-${i}`} onClick={() => go(a.page)}><span className="alert-icon" style={{ color: CV[a.level], background: `${CV[a.level]}17` }}><AlertTriangle size={17}/></span><span><b>{a.page}</b><small>{a.msg}</small></span><ChevronRight size={16}/></button>)}</div>
          : <div className="quiet"><Info size={19}/> 已接入資料未觸發觀察條件；缺資料或暖機中的模組無法判定風險。</div>}
      </Panel>
      <Panel title="指數走勢" subtitle={`資料日 ${market.indexHistory?.at(-1)?.date || '—'} · 非即時報價`} right={<button className="softlink" onClick={() => go('市場體制')}>體制分析 <ChevronRight size={14}/></button>}>
        <Spark rows={(market.indexHistory||[]).slice(-120)} valueKey="close" color="#f3c875" height={242} lineName="加權指數"/>
      </Panel>
    </div>
    <div className="two-columns">
      <Panel title="強勢股觀察" subtitle="依當日漲幅排序；點選個股查看資料" right={<button className="softlink" onClick={() => go('高點突破')}>查看突破 <ChevronRight size={14}/></button>}>
        <DataGrid rows={bestStocks} columns={stockCols} onRow={onStock}/>
      </Panel>
      <Panel title="我的關注名單" subtitle="僅儲存在此瀏覽器，不會同步到其他裝置" right={<button className="softlink" onClick={() => go('我的關注')}>管理 <ChevronRight size={14}/></button>}>
        {watchlist.length ? <DataGrid rows={latest.filter(s => watchlist.includes(securityKey(s))||watchlist.includes(s.symbol)&&s.market!=='TPEx')} columns={stockCols} onRow={onStock}/>
        : <Empty title="尚未加入關注股票" detail="點選個股後按星號，即可建立個人的研究清單。" icon={Star}/>}
      </Panel>
    </div>
  </>;
}
function CreditView({ market, signals, range, setRange }) {
  const rows = signals.credit.filter(r => numeric(r.indicator));
  const [cursor, setCursor] = useState(null);
  const pos = cursor == null ? rows.length - 1 : Math.min(cursor, rows.length - 1);
  const now = rows[pos];
  const light = LIGHTS[market.creditRule?.status!=='confirmed'?'PENDING':now?.light || 'UNKNOWN'];
  const chart = rows.slice(0, pos + 1).slice(-({ '60D': 60, '120D':120, '1Y':252, '全部':rows.length }[range] || 120));
  return <>
    <div className="credit-hero panel">
      <div className="eyebrow">CREDIT SPREAD RISK MONITOR</div>
      <div className="credit-light" style={{ color: light.color }}><span className="signal-dot" style={{ background: light.color }}/>{light.cn}<span className="credit-en">{market.creditRule?.status!=='confirmed'?'PENDING':now?.light || 'UNKNOWN'}</span></div>
      <p className="muted">{light.desc}</p>
      <div className="credit-stats"><span>指標 <b>{format(now?.indicator, 4)}</b></span><span>HYG / SHY <b>{format(now?.ratio, 4)}</b></span><span>資料日期 <b>{readableDate(now?.date)}</b></span></div>
      {market.creditRule?.status==='confirmed'?<div className="credit-keys"><span>綠 &lt; {market.creditRule.greenBelow}</span><span>黃：緩衝區</span><span>紅 ≥ {market.creditRule.redAtOrAbove}</span></div>:<div className="tip">截圖出現 0.30、0.28 / 0.32，且 0.2540 為紅燈；原始判定尚未唯一還原。保留指標，不發布假定燈號。HYG / SHY 目前未接入可公開轉載的資料。</div>}
    </div>
    <Panel title="歷史回放" subtitle="拖曳後，燈號、數值與下方走勢會一起回到所選日期" right={cursor !== null && <button className="softlink" onClick={() => setCursor(null)}><RotateCcw size={13}/> 回最新</button>}>
      {rows.length > 0 ? <><input aria-label="信用利差歷史日期" className="range-input" type="range" min="0" max={rows.length-1} value={pos} onChange={e => setCursor(Number(e.target.value))}/>
        <div className="range-label"><span>{rows[0].date}</span><strong>{now.date}</strong><span>{rows.at(-1).date}</span></div></> : <Empty title="無法回放" detail="需要完整 HYG、SHY 還原權息價，至少 189 個交易日。"/>}
    </Panel>
    <Panel title="信用壓力指標 × SPY" subtitle="雙軸：指標 0–1 / SPY 價格；顯示為研究圖表，不含可驗證回測績效" right={<Toggle value={range} setValue={setRange} options={['60D','120D','1Y','全部']}/> }>
      {chart.length ? <div className="chart-wrap" style={{ height: 310 }}><ResponsiveContainer>
        <ComposedChart data={chart} margin={{ top: 8, left: -20, right: 8 }}><CartesianGrid stroke="#203046" vertical={false} strokeDasharray="3 4"/><XAxis dataKey="date" {...axisProps} tickFormatter={lightDate}/>
          <YAxis yAxisId="ind" domain={[0,1]} {...axisProps}/><YAxis yAxisId="spy" orientation="right" domain={['auto','auto']} {...axisProps}/><Tooltip {...tooltipProps}/><Legend wrapperStyle={{ fontSize: 11 }}/>
          {market.creditRule?.status==='confirmed'&&<><ReferenceLine yAxisId="ind" y={market.creditRule.greenBelow} stroke={COLORS.green} strokeDasharray="5 3"/><ReferenceLine yAxisId="ind" y={market.creditRule.redAtOrAbove} stroke={COLORS.red} strokeDasharray="5 3"/></>}
          <Area yAxisId="ind" type="stepAfter" name="前日訊號持有" dataKey="position" stroke="none" fill="#2ec99519"/>
          <Line yAxisId="ind" type="monotone" name="信用壓力" dataKey="indicator" stroke="#8f9bfa" strokeWidth={2} dot={false} isAnimationActive={false}/>
          <Line yAxisId="spy" type="monotone" name="SPY" dataKey="spy" stroke="#f3c875" strokeWidth={1.6} dot={false} connectNulls={false} isAnimationActive={false}/>
        </ComposedChart>
      </ResponsiveContainer></div> : <Empty title="資料不足" detail="正式模式必須提供 HYG、SHY 歷史還原權息價。"/>}
      <div className="tip"><Info size={14}/> 工程計算式：1 − HYG/SHY 在過去 189 個有效交易日的百分位排名（包含當日）。原始算法、燈號與部位規則仍待核對，沒有可驗證回測績效。</div>
    </Panel>
    <Panel title="最近 12 筆紀錄"><DataGrid rows={[...rows].slice(-12).reverse()} columns={[
      {key:'date',name:'日期',left:true}, {key:'ratio',name:'HYG/SHY',render:r=>format(r.ratio,4)}, {key:'indicator',name:'指標',render:r=>format(r.indicator,4)},
      {key:'light',name:'燈號',render:r=><Pill tone={r.light === 'GREEN' ? 'good':r.light === 'RED'?'danger':'warn'}>{LIGHTS[r.light].cn}</Pill>}
    ]}/></Panel>
  </>;
}
function BreadthView({ signals, universe }) {
  const rows = signals.breadth, last = rows.at(-1);
  const cards = [20, 60, 120, 240].map(n => ({ n, pct: last?.[`a${n}`], count: last?.[`n${n}`] }));
  return <><div className="metrics-grid grid-3">{cards.map(c => <Metric key={c.n} title={`站上 MA${c.n}`} value={numeric(c.pct) ? `${format(c.pct,1)}%`:'—'} note={`有效樣本 ${c.count || 0} 檔`} />)}</div>
    <Panel title="站上均線的股票比例" subtitle={`每種均線分母不同：排除歷史不足及當日無價格標的 · ${universe}`}>
      {rows.some(r => numeric(r.a20)) ? <div className="chart-wrap" style={{ height: 320 }}><ResponsiveContainer>
        <ComposedChart data={rows} margin={{ left:-17, right:4, top:8 }}><CartesianGrid stroke="#203046" vertical={false} strokeDasharray="3 4"/><XAxis dataKey="date" {...axisProps} tickFormatter={lightDate}/><YAxis domain={[0,100]} {...axisProps}/><Tooltip {...tooltipProps} formatter={v=>numeric(v) ? `${v}%`: '—'}/><Legend wrapperStyle={{fontSize:11}}/>
          <ReferenceLine y={30} stroke="#2ec99580" strokeDasharray="4 4"/><ReferenceLine y={70} stroke="#fb637380" strokeDasharray="4 4"/>
          <Line dataKey="a20" name="MA20" stroke="#69c9ed" dot={false} strokeWidth={2} connectNulls={false}/><Line dataKey="a60" name="MA60" stroke="#a095fb" dot={false} strokeWidth={2} connectNulls={false}/><Line dataKey="a120" name="MA120" stroke="#f2bd63" dot={false} strokeWidth={2} connectNulls={false}/><Line dataKey="a240" name="MA240" stroke="#2ec995" dot={false} strokeWidth={2} connectNulls={false}/>
        </ComposedChart></ResponsiveContainer></div> : <Empty title="廣度尚未成熟" detail="需至少 20 / 60 / 120 / 240 個交易日的收盤資料才會顯示對應均線。"/>}
      <div className="tip"><Info size={14}/> 30%／70% 僅為觀察門檻，不是經回測驗證的買賣點；若不是完整上市櫃母體，請勿稱為全市場廣度。</div>
    </Panel>
    <Panel title="上漲與下跌家數" subtitle={`資料日 ${signals.daily.date||"—"} · 官方漲跌價差；可判定 ${signals.daily.eligible}/${signals.daily.total} 檔；兩市場日期不同不合計`}><div className="breadth-split"><div><b style={{color:COLORS.red}}>{signals.daily.available?signals.daily.up:'—'}</b><small>上漲</small></div><div><b style={{color:COLORS.green}}>{signals.daily.available?signals.daily.down:'—'}</b><small>下跌</small></div></div></Panel>
  </>;
}
function RegimeView({ market, signals }) {
  const regime = signals.regime, data = (market.indexHistory || []).slice(-120).map((r, i, arr) => {
    const h = (market.indexHistory || []).slice(0, (market.indexHistory || []).length - arr.length + i + 1);
    const d = detectRegime(h);
    return { ...r, vol: d.vol, state: d.state, ret: d.ret };
  });
  const stateColor = { '高波動':COLORS.yellow,'趨勢多頭':COLORS.red,'趨勢空頭':COLORS.green,'盤整':'#93a7c1','資料不足':'#64748b'};
  return <><div className="state-banner panel"><div className="eyebrow">MARKET REGIME</div><h1 style={{ color: stateColor[regime.state] }}>{regime.state}</h1><p>描述統計：20 交易日報酬高於 2.5% 為趨勢多頭、低於 -2.5% 為趨勢空頭；年化波動高於 22% 優先判為高波動。這不是原站 AE 算法，AE 參數待確認。</p>
    <div className="state-numbers"><span>有效樣本 {market.indexHistory?.length||0} 筆／需 21 筆</span><span>20 日報酬 <b>{signed(regime.ret)}</b></span><span>20 日年化波動 <b>{format(regime.vol,1)}%</b></span></div></div>
    <Panel title="體制轉換時間帶" subtitle="綠色=空頭 · 紅色=多頭（台股慣例） · 黃色=高波動"><div className="regime-strip">{data.map(r => <div key={r.date} title={`${r.date}: ${r.state}`} style={{ background:stateColor[r.state] }}/>)}</div><div className="legendline">{['趨勢多頭','趨勢空頭','高波動','盤整'].map(s => <span key={s}><i style={{background:stateColor[s]}}/>{s}</span>)}</div></Panel>
    <Panel title="歷史年化波動率" subtitle="使用樣本標準差（扣除平均日報酬），不是日報酬均方根"><Spark rows={data} valueKey="vol" color="#70c8e8" height={250} lineName="20日年化波動 %"/></Panel>
  </>;
}
const US_DEMO = [ ['NVDA','輝達',13,4.5],['MSFT','微軟',12,0.8],['AAPL','蘋果',11,-0.8],['GOOGL','Alphabet',9,1.5],['AMZN','亞馬遜',8,-1.2],['META','Meta',7,2.7],['AVGO','博通',5,3.1],['TSLA','特斯拉',5,-2.3],['JPM','摩根大通',4,0.1],['AMD','超微',4,1.9],['WMT','沃爾瑪',4,-0.2],['V','Visa',3,0.9] ];
function HeatContent(props) {
  const { x, y, width, height, symbol, name, change, marketStyle } = props;
  if (width < 12 || height < 10) return null;
  const rise = (change || 0) > 0, mag = Math.min(1,Math.abs(change || 0)/5);
  const rgb = change === 0 ? 'rgba(110,136,166,.4)' : marketStyle === 'tw' ? (rise ? `rgba(251,99,115,${.28 + mag*.65})`:`rgba(46,201,149,${.25 + mag*.65})`) : (rise ? `rgba(46,201,149,${.25+mag*.65})`:`rgba(251,99,115,${.28+mag*.65})`);
  return <g><rect x={x} y={y} width={width} height={height} fill={rgb} stroke="#08111e" strokeWidth={2} rx={5}/>
    {width > 55 && height > 31 && <><text x={x+width/2} y={y+height/2 - 6} fill="#fff" fontSize={width>110 ? 15:12} fontWeight="700" textAnchor="middle">{symbol}</text><text x={x+width/2} y={y+height/2+11} fill="#fff" fontSize="11" textAnchor="middle">{signed(change)}</text></>}
    {width>125 && height>72 && <text x={x+width/2} y={y+height/2+28} fill="#e4edee" fontSize="10" textAnchor="middle">{name}</text>}
  </g>;
}
function Heatmap({ market, signals, us, onStock }) {
  const [sector,setSector] = useState('全部'), [rank,setRank] = useState('市值');
  const tw = !us, raw = tw ? signals.latest : (market.usStocks || (market.mode === 'demo' ? US_DEMO.map(([symbol,name,cap,change])=>({symbol,name,marketCapM:cap*100000,change,sector:'美股示範'})) : []));
  const sectors = ['全部', ...new Set(raw.map(r=>r.sector || '未分類'))];
  const filtered = raw.filter(r => sector === '全部' || (r.sector || '未分類') === sector);
  const ranked = filtered.filter(r=>numeric(r.change)).sort((a,b) => rank === '漲跌幅' ? (b.change || 0) - (a.change || 0) : (b.marketCapM || 0) - (a.marketCapM || 0));
  const useCap=ranked.every(r=>numeric(r.marketCapM)&&r.marketCapM>0);
  const treemap = ranked.filter(r => numeric(r.change)).map(r => ({ ...r, size: useCap?r.marketCapM:1, marketStyle:tw?'tw':'us' }));
  const up = treemap.filter(r=>r.change>0).length, down = treemap.filter(r=>r.change<0).length;
  return <><Panel title={tw ? '台股漲跌熱力圖' : '美股觀察池熱力圖'} subtitle={`${tw?'台股紅漲綠跌':'美股綠漲紅跌'} · 全部可用時以官方普通股數×收盤價為市值；缺市值時全母體採等權`} right={<Pill tone={market.mode === 'demo' ? 'warn':'neutral'}>{market.mode === 'demo'?'虛構示範':'匯入資料'}</Pill>}>
    {!tw && <div className="tip"><Info size={14}/> 此頁不是完整 S&P 500 成分股。沒有美股資料時不以台股或隨機行情偽裝完整指數。</div>}
    <div className="filters"><label>產業 <select value={sector} onChange={e=>setSector(e.target.value)}>{sectors.map(v=><option key={v}>{v}</option>)}</select></label><Toggle value={rank} setValue={setRank} options={['市值','漲跌幅']}/><span className="muted tiny">上漲 {up} ／ 下跌 {down}</span></div>
    {treemap.length ? <div className="heatmap"><ResponsiveContainer width="100%" height="100%"><Treemap data={treemap} dataKey="size" nameKey="symbol" content={<HeatContent/>} isAnimationActive={false}/></ResponsiveContainer></div>
      : <Empty title="未接入市場資料" detail={us?'匯入資料需包含 usStocks 才會顯示美股行情。':'匯入有效上市櫃個股收盤資料後即可顯示。'}/>}
  </Panel>
  <Panel title="漲跌排行"><DataGrid rows={ranked.slice(0,25)} columns={[nameCol,changeCol,{key:'sector',name:'產業',render:r=>r.sector || '—'},{key:'marketCapM',name:'市值權重',render:r=>format(r.marketCapM)}]} onRow={tw ? onStock:undefined}/></Panel>
  </>;
}
function BreakoutView({ signals, onStock }) {
  const [period,setPeriod] = useState(60), [minVol,setMinVol] = useState(0), [search,setSearch] = useState('');
  const {eligible,rows,hits,near}=breakoutSelection(signals.latest,period,minVol,search);
  const cols = [nameCol, {key:'dist',name:'距高點',render:r=><span className="num" style={{color:r.dist>0?COLORS.red:COLORS.yellow}}>{signed(r.dist)}</span>},{key:'volRatio',name:'量比',render:r=>numeric(r.volRatio)?`${format(r.volRatio,2)}x`:'—'},changeCol];
  return <><Panel title="N 日高點突破" subtitle="今日選定基礎收盤價 > 前 N 個完整交易日最高價；未還原窗口含公司事件或事件覆蓋不明時不判定" right={<Toggle value={String(period)} setValue={v=>setPeriod(Number(v))} options={['20','60','120','240']}/> }>
    <div className="filters"><label>量能比至少 <select value={minVol} onChange={e=>setMinVol(Number(e.target.value))}><option value={0}>不限</option><option value={1}>1.0x</option><option value={1.5}>1.5x</option><option value={2}>2.0x</option></select></label><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="搜尋代號或名稱"/></div>
    <div className="section-subtitle"><span className="headline-number" style={{color:COLORS.red}}>{eligible?hits.length:"暖機中"}</span> 檔突破　·　{eligible} 檔具備完整 N+1 日及價格／事件驗證 · 篩選後 {rows.length} 檔</div>
    <DataGrid rows={hits} columns={cols} onRow={onStock} empty={eligible?"0 檔符合目前篩選條件":"0 檔具備足夠資料，不能判定突破"}/>
  </Panel><Panel title="接近突破" subtitle="距離前 N 日高點 3% 以內（尚未突破）"><DataGrid rows={near.slice(0,15)} columns={cols} onRow={onStock}/></Panel></>;
}
function InstitutionView({ market, signals, onStock }) {
  const [kind,setKind] = useState('外資'), [side,setSide] = useState('買超');
  if(market.sources?.institutional?.status==='unavailable') return <Panel title="法人買賣超尚未接入"><Empty title="資料公開授權待核實" detail={market.sources.institutional.reason}/></Panel>;
  const key = {外資:'foreignShares',投信:'trustShares',自營商:'dealerShares',合計:'total'}[kind];
  const instDate = [...new Set(market.stocks.flatMap(s => (s.institutional || []).map(r => r.date)))].sort().at(-1);
  const derived = signals.latest.map(s => {
    const i = s.institutional?.at(-1)?.date === instDate ? s.institutional.at(-1) : null;
    const raw = !i ? null : key === 'total' ? i.totalShares ?? (['foreignShares','trustShares','dealerShares'].every(k=>numeric(i[k])) ? i.foreignShares+i.trustShares+i.dealerShares : null) : i[key];
    return { ...s, netShares: numeric(raw) ? raw : null, netLots: sharesToLots(raw) };
  });
  const rows = derived.filter(r=>numeric(r.netLots) && (side==='買超' ? r.netLots > 0 : r.netLots < 0)).sort((a,b)=>side==='買超'?b.netLots-a.netLots:a.netLots-b.netLots);
  const dates = [...new Set(market.stocks.flatMap(s=>(s.institutional||[]).map(r=>r.date)))].sort().slice(-25);
  const chart = dates.map(date=>{
    const values=market.stocks.map(s=>{
      const r=(s.institutional||[]).find(x=>x.date===date);
      if(!r)return null;
      return key==='total'?r.totalShares??(['foreignShares','trustShares','dealerShares'].every(k=>numeric(r[k]))?r.foreignShares+r.trustShares+r.dealerShares:null):r[key];
    }).filter(numeric);
    return {date,net:values.length?values.reduce((a,v)=>a+v,0)/1000:null,samples:values.length};
  });
  return <><Panel title="法人買賣超" subtitle={`法人資料日 ${instDate || "—"} · 股 ÷ 1,000 = 張，非買賣超金額（億元）。不同日資料不混排名。`} right={<Toggle value={kind} setValue={setKind} options={['外資','投信','自營商','合計']}/> }>
    <div className="filters"><Toggle value={side} setValue={setSide} options={['買超','賣超']}/><span className="muted tiny">共 {rows.length} 檔 · 僅為目前載入母體</span></div>
    <DataGrid rows={rows.slice(0,30)} onRow={onStock} columns={[nameCol,{key:'netLots',name:'買賣超(張)',render:r=><span style={{color:candleColor(r.netLots)}} className="num">{format(r.netLots,1)}</span>},changeCol]}/>
  </Panel><Panel title={`${kind}買賣超趨勢`} subtitle="僅加總有完整數值之股票，缺值排除；各日樣本數獨立，不代表全部上市金額">
    {chart.length ? <div style={{height:240}} className="chart-wrap"><ResponsiveContainer><BarChart data={chart} margin={{left:-4,top:9,right:5}}><CartesianGrid stroke="#203046" vertical={false}/><XAxis dataKey="date" {...axisProps} tickFormatter={lightDate}/><YAxis {...axisProps}/><Tooltip {...tooltipProps} formatter={v=>`${format(v,0)} 張`}/><ReferenceLine y={0} stroke="#7183a0"/><Bar dataKey="net" name="淨買賣(張)">{chart.map((r,i)=><Cell key={i} fill={candleColor(r.net)}/>)}</Bar></BarChart></ResponsiveContainer></div>
    : <Empty title="無法人歷史資料" detail="僅使用已核准來源的逐日法人股數；TWSE T86 維持停用。"/>}
  </Panel></>;
}
function StreakView({ market, signals, onStock }) {
  const [kind,setKind] = useState('外資'), [days,setDays] = useState('3');
  if(market.sources?.institutional?.status==='unavailable') return <Panel title="法人連續買賣超尚未接入"><Empty title="資料公開授權待核實" detail={market.sources.institutional.reason}/></Panel>;
  const key = kind==='外資'?'foreignShares':'trustShares';
  const instDate = [...new Set(market.stocks.flatMap(s => (s.institutional || []).map(r => r.date)))].sort().at(-1);
  const calendarVerified=signals.scope!=='ALL'&&marketMeta(market,signals.scope).calendarStatus==='verified';
  const rows = (calendarVerified?signals.latest:[]).filter(s => s.institutional?.at(-1)?.date === instDate).map(s=>({...s, streak:institutionalStreak(s.institutional,key,market.institutionalSessions||[])})).filter(s=>s.streak.days >= +days);
  const cols = [nameCol,{key:'days',name:'連續天數',render:r=><b>{r.streak.days} 天</b>},{key:'shares',name:'累計張數',render:r=><span style={{color:candleColor(r.streak.shares)}}>{format(sharesToLots(r.streak.shares),1)}</span>},changeCol];
  return <Panel title="法人連續買賣超" subtitle={`最新法人資料日 ${instDate || "—"}；數值缺漏及 0 張會中斷連續性，未納入過期資料`} right={<Toggle value={kind} setValue={setKind} options={['外資','投信']}/> }>
    <div className="filters"><label>至少 <select value={days} onChange={e=>setDays(e.target.value)}>{['3','5','10'].map(v=><option key={v} value={v}>{v} 日</option>)}</select></label></div>
    <p>{calendarVerified?"依已驗證交易日判定":"0 檔具備連續交易日驗證；不以零散快照推定連買或連賣"}</p>
    <div className="two-columns"><div><h3 className="subhead">連續買超</h3><DataGrid rows={rows.filter(s=>s.streak.direction>0).sort((a,b)=>b.streak.days-a.streak.days)} columns={cols} onRow={onStock}/></div>
      <div><h3 className="subhead">連續賣超</h3><DataGrid rows={rows.filter(s=>s.streak.direction<0).sort((a,b)=>b.streak.days-a.streak.days)} columns={cols} onRow={onStock}/></div></div>
  </Panel>;
}
function FuturesView({ market }) {
  const data = market.futures || [], last = data.at(-1), previous = data.at(-2);
  const names = [['外資','foreign'],['投信','trust'],['自營商','dealer']];
  return <><div className="metrics-grid grid-3">{names.map(([name,key])=><Metric key={name} title={`${name}淨未平倉`} value={numeric(last?.[key])?`${format(last[key])} 口`:'—'} note={numeric(previous?.[key]) ? `較前筆 ${format(last[key]-previous[key])} 口`:'尚無前筆資料'} />)}</div>
    <Panel title="外資期貨淨部位" subtitle={`TX 各到期月份合計 · 資料日 ${last?.date||'—'} · 淨未平倉口數，不代表盤中報價或方向性預測`}>
      {data.length ? <div className="chart-wrap" style={{height:290}}><ResponsiveContainer><BarChart data={data} margin={{left:-2,right:5,top:8}}><CartesianGrid stroke="#203046" vertical={false}/><XAxis dataKey="date" {...axisProps} tickFormatter={lightDate}/><YAxis {...axisProps}/><Tooltip {...tooltipProps} formatter={v=>`${format(v)} 口`}/><ReferenceLine y={0} stroke="#70819b"/><Bar dataKey="foreign" name="外資淨未平倉">{data.map((r,i)=><Cell key={i} fill={candleColor(r.foreign)}/>)}</Bar></BarChart></ResponsiveContainer></div>
      : <Empty title="期貨法人資料尚未接入" detail="需使用期交所依日期及契約分類的未平倉資料，統一商品口徑。"/>}
    </Panel></>;
}
function MarginView({ signals, onStock }) {
  const rows = signals.latest.filter(s=>numeric(s.margin?.usagePct)).sort((a,b)=>b.margin.usagePct-a.margin.usagePct);
  return <Panel title="融資使用率觀察" subtitle="公式：今日融資餘額 ÷ 次一營業日限額；80% / 60% 為研究門檻，非追繳判定">
    <DataGrid rows={rows.slice(0,40)} onRow={onStock} columns={[nameCol,{key:'marginDate',name:'資料日',render:s=>s.margin.date||'—'},{key:'balance',name:'融資餘額(張)',render:s=>format(sharesToLots(s.margin.balanceShares),0)},
      {key:'usage',name:'使用率',render:s=><span className="num" style={{color:s.margin.usagePct>=80?COLORS.red:s.margin.usagePct>=60?COLORS.yellow:COLORS.green}}>{format(s.margin.usagePct,1)}%</span>},
      {key:'bar',name:'水位',render:s=><div className="mini-meter"><i style={{width:`${Math.min(100,s.margin.usagePct)}%`,background:s.margin.usagePct>=80?COLORS.red:s.margin.usagePct>=60?COLORS.yellow:COLORS.green}}/></div>},changeCol]}/>
  </Panel>;
}
function SectorView({ signals, onStock }) {
  const [activeSector, setActiveSector] = useState(null);
  const groups = Object.values(signals.latest.reduce((acc,s)=>{
    const key = s.sector || '未分類'; if(!acc[key]) acc[key]={name:key,stocks:[]}; acc[key].stocks.push(s);return acc;
  },{})).map(g=>({name:g.name,count:g.stocks.length,valid:g.stocks.filter(s=>numeric(s.change)).length,advancers:g.stocks.filter(s=>s.change>0).length,
    avgChange:avg(g.stocks.map(s=>s.change).filter(numeric)), capWeighted:(()=>{const eligible=g.stocks.filter(s=>numeric(s.change)&&numeric(s.marketCapM));const total=eligible.reduce((a,s)=>a+s.marketCapM,0);return total?eligible.reduce((a,s)=>a+s.change*s.marketCapM,0)/total:null;})(),stocks:g.stocks
  })).sort((a,b)=>(b.avgChange??-Infinity)-(a.avgChange??-Infinity));
  return <><Panel title="產業輪動" subtitle="預設用等權平均漲跌幅，避免少數權值股完全主導；樣本不足時勿外推全產業">
    <div className="sector-list">{groups.map((s,i)=><div key={s.name} className="sector-row"><span className="sector-index">{String(i+1).padStart(2,'0')}</span><b>{s.name}</b><span className="sector-bar-holder"><i style={{background:candleColor(s.avgChange),width:`${Math.min(100,Math.abs(s.avgChange||0)*12)}%`}}/></span><span className="num" style={{color:candleColor(s.avgChange)}}>{signed(s.avgChange)}</span><span className="muted tiny">{s.advancers}/{s.valid} 有效樣本上漲</span></div>)}</div>
  </Panel><Panel title="族群明細" subtitle="點選產業列，可展開該產業的成分股"><DataGrid rows={groups} onRow={r => setActiveSector(prev => prev === r.name ? null : r.name)} columns={[{key:'name',name:'產業',left:true},{key:'count',name:'母體檔數'}, {key:'valid',name:'有效檔數'}, {key:'avgChange',name:'等權漲跌',render:r=><Percent value={r.avgChange}/>},{key:'capWeighted',name:'市值加權',render:r=><Percent value={r.capWeighted}/>}]} />
      {activeSector && <div className="sector-members"><h3>{activeSector} · 成分股</h3><DataGrid rows={groups.find(g=>g.name===activeSector)?.stocks || []} columns={stockCols} onRow={onStock}/></div>}
      <div className="tip">目前母體：{signals.latest.length} 檔。完整市場需要涵蓋所有符合資格的標的及正確產業分類。</div>
  </Panel></>;
}
function VolumeView({ signals }) {
  // Rough reference curve; requires asOf for each actual intraday observation.
  const curve = [[9,0],[9.5,.22],[10,.34],[10.5,.44],[11,.53],[11.5,.61],[12,.69],[12.5,.78],[13,.88],[13.5,1]];
  const estimate = (t) => {const a=curve.find((x,i)=>i<curve.length-1&&t>=x[0]&&t<curve[i+1][0]);if(!a)return t>=13.5?1:null;const b=curve[curve.indexOf(a)+1];return a[1]+(b[1]-a[1])*(t-a[0])/(b[0]-a[0]);};
  const rows = signals.latest.map(s=>{
    const intraday=s.intraday, asOf = intraday?.asOf, match=asOf?.match(/T(\d\d):(\d\d)/);
    const t=match?Number(match[1])+Number(match[2])/60:null, frac=numeric(t)?estimate(t):null;
    const actual=intraday?.cumulativeVolumeShares, eligible=numeric(actual)&&numeric(frac)&&frac>0.08&&asOf.slice(0,10)===s.date;
    const est=eligible?actual/frac:null, yesterday=s.history?.at(-2)?.volumeShares;
    return {...s,progress:frac,actual:eligible?actual:null,est,ratio:eligible&&yesterday>0?est/yesterday:null,asOf};
  }).filter(s=>numeric(s.est)).sort((a,b)=>(b.ratio||0)-(a.ratio||0));
  return <Panel title="盤中量能預估" subtitle="僅對當日實際盤中累積成交量估算；時間進度曲線是研究假設，非交易所官方模型">
    <div className="tip"><Info size={14}/> 估計全日量 = 盤中累積量 ÷ 典型成交量進度；開盤初期容易失準，收盤後請改用實際量。</div>
    <DataGrid rows={rows.slice(0,30)} columns={[nameCol,{key:'asOf',name:'資料時間',render:r=>r.asOf?.slice(11,16) || '—'}, {key:'actual',name:'累積量(張)',render:r=>format(sharesToLots(r.actual),0)}, {key:'est',name:'預估全日(張)',render:r=>format(sharesToLots(r.est),0)},{key:'ratio',name:'量比',render:r=><span style={{color:r.ratio>=1.8?COLORS.red:'#b7c9df'}}>{format(r.ratio,2)}x</span>}]} empty="目前沒有符合條件的當日盤中資料"/>
  </Panel>;
}
function WeeklyView({ market, signals }) {
  const h=market.indexHistory||[], n=h.length, last=h.at(-1), week=n>=6 ? (last.close/h[n-6].close-1)*100 : null;
  const b=signals.breadth, bNow=b.at(-1), bOld=b.at(-6);
  const changeBreadth = numeric(bNow?.a20)&&numeric(bOld?.a20)?round(bNow.a20-bOld.a20,1):null;
  const sectors=Object.entries(signals.latest.reduce((acc,s)=>{ if(s.history.length<6)return acc;const key=s.sector||'未分類'; const ret=(s.close/s.history.at(-6).close-1)*100;(acc[key] ||= []).push(ret);return acc;},{}))
    .map(([name,vals])=>({name,value:avg(vals)})).sort((a,b)=>b.value-a.value);
  return <Panel title="市場研究週報" subtitle={`依目前已載入資料自動組成 · 截至 ${last?.date||market.asOf}，不是額外生成的市場消息`}>
    <article className="weekly"><div className="weekly-head"><span className="eyebrow">RESEARCH NOTE</span><h2>本週市場觀察</h2><p>{market.mode==='demo'?'虛構示範，非市場事實':market.source}</p></div>
      <section><h3>01　大盤表現</h3><p>加權指數最近 5 個交易日報酬為 <b style={{color:candleColor(week)}}>{signed(week)}</b>，最新點位 <b>{format(last?.close)}</b>。資料觀察至 {readableDate(last?.date)}。</p></section>
      <section><h3>02　市場廣度</h3><p>MA20 站上比例 {format(bNow?.a20,1)}%，相較 5 個交易日前變化 {numeric(changeBreadth)?signed(changeBreadth):'資料不足'}。觀察樣本 {bNow?.n20||0} 檔。</p></section>
      <section><h3>03　信用與波動</h3><p>信用壓力燈號：<b>{LIGHTS[signals.creditNow?.light||'UNKNOWN'].cn}</b>（指標 {format(signals.creditNow?.indicator,4)}）。20 日年化波動率：{format(signals.regime.vol,1)}%。</p></section>
      <section><h3>04　產業輪動</h3><p>{sectors.length?`依最近五日等權報酬，目前樣本中最強族群為「${sectors[0].name}」(${signed(sectors[0].value)})，最弱為「${sectors.at(-1).name}」(${signed(sectors.at(-1).value)})。`:'尚無足夠資料計算產業週報。'}</p></section>
      <div className="tip">此報告是輸入資料的描述性統計，不包含任何未接入的新聞、預測或保證獲利的策略。</div>
    </article>
  </Panel>;
}
function NoDataModule({title,detail,info}) { return <><Panel title={title}><Empty title="尚未接入可核實的資料來源" detail={detail}/></Panel>{info&&<div className="tip">{info}</div>}</>; }
function PollView() {
  const [mine,setMine] = useState(null), options=['0–2 成','2–4 成','4–6 成','6–8 成','8–10 成'];
  return <Panel title="個人持股水位紀錄" subtitle="原版假的投票總數已移除；此頁不會假裝其他人真的參與投票。">
    <p className="muted">你目前的股票部位約佔可投資資產多少？這只是本機畫面紀錄，不會送出伺服器。</p><div className="poll-grid">{options.map((o,i)=><button key={o} onClick={()=>setMine(i)} className={mine===i?'selected':''}>{o}</button>)}</div>
    {mine!==null?<div className="quiet"><CheckCircle2 size={17}/> 你選擇了 {options[mine]}。正式匿名投票功能需後端驗證、防重複投票、隱私告知才能開放。</div>:null}
  </Panel>;
}
function WatchView({ signals, watchlist, onStock }) { return <Panel title="我的關注名單" subtitle="資料儲存在本機瀏覽器；不會同步券商持倉">
  <DataGrid rows={signals.latest.filter(s=>watchlist.includes(securityKey(s))||watchlist.includes(s.symbol)&&s.market!=='TPEx')} onRow={onStock} columns={[...stockCols,{key:'volRatio',name:'量比',render:r=>numeric(r.volRatio)?`${format(r.volRatio,2)}x`:'—'}]} empty="還沒有關注股票"/>
  </Panel>;
}
function StockDrawer({ stock, close, watching, toggle }) {
  if(!stock)return null;
  const s=stockMetrics(stock);
  return <div className="modal-backdrop" onClick={close}><aside className="stock-drawer" role="dialog" aria-modal="true" aria-label={`${s.name} 個股明細`} onClick={e=>e.stopPropagation()}>
    <div className="drawer-head"><div><span className="eyebrow">STOCK RESEARCH</span><h2>{s.symbol} {s.name}</h2><small className="muted">{s.sector}　·　資料日 {s.date || '—'}</small></div><button className="icon-btn" onClick={close} aria-label="關閉"><X size={20}/></button></div>
    <div className="stock-price"><b>{format(s.close,2)}</b><Percent value={s.change}/><button className={`fav-btn ${watching?'active':''}`} onClick={()=>toggle(securityKey(s))}><Star size={17} fill={watching?'currentColor':'none'}/>{watching?'已關注':'加入關注'}</button></div>
    <div className="drawer-stats">{[['MA20',s.ma20],['MA60',s.ma60],['MA120',s.ma120],['MA240',s.ma240],['量比',s.volRatio]].map(([k,v])=><div key={k}><span>{k}</span><b>{format(v,2)}{k==='量比'&&numeric(v)?'x':''}</b></div>)}</div>
    <p className="muted">均線：{BASIS_NAMES[s.indicatorBasis]||'未還原'} · 價格與走勢圖：未還原成交價。{s.maReasons?.[240]}</p><Panel title="未還原收盤走勢"><Spark rows={(s.history||[]).slice(-120)} valueKey="close" color="#8f9bfa" height={200} /></Panel>
    <Panel title="法人買賣超" subtitle={`法人資料日 ${s.institutional?.at(-1)?.date||"—"}，與價格獨立`}><div className="drawer-stats">{[['外資',getInst(s,'foreignShares')],['投信',getInst(s,'trustShares')],['自營商',getInst(s,'dealerShares')]].map(([k,v])=><div key={k}><span>{k}</span><b style={{color:candleColor(v)}}>{format(sharesToLots(v),1)} 張</b></div>)}</div></Panel>
    <div className="tip">個股頁僅依匯入資料計算。沒有資料時顯示「—」，不以隨機值填補。</div>
  </aside></div>;
}
function DataModal({ onClose, onImport, onDemo, error, clearError }) {
  const [url,setUrl]=useState(import.meta.env.VITE_MARKET_URL || ''), [loading,setLoading]=useState(false);
  const fileRef = useRef();
  async function submitUrl(){ setLoading(true);clearError();try{onImport(await fetchMarket(url.trim()));}catch(e){clearError(e.message)}finally{setLoading(false)} }
  async function submitFile(e){const f=e.target.files?.[0];if(!f)return;setLoading(true);clearError();try{onImport(validateMarket(JSON.parse(await f.text())));}catch(err){clearError(err.message)}finally{setLoading(false);if(fileRef.current)fileRef.current.value='';}}
  return <div className="modal-backdrop" onClick={onClose}><div className="data-modal" role="dialog" aria-modal="true" aria-label="資料來源設定" onClick={e=>e.stopPropagation()}>
    <div className="drawer-head"><div><span className="eyebrow">DATA SOURCE</span><h2>接入正式市場資料</h2></div><button className="icon-btn" onClick={onClose} aria-label="關閉資料設定"><X size={20}/></button></div>
    <p className="muted">只讀取通過契約驗證的官方盤後快照。缺值與舊資料保留原日期，不自動補成模擬行情。</p>
    <label className="field-label" htmlFor="dataurl">market.json 網址（本站或 raw.githubusercontent.com）</label><div className="source-row"><input id="dataurl" value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://raw.githubusercontent.com/0857ken/tw-market-scanner/market-data/data/market.json"/><button className="primary-btn" disabled={!url.trim()||loading} onClick={submitUrl}>{loading?'讀取中':'讀取 JSON'}</button></div>
    <div className="data-sep">或</div><label className="upload-btn"><Upload size={17}/> 從手機／電腦選擇 market.json<input type="file" accept=".json,application/json" ref={fileRef} onChange={submitFile} hidden/></label>
    {error&&<div className="errorbox"><AlertTriangle size={16}/>{error}</div>}
    <button type="button" className="demo-choice" onClick={onDemo}>檢視虛構 DEMO（僅供介面示意）</button>
    <div className="tip"><Info size={14}/> 上傳檔案只在目前分頁記憶體解析，不傳送至其他服務；重新整理後重新讀取官方盤後快照。API 金鑰、券商憑證不得放進公開 JSON 或網頁程式碼。</div>
  </div></div>;
}
const STATUS_NAMES={fresh:'日期符合',stale:'資料落後',error:'更新失敗',unavailable:'未接入',unknown:'日期待核對',imported:'人工提供',demo:'虛構 DEMO'};
function HealthView({market}){
  return <><Panel title="資料健康與來源" subtitle="每個來源獨立記錄資料日及更新結果；重新產檔不會改寫行情日期。">
    <div className="health-grid">{Object.entries(market.sources||{}).map(([key,s])=>{
      const status=key==='calendar'?s.status:effectiveStatus(s,key.startsWith('tpex')?null:market.calendar);
      return <article className="source-card" key={key}><div><b>{s.name||key}</b><Pill tone={status==='fresh'?'good':['stale','error'].includes(status)?'danger':'warn'}>{STATUS_NAMES[status]||status}</Pill></div>
        <p>{key==='calendar'?'日曆涵蓋至':'資料日'} <strong>{s.asOf||'—'}</strong>　·　{s.rowCount??'—'} 筆</p>
        <p>快照首次抓取：{s.fetchedAt?.replace('T',' ')||'尚無成功紀錄'}</p>
        {s.lastAttemptAt&&<p>最近檢查：{s.lastAttemptAt.replace('T',' ')}</p>}
        {s.error&&<p className="source-error">{s.error}</p>}{s.reason&&<p>{s.reason}</p>}
        {s.sha256&&<p title={s.sha256}>來源摘要：{s.sha256.slice(0,12)}…</p>}
        {s.url&&<a href={s.url} target="_blank" rel="noreferrer">官方來源 ↗</a>}{s.license&&<a href={s.license} target="_blank" rel="noreferrer">授權說明 ↗</a>}
      </article>;
    })}</div>
  </Panel><Panel title="計算與母體" subtitle={`${market.universe} · 行情日期 ${market.asOf||'—'}`}>
    <div className="method-list"><p>MA20／60／120／240：包含當日的 N 個有效收盤價平均；缺值不補零。突破：今日收盤嚴格大於前 N 個交易日最高收盤。</p>
      <p>市場廣度：站上均線家數 ÷ 該均線具完整歷史的當日有效家數；不同均線有不同分母。</p>
      <p>價量歷史快照 {market.quoteSessions?.length||0} 日；MA20／60／120／240 需 20／60／120／240 日，240 日突破需 241 日；不足時顯示暖機。</p>
      {Object.entries(market.methodology||{}).map(([k,text])=><p key={k}>{text}</p>)}
      <p>未取得含息還原股價；未還原研究值會受除權息或分割影響。目前普通股母體依最新公司名單，不適合直接回測歷史績效。</p>
    </div>
  </Panel></>;
}
export default function Scanner(){
  const [market,setMarket] = useState(makeUnavailable);
  const [page,setPage] = useState('總覽'),[menu,setMenu] = useState(false),[sourceOpen,setSourceOpen] = useState(false);
  const [error,setError]=useState(''),[search,setSearch]=useState(''),[selected,setSelected]=useState(null),[creditRange,setCreditRange]=useState('120D');
  const [scope,setScope]=useState('ALL'),[basis,setBasis]=useState('adjusted');
  const [reload,setReload]=useState(0),[loading,setLoading]=useState(true),[clock,setClock]=useState(Date.now());
  const [watchlist,setWatchlist] = useState(()=>{ try{return JSON.parse(localStorage.getItem('tw-scanner-favorites-v1') || '[]').filter(s=>typeof s==='string').map(s=>s.includes(':')?s:`TWSE:${s}`);}catch{return [];} });
  useEffect(()=>{try{localStorage.setItem('tw-scanner-favorites-v1',JSON.stringify(watchlist))}catch{}},[watchlist]);
  useEffect(() => {
    const specified = import.meta.env.VITE_MARKET_URL;
    const autoUrl = specified || `${import.meta.env.BASE_URL}market.json`;
    let active = true;
    setLoading(true);
    fetchMarket(autoUrl).then(next => { if(active) { setMarket(next); setError('');setSelected(null); } }).catch(e => {
      if (active) setError(`行情載入失敗：${e.message}。若已有快照，保留其原始日期；不以模擬資料替代。`);
    }).finally(()=>{if(active)setLoading(false)});
    return () => { active = false; };
  }, [reload]);
  useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),60000);return()=>clearInterval(timer)},[]);
  useEffect(()=>{
    if(!selected&&!sourceOpen&&!menu)return;
    const previous=document.activeElement;
    const close=e=>{if(e.key==='Escape'){setSelected(null);setSourceOpen(false);setMenu(false)}};
    const prior=document.body.style.overflow;
    document.body.style.overflow='hidden';document.addEventListener('keydown',close);
    const timer=setTimeout(()=>document.querySelector('[role="dialog"] button,.sidebar-open button')?.focus(),0);
    return()=>{clearTimeout(timer);document.body.style.overflow=prior;document.removeEventListener('keydown',close);previous?.focus?.()};
  },[selected,sourceOpen,menu]);
  const signals=useMemo(()=>getSignals(market,scope,basis),[market,scope,basis]);
  const viewMarket={...market, asOf:signals.anchor, stocks:market.stocks.filter(s=>(scope==='ALL'||(s.market||'TWSE')===scope)&&memberOn(s,signals.anchor)),
    universe:`${MARKET_NAMES[scope]} · ${BASIS_NAMES[basis]} · 當期普通股名單，非歷史成員回測`,
    sources:scope==='TPEx'?{...market.sources,institutional:market.sources.tpexInstitutional||{status:'unavailable',reason:'TPEx 法人資料尚未載入'}}:market.sources,
    institutionalSessions:scope==='TPEx'?(market.research?.markets?.TPEx?.institutionalSessions||[]):market.institutionalSessions};
  const newPage=v=>{setPage(v);setMenu(false);window.scrollTo({top:0,behavior:'smooth'});};
  const toggleWatch=symbol=>setWatchlist(prev=>prev.includes(symbol)?prev.filter(s=>s!==symbol):[...prev,symbol]);
  const currentStocks=signals.latest.filter(s=>`${s.symbol} ${s.name}`.toLowerCase().includes(search.toLowerCase())).slice(0,8);
  const selectedExchanges=scope==='ALL'?['TWSE','TPEx']:[scope];
  const statuses=selectedExchanges.map(m=>effectiveStatus(market.sources?.[m==='TWSE'?'quotes':'tpexQuotes'],m==='TWSE'?market.calendar:null,new Date(clock)));
  const quoteStatus=['error','unavailable','stale','unknown','imported'].find(s=>statuses.includes(s))||'fresh';
  const sourceDate=selectedExchanges.map((m,i)=>`${m} ${market.sources?.[m==='TWSE'?'quotes':'tpexQuotes']?.asOf||'未接入'}（${STATUS_NAMES[statuses[i]]}）`).join(' ／ ');
  const render=()=>{
    switch(page){
      case '總覽':return <Overview market={viewMarket} signals={signals} go={newPage} onStock={setSelected} watchlist={watchlist}/>;
      case '資料健康':return <HealthView market={market}/>;
      case '我的關注':return <WatchView signals={signals} watchlist={watchlist} onStock={setSelected}/>;
      case '信用利差':return <CreditView market={viewMarket} signals={signals} range={creditRange} setRange={setCreditRange}/>;
      case '市場廣度':return <BreadthView signals={signals} universe={viewMarket.universe}/>;
      case '市場體制':return <RegimeView market={viewMarket} signals={signals}/>;
      case '台股熱力圖':return <Heatmap market={viewMarket} signals={signals} onStock={setSelected}/>;
      case '美股熱力圖':return <Heatmap market={viewMarket} signals={signals} us/>;
      case '高點突破':return <BreakoutView signals={signals} onStock={setSelected}/>;
      case '法人買賣超':return <InstitutionView market={viewMarket} signals={signals} onStock={setSelected}/>;
      case '連續買賣超':return <StreakView market={viewMarket} signals={signals} onStock={setSelected}/>;
      case '期貨籌碼':return <FuturesView market={market}/>;
      case '融資水位':return <MarginView signals={signals} onStock={setSelected}/>;
      case '盤中量能':return <VolumeView signals={signals}/>;
      case '產業輪動':return <SectorView signals={signals} onStock={setSelected}/>;
      case '研究週報':return <WeeklyView market={viewMarket} signals={signals}/>;
      case '持股水位':return <PollView/>;
      case '盤前觀察':return market.overnight?.length?<Panel title="隔夜市場" subtitle="需輸入實際昨夜市場資料"><DataGrid rows={market.overnight} columns={[{key:'name',name:'指數',left:true},{key:'change',name:'漲跌',render:r=><Percent value={r.change}/>}]} /></Panel>:<NoDataModule title="盤前觀察" detail="需要具日期時間與交易日對齊的台指期夜盤、美股指數、費半、台積電 ADR 資料；原版固定負報酬已移除。"/>;
      case '券商分點':return market.branches?.length?<Panel title="個股分點"><DataGrid rows={market.branches} columns={[{key:'broker',name:'券商分點',left:true},{key:'buyShares',name:'買進(張)',render:r=>format(sharesToLots(r.buyShares))},{key:'sellShares',name:'賣出(張)',render:r=>format(sharesToLots(r.sellShares))}]}/></Panel>:<NoDataModule title="券商分點" detail="證交所免費 T86 是法人買賣超，不等於個股分點逐筆進出。需要合法取得的券商分點資料來源；不能用隨機分點列表代替。"/>;
      default:return null;
    }
  };
  return <div className="app">
    {menu&&<button type="button" aria-label="關閉側邊選單" className="mobile-scrim" onClick={()=>setMenu(false)}/>}
    <aside className={`sidebar ${menu?'sidebar-open':''}`}>
      <div className="brand"><div className="brand-icon"><Activity size={23}/></div><div><b>市場雷達</b><small>TAIWAN MARKET SCANNER</small></div></div>
      <button className={`nav-home ${page==='總覽'?'active':''}`} onClick={()=>newPage('總覽')}><LayoutDashboard size={17}/> 市場總覽 <ChevronRight size={16}/></button>
      <div className="nav-scroll">{NAV.map(group=><div className="nav-group" key={group.label}><span className="nav-heading">{group.label}</span>{group.items.filter(row=>row[0]!=='總覽').map(([name,Icon])=><button className={`nav-item ${page===name?'active':''}`} key={name} onClick={()=>newPage(name)}><Icon size={17}/><span>{name}</span>{name==='信用利差'&&signals.creditNow?.light==='RED'&&<i className="nav-alert"/>}</button>)}</div>)}</div>
      <div className="sidebar-bottom"><div className="source-indicator"><span className={`live-dot ${quoteStatus!=='fresh'?'is-demo':''}`}/>{market.mode==='demo'?'DEMO / 虛構市場':`${STATUS_NAMES[quoteStatus]} / 盤後資料`}</div><button onClick={()=>setSourceOpen(true)}><Database size={16}/> 資料來源設定 <ChevronRight size={15}/></button></div>
    </aside>
    <div className="main-col">
      <header className="topbar"><button className="hamburger" onClick={()=>setMenu(!menu)} aria-label="開啟選單"><Menu size={21}/></button>
        <div className="breadcrumb"><span>台股掃描器</span><ChevronRight size={13}/><strong>{page}</strong></div>
        <div className="top-actions"><button className="search-toggle" onClick={()=>{const e=document.querySelector('#stock-search');e?.focus();}} aria-label="搜尋股票"><Search size={18}/></button>
          <button className="icon-btn refresh-btn" aria-label="重新讀取盤後快照" disabled={loading} onClick={()=>setReload(v=>v+1)}><RotateCcw size={17}/></button>
          <button className="data-cta" onClick={()=>setSourceOpen(true)} aria-label="接入資料"><Database size={16}/><span>接入資料</span></button><span className={`top-mode ${quoteStatus!=='fresh'?'top-demo':''}`}>{market.mode==='demo'?'DEMO':market.mode==='unavailable'?'待資料':'盤後'}</span></div>
      </header>
      <main className="content">
        <div className="page-top"><div><div className="eyebrow">盤後觀察版 / {signals.anchor||market.asOf||"待資料"}</div><h1>{page==='總覽'?'市場總覽':page}</h1><p>{page==='總覽'?'用更少的畫面，掌握真正重要的市場變化。':'資料缺口會明確標示，不用猜測任何數字。'}</p></div>
          <div className="quick-search"><Search size={16}/><input id="stock-search" placeholder="搜尋股票，例如 2330、台積電" value={search} onChange={e=>setSearch(e.target.value)}/>{search&&<button aria-label="清除搜尋" onClick={()=>setSearch('')}><X size={15}/></button>}
            {search&&<div className="search-results">{currentStocks.length?currentStocks.map(s=><button key={securityKey(s)} onClick={()=>{setSelected(s);setSearch('')}}><b>{s.symbol}</b><span>{s.name}</span><Percent value={s.change}/></button>):<p>找不到此股票</p>}</div>}
          </div>
        </div>
        <div className={`data-banner ${quoteStatus!=='fresh'?'demo-banner':''}`} role="status"><Database size={17}/><span>{loading?'讀取官方盤後快照…':market.mode==='demo'?'虛構 DEMO · 固定測試行情，所有數字都不是市場事實。':market.mode==='unavailable'?'官方行情尚未載入；空白不代表價格或風險為零。':`官方盤後資料日 ${sourceDate} · ${STATUS_NAMES[quoteStatus]} · 非即時報價。`}</span><button onClick={()=>newPage('資料健康')}>資料健康 <ChevronRight size={14}/></button></div>
        {page==='總覽'&&<div className="health-strip"><button onClick={()=>newPage('資料健康')}>價量 {STATUS_NAMES[quoteStatus]}</button><span>觀測 {selectedExchanges.map(m=>`${m} ${marketMeta(market,m).sessions?.length||0} 日`).join('／')}</span><span>{market.mode==='demo'?'DEMO 觀察池':`${MARKET_NAMES[scope]} ${signals.latest.length} 檔`}</span><span>{market.calendar?.state==='closed'?'官方日曆：休市':market.calendar?.state==='open'?'官方日曆：交易日':'日曆待核對'}</span></div>}
        {error && !sourceOpen && <div className="errorbox global-error"><AlertTriangle size={16}/>{error}<button onClick={() => setSourceOpen(true)}>檢查資料來源</button></div>}
        <section className="coverage-panel" aria-label="研究母體與資料覆蓋">
          <div className="filters"><label>市場母體 <select aria-label="市場母體" value={scope} onChange={e=>{setScope(e.target.value);setSelected(null)}}>{Object.entries(MARKET_NAMES).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>
          <label>研究價格基礎 <select aria-label="均線／突破價格基礎" value={basis} onChange={e=>{setBasis(e.target.value);setSelected(null)}}>{Object.entries(BASIS_NAMES).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label></div>
          <p>{MARKET_NAMES[scope]}普通股 {signals.coverage.total} 檔 · 同日未還原價 {signals.coverage.quotes} / {signals.coverage.total}（{format(signals.coverage.quotePct,1)}%）· 經驗證還原價 {signals.coverage.adjusted} 檔</p>
          <p>同日原價未涵蓋 {signals.coverage.total-signals.coverage.quotes} 檔；缺價、來源日期不同或原因未確認，不推定為停牌。</p>
          <p className="daily-breadth">行情日 {signals.daily.date||"—"} · {signals.daily.available?`上漲 ${signals.daily.up} ／ 下跌 ${signals.daily.down} ／ 平盤 ${signals.daily.flat}`:signals.daily.datesAligned?"0 檔具備可判定漲跌資料":"上市櫃日期不一致，合併漲跌暫不計算"} · 可判定 {signals.daily.eligible}/{signals.daily.total} 檔</p>
          <details className="coverage-details"><summary>來源、更新時間與停用功能說明</summary>
          <p>已觀測有效價格 {signals.coverage.minDays}–{signals.coverage.maxDays} 日／目標約 300 交易日；不代表連續完整日曆。</p>
          <p>完整 MA20／60／120／240：{[20,60,120,240].map(n=>signals.coverage.ma[n]).join('／')} 檔 · 可判定240日突破 {signals.coverage.breakout240} 檔</p>
          <p>{BASIS_NAMES[basis]} · {basis==='adjusted'?'尚無經驗證還原價時保持缺資料，不改用原價。':'均線為暫行研究；未還原突破須完整事件覆蓋且窗口無除權息／資本事件。'}</p>
          <p>資料日：{sourceDate} · 檔案產生：{market.generatedAt?.replace('T',' ')}；產檔時間不是行情更新日。</p>
          <p>法人：TPEx 可獨立研究；TWSE T86 停用，不提供完整上市櫃法人合計。轉板／下市／停牌歷史尚未完整驗證。</p>
          </details>
        </section>
        {render()}
        <footer>台股掃描器 3.0　／　資料日期 {market.asOf||'—'}　／　{market.mode==='demo'?'虛構示範':'臺灣證券交易所／證券櫃檯買賣中心／臺灣期貨交易所；開放資料第1版，普通股篩選及研究統計，非交易指令'}　／　<a href="https://data.gov.tw/license" target="_blank" rel="noreferrer">政府資料開放授權條款第 1 版</a></footer>
      </main>
    </div>
    <nav className="bottom-nav">{[['總覽',LayoutDashboard],['信用利差',ShieldAlert],['市場廣度',Waves],['高點突破',Zap],['我的關注',Star]].map(([v,Icon])=><button key={v} className={page===v?'active':''} onClick={()=>newPage(v)}><Icon size={20}/><span>{v}</span></button>)}</nav>
    <StockDrawer stock={selected} close={()=>setSelected(null)} watching={selected?(watchlist.includes(securityKey(selected))||watchlist.includes(selected.symbol)&&selected.market!=='TPEx'):false} toggle={toggleWatch}/>
    {sourceOpen&&<DataModal onClose={()=>setSourceOpen(false)} error={error} clearError={setError} onDemo={()=>{setMarket(makeDemo());setSourceOpen(false);setError('');setPage('總覽')}} onImport={next=>{setMarket(next);setSourceOpen(false);setError('');setPage('總覽')}}/>}
  </div>;
}
