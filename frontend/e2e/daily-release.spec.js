import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const manifest=JSON.parse(fs.readFileSync(new URL('../dist-daily/release-manifest.json',import.meta.url)));
const actualMarket=JSON.parse(fs.readFileSync(new URL('../dist-daily/market.json',import.meta.url)));
async function loaded(page){await page.goto('./');await expect(page.locator('.data-banner')).toContainText(manifest.asOf);}
async function go(page,name){
  if(await page.getByRole('button',{name:'開啟選單',exact:true}).isVisible())await page.getByRole('button',{name:'開啟選單',exact:true}).click();
  await page.locator('.sidebar .nav-item').filter({hasText:new RegExp(`^${name}$`)}).click();
  await expect(page.locator('.page-top h1')).toHaveText(name);
  if(await page.getByRole('button',{name:'開啟選單',exact:true}).isVisible())await expect.poll(()=>page.locator('.sidebar').evaluate(e=>e.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
}
for(const width of [320,375,390,430,1440])test(`${width}px: pinned observation RC assets, features and scope`,async({page})=>{
  await page.setViewportSize({width,height:844});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const failures=[];page.on('response',r=>{if(r.status()>=400)failures.push(r.url())});
  await loaded(page);
  await expect(page.locator('.rc-version')).toContainText('不保證最新');
  await expect(page.locator('.rc-version')).toContainText(manifest.version);
  await expect(page.getByRole('region',{name:'研究母體與資料覆蓋'})).toContainText(`上市 ${actualMarket.sources.companies.asOf}`);
  await expect(page.getByRole('button',{name:'接入資料',exact:true})).toHaveCount(0);
  await expect(page.locator('input[type=file]')).toHaveCount(0);
  await expect(page.getByText('檢視虛構 DEMO（僅供介面示意）')).toHaveCount(0);
  await page.locator('#stock-search').fill('2330');await page.locator('.search-results button').first().click();
  await expect(page.getByRole('dialog')).toContainText('2330');
  await expect(page.getByRole('dialog').locator('.drawer-stats').first()).toContainText('停用');
  await page.getByRole('button',{name:'加入關注',exact:true}).click();await page.keyboard.press('Escape');
  await page.reload();await expect(page.locator('.data-banner')).toContainText(manifest.asOf);
  await go(page,'我的關注');await expect(page.locator('tbody')).toContainText('2330');
  await page.getByRole('combobox',{name:'市場母體'}).selectOption('TPEx');
  await go(page,'法人買賣超');await expect(page.locator('main')).toContainText('TPEx');
  await go(page,'台股熱力圖');await expect(page.locator('g[data-security-id]').first()).toBeVisible();
  await page.locator('g[data-security-id]').first().click();await expect(page.getByRole('dialog')).toBeVisible();await page.keyboard.press('Escape');
  await go(page,'產業輪動');await expect(page.locator('.panel').last()).toBeVisible();
  await page.locator('.panel').last().locator('tbody tr').first().click();
  await expect(page.locator('.sector-members')).toBeVisible();
  await go(page,'停用功能');await expect(page.locator('main')).toContainText('0 檔具備足夠策略資料');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  expect(errors).toEqual([]);expect(failures).toEqual([]);
  await page.screenshot({path:`../test-results/stage4c1-${width}-disabled.png`,fullPage:true});
  if(await page.getByRole('button',{name:'開啟選單',exact:true}).isVisible())await page.getByRole('button',{name:'開啟選單',exact:true}).click();
  await page.locator('.nav-home').click();
  if(await page.getByRole('button',{name:'開啟選單',exact:true}).isVisible())await expect.poll(()=>page.locator('.sidebar').evaluate(e=>e.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
  await expect(page.locator('.page-top h1')).toHaveText('市場總覽');
  await page.screenshot({path:`../test-results/stage4c1-${width}-home.png`,fullPage:true});
});
test('failed refresh and mismatched cached data retain last approved version',async({page})=>{
  await loaded(page);
  await page.route('**/market.json*',r=>r.fulfill({status:503,body:'failed'}));
  await page.getByRole('button',{name:'重新讀取盤後快照'}).click();
  await expect(page.locator('.global-error')).toContainText('HTTP 503');
  await expect(page.locator('.data-banner')).toContainText(manifest.asOf);
  await page.route('**/market.json*',r=>r.fulfill({json:{mode:'demo',asOf:'2026-10-01'}}));
  await page.getByRole('button',{name:'重新讀取盤後快照'}).click();
  await expect(page.locator('.global-error')).toContainText('SHA256 不符');
  await expect(page.locator('.data-banner')).toContainText(manifest.asOf);
  await expect(page.locator('.top-mode')).toHaveText('盤後');
});
test('unapproved bytes on initial load stay unavailable',async({page})=>{
  await page.route('**/market.json*',r=>r.fulfill({body:'{}',contentType:'application/json'}));
  await page.goto('./');await expect(page.locator('.global-error')).toContainText('SHA256 不符');
  await expect(page.locator('.data-banner')).toContainText('尚未載入');
});
test('real missing same-day price stays unknown in search and stock drawer',async({page})=>{
  const stock=actualMarket.stocks.find(s=>{const day=actualMarket.sources[s.market==='TWSE'?'quotes':'tpexQuotes'].asOf;return !s.history.find(r=>r.date===day)?.close;});
  expect(stock).toBeTruthy();await loaded(page);
  await page.getByRole('combobox',{name:'市場母體'}).selectOption(stock.market);
  await page.locator('#stock-search').fill(stock.symbol);await page.locator('.search-results button').first().click();
  await expect(page.getByRole('dialog').locator('.stock-price b').first()).toHaveText('—');
  await expect(page.getByRole('dialog').locator('.drawer-stats').first()).toContainText('停用');
});

test('wrong frontend manifest and dated versions fail closed',async({page})=>{
 await loaded(page);
 await page.route('**/release-manifest.json*',r=>r.fulfill({json:{...manifest,frontendId:'other'}}));
 await page.getByRole('button',{name:'重新讀取盤後快照'}).click();
 await expect(page.locator('.global-error')).toContainText('manifest');
 await expect(page.locator('.data-banner')).toContainText(manifest.asOf);
});

// Issue #7: real daily-loader path with merged mobile UI; offline responses only.
import {heatmapOverviewCases} from './heatmap-overview-cases.js';
import crypto from 'node:crypto';
heatmapOverviewCases(actualMarket,{rc:true});
for(const width of [320,375,390,430,1440])test(`integration ${width}px: mixed source dates suppress up/down/flat`,async({page})=>{
  const p=structuredClone(actualMarket),m=structuredClone(manifest),day='2026-10-12';
  const version=p.stocks.filter(s=>s.market==='TPEx').flatMap(s=>s.history).find(r=>r.date===day&&r.close>0).sourceVersion;
  Object.assign(p.sources.tpexQuotes,{asOf:day,sha256:version});
  p.research.markets.TPEx.asOf=day;p.research.markets.TPEx.sessions=p.research.markets.TPEx.sessions.filter(d=>d<=day);
  for(const s of p.stocks.filter(s=>s.market==='TPEx'))s.history=s.history.filter(r=>r.date<=day);
  const body=JSON.stringify(p),digest=crypto.createHash('sha256').update(body).digest('hex');
  m.publishedDataSha256=digest;m.assets['market.json']=digest;
  Object.assign(m.sourceVersions.tpexQuotes,{asOf:day,sha256:version});
  await page.route('**/release-manifest.json*',r=>r.fulfill({json:m}));
  await page.route('**/market.json*',r=>r.fulfill({body,contentType:'application/json'}));
  await page.setViewportSize({width,height:844});await loaded(page);
  await expect(page.locator('.global-error')).toHaveCount(0);
  await expect(page.locator('.daily-breadth')).toContainText('上市櫃日期不一致');
  await go(page,'台股熱力圖');
  await expect(page.locator('.heatmap-summary')).toContainText('上漲 — ／ 下跌 — ／ 平盤 —');
  await expect(page.locator('.heatmap-summary')).toContainText('上市櫃日期不一致');
});
for(const missing of ['manifest','hash'])test(`integration missing ${missing}: fail closed initially and retain verified snapshot on refresh`,async({page})=>{
  const reject=()=>page.route('**/release-manifest.json*',r=>missing==='manifest'?r.fulfill({status:404,body:'missing'}):r.fulfill({json:{...manifest,publishedDataSha256:undefined}}));
  await reject();await page.goto('./');await expect(page.locator('.global-error')).toContainText('manifest');
  await expect(page.locator('.data-banner')).toContainText('尚未載入');
  await page.unroute('**/release-manifest.json*');await page.getByRole('button',{name:'重新讀取盤後快照'}).click();
  await expect(page.locator('.data-banner')).toContainText(manifest.asOf);
  await reject();await page.getByRole('button',{name:'重新讀取盤後快照'}).click();
  await expect(page.locator('.global-error')).toContainText('manifest');
  await expect(page.locator('.data-banner')).toContainText(manifest.asOf);
});
test('integration daily keyboard, drawer focus and full verified identity',async({page})=>{
  await page.setViewportSize({width:390,height:844});await loaded(page);
  const search=page.locator('#stock-search');await search.fill('2330');
  await page.evaluate(()=>{Object.defineProperty(visualViewport,'height',{configurable:true,get:()=>500});visualViewport.dispatchEvent(new Event('resize'))});
  await expect(page.locator('.bottom-nav')).toBeHidden();
  await page.getByRole('button',{name:'收起搜尋鍵盤',exact:true}).click();
  await expect(search).toHaveValue('2330');await expect(search).not.toBeFocused();await expect(page.locator('.bottom-nav')).toBeVisible();
  await page.locator('.search-results button').first().click();
  const drawer=page.getByRole('dialog'),close=drawer.getByRole('button',{name:'關閉',exact:true});
  await expect(close).toBeFocused();await page.keyboard.press('Shift+Tab');
  expect(await drawer.evaluate(e=>e.contains(document.activeElement))).toBe(true);
  await page.keyboard.press('Tab');await expect(close).toBeFocused();
  await drawer.evaluate(e=>{e.scrollTop=e.scrollHeight});await expect(close).toBeInViewport();
  await page.keyboard.press('Escape');await expect(search).toBeFocused();
  expect(await page.evaluate(()=>document.body.style.position)).toBe('');
  await page.locator('.version-details summary').click();
  await expect(page.locator('.version-details')).toContainText(manifest.publishedDataSha256);
  await expect(page.locator('.version-details')).toContainText(manifest.runId);
});
test('integration dated daily snapshot retains explicit age and disabled scope',async({page})=>{
  await page.clock.setFixedTime(new Date('2026-10-28T10:00:00Z'));await loaded(page);
  await expect(page.locator('.rc-version')).toContainText('15 個日曆日');
  await expect(page.locator('.rc-version')).toContainText('不保證最新');
  await expect(page.locator('.rc-version')).toContainText('信用與 TWSE T86 停用');
  // Displaying a dated verified observation is not approval for new-day publication.
  await expect(page.locator('.data-banner')).toContainText('非即時');
});
