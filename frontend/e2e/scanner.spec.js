import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const market=JSON.parse(fs.readFileSync(new URL('../../tests/fixtures/official-market-20261007.json',import.meta.url),'utf8'));
const pages=['資料健康','我的關注','信用利差','市場廣度','市場體制','台股熱力圖','美股熱力圖','高點突破','產業輪動','盤中量能','法人買賣超','連續買賣超','期貨籌碼','融資水位','券商分點','盤前觀察','研究週報','持股水位'];
for(const width of [320,375,390,430])test(`mobile polish ${width}px: touch, search, drawer and focus`,async({browser})=>{
  const context=await browser.newContext({viewport:{width,height:844},isMobile:true,hasTouch:true});
  const page=await context.newPage();
  try{
    await loaded(page);
    const search=page.locator('#stock-search');
    expect(await search.evaluate(e=>parseFloat(getComputedStyle(e).fontSize))).toBeGreaterThanOrEqual(16);
    await search.fill('2330');
    for(const name of ['清除搜尋','收起搜尋鍵盤']){
      const box=await page.getByRole('button',{name,exact:true}).boundingBox();
      expect(box.width).toBeGreaterThanOrEqual(44);expect(box.height).toBeGreaterThanOrEqual(44);
    }
    await page.getByRole('button',{name:'收起搜尋鍵盤',exact:true}).tap();
    await expect(search).not.toBeFocused();await expect(search).toHaveValue('2330');
    await expect(page.locator('.search-results button').first()).toBeVisible();
    await page.locator('.search-results button').first().tap();
    const drawer=page.getByRole('dialog');await expect(drawer).toContainText('2330');
    await expect(page.locator('.main-col')).toHaveAttribute('inert','');
    expect(await page.evaluate(()=>document.body.style.position)).toBe('fixed');
    const close=drawer.getByRole('button',{name:'關閉',exact:true});await expect(close).toBeFocused();
    const box=await close.boundingBox();expect(box.width).toBeGreaterThanOrEqual(44);expect(box.height).toBeGreaterThanOrEqual(44);
    await page.keyboard.press('Shift+Tab');expect(await drawer.evaluate(e=>e.contains(document.activeElement))).toBe(true);
    await page.keyboard.press('Tab');await expect(close).toBeFocused();
    await drawer.evaluate(e=>{e.scrollTop=e.scrollHeight});await expect(close).toBeInViewport();
    await close.tap();await expect(drawer).toHaveCount(0);await expect(search).toBeFocused();
    expect(await page.evaluate(()=>document.body.style.position)).toBe('');
    await search.fill('2330');await search.press('Enter');await expect(drawer).toContainText('2330');
    await page.keyboard.press('Escape');await expect(drawer).toHaveCount(0);
    await search.fill('沒有這個代碼'.repeat(10));await expect(page.locator('.search-results')).toContainText('找不到此股票');
    const bounds=await page.locator('.quick-search').boundingBox();expect(bounds.x+bounds.width).toBeLessThanOrEqual(width+1);
    await page.getByRole('button',{name:'清除搜尋',exact:true}).tap();await expect(search).toHaveValue('');await expect(search).toBeFocused();
    await page.locator('.page-top h1').tap();await expect(page.locator('.search-results')).toHaveCount(0);
  }finally{await context.close()}
});
test('mobile polish: visual viewport keyboard response and search key navigation',async({page})=>{
  await page.setViewportSize({width:390,height:844});await loaded(page);
  const search=page.locator('#stock-search');await search.fill('23');
  // Controlled viewport resize checks application behavior, not a real OS keyboard.
  await page.evaluate(()=>{Object.defineProperty(visualViewport,'height',{configurable:true,get:()=>500});visualViewport.dispatchEvent(new Event('resize'))});
  await expect(page.locator('.bottom-nav')).toBeHidden();
  expect(await page.locator('.search-results').evaluate(e=>e.getBoundingClientRect().bottom)).toBeLessThanOrEqual(500);
  await page.getByRole('button',{name:'收起搜尋鍵盤',exact:true}).click();await expect(page.locator('.bottom-nav')).toBeVisible();
  await search.focus();await search.press('ArrowDown');await expect(page.locator('.search-results button').first()).toBeFocused();
  await page.keyboard.press('ArrowDown');await expect(page.locator('.search-results button').nth(1)).toBeFocused();
  await page.keyboard.press('Enter');await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');await expect(search).toBeFocused();
  await page.evaluate(()=>{delete visualViewport.height;visualViewport.dispatchEvent(new Event('resize'))});
});
test('mobile polish: backdrop drag does not dismiss and closing restores page scroll',async({page})=>{
  await page.setViewportSize({width:1440,height:844});await loaded(page);
  await page.locator('#stock-search').fill('2330');await page.locator('#stock-search').press('Enter');
  const drawer=page.getByRole('dialog');await expect(drawer).toBeVisible();
  const box=await drawer.boundingBox();await page.mouse.move(box.x+30,box.y+160);await page.mouse.down();await page.mouse.move(10,160);await page.mouse.up();await expect(drawer).toBeVisible();
  await page.locator('.modal-backdrop').click({position:{x:10,y:160}});await expect(drawer).toHaveCount(0);
  await page.evaluate(()=>scrollTo(0,400));const scroll=await page.evaluate(()=>scrollY);
  await page.getByRole('button',{name:'接入資料',exact:true}).evaluate(e=>e.click());await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');await expect.poll(()=>page.evaluate(()=>scrollY)).toBe(scroll);
});
async function loaded(page){
  await page.route('**/market.json*',route=>route.fulfill({json:market}));
  await page.goto('./');await expect(page.locator('.data-banner')).toContainText(market.asOf,{timeout:15000});
}
async function go(page,name){
  if(await page.getByRole('button',{name:'開啟選單',exact:true}).isVisible())await page.getByRole('button',{name:'開啟選單',exact:true}).click();
  await page.locator('.sidebar .nav-item').filter({hasText:new RegExp(`^${name}$`)}).click();
  await expect(page.locator('.page-top h1')).toHaveText(name);
  if(await page.getByRole('button',{name:'開啟選單',exact:true}).isVisible())await expect.poll(()=>page.locator('.sidebar').evaluate(e=>e.getBoundingClientRect().right)).toBeLessThanOrEqual(1);
}
for(const width of [320,375,390,430,1440]){
  test(`${width}px production subpath: every module renders without horizontal overflow`,async({page})=>{
    await page.setViewportSize({width,height:844});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await loaded(page);
    for(const name of pages){
      await go(page,name);
      await expect(page.locator('main')).toBeVisible();
      const measured=await page.evaluate(()=>({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,body:document.body.scrollWidth}));
      expect(measured.scroll,`${name} root overflow`).toBeLessThanOrEqual(measured.client+1);
      expect(measured.body,`${name} body overflow`).toBeLessThanOrEqual(measured.client+1);
      const outside=await page.locator('.panel,.dashboard-hero,.data-banner,.metrics-grid').evaluateAll(els=>els.filter(e=>{const r=e.getBoundingClientRect();return r.right>innerWidth+1||r.left<-1}).map(e=>e.className));
      expect(outside,`${name} cards outside viewport`).toEqual([]);
    }
    expect(errors).toEqual([]);
    if(width===390){await go(page,'資料健康');await page.screenshot({path:'../test-results/mobile-health.png',fullPage:true});}
  });
}
test('real data date, warmup and pending credit are truthful',async({page})=>{
  await page.setViewportSize({width:390,height:844});await loaded(page);
  await expect(page.locator('.data-banner')).toContainText('資料落後');
  await expect(page.locator('.metric').filter({hasText:'60 日高點突破'})).toContainText('暖機中');
  await page.screenshot({path:'../test-results/mobile-home.png',fullPage:false});
  await go(page,'信用利差');await expect(page.locator('.credit-light')).toContainText('規則待確認');
  await expect(page.locator('.credit-keys')).toHaveCount(0);
  await page.screenshot({path:'../test-results/mobile-credit.png',fullPage:true});
  await go(page,'美股熱力圖');await expect(page.getByText('未接入市場資料',{exact:true})).toBeVisible();
});
test('search, stock drawer, local watchlist persistence and table sort',async({page})=>{
  await page.setViewportSize({width:390,height:844});await loaded(page);
  await page.locator('#stock-search').fill('2330');
  await page.locator('.search-results button').first().click();
  await expect(page.getByRole('dialog')).toContainText('2330');
  await page.getByRole('button',{name:'加入關注',exact:true}).click();
  await page.keyboard.press('Escape');await expect(page.getByRole('dialog')).toHaveCount(0);
  await page.reload();await expect(page.locator('.data-banner')).toContainText(market.asOf);
  await go(page,'我的關注');await expect(page.locator('tbody')).toContainText('2330');
  await page.getByRole('button',{name:'收盤價',exact:true}).click();
  await expect(page.locator('th[aria-sort="ascending"]')).toContainText('收盤價');
  await go(page,'我的關注');
  const table=page.locator('.table-scroll').first();
  const dims=await table.evaluate(e=>({scroll:e.scrollWidth,client:e.clientWidth}));
  expect(dims.scroll).toBeGreaterThanOrEqual(dims.client);
});
test('missing default feed stays unavailable and never falls back to DEMO',async({page})=>{
  await page.route('**/market.json*',route=>route.fulfill({status:503,body:'source unavailable'}));
  await page.goto('./');await expect(page.locator('.global-error')).toContainText('HTTP 503');
  await expect(page.locator('.data-banner')).toContainText('尚未載入');
  await expect(page.locator('.top-mode')).toHaveText('待資料');
  await expect(page.locator('.metric').filter({hasText:'加權指數'})).toContainText('—');
});
test('failed refresh retains the last observed date and shows the error',async({page})=>{
  await loaded(page);
  await page.route('**/market.json*',route=>route.fulfill({status:503,body:'failure'}));
  await page.getByRole('button',{name:'重新讀取盤後快照'}).click();
  await expect(page.locator('.global-error')).toContainText('HTTP 503');
  await expect(page.locator('.data-banner')).toContainText(market.asOf);
});
test('DEMO is explicit opt-in; relabelled demo file is refused',async({page})=>{
  await loaded(page);await page.getByRole('button',{name:'接入資料',exact:true}).click();
  await page.getByRole('button',{name:'檢視虛構 DEMO（僅供介面示意）'}).click();
  await expect(page.locator('.data-banner')).toContainText('虛構 DEMO');
  await page.getByRole('button',{name:'接入資料',exact:true}).click();
  const invalid={...market,schemaVersion:1,mode:'live'};
  await page.locator('input[type=file]').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(invalid))});
  await expect(page.getByRole('dialog')).toContainText('schemaVersion: 2');
});

