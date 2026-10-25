import {test,expect} from '@playwright/test';

async function go(page){
  if(await page.getByRole('button',{name:'開啟選單',exact:true}).isVisible())await page.getByRole('button',{name:'開啟選單',exact:true}).click();
  await page.locator('.sidebar .nav-item').filter({hasText:/^台股熱力圖$/}).click();
  await expect(page.locator('.page-top h1')).toHaveText('台股熱力圖');
}
function rows(market,scope='ALL'){
  return market.stocks.filter(s=>scope==='ALL'||s.market===scope).flatMap(s=>{
    const q=s.history.find(q=>q.date===market.asOf);
    return q&&q.close>0&&Number.isFinite(q.changeAmount)&&q.close-q.changeAmount>0?[{...s,change:(q.close/(q.close-q.changeAmount)-1)*100}]:[];
  });
}
const ids=list=>list.map(s=>s.securityId).sort();
async function tileIds(page){return (await page.locator('.heatmap [data-security-id]').evaluateAll(nodes=>nodes.map(n=>n.dataset.securityId))).sort()}
async function noOverflow(page){expect(await page.evaluate(()=>Math.max(document.body.scrollWidth,document.documentElement.scrollWidth)<=innerWidth+1)).toBe(true)}

export function heatmapOverviewCases(market,{rc=false}={}){
 for(const width of [320,375,390,430,1440])test(`P1 ${width}px: selection, sorting, filters, focus and overview`,async({page})=>{
  await page.setViewportSize({width,height:844});await page.goto('./');
  await expect(page.locator('.data-banner')).toContainText(market.asOf,{timeout:15000});
  await expect(page.locator('.data-banner')).toContainText('非即時');
  await expect(page.locator('.daily-summary')).toBeVisible();
  // Core facts must begin in the first screen while warnings remain expanded.
  const summaryBox=await page.locator('.daily-summary').boundingBox();
  expect(summaryBox.y+summaryBox.height).toBeLessThanOrEqual(width<=750?780:844);
  await expect(page.locator('.scope-warning')).toBeVisible();
  await expect(page.locator('.coverage-details')).not.toHaveAttribute('open','');
  if(rc){
    await expect(page.locator('.rc-version')).toContainText('不保證最新');
    await expect(page.locator('.version-details')).not.toHaveAttribute('open','');
    await page.locator('.version-details summary').focus();await page.keyboard.press('Enter');
    await expect(page.locator('.version-details')).toHaveAttribute('open','');
    await expect(page.locator('.version-details')).toContainText(/[a-f0-9]{64}/);
    await page.keyboard.press('Enter');
  }
  await noOverflow(page);await go(page);
  const all=rows(market),byCap=[...all].sort((a,b)=>(b.marketCapM||0)-(a.marketCapM||0));
  const limit=page.getByLabel('顯示檔數',{exact:true}),rank=page.getByLabel('排序與入選（非面積）',{exact:true});
  await expect(limit).toHaveValue(width<=750?'100':'全部');
  expect(await tileIds(page)).toEqual(ids(width<=750?byCap.slice(0,100):byCap));
  for(const value of ['300','全部','100']){
    await limit.selectOption(value);
    await expect(page.locator('.heatmap [data-security-id]')).toHaveCount(value==='全部'?all.length:Math.min(Number(value),all.length));
  }
  await rank.selectOption('漲跌幅');
  expect(await tileIds(page)).toEqual(ids([...all].sort((a,b)=>b.change-a.change).slice(0,100)));
  await expect(page.locator('.heatmap-summary')).toContainText('漲跌幅排序前100');
  await rank.selectOption('市值');
  const sector=byCap[0].sector;await page.getByLabel('產業',{exact:true}).selectOption(sector);
  const filtered=byCap.filter(s=>s.sector===sector);
  expect(await tileIds(page)).toEqual(ids(filtered.slice(0,100)));
  await expect(page.locator('.heatmap-summary')).toContainText(`符合條件 ${filtered.length} 檔`);
  await expect(page.locator('.heatmap-summary')).toContainText(`可判定 ${all.length}/${market.stocks.length} 檔`);
  await page.getByLabel('產業',{exact:true}).selectOption('全部');
  await page.getByLabel('市場母體',{exact:true}).selectOption('TPEx');
  const tpex=rows(market,'TPEx').sort((a,b)=>(b.marketCapM||0)-(a.marketCapM||0));
  expect(await tileIds(page)).toEqual(ids(tpex.slice(0,100)));
  const tile=page.locator('.heatmap g[role=button]').first();const id=await tile.getAttribute('data-security-id');
  await tile.focus();await page.keyboard.press('Enter');
  await expect(page.getByRole('dialog')).toContainText(id.split(':')[1]);
  await page.keyboard.press('Escape');await expect(tile).toBeFocused();
  await tile.click();await expect(page.getByRole('dialog')).toBeVisible();await page.keyboard.press('Escape');
  await limit.selectOption('全部');
  const small=page.locator('.heatmap g[data-security-id]:not([role=button])');
  if(await small.count()){
    await small.first().dispatchEvent('click');await expect(page.getByRole('dialog')).toHaveCount(0);
    expect(await small.first().getAttribute('tabindex')).toBeNull();
  }
  await expect(page.getByLabel('漲跌色彩圖例')).toContainText('上漲');
  await noOverflow(page);
 });
 test('P1 resize: adaptive default follows viewport until explicit choice',async({page})=>{
  await page.setViewportSize({width:390,height:844});await page.goto('./');
  await expect(page.locator('.data-banner')).toContainText(market.asOf,{timeout:15000});await go(page);
  const limit=page.getByLabel('顯示檔數',{exact:true});await expect(limit).toHaveValue('100');
  await page.setViewportSize({width:844,height:390});await expect(limit).toHaveValue('全部');
  await page.setViewportSize({width:390,height:844});await expect(limit).toHaveValue('100');
  await limit.selectOption('300');await page.setViewportSize({width:1440,height:844});await expect(limit).toHaveValue('300');
  await page.setViewportSize({width:320,height:844});await expect(limit).toHaveValue('300');
  await limit.selectOption('全部');await page.setViewportSize({width:844,height:390});await expect(limit).toHaveValue('全部');
  await page.setViewportSize({width:375,height:844});await expect(limit).toHaveValue('全部');await noOverflow(page);
 });
 if(!rc)test('P1 missing cap outside top100 still forces group-wide equal weights; no-price excluded',async({page})=>{
  const fixture=structuredClone(market);
  const valid=rows(fixture).sort((a,b)=>(b.marketCapM||0)-(a.marketCapM||0));
  const missingId=valid.at(-1).securityId;
  fixture.stocks.find(s=>s.securityId===missingId).marketCapM=null;
  await page.route('**/market.json*',r=>r.fulfill({json:fixture}));
  await page.setViewportSize({width:390,height:844});await page.goto('./');
  await expect(page.locator('.data-banner')).toContainText(market.asOf,{timeout:15000});await go(page);
  await expect(page.locator('.heatmap-summary')).toContainText('等權');
  expect(await tileIds(page)).not.toContain(missingId);
  const areas=await page.locator('.heatmap g[data-security-id]>rect').evaluateAll(nodes=>nodes.map(n=>Number(n.getAttribute('width'))*Number(n.getAttribute('height'))));
  const eligibleIds=new Set(rows(fixture).map(s=>s.securityId));
  const unavailable=fixture.stocks.filter(s=>!eligibleIds.has(s.securityId));
  await page.getByLabel('顯示檔數',{exact:true}).selectOption('全部');
  const selected=await tileIds(page);for(const stock of unavailable)expect(selected).not.toContain(stock.securityId);
  // Recharts distributes rounding residuals to the last row. Compare geometry
  // with an independent equal-cap fixture rather than requiring identical pixels.
  for(const stock of fixture.stocks)stock.marketCapM=1;
  await page.reload();await expect(page.locator('.data-banner')).toContainText(market.asOf);await go(page);
  await expect(page.locator('.heatmap-summary')).toContainText('市值權重');
  const equalAreas=await page.locator('.heatmap g[data-security-id]>rect').evaluateAll(nodes=>nodes.map(n=>Number(n.getAttribute('width'))*Number(n.getAttribute('height'))));
  expect(areas.sort((a,b)=>a-b)).toEqual(equalAreas.sort((a,b)=>a-b));
  for(const stock of fixture.stocks)stock.marketCapM=null;
  await page.reload();await expect(page.locator('.data-banner')).toContainText(market.asOf);await go(page);
  await expect(page.locator('.heatmap-summary')).toContainText('等權');
  const noCapAreas=await page.locator('.heatmap g[data-security-id]>rect').evaluateAll(nodes=>nodes.map(n=>Number(n.getAttribute('width'))*Number(n.getAttribute('height'))));
  expect(noCapAreas.sort((a,b)=>a-b)).toEqual(equalAreas);
 });
}
