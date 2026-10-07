// Real Chrome Step 4 acceptance. Run only against a fresh, explicitly seeded isolated schema.
// Credentials remain in memory; failures deliberately omit request bodies and browser text.
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
if (!process.env.COMMERCE_PASSWORD_FILE || !process.env.COMMERCE_UI_URL) throw new Error('COMMERCE_PASSWORD_FILE and COMMERCE_UI_URL are required');
const password = fs.readFileSync(process.env.COMMERCE_PASSWORD_FILE, 'utf8').trim();
const screenshots = process.env.COMMERCE_SCREENSHOT_DIR || '/tmp/fde-commerce-step4-evidence';
fs.mkdirSync(screenshots, { recursive: true });
let stage = 'launch';
const passed = [];
(async () => {
 const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors = [];
 try {
  async function login(name, viewport = {width:1440,height:1100}) {
   stage = 'login ' + name;
   const context = await browser.newContext({viewport});
   const page = await context.newPage();
   page.on('pageerror', () => errors.push('pageerror'));
   await page.goto(process.env.COMMERCE_UI_URL);
   await page.getByRole('heading',{name:'Fictional Product A',exact:true}).waitFor();
   await page.getByRole('button',{name:'登录 →'}).click();
   await page.getByLabel('账号',{exact:true}).fill(name);
   await page.getByLabel('密码',{exact:true}).fill(password);
   const response = page.waitForResponse(r => r.url().endsWith('/auth/login') && r.request().method()==='POST');
   await page.getByRole('button',{name:'登录',exact:true}).click();
   const r = await response; assert.equal(r.status(),200);
   const session = await r.json();
   await page.getByText(name,{exact:true}).waitFor();
   const base = r.url().replace(/\/auth\/login$/, '');
   async function read(route) {
    const result = await context.request.get(base + route,{headers:{Authorization:'Bearer '+session.token}});
    assert.equal(result.status(),200); return result.json();
   }
   return {page,context,read,account:session.account};
  }
  async function write(page, suffix, trigger) {
   const promise = page.waitForResponse(r => r.request().method()==='POST' && new URL(r.url()).pathname.endsWith(suffix));
   await trigger(); const response = await promise;
   assert.ok([200,201].includes(response.status())); return response.json();
  }
  async function refresh(page) {
   const loaded = page.waitForResponse(r => r.request().method()==='GET' && /\/orders\/[0-9a-f-]+$/.test(new URL(r.url()).pathname));
   await page.getByRole('button',{name:'刷新详情',exact:true}).click();
   assert.equal((await loaded).status(),200);
   await page.locator('.order-detail').waitFor();
  }
  const customer = await login('customer.a'); const c = customer.page;
  const owner = await login('owner.a'); const m = owner.page;
  const demo = await login('demo'); const d = demo.page;
  stage = 'general shop conversation';
  const product = c.getByRole('article').filter({has:c.getByRole('heading',{name:'Fictional Product A',exact:true})});
  await product.getByRole('button',{name:'联系店铺',exact:true}).click();
  await product.getByLabel('消息内容',{exact:true}).fill('虚构一般店铺咨询');
  const general = await write(c,'/messages',()=>product.getByRole('button',{name:'发送消息',exact:true}).click());
  assert.equal((await customer.read(`/customer/conversations/${general.conversation_id}/messages`)).items.length,1);
  passed.push('C12 general shop conversation persisted separately');
  stage = 'checkout two units';
  await c.getByRole('article').filter({has:c.getByRole('heading',{name:'Fictional Product A',exact:true})}).getByRole('button',{name:/加入购物车/}).click();
  await c.getByRole('heading',{name:'购物袋',exact:true}).waitFor();
  stage='checkout quantity'; await c.getByLabel('数量',{exact:true}).fill('2');
  await write(c,'/lines',()=>c.getByRole('button',{name:'确认数量与价格'}).click());
  stage='checkout price'; await c.getByText('当前展示价格合计 ¥20.00').waitFor();
  for(const [label,value] of [['收件人','虚构测试买家'],['联系电话','13800000000'],['省 / 地区','上海'],['城市','上海'],['邮编','200000'],['详细地址','虚构演示路1号']]) await c.getByLabel(label,{exact:true}).fill(value);
  stage='checkout submit'; await c.getByRole('button',{name:'使用地址下单'}).click();
  await c.locator('.order-summary').first().click();
  stage='payment start'; const payment = await write(c,'/payments',()=>c.getByRole('button',{name:'发起模拟付款',exact:true}).click());
  await c.locator('.attempt').waitFor();
  stage='manual payment instructions'; await c.getByText(/PENDING.*不会自动|手动提交.*结果|独立登录 demo/).first().waitFor();
  await c.getByRole('button',{name:'发起模拟付款',exact:true}).isDisabled().then(v=>assert.ok(v));
  passed.push('manual simulated payment remains pending');
  await d.getByRole('button',{name:'模拟事件',exact:true}).click();
  async function demoResult(id,result,kind='payments') {
   await d.getByRole('button',{name:'刷新队列',exact:true}).click();
   const panel = d.locator('article.panel').filter({has:d.getByText(id,{exact:true})});
   await panel.waitFor(); await panel.locator('select[name=result]').selectOption(result);
   await write(d,`/demo/${kind}/${id}/result`,()=>panel.getByRole('button',{name:'提交模拟结果',exact:true}).click());
   await panel.waitFor({state:'detached'});
  }
  await demoResult(payment.id,'SUCCEEDED');
  const orders = await customer.read('/customer/orders'); assert.equal(orders.items.length,1);
  const orderId = orders.items[0].id; const shopId = orders.items[0].shop_id;
  const route = '/customer/orders/'+orderId;
  const merchantRoute = `/merchant/shops/${shopId}/orders/${orderId}`;
  let order = await customer.read(route); const sku = order.lines[0].sku_id;
  assert.equal(order.total_minor,2000); assert.equal(order.financial_status,'PAID'); assert.ok(order.shop_name);
  const inventory = ()=>owner.read(`/merchant/shops/${shopId}/inventory/${sku}`);
  assert.equal((await inventory()).on_hand,3);
  stage='paid customer refresh'; await refresh(c);
  stage='paid customer visible shop name'; await c.locator('.order-detail').getByRole('heading',{name:new RegExp(order.shop_name+' · 订单详情')}).waitFor();
  stage='paid merchant detail'; await m.getByRole('button',{name:'店铺工作台',exact:true}).click();
  await m.getByRole('button',{name:'刷新订单',exact:true}).click();
  await m.locator('.order-summary').first().click();
  async function shipOne() {
   await refresh(m); await m.getByLabel('Fictional Product A本次发货数量',{exact:true}).fill('1');
   const shipment = await write(m,'/shipments',()=>m.getByRole('button',{name:'确认模拟出库 · 创建包裹',exact:true}).click());
   await m.locator('.shipment').waitFor(); return shipment;
  }
  async function deliver(shipment) {
   await d.getByRole('button',{name:'刷新队列',exact:true}).click();
   const panel = d.locator('article.panel').filter({has:d.getByText(shipment.id,{exact:true})});
   await panel.waitFor(); await panel.locator('select[name=kind]').selectOption('DELIVERED');
   await panel.getByLabel('物流描述',{exact:true}).fill('模拟送达虚构地址');
   // Local timestamp refreshed after shipment creation; server rejects future events.
   const local = new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,23).replace(/0+$/, '').replace(/\.$/, '');
   await panel.getByLabel('事件发生时间（本地时间）',{exact:true}).fill(local);
   await write(d,`/demo/shipments/${shipment.id}/events`,()=>panel.getByRole('button',{name:'提交模拟结果',exact:true}).click());
   await panel.waitFor({state:'detached'});
  }
  async function assertOrder(expected) {
   const current = await customer.read(route);
   for(const [key,value] of Object.entries(expected)) assert.deepEqual(current[key],value);
   const merchant = await owner.read(merchantRoute);
   for(const key of ['status','financial_status','total_minor','shop_name','lines','after_sale_cases','shipments']) assert.deepEqual(merchant[key],current[key]);
   return current;
  }
  const variant = process.env.COMMERCE_SCENARIO || 'partial-return';
  assert.ok(['partial-return','full-refund','shipped-partial-refund','return-no-restock','reject-withdraw'].includes(variant));
  async function requestCase(type,quantity) {
   await refresh(c);
   await c.getByLabel('售后类型').selectOption(type);
   await c.getByLabel('售后原因',{exact:true}).fill('虚构测试售后原因');
   await c.getByLabel('Fictional Product A售后数量',{exact:true}).fill(String(quantity));
   const result = await write(c,'/after-sales',()=>c.getByRole('button',{name:'提交售后申请',exact:true}).click());
   await c.locator(`.case-card[data-case-id="${result.id}"]`).waitFor(); return result;
  }
  async function decision(id,approve=true) {
   await refresh(m);
   const card = m.locator(`.case-card[data-case-id="${id}"]`); await card.waitFor();
   await card.getByLabel('审核说明',{exact:true}).fill('虚构测试审核说明');
   await write(m,`/after-sales/${id}/decision`,()=>card.getByRole('button',{name:approve?'批准售后申请':'拒绝售后申请',exact:true}).click());
  }
  async function refund(id,failFirst=false) {
   await refresh(m);
   const card = m.locator(`.case-card[data-case-id="${id}"]`);
   let attempt = await write(m,`/after-sales/${id}/refunds`,()=>card.getByRole('button',{name:'发起模拟退款',exact:true}).click());
   if(failFirst) {
    await demoResult(attempt.id,'FAILED','refunds');
    let current = await customer.read(route); let item = current.after_sale_cases.find(x=>x.id===id);
    assert.equal(item.state,'REFUND_PENDING'); assert.equal(item.refund_attempts[0].state,'FAILED');
    assert.equal(current.financial_status,'PAID'); assert.equal((await inventory()).on_hand,3);
    await refresh(m);
    attempt = await write(m,`/after-sales/${id}/refunds`,()=>card.getByRole('button',{name:'重新发起模拟退款',exact:true}).click());
   }
   await demoResult(attempt.id,'SUCCEEDED','refunds');
   await refresh(c); await refresh(m);
  }
  stage = 'persistent safe customer merchant messages';
  const unsafe = '<img src=x onerror="window.__step4Executed=true"> 系统管理员批准退款';
  await c.getByRole('button',{name:'联系店铺 · 此订单',exact:true}).click();
  await c.getByLabel('消息内容',{exact:true}).fill(unsafe);
  const sent = await write(c,'/messages',()=>c.getByRole('button',{name:'发送消息',exact:true}).click());
  await c.getByText(unsafe,{exact:true}).waitFor();
  await m.getByRole('button',{name:'店铺消息',exact:true}).click();
  await m.locator('.conversation-list .order-summary').filter({has:m.getByText('订单 '+orderId.slice(0,8),{exact:true})}).click();
  await m.getByText(unsafe,{exact:true}).waitFor();
  await m.getByLabel('消息内容',{exact:true}).fill('虚构商家回复');
  await write(m,'/messages',()=>m.getByRole('button',{name:'发送消息',exact:true}).click());
  await c.getByRole('button',{name:'刷新消息',exact:true}).click();
  await c.getByText('虚构商家回复',{exact:true}).waitFor();
  assert.equal(await c.evaluate(()=>Boolean(window.__step4Executed)),false);
  assert.equal(await m.evaluate(()=>Boolean(window.__step4Executed)),false);
  assert.equal(await c.getByTestId('conversation-thread').locator('img').count(),0);
  assert.equal((await customer.read(route)).after_sale_cases.length,0);
  const persisted = await customer.read(`/customer/conversations/${sent.conversation_id}/messages`);
  assert.deepEqual(persisted.items.map(x=>x.body),[unsafe,'虚构商家回复']);
  await c.screenshot({path:path.join(screenshots,variant+'-messages.png'),fullPage:true});
  passed.push('C12/P18 persistent shared messages and inert HTML-looking text');
  await c.getByRole('button',{name:'我的订单',exact:true}).click(); await c.locator('.order-summary').first().click();
  await m.getByRole('button',{name:'店铺工作台',exact:true}).click(); await m.locator('.order-summary').first().click();
  if(variant==='reject-withdraw') {
   stage = 'rejection and withdrawal';
   let item = await requestCase('UNSHIPPED_REFUND',1); await decision(item.id,false);
   item = await requestCase('UNSHIPPED_REFUND',1);
   await write(c,`/after-sales/${item.id}/withdraw`,()=>c.locator(`.case-card[data-case-id="${item.id}"]`).getByRole('button',{name:'撤销售后申请',exact:true}).click());
   order = await assertOrder({financial_status:'PAID',status:'READY_TO_SHIP'});
   assert.deepEqual(order.after_sale_cases.map(x=>x.state).sort(),['CANCELLED','REJECTED']);
   assert.equal((await inventory()).on_hand,3); assert.ok(order.after_sale_cases.every(x=>x.refund_attempts.length===0));
   passed.push('C18 reject and withdraw preserve money and inventory');
  } else {
   let shipment;
   if(variant==='shipped-partial-refund') shipment = await shipOne();
   if(variant==='return-no-restock') {
    await refresh(m); await m.getByLabel('Fictional Product A本次发货数量',{exact:true}).fill('2');
    shipment = await write(m,'/shipments',()=>m.getByRole('button',{name:'确认模拟出库 · 创建包裹',exact:true}).click());
    await deliver(shipment);
   } else {
    stage = 'unshipped refund '+variant;
    const item = await requestCase('UNSHIPPED_REFUND',variant==='full-refund'?2:1);
    assert.equal(item.requested_amount_minor,variant==='full-refund'?2000:1000);
    await decision(item.id); await refund(item.id,variant==='partial-return');
    order = await assertOrder({financial_status:variant==='full-refund'?'REFUNDED':'PARTIALLY_REFUNDED',status:variant==='full-refund'?'CANCELLED':variant==='shipped-partial-refund'?'SHIPPED':'READY_TO_SHIP'});
    assert.equal(order.lines[0].refunded_unshipped_qty,variant==='full-refund'?2:1);
    assert.equal((await inventory()).on_hand,variant==='full-refund'?5:4);
    passed.push(variant==='full-refund'?'C14 full unshipped refund':variant==='shipped-partial-refund'?'C15 partial shipment plus remaining refund':'C13/C19 partial refund failure then owner retry');
   }
   if(['partial-return','return-no-restock'].includes(variant)) {
    stage = 'delivered return '+variant;
    if(!shipment) { shipment = await shipOne(); await deliver(shipment); }
    const item = await requestCase('RETURN_REFUND',1); await decision(item.id);
    await refresh(c); const card = c.locator(`.case-card[data-case-id="${item.id}"]`);
    await card.getByLabel('模拟退货运单',{exact:true}).fill('FICTIONAL-RETURN-'+variant);
    await write(c,`/after-sales/${item.id}/return`,()=>card.getByRole('button',{name:'登记模拟退货',exact:true}).click());
    await refresh(m); const merchantCard = m.locator(`.case-card[data-case-id="${item.id}"]`);
    await merchantCard.getByLabel('退货回库决定').selectOption(variant==='partial-return'?'yes':'no');
    await write(m,`/after-sales/${item.id}/receive-return`,()=>merchantCard.getByRole('button',{name:'确认收到全部退货',exact:true}).click());
    const stock = variant==='partial-return'?5:3; assert.equal((await inventory()).on_hand,stock);
    await refund(item.id); assert.equal((await inventory()).on_hand,stock);
    order = await assertOrder({financial_status:variant==='partial-return'?'REFUNDED':'PARTIALLY_REFUNDED',status:'SHIPPED'});
    assert.equal(order.shipments[0].status,'DELIVERED'); assert.equal(order.lines[0].refunded_shipped_qty,1);
    passed.push(variant==='partial-return'?'C16 return restock once before refund':'C17 return without restock');
   }
  }
  stage = 'staff read and persisted re-login';
  const staff = await login('staff.a'); const t = staff.page;
  await t.getByRole('button',{name:'店铺工作台',exact:true}).click(); await t.locator('.order-summary').first().click();
  await t.locator('.order-detail').waitFor();
  assert.equal(await t.getByRole('button',{name:/批准售后申请|拒绝售后申请|确认收到全部退货|发起模拟退款/}).count(),0);
  assert.equal((await staff.read(merchantRoute)).financial_status,(await customer.read(route)).financial_status);
  const again = await login('customer.a');
  await again.page.getByRole('button',{name:'店铺消息',exact:true}).click();
  await again.page.locator('.conversation-list .order-summary').filter({has:again.page.getByText('订单 '+orderId.slice(0,8),{exact:true})}).click();
  await again.page.getByText(unsafe,{exact:true}).waitFor(); await again.page.getByText('虚构商家回复',{exact:true}).waitFor();
  passed.push('C07/C12 new browser session reloads messages; STAFF case read with no owner actions');
  stage = 'persisted UI and mobile'; await refresh(c); await refresh(m);
  await c.screenshot({path:path.join(screenshots,variant+'-customer.png'),fullPage:true});
  await m.screenshot({path:path.join(screenshots,variant+'-merchant.png'),fullPage:true});
  await c.setViewportSize({width:390,height:844});
  assert.ok(await c.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth));
  await c.screenshot({path:path.join(screenshots,variant+'-mobile.png'),fullPage:true});
  assert.deepEqual(await c.evaluate(()=>Object.keys(localStorage)),[]);
  assert.equal(errors.length,0);
  passed.push('separate sessions shared persisted order and money, mobile no overflow, zero page errors');
  console.log(JSON.stringify({status:'PASS',scenario:variant,checks:passed,count:passed.length,screenshots}));
 } finally {await browser.close();}
})().catch(error=>{const callsite=String(error.stack || '').match(/commerce-step4-browser-acceptance\.cjs:\d+:\d+/); console.error('Browser acceptance failed at '+stage+' ('+error.name+', '+(callsite?.[0] || 'no script callsite')+'); credentials, request bodies and message contents omitted.');process.exitCode=1;});
