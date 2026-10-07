import {test, afterEach} from 'node:test';
import assert from 'node:assert/strict';
import {CommerceClient} from '../.test-output/client.js';
const originalFetch = globalThis.fetch;
afterEach(() => {globalThis.fetch = originalFetch;});
test('merchant generation submits only empty server-snapshot request and never sends reply', async () => {
    const calls=[];
    globalThis.fetch = async (url, init) => {
        calls.push({url,init});
        return new Response(JSON.stringify({available:true, latest_success:{result:{draft:'可为您进一步确认'}},latest_attempt:null,stale:false}), {status:200});
    };
    const client=new CommerceClient('http://local','merchant-session');
    const path='/merchant/shops/shop/conversations/conversation/ai-assistance';
    await client.request(path);
    const result=await client.request(path,'POST',{});
    let editableText = result.latest_success.result.draft;
    editableText += '，请告诉我们规格。';
    assert.equal(calls.length,2);
    assert.equal(calls[1].init.body,'{}');
    assert.ok(calls[1].init.headers['Idempotency-Key']);
    assert.equal(calls[1].init.headers.Authorization,'Bearer merchant-session');
    assert.ok(calls.every(c => !c.url.endsWith('/messages')));
    await client.request('/merchant/shops/shop/conversations/conversation/messages','POST',{body:editableText});
    assert.equal(JSON.parse(calls[2].init.body).body,'可为您进一步确认，请告诉我们规格。');
});
test('uncertain AI request retries original key without attaching edited conversation text', async () => {
    const calls=[];
    globalThis.fetch=async(url,init)=>{calls.push({url,init});if(calls.length===1)throw new TypeError('network');return new Response('{}',{status:200});};
    const client=new CommerceClient('http://local');
    await assert.rejects(client.request('/merchant/shops/s/conversations/c/ai-assistance','POST',{}));
    await client.retryPending();
    assert.equal(calls[0].init.headers['Idempotency-Key'],calls[1].init.headers['Idempotency-Key']);
    assert.equal(calls[1].init.body,'{}');
});
