const assert=require('node:assert/strict');
const {LiveRules}=require('../static/live-rules.js');
(async()=>{
 let calls=[],busy=true,release;
 const live=new LiveRules({delay:1,busy:()=>busy,save:async p=>{calls.push(p); if(p.value===2)await new Promise(r=>release=r);}});
 live.schedule({value:1});live.schedule({value:2});
 await new Promise(r=>setTimeout(r,10));assert.equal(calls.length,0,'scan defers settings');
 busy=false;live.resume();await new Promise(r=>setTimeout(r,10));assert.deepEqual(calls,[{value:2}]);
 live.schedule({value:3});live.schedule({value:4});release();
 await new Promise(r=>setTimeout(r,20));assert.deepEqual(calls,[{value:2},{value:4}],'serialize and keep newest edit');
 console.log('live rules queue passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
