// Real Chrome acceptance; use only a fresh, explicitly seeded isolated schema.
// All business writes use UI. Authenticated GETs inspect persisted invariants.
const fs = require('fs');
const path = require('path');
const assert = require('assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
if (!process.env.COMMERCE_PASSWORD_FILE || !process.env.COMMERCE_UI_URL) throw new Error('COMMERCE_PASSWORD_FILE and COMMERCE_UI_URL are required');
const password = fs.readFileSync(process.env.COMMERCE_PASSWORD_FILE, 'utf8').trim();
const screenshots = process.env.COMMERCE_SCREENSHOT_DIR || '/tmp/fde-commerce-step5-evidence';
fs.mkdirSync(screenshots, { recursive: true });
let stage = 'launch';
const passed = [];
(async () => {
 const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const errors = [];
 try {
  async function login(name) {
   const context = await browser.newContext({viewport:{width:1440,height:1100}});
   const page = await context.newPage(); page.on('pageerror',()=>errors.push('pageerror'));
   await page.goto(process.env.COMMERCE_UI_URL);
   await page.getByRole('heading',{name:'Fictional Product A',exact:true}).waitFor();
   await page.getByRole('button',{name:'登录 →'}).click();
   await page.getByLabel('账号',{exact:true}).fill(name); await page.getByLabel('密码',{exact:true}).fill(password);
   const pending = page.waitForResponse(r=>r.url().endsWith('/auth/login') && r.request().method()==='POST');
   await page.getByRole('button',{name:'登录',exact:true}).click();
   const response = await pending; assert.equal(response.status(),200);
   const session = await response.json(); await page.getByText(name,{exact:true}).waitFor();
   const base = response.url().replace(/\/auth\/login$/, '');
   async function read(route) { const r=await context.request.get(base+route,{headers:{Authorization:'Bearer '+session.token}}); assert.equal(r.status(),200); return r.json(); }
   return {page,context,read};
  }
  async function write(page,suffix,trigger,status=200) {
   const pending=page.waitForResponse(r=>r.request().method()==='POST' && new URL(r.url()).pathname.endsWith(suffix));
   await trigger(); const response=await pending;
   if(status===200) assert.ok([200,201].includes(response.status())); else assert.equal(response.status(),status);
   return response.json();
  }
  async function refresh(page) {
   const pending=page.waitForResponse(r=>r.request().method()==='GET' && /\/orders\/[0-9a-f-]+$/.test(new URL(r.url()).pathname));
   await page.getByRole('button',{name:'刷新详情',exact:true}).click(); assert.equal((await pending).status(),200);
  }
  const customer=await login('customer.a'), owner=await login('owner.a'), demo=await login('demo');
  const c=customer.page,m=owner.page,d=demo.page;
  stage='price conflict';
  assert.equal((await customer.read('/customer/orders')).items.length,0);
  stage='price conflict add cart';
  await write(c,'/lines',()=>c.getByRole('article').filter({has:c.getByRole('heading',{name:'Fictional Product A',exact:true})}).getByRole('button',{name:/加入购物车/}).click());
  await c.getByRole('heading',{name:'购物袋',exact:true}).waitFor();
  const oldCart=await customer.read('/customer/cart'); assert.equal(oldCart.lines[0].seen_price_minor,1000);
  await m.getByRole('button',{name:'店铺工作台',exact:true}).click();
  await m.getByRole('button',{name:'商品与库存',exact:true}).click();
  await m.locator('.order-summary').filter({has:m.getByText('Fictional Product A',{exact:true})}).click();
  await m.getByLabel('价格（分）',{exact:true}).fill('1200');
  stage='price conflict merchant price POST';
  await write(m,'/edit',()=>m.getByRole('button',{name:'保存款式',exact:true}).click());
  async function fillAddress() {
   for(const [label,value] of [['收件人','虚构验收买家'],['联系电话','13800000000'],['省 / 地区','上海'],['城市','上海'],['邮编','200000'],['详细地址','虚构验收路1号']]) await c.getByLabel(label,{exact:true}).fill(value);
  }
  await fillAddress();
  stage='price conflict rejected checkout';
  const conflict=await write(c,'/checkouts',()=>c.getByRole('button',{name:'使用地址下单',exact:true}).click(),409);
  assert.equal(conflict.error.code,'PRICE_CHANGED');
  assert.equal((await customer.read('/customer/orders')).items.length,0);
  let cart=await customer.read('/customer/cart'); assert.equal(cart.lines[0].seen_price_minor,1000); assert.equal(cart.lines[0].current_price_minor,1200);
  await c.getByRole('button',{name:'刷新购物袋',exact:true}).click();
  await c.getByText(/价格已由 ¥10.00 变为 ¥12.00/).waitFor();
  assert.equal(await c.getByLabel('收件人',{exact:true}).inputValue(),'虚构验收买家');
  assert.equal(await c.getByLabel('详细地址',{exact:true}).inputValue(),'虚构验收路1号');
  stage='price conflict explicit price acceptance';
  await write(c,'/lines',()=>c.getByRole('button',{name:'确认数量与价格',exact:true}).click());
  cart=await customer.read('/customer/cart'); assert.equal(cart.lines[0].seen_price_version,cart.lines[0].current_price_version);
  stage='price conflict preserved address draft';
  assert.equal(await c.getByLabel('收件人',{exact:true}).inputValue(),'虚构验收买家');
  assert.equal(await c.getByLabel('详细地址',{exact:true}).inputValue(),'虚构验收路1号');
  stage='price conflict recovered checkout';
  await write(c,'/checkouts',()=>c.getByRole('button',{name:'使用地址下单',exact:true}).click());
  await c.locator('.order-summary').first().click(); await c.locator('.order-detail').waitFor();
  const orders=await customer.read('/customer/orders'); assert.equal(orders.items.length,1);
  const id=orders.items[0].id,shop=orders.items[0].shop_id,route='/customer/orders/'+id;
  let order=await customer.read(route); assert.equal(order.total_minor,1200); assert.equal(order.lines[0].unit_price_minor,1200);
  const inventory=()=>owner.read(`/merchant/shops/${shop}/inventory/${order.lines[0].sku_id}`);
  assert.equal((await inventory()).reserved,1);
  passed.push('S5-B01 PRICE_CHANGED creates no order; address draft survives refresh/confirmation; explicit price confirmation creates one order at 1200 minor units');
  stage='order snapshot survives new catalog price';
  await m.getByLabel('价格（分）',{exact:true}).fill('1300');
  await write(m,'/edit',()=>m.getByRole('button',{name:'保存款式',exact:true}).click());
  const catalog=await customer.read('/catalog/products?limit=100');
  const currentProduct=catalog.items.find(p=>p.title==='Fictional Product A');
  assert.equal(currentProduct.skus.find(s=>s.id===order.lines[0].sku_id).unit_price_minor,1300);
  await refresh(c); order=await customer.read(route);
  assert.equal(order.total_minor,1200); assert.equal(order.lines[0].unit_price_minor,1200);
  await c.locator('.order-detail').getByRole('cell',{name:'¥12.00',exact:true}).waitFor();
  passed.push('C06/S5-B05 merchant catalog repricing to 1300 preserves existing order snapshot at 1200');
  await d.getByRole('button',{name:'模拟事件',exact:true}).click();
  async function refreshQueue() {
   const pending=d.waitForResponse(r=>r.request().method()==='GET' && new URL(r.url()).pathname.endsWith('/demo/pending'));
   await d.getByRole('button',{name:'刷新队列',exact:true}).click(); assert.equal((await pending).status(),200);
   await d.getByText('正在读取待处理事件…',{exact:true}).waitFor({state:'hidden'});
  }
  async function paymentResult(attempt,result) {
   await refreshQueue();
   const panel=d.locator(`article[data-demo-id="${attempt.id}"]`); await panel.waitFor();
   await panel.locator('select[name=result]').selectOption(result);
   await write(d,`/demo/payments/${attempt.id}/result`,()=>panel.getByRole('button',{name:'提交模拟结果',exact:true}).click());
   await panel.waitFor({state:'detached'});
  }
  stage='failed payment and retry';
  const first=await write(c,'/payments',()=>c.getByRole('button',{name:'发起模拟付款',exact:true}).click());
  await paymentResult(first,'FAILED'); await refresh(c);
  order=await customer.read(route); assert.equal(order.status,'PENDING_PAYMENT'); assert.equal(order.financial_status,'UNPAID'); assert.equal((await inventory()).reserved,1);
  const second=await write(c,'/payments',()=>c.getByRole('button',{name:'发起模拟付款',exact:true}).click());
  assert.notEqual(second.id,first.id); await paymentResult(second,'SUCCEEDED'); await refresh(c);
  order=await customer.read(route); assert.equal(order.status,'READY_TO_SHIP'); assert.equal(order.financial_status,'PAID');
  await c.locator('.order-list .status-READY_TO_SHIP').waitFor({timeout:5000});
  assert.deepEqual(order.payment_attempts.map(a=>a.state).sort(),['FAILED','SUCCEEDED']);
  assert.equal((await inventory()).on_hand,4); assert.equal((await inventory()).reserved,0);
  passed.push('S5-B02 FAILED keeps unpaid order/reservation; new payment succeeds once with two distinct attempts');
  stage='shipment exception recovery';
  await m.getByRole('button',{name:'店铺工作台',exact:true}).click();
  await m.getByRole('button',{name:'刷新订单',exact:true}).click(); await m.locator('.order-summary').first().click();
  await m.getByLabel('Fictional Product A本次发货数量',{exact:true}).fill('1');
  const shipment=await write(m,'/shipments',()=>m.getByRole('button',{name:'确认模拟出库 · 创建包裹',exact:true}).click());
  await d.getByRole('button',{name:'刷新包裹',exact:true}).click();
  await d.locator(`[data-shipment-id="${shipment.id}"]`).click();
  async function shipmentEvent(kind,action) {
   const panel=d.locator(`article[data-demo-id="${shipment.id}"]`);
   await panel.getByRole('button',{name:action,exact:true}).waitFor();
   await panel.getByLabel('物流描述',{exact:true}).fill('虚构模拟物流 '+kind);
   await write(d,`/demo/shipments/${shipment.id}/events`,()=>panel.getByRole('button',{name:action,exact:true}).click());
   await refresh(c);
   order=await customer.read(route); assert.equal(order.shipments[0].status,kind);
  }
  await shipmentEvent('COLLECTED','模拟揽收');
  await shipmentEvent('IN_TRANSIT','开始运输');
  await shipmentEvent('EXCEPTION','运输延误');
  assert.equal(await c.getByRole('button',{name:'所有包裹已送达 · 确认收货',exact:true}).count(),0);
  await c.locator('.shipment .status-EXCEPTION').waitFor();
  await c.screenshot({path:path.join(screenshots,'step5-exception.png'),fullPage:true});
  await shipmentEvent('IN_TRANSIT','恢复物流');
  assert.equal(await c.getByRole('button',{name:'所有包裹已送达 · 确认收货',exact:true}).count(),0);
  await shipmentEvent('OUT_FOR_DELIVERY','开始派送');
  await shipmentEvent('DELIVERED','模拟签收');
  assert.deepEqual(order.shipments[0].events.slice(-4).map(e=>e.kind),['EXCEPTION','IN_TRANSIT','OUT_FOR_DELIVERY','DELIVERED']);
  await write(c,'/confirm-receipt',()=>c.getByRole('button',{name:'所有包裹已送达 · 确认收货',exact:true}).click());
  passed.push('S5-B03 EXCEPTION and IN_TRANSIT hide receipt; DELIVERED enables explicit completion with persisted event history');
  stage='fresh login persistence';
  const again=await login('customer.a'); await again.page.getByRole('button',{name:'我的订单',exact:true}).click(); await again.page.locator('.order-summary').first().click();
  await again.page.locator('.order-detail .status-COMPLETED').waitFor();
  await refresh(m); order=await again.read(route);
  assert.equal(order.status,'COMPLETED'); assert.equal(order.financial_status,'PAID'); assert.equal(order.total_minor,1200);
  const merchant=await owner.read(`/merchant/shops/${shop}/orders/${id}`);
  for(const key of ['status','financial_status','total_minor','lines','shipments','payment_attempts']) assert.deepEqual(merchant[key],order[key]);
  assert.equal((await inventory()).on_hand,4); assert.equal((await inventory()).reserved,0);
  assert.equal((await again.read('/customer/orders')).items.length,1);
  await again.page.screenshot({path:path.join(screenshots,'step5-completed.png'),fullPage:true});
  for(const page of [c,m,d,again.page]) assert.deepEqual(await page.evaluate(()=>Object.keys(localStorage)),[]);
  assert.equal(errors.length,0);
  passed.push('S5-B04 fresh login and merchant refresh agree on completed order; inventory stable; no persisted tokens or page errors');
  console.log(JSON.stringify({status:'PASS',checks:passed,count:passed.length,screenshots}));
 } finally {await browser.close();}
})().catch(error=>{const site=String(error.stack||'').match(/commerce-step5-browser-acceptance\.cjs:\d+:\d+/);console.error('Browser acceptance failed at '+stage+' ('+error.name+', '+(site?.[0]||'no script callsite')+'); credentials and payloads omitted.');process.exitCode=1;});
