import {test} from 'node:test';
import assert from 'node:assert/strict';
import {observationSignals} from '../src/observation.js';
const input={latest:[{symbol:'2330',change:2,ma240:80,breakout240:true}],daily:{datesAligned:true},coverage:{total:1,ma:{240:1}},hits:[{}],creditNow:{light:'RED'}};
test('observation profile cannot expose historical strategy signals even when inputs contain them',()=>{
  const result=observationSignals(input);
  assert.equal(result.latest[0].change,2);
  assert.equal(result.latest[0].ma240,null);
  assert.equal(result.latest[0].breakout240,false);
  assert.equal(result.creditNow,null);
  assert.deepEqual(result.hits,[]);
  assert.equal(result.coverage.ma[240],0);
  assert.equal(input.latest[0].ma240,80);
});
test('different-market dates suppress combined rankings and heatmap changes',()=>{
  const result=observationSignals({...input,daily:{datesAligned:false}});
  assert.equal(result.latest[0].change,null);
});
