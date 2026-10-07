import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createReadRefresh, dataQuery, fieldChanges} from '../.test-output/data-center.js';

test('inspection query encodes hostile values and sends bounded paging',()=>{
 assert.equal(dataQuery({q:"';drop",limit:50,offset:100}), '?q=%27%3Bdrop&limit=50&offset=100');
});
test('refresh skips hidden and in-flight requests and disposes timer',async()=>{
 let tick, stopped=false, hidden=false, release, calls=0;
 const refresh=createReadRefresh(()=>{calls++;return new Promise(r=>{release=r;});},()=>!hidden,(fn,ms)=>{assert.equal(ms,15000);tick=fn;return 1;},()=>{stopped=true;});
 hidden=true;tick();assert.equal(calls,0);hidden=false;tick();tick();await Promise.resolve();assert.equal(calls,1);
 release();await new Promise(r=>setImmediate(r));tick();await Promise.resolve();assert.equal(calls,2);
 refresh();assert.equal(stopped,true);release();await Promise.resolve();tick();assert.equal(calls,2);
});
test('history compares safe scalar and nested fields and preserves baseline unknown before',()=>{
 assert.deepEqual(fieldChanges({city:'A'},{city:'B'}),[{field:'city',before:'A',after:'B'}]);
 assert.deepEqual(fieldChanges(null,{title:'Current'}),[{field:'title',before:undefined,after:'Current'}]);
});

test('latest view queues behind in-flight read and discards stale result',async()=>{
 const {createLatestRead}=await import('../.test-output/data-center.js');
 const results=[];let release;const read=createLatestRead(v=>results.push(v),e=>{throw e;});
 read(()=>new Promise(r=>{release=r;}));
 read(async()=> 'new view');
 release('old view');await new Promise(r=>setImmediate(r));
 assert.deepEqual(results,['new view']);read.dispose();
});

test('StrictMode cleanup and setup resumes reader but rejects pre-cleanup response',async()=>{
 const {createLatestRead}=await import('../.test-output/data-center.js');const results=[];let release;
 const read=createLatestRead(v=>results.push(v),e=>{throw e;});
 read(()=>new Promise(r=>{release=r;}));read.dispose();read.resume();read(async()=> 'fresh setup');
 release('stale setup');await new Promise(r=>setImmediate(r));assert.deepEqual(results,['fresh setup']);read.dispose();
});

test('cross-resource parent navigation clears child relation and incompatible filters',async()=>{
 const {recordNavigationFilters}=await import('../.test-output/data-center.js');
 const filters={q:'payment',status:'SUCCEEDED',from:'2026-10-07',to:'2026-10-08',relation:{field:'order_id',value:'order-1'}};
 assert.deepEqual(recordNavigationFilters('commerce_payment_attempts','commerce_payment_attempts',filters),filters);
 const returning=recordNavigationFilters('commerce_payment_attempts','commerce_orders',filters);
 assert.deepEqual(returning,{q:'',status:'',from:'',to:'',relation:undefined});
 assert.equal(dataQuery({limit:50,offset:0,...returning}), '?limit=50&offset=0');
});

test('directory and child transitions reset date range before applying exact relation',async()=>{
 const {resetListingFilters}=await import('../.test-output/data-center.js');
 const child={...resetListingFilters(),relation:{field:'order_id',value:'order-1'}};
 assert.equal(child.from,'');assert.equal(child.to,'');
 assert.equal(dataQuery({limit:50,offset:0,q:child.q,status:child.status,from:child.from,to:child.to,...child.relation}), '?limit=50&offset=0&field=order_id&value=order-1');
});