test('missing calendar marks freshness unknown and forged credit approval is rejected',async({page})=>{
  const value=structuredClone(market);delete value.calendar;value.sources.quotes.status='fresh';
  await page.route('**/market.json*',route=>route.fulfill({json:value}));
  await page.goto('./');await expect(page.locator('.data-banner')).toContainText('日期待核對');
  value.creditRule.status='confirmed';
  await page.getByRole('button',{name:'重新讀取盤後快照'}).click();
  await expect(page.locator('.global-error')).toContainText('信用規則待原作者確認');
  await expect(page.locator('.data-banner')).toContainText(market.asOf);
  await go(page,'信用利差');await expect(page.locator('.credit-light')).toContainText('規則待確認');
});

const integrated=JSON.parse(fs.readFileSync(new URL('../../data/market.json',import.meta.url),'utf8'));
for(const width of [320,390,1440])test(`Stage3B ${width}px markets, basis, coverage and institutional scope`,async({page})=>{
  await page.setViewportSize({width,height:844});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/market.json*',route=>route.fulfill({json:integrated}));
  await page.goto('./');await expect(page.locator('.data-banner')).toContainText(integrated.asOf);
  const panel=page.getByRole('region',{name:'研究母體與資料覆蓋'});
  await expect(panel).toContainText('經驗證還原價 0 檔');
  await page.getByLabel('市場母體',{exact:true}).selectOption('TPEx');
  await expect(panel).toContainText('上櫃普通股');
  await page.getByLabel('均線／突破價格基礎',{exact:true}).selectOption('raw');
  await expect(panel).toContainText('未還原價（暫行研究）');
  await go(page,'市場廣度');await expect(page.locator('.metric').filter({hasText:'站上 MA240'})).toContainText('—');
  await go(page,'高點突破');await page.getByRole('button',{name:'240',exact:true}).click();
  await expect(page.locator('.section-subtitle')).toContainText('暖機中');
  await go(page,'法人買賣超');await expect(page.locator('main')).not.toContainText('法人買賣超尚未接入');
  await page.getByLabel('市場母體',{exact:true}).selectOption('TWSE');
  await expect(page.locator('main')).toContainText('法人買賣超尚未接入');
  await page.getByLabel('市場母體',{exact:true}).selectOption('ALL');
  await expect(panel).toContainText('上市櫃合併普通股');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  expect(errors).toEqual([]);
  if(width===390)await page.screenshot({path:'../test-results/stage3b-mobile.png',fullPage:true});
});

