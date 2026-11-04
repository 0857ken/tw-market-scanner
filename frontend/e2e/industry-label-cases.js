import {test,expect} from '@playwright/test';
async function go(page,name){
 if(await page.getByRole('button',{name:'開啟選單',exact:true}).isVisible())await page.getByRole('button',{name:'開啟選單',exact:true}).click();
 await page.locator('.sidebar .nav-item').filter({hasText:new RegExp(`^${name}$`)}).click();
 await expect(page.locator('.page-top h1')).toHaveText(name);
}
export function industryLabelCases(market){
 for(const width of [320,375,390,430,1440])test(`industry labels ${width}px: names, unchanged groups and filters`,async({page})=>{
  await page.setViewportSize({width,height:844});await page.goto('./');await expect(page.locator('.data-banner')).toContainText(market.asOf);
  await go(page,'產業輪動');
  for(const name of ['塑膠工業（03）','資訊服務業（30）','金融業／金融保險（17）'])await expect(page.locator('.sector-list')).toContainText(name);
  const detail=page.locator('.panel').filter({has:page.getByRole('heading',{name:'族群明細',exact:true})});
  const plastic=detail.locator('tbody tr').filter({hasText:'塑膠工業（03）'}),expected=market.stocks.filter(s=>s.sector==='產業 03');
  await expect(plastic.locator('td').nth(1)).toHaveText(String(expected.length));await plastic.click();
  await expect(page.locator('.sector-members h3')).toHaveText('塑膠工業（03） · 成分股');await expect(page.locator('.sector-members tbody tr')).toHaveCount(expected.length);
  for(const scope of ['TWSE','TPEx']){
   await page.getByLabel('市場母體',{exact:true}).selectOption(scope);
   await expect(page.locator('.sector-list')).toContainText(scope==='TWSE'?'金融保險（17）':'金融業（17）');
  }
  await page.getByLabel('市場母體',{exact:true}).selectOption('ALL');await go(page,'台股熱力圖');
  const select=page.getByLabel('產業',{exact:true});await expect(select.locator('option[value="產業 03"]')).toHaveText('塑膠工業（03）');await select.selectOption('產業 03');await expect(select).toHaveValue('產業 03');
  const eligible=expected.filter(s=>{const q=s.history.find(q=>q.date===market.asOf);return q?.close>0&&Number.isFinite(q.changeAmount)&&q.close-q.changeAmount>0});
  expect((await page.locator('.heatmap [data-security-id]').evaluateAll(n=>n.map(x=>x.dataset.securityId))).sort()).toEqual(eligible.map(s=>s.securityId).sort());
  await page.locator('#stock-search').fill('2330');await page.locator('.search-results button').first().click();await expect(page.getByRole('dialog').locator('.drawer-head')).toContainText('半導體業（24）');await page.keyboard.press('Escape');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);await go(page,'產業輪動');
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBe(true);
  await page.screenshot({path:`../test-results/industry-labels-${width}.png`,fullPage:true});
 });
}
