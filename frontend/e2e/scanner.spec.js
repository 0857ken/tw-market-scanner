import {test,expect} from '@playwright/test';
import fs from 'node:fs';
const market=JSON.parse(fs.readFileSync(new URL('../../tests/fixtures/official-market-20261007.json',import.meta.url),'utf8'));
const pages=['資料健康','我的關注','信用利差','市場廣度','市場體制','台股熱力圖','美股熱力圖','高點突破','產業輪動','盤中量能','法人買賣超','連續買賣超','期貨籌碼','融資水位','券商分點','盤前觀察','研究週報','持股水位'];
async function loaded(page){
  await page.route('**/market.json',route=>route.fulfill({json:market}));
  await page.goto('./');await expect(page.locator('.data-banner')).toContainText(market.asOf);
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
  await page.route('**/market.json',route=>route.fulfill({status:503,body:'source unavailable'}));
  await page.goto('./');await expect(page.locator('.global-error')).toContainText('HTTP 503');
  await expect(page.locator('.data-banner')).toContainText('尚未載入');
  await expect(page.locator('.top-mode')).toHaveText('待資料');
  await expect(page.locator('.metric').filter({hasText:'加權指數'})).toContainText('—');
});
test('failed refresh retains the last observed date and shows the error',async({page})=>{
  await loaded(page);
  await page.route('**/market.json',route=>route.fulfill({status:503,body:'failure'}));
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
  await page.route('**/market.json',route=>route.fulfill({json:value}));
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
  await page.route('**/market.json',route=>route.fulfill({json:integrated}));
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
  await page.route('**/market.json',route=>route.fulfill({json:integrated}));
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