test('Stage3C mobile daily dates, separate universes, search and empty eligibility',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.route('**/market.json*',route=>route.fulfill({json:integrated}));
  await page.goto('./');await expect(page.locator('.data-banner')).toContainText(integrated.asOf);
  const daily=page.locator('.daily-breadth');
  if(integrated.sources.quotes.asOf!==integrated.sources.tpexQuotes.asOf)await expect(daily).toContainText('上市櫃日期不一致');
  for(const scope of ['TWSE','TPEx']){
    await page.getByLabel('市場母體',{exact:true}).selectOption(scope);
    await expect(daily).toContainText(integrated.research.markets[scope].asOf);
    await expect(daily).toContainText('平盤');
  }
  const stock=integrated.stocks.find(s=>s.market==='TPEx'&&s.history.some(r=>r.date===integrated.sources.tpexQuotes.asOf&&r.close>0));
  await page.locator('#stock-search').fill(stock.symbol);await page.locator('.search-results button').first().click();
  await expect(page.getByRole('dialog')).toContainText(stock.name);await page.keyboard.press('Escape');
  await go(page,'高點突破');await expect(page.locator('main')).toContainText('0 檔具備足夠資料');
  await go(page,'台股熱力圖');await expect(page.locator('.recharts-wrapper').first()).toBeVisible();
  await go(page,'產業輪動');await expect(page.locator('main')).toContainText('有效檔數');
  await go(page,'連續買賣超');await expect(page.locator('main')).toContainText('不以零散快照推定');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
});

