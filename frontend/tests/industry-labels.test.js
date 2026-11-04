import {test} from 'node:test';
import assert from 'node:assert/strict';
import {industryLabel,industryGroupLabel} from '../src/industry-labels.js';
const row=(code,market='TWSE')=>({sector:`產業 ${code}`,sectorCode:code,market});
test('official codes and post-2023 names',()=>{
 for(const market of ['TWSE','TPEx'])for(const [code,name] of [['03','塑膠工業'],['30','資訊服務業'],['16','觀光餐旅'],['35','綠能環保'],['36','數位雲端'],['37','運動休閒'],['38','居家生活']])assert.equal(industryLabel(row(code,market)),`${name}（${code}）`);
});
test('market-specific names never borrowed across markets',()=>{
 assert.equal(industryLabel(row('17')),'金融保險（17）');assert.equal(industryLabel(row('17','TPEx')),'金融業（17）');
 assert.equal(industryLabel(row('32','TPEx')),'文化創意業（32）');assert.equal(industryLabel(row('33','TPEx')),'農業科技業（33）');
 assert.equal(industryLabel(row('32')),'產業 32（分類未確認）');assert.equal(industryLabel(row('18','TPEx')),'產業 18（分類未確認）');
});
test('unknown and malformed codes and missing markets remain explicit',()=>{
 for(const r of [row('99'),row('03','UNKNOWN'),row('003'),{sector:'產業 X',market:'TWSE'}])assert.equal(industryLabel(r),`${r.sector}（分類未確認）`);
 assert.equal(industryLabel({}),'未分類（分類未確認）');
 assert.equal(industryGroupLabel('產業 X',[]),'產業 X（分類未確認）');
});
test('existing descriptive labels remain unchanged',()=>{
 for(const sector of ['半導體','美股示範','未分類'])assert.equal(industryLabel({sector}),sector);
 assert.equal(industryGroupLabel('全部',[]),'全部');
});
test('combined groups keep both official names and never mutate records',()=>{
 const rows=[row('17'),row('17','TPEx')],before=JSON.stringify(rows);
 assert.equal(industryGroupLabel('產業 17',rows),'金融業／金融保險（17）');assert.equal(JSON.stringify(rows),before);
 assert.equal(industryGroupLabel('產業 03',[row('03'),row('03','TPEx')]),'塑膠工業（03）');
 assert.equal(industryGroupLabel('產業 03',[row('03','UNKNOWN')]),'產業 03（分類未確認）');
 assert.equal(industryGroupLabel('產業 03',[]),'產業 03（分類未確認）');
});
test('single digit normalized only for display',()=>{
 const r=row('3');assert.equal(industryLabel(r),'塑膠工業（03）');assert.equal(r.sectorCode,'3');
});
