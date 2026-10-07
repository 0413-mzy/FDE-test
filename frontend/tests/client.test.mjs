import {test,afterEach} from 'node:test'
import assert from 'node:assert/strict'
import {CommerceClient,ApiError} from '../.test-output/client.js'
const originalFetch=globalThis.fetch
const response=(body,status=200)=>new Response(JSON.stringify(body),{status,headers:{'Content-Type':'application/json'}})
afterEach(()=>{globalThis.fetch=originalFetch})
test('uncertain network failure reuses exact key and blocks a distinct intended body',async()=>{
 const calls=[];globalThis.fetch=async(_url,init)=>{calls.push(init);throw new TypeError('Network unavailable')}
 const c=new CommerceClient('http://local','secret');await assert.rejects(c.request('/customer/checkouts','POST',{expected_version:1}));await assert.rejects(c.request('/customer/checkouts','POST',{expected_version:1}));await assert.rejects(c.request('/customer/checkouts','POST',{expected_version:2}),e=>e.code==='CLIENT_OPERATION_PENDING');assert.equal(calls.length,2);assert.equal(calls[0].headers['Idempotency-Key'],calls[1].headers['Idempotency-Key']);assert.equal(calls[0].headers.Authorization,'Bearer secret');assert.equal(calls[0].cache,'no-store')
})
test('busy and internal errors preserve key, success resets it',async()=>{
 const keys=[];let count=0;globalThis.fetch=async(_url,init)=>{keys.push(init.headers['Idempotency-Key']);count++;return count<3?response({error:{code:count===1?'OPERATION_BUSY':'INTERNAL_ERROR',message:'等待',details:{},request_id:'req'}},count===1?409:500):response({id:'one'})};const c=new CommerceClient('http://local');await assert.rejects(c.request('/write','POST',{}));await assert.rejects(c.request('/write','POST',{}));await c.request('/write','POST',{});await c.request('/write','POST',{});assert.equal(keys[0],keys[1]);assert.equal(keys[1],keys[2]);assert.notEqual(keys[2],keys[3])
})
test('business conflict surfaces details and requires a fresh intended action key',async()=>{
 const keys=[];globalThis.fetch=async(_url,init)=>{keys.push(init.headers['Idempotency-Key']);return response({error:{code:'PRICE_CHANGED',message:'价格变化',details:{current_price_minor:1200},request_id:'safe'}},409)};const c=new CommerceClient('http://local');await assert.rejects(c.request('/write','POST',{}),e=>e instanceof ApiError&&e.details.current_price_minor===1200&&e.requestId==='safe');await assert.rejects(c.request('/write','POST',{}));assert.notEqual(keys[0],keys[1])
})
test('DELETE carries JSON version and 204 returns no content',async()=>{
 let request;globalThis.fetch=async(_url,init)=>{request=init;return new Response(null,{status:204})};const c=new CommerceClient('http://local');assert.equal(await c.request('/customer/cart/lines/sku','DELETE',{expected_version:4}),undefined);assert.equal(request.body,'{"expected_version":4}')
})
test('disposed account rejects late response and prevents another request',async()=>{
 let complete;globalThis.fetch=()=>new Promise(resolve=>{complete=resolve});const c=new CommerceClient('http://local','old');const pending=c.request('/customer/orders');c.dispose();complete(response({items:[{id:'private'}]}));await assert.rejects(pending,/会话已切换/);await assert.rejects(c.request('/customer/orders'),/会话已切换/)
})
test('unreadable successful response preserves key until exact replay is decoded',async()=>{
 const keys=[];let count=0;globalThis.fetch=async(_url,init)=>{keys.push(init.headers['Idempotency-Key']);return ++count===1?new Response('{broken',{status:201}):response({id:'once'})};const c=new CommerceClient('http://local');await assert.rejects(c.request('/write','POST',{quantity:1}));assert.deepEqual(await c.request('/write','POST',{quantity:1}),{id:'once'});assert.equal(keys[0],keys[1])
})
test('uncertain inventory adjustment blocks changed version and unrelated shipment across view changes',async()=>{
 const calls=[];let fail=true;globalThis.fetch=async(url,init)=>{calls.push({url,init});if(fail)throw new TypeError('lost response');return response({version:3})};const c=new CommerceClient('http://local');const body={expected_version:1,delta:2,reason:'restock'};await assert.rejects(c.request('/inventory/sku/adjust','POST',body));const originalKey=calls[0].init.headers['Idempotency-Key'];body.delta=99;
 await assert.rejects(c.request('/inventory/sku/adjust','POST',{expected_version:2,delta:2,reason:'restock'}),e=>e.code==='CLIENT_OPERATION_PENDING');await assert.rejects(c.request('/orders/order/shipments','POST',{expected_version:2,lines:[{order_line_id:'line',quantity:1}]}),e=>e.code==='CLIENT_OPERATION_PENDING');assert.equal(calls.length,1);
 // A newly mounted view observes the shared client, not the old form state.
 assert.deepEqual(c.getPending().body,{expected_version:1,delta:2,reason:'restock'});fail=false;await c.retryPending();assert.equal(calls[1].init.headers['Idempotency-Key'],originalKey);assert.equal(calls[1].init.body,calls[0].init.body);assert.equal(c.getPending(),null);await c.request('/inventory/sku/adjust','POST',{expected_version:3,delta:1,reason:'new intent'});assert.notEqual(calls[2].init.headers['Idempotency-Key'],originalKey)
})
test('late pending write cannot restore unresolved intent after account logout',async()=>{
 let reject;globalThis.fetch=()=>new Promise((_resolve,r)=>{reject=r});const c=new CommerceClient('http://local');const request=c.request('/orders/o/shipments','POST',{expected_version:1,lines:[{order_line_id:'line',quantity:1}]});assert.ok(c.getPending());c.dispose();reject(new TypeError('network'));await assert.rejects(request);assert.equal(c.getPending(),null)
})
test('partial shipment intent remains immutable while reads reconcile the latest order',async()=>{
 const calls=[];let fail=true;globalThis.fetch=async(url,init)=>{calls.push({url,init});if(init.method==='GET')return response({version:2,shipped_qty:1});if(fail)throw new TypeError('response lost');return response({id:'original-parcel'})};const c=new CommerceClient('http://local');await assert.rejects(c.request('/orders/o/shipments','POST',{expected_version:1,lines:[{order_line_id:'l',quantity:1}]}));const observed=c.getPending();assert.throws(()=>{observed.body.lines[0].quantity=2},TypeError);assert.equal((await c.request('/orders/o')).version,2);await assert.rejects(c.request('/orders/o/shipments','POST',{expected_version:2,lines:[{order_line_id:'l',quantity:1}]}),e=>e.code==='CLIENT_OPERATION_PENDING');assert.equal(c.getPending(),observed);fail=false;await c.retryPending();assert.equal(calls[2].init.body,calls[0].init.body);assert.equal(calls[2].init.headers['Idempotency-Key'],calls[0].init.headers['Idempotency-Key'])
})
test('pending subscription survives view unsubscription and blocks concurrent writes',async()=>{
 let complete;globalThis.fetch=()=>new Promise(resolve=>{complete=resolve});const c=new CommerceClient('http://local');let notifications=0;const unsub=c.subscribe(()=>notifications++);const first=c.request('/orders/o/shipments','POST',{expected_version:1});assert.equal(notifications,1);unsub();await assert.rejects(c.request('/orders/o/shipments','POST',{expected_version:1}),e=>e.code==='CLIENT_OPERATION_PENDING');assert.ok(c.getPending());complete(response({id:'parcel'}));await first;assert.equal(c.getPending(),null);assert.equal(notifications,1)
})
test('anonymous onboarding requests preserve their idempotency key on uncertain retry',async()=>{
 const calls=[];let fail=true;globalThis.fetch=async(_url,init)=>{calls.push(init);if(fail)throw new TypeError('lost receipt');return response({accepted:true,simulation:true},202)};
 const c=new CommerceClient('http://local');const body={username:'new.customer',email:'new@example.test',password:'a-long-password'};
 await assert.rejects(c.request('/auth/register','POST',body));assert.ok(c.getPending());assert.ok(calls[0].headers['Idempotency-Key']);
 await assert.rejects(c.request('/auth/password-reset/request','POST',{email:'new@example.test'}),e=>e.code==='CLIENT_OPERATION_PENDING');
 fail=false;await c.retryPending();assert.equal(calls[0].headers['Idempotency-Key'],calls[1].headers['Idempotency-Key']);assert.equal(calls[0].body,calls[1].body);assert.equal(c.getPending(),null);
})
test('login and logout do not become replayable business actions',async()=>{
 const calls=[];globalThis.fetch=async(_url,init)=>{calls.push(init);return response({})};const c=new CommerceClient('http://local');await c.request('/auth/login','POST',{});await c.request('/auth/logout','POST',{});assert.ok(calls.every(r=>!r.headers['Idempotency-Key']));assert.equal(c.getPending(),null);
})
test('closed mailbox delivery failure releases pending intent so a fresh verification request can recover',async()=>{
 const calls=[];globalThis.fetch=async(url,init)=>{calls.push({url,init});return url.endsWith('/auth/register')?response({error:{code:'MAILBOX_DELIVERY_FAILED',message:'本机模拟邮件投递失败'}},503):response({accepted:true,simulation:true},202)};
 const c=new CommerceClient('http://local');await assert.rejects(c.request('/auth/register','POST',{username:'new.customer',email:'new@example.test',password:'a-long-password'}),e=>e.code==='MAILBOX_DELIVERY_FAILED');
 assert.equal(c.getPending(),null);await c.request('/auth/verification-request','POST',{email:'new@example.test'});assert.equal(calls.length,2);assert.notEqual(calls[0].init.headers['Idempotency-Key'],calls[1].init.headers['Idempotency-Key']);
})