test('Stage3D real static artifact, mobile modules, source details and performance evidence',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  const errors=[],bad=[];page.on('pageerror',e=>errors.push(e.message));page.on('response',r=>{if(r.status()>=400)bad.push({url:r.url(),status:r.status()});});
  // No mock: verify the real built data file and asset URLs under /tw-market-scanner/.
  const started=Date.now();await page.goto('./');await expect(page.locator('.data-banner')).toContainText(integrated.asOf);
  await expect(page.locator('.coverage-details')).not.toHaveAttribute('open','');
  await page.screenshot({path:'../test-results/stage3d-home.png',fullPage:false});
  await page.locator('.coverage-details summary').click();await expect(page.getByRole('region',{name:'研究母體與資料覆蓋'})).toContainText('檔案產生');
  await go(page,'資料健康');await expect(page.locator('main')).toContainText('快照首次抓取');await expect(page.locator('main')).toContainText('最近檢查');
  await page.getByLabel('市場母體',{exact:true}).selectOption('TPEx');
  await page.locator('.coverage-details summary').click();
  await go(page,'法人買賣超');await expect(page.locator('tbody').first()).toBeVisible();
  await page.locator('main .panel').first().evaluate(e=>{e.scrollIntoView({block:'start'});window.scrollBy(0,-70)});
  await page.screenshot({path:'../test-results/stage3d-tpex.png',fullPage:false});
  await go(page,'台股熱力圖');await expect(page.locator('.recharts-wrapper').first()).toBeVisible();
  await page.locator('main .panel').first().evaluate(e=>{e.scrollIntoView({block:'start'});window.scrollBy(0,-70)});
  const tiles=page.locator('.heatmap [data-security-id]');
  const expectedTiles=integrated.stocks.filter(s=>s.market==='TPEx').filter(s=>{const r=s.history.find(r=>r.date===integrated.sources.tpexQuotes.asOf);return r&&r.close>0&&typeof r.changeAmount==='number'&&r.close-r.changeAmount>0;}).length;
  await expect(tiles).toHaveCount(Math.min(100,expectedTiles));
  const tileId=await tiles.first().getAttribute('data-security-id');await tiles.first().click();
  await expect(page.getByRole('dialog')).toContainText(tileId.split(':')[1]);await page.keyboard.press('Escape');
  await page.screenshot({path:'../test-results/stage3d-heatmap.png',fullPage:false});
  await go(page,'產業輪動');await expect(page.locator('main')).toContainText('有效檔數');
  await page.getByLabel('市場母體',{exact:true}).selectOption('ALL');
  await go(page,'高點突破');await expect(page.locator('main')).toContainText('0 檔具備足夠資料');
  await go(page,'信用利差');await expect(page.locator('.credit-light')).toContainText('規則待確認');
  expect(errors).toEqual([]);expect(bad).toEqual([]);
  const measurements=await page.evaluate(()=>({resources:performance.getEntriesByType('resource').filter(r=>/assets\//.test(r.name)).map(r=>({name:new URL(r.name).pathname,durationMs:Math.round(r.duration),bytes:r.transferSize})),serviceWorkerRegistrations:0}));
  measurements.serviceWorkerRegistrations=await page.evaluate(async()=>navigator.serviceWorker?(await navigator.serviceWorker.getRegistrations()).length:0);
  expect(measurements.serviceWorkerRegistrations).toBe(0);
  fs.writeFileSync('../test-results/stage3d-browser-audit.json',JSON.stringify({viewport:390,asOf:integrated.asOf,scenarioElapsedMs:Date.now()-started,actualDataFile:true,errors,bad,...measurements},null,2));
});

test('Stage3D mobile mismatched dates suppress combined breadth and refresh retains last valid data',async({page})=>{
  await page.setViewportSize({width:375,height:812});
  const p=structuredClone(integrated);p.sources.tpexQuotes.asOf='2026-10-08';p.research.markets.TPEx.asOf='2026-10-08';p.research.markets.TPEx.sessions=['2026-10-08'];p.sources.tpexQuotes.sha256=p.stocks.find(s=>s.market==='TPEx'&&s.history.some(r=>r.date==='2026-10-08'&&r.close>0)).history.find(r=>r.date==='2026-10-08').sourceVersion;
  for(const s of p.stocks.filter(s=>s.market==='TPEx'))s.history=s.history.filter(r=>r.date<='2026-10-08');
  await page.route('**/market.json*',r=>r.fulfill({json:p}));await page.goto('./');await expect(page.locator('.daily-breadth')).toContainText('上市櫃日期不一致');
  await page.getByLabel('市場母體',{exact:true}).selectOption('TPEx');await expect(page.locator('.daily-breadth')).toContainText('2026-10-08');
  await page.route('**/market.json*',r=>r.fulfill({status:503,body:'controlled failure'}));await page.getByRole('button',{name:'重新讀取盤後快照'}).click();
  await expect(page.locator('.global-error')).toContainText('HTTP 503');await expect(page.locator('.daily-breadth')).toContainText('2026-10-08');
});

import {heatmapOverviewCases} from './heatmap-overview-cases.js';
heatmapOverviewCases(integrated);
