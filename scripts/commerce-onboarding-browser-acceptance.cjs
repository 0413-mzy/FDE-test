// Fresh-schema Chrome acceptance. Business writes use UI; private reads use scoped GET.
// Simulated credentials are read by the local operator, never exposed by HTTP/logs.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const assert = require('assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
for (const key of ['COMMERCE_PASSWORD_FILE', 'COMMERCE_UI_URL', 'COMMERCE_MAILBOX_DIR']) {
 if (!process.env[key]) throw new Error(key + ' is required');
}
const password = fs.readFileSync(process.env.COMMERCE_PASSWORD_FILE, 'utf8').trim();
const mailbox = process.env.COMMERCE_MAILBOX_DIR;
const screenshots = process.env.COMMERCE_SCREENSHOT_DIR || '/tmp/fde-commerce-onboarding-evidence';
fs.mkdirSync(screenshots, { recursive: true });
const suffix = crypto.randomBytes(8).toString('hex');
const username = 'onboard.' + suffix, email = username + '@example.test';
const newPassword = crypto.randomBytes(32).toString('base64url');
const resetPassword = crypto.randomBytes(32).toString('base64url');
let stage = 'launch';
const passed = [], errors = [];

(async () => {
 const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_EXECUTABLE || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
 try {
  async function surface() {
   const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
   const page = await context.newPage();
   page.on('pageerror', () => errors.push('pageerror'));
   await page.goto(process.env.COMMERCE_UI_URL);
   await page.getByRole('heading', { name: 'Fictional Product A', exact: true }).waitFor();
   return { page, context };
  }
  async function write(page, route, trigger, status = 200) {
   const pending = page.waitForResponse(r => r.request().method() === 'POST' && new URL(r.url()).pathname.endsWith(route));
   await trigger();
   const response = await pending;
   assert.equal(response.status(), status);
   return response.json();
  }
  async function login(name, secret = password) {
   const s = await surface(), p = s.page;
   await p.getByRole('button', { name: '登录 →', exact: true }).click();
   await p.getByLabel('账号', { exact: true }).fill(name);
   await p.getByLabel('密码', { exact: true }).fill(secret);
   const pending = p.waitForResponse(r => r.request().method() === 'POST' && r.url().endsWith('/auth/login'));
   await p.getByRole('button', { name: '登录', exact: true }).click();
   const response = await pending;
   assert.equal(response.status(), 200);
   const session = await response.json(), base = response.url().replace(/\/auth\/login$/, '');
   await p.getByText(name, { exact: true }).waitFor();
   s.read = async route => {
    const r = await s.context.request.get(base + route, { headers: { Authorization: 'Bearer ' + session.token } });
    assert.equal(r.status(), 200);
    return r.json();
   };
   s.stale = async () => (await s.context.request.get(base + '/auth/me', { headers: { Authorization: 'Bearer ' + session.token } })).status();
   return s;
  }
  async function fillAddress(p, line) {
   for (const [label, value] of [['收件人', '虚构入驻买家'], ['联系电话', '13800000000'], ['省 / 地区', '上海'], ['城市', '上海'], ['邮编', '200000'], ['详细地址', line]]) await p.getByLabel(label, { exact: true }).fill(value);
  }
  function mailCode(purpose) {
   assert.equal(fs.statSync(mailbox).mode & 0o077, 0);
   const letters = fs.readdirSync(mailbox).filter(n => n.endsWith('.json')).map(n => {
    const file = path.join(mailbox, n);
    assert.equal(fs.lstatSync(file).isSymbolicLink(), false);
    assert.equal(fs.statSync(file).mode & 0o077, 0);
    return JSON.parse(fs.readFileSync(file, 'utf8'));
   }).filter(l => l.email === email && l.purpose === purpose);
   assert.equal(letters.length, 1);
   assert.equal(letters[0].simulation, true);
   assert.equal(typeof letters[0].code, 'string');
   return letters[0].code;
  }
  stage = 'registration and protected simulated email';
  const anonymous = await surface(), a = anonymous.page;
  await a.getByRole('button', { name: '登录 →', exact: true }).click();
  await a.getByLabel('新账号', { exact: true }).fill(username);
  await a.getByLabel('邮箱', { exact: true }).fill(email);
  await a.getByLabel('新密码', { exact: true }).fill(newPassword);
  assert.deepEqual(await write(a, '/auth/register', () => a.getByRole('button', { name: '提交', exact: true }).click(), 202), { accepted: true, simulation: true });
  const code = mailCode('REGISTER');
  await a.getByRole('button', { name: '验证邮箱', exact: true }).click();
  await a.getByLabel('邮箱', { exact: true }).fill(email);
  await a.getByLabel('邮件验证码', { exact: true }).fill(code);
  assert.deepEqual(await write(a, '/auth/verify-email', () => a.getByRole('button', { name: '提交', exact: true }).click()), { verified: true });
  await a.getByLabel('邮件验证码', { exact: true }).fill('');
  passed.push('O-B01 anonymous registration returns only safe acknowledgement; privileged local 0700/0600 simulated mail verifies new customer');

  const customer = await login(username, newPassword), c = customer.page;
  stage = 'profile and default address';
  assert.equal((await customer.read('/auth/me')).customer_enabled, true);
  assert.equal((await customer.read('/auth/me')).shops.length, 0);
  await c.getByRole('button', { name: '我的账户', exact: true }).click();
  const profilePanel = c.locator('section').filter({ has: c.getByRole('heading', { name: '个人资料', exact: true }) }).first();
  await profilePanel.getByLabel('显示名称', { exact: true }).fill('虚构入驻店主');
  await profilePanel.getByLabel('联系电话', { exact: true }).fill('13800000000');
  await write(c, '/account/profile', () => c.getByRole('button', { name: '保存资料', exact: true }).click());
  assert.equal((await customer.read('/account/profile')).display_name, '虚构入驻店主');
  const addressForm = c.locator('.address-form');
  await fillAddress(addressForm, '虚构入驻路1号');
  const address = await write(c, '/customer/addresses', () => c.getByRole('button', { name: '添加地址', exact: true }).click(), 201);
  assert.equal(address.is_default, true);
  passed.push('O-B02 profile persists and first saved address becomes the sole default');

  stage = 'saved address checkout and snapshot isolation';
  await c.getByRole('button', { name: '选物集', exact: true }).click();
  await write(c, '/lines', () => c.getByRole('article').filter({ has: c.getByRole('heading', { name: 'Fictional Product A', exact: true }) }).getByRole('button', { name: /加入购物车/ }).click(), 201);
  await c.getByLabel('从地址簿预填').selectOption(address.id);
  assert.equal(await c.getByLabel('详细地址', { exact: true }).inputValue(), '虚构入驻路1号');
  await write(c, '/checkouts', () => c.getByRole('button', { name: '使用地址下单', exact: true }).click(), 201);
  const oldOrder = (await customer.read('/customer/orders')).items[0];
  const oldDetail = await customer.read('/customer/orders/' + oldOrder.id);
  await c.getByRole('button', { name: '我的账户', exact: true }).click();
  await c.getByRole('button', { name: '编辑地址', exact: true }).click();
  await c.locator('.address-form').getByLabel('详细地址', { exact: true }).fill('虚构入驻路2号');
  await write(c, `/customer/addresses/${address.id}/edit`, () => c.getByRole('button', { name: '保存地址', exact: true }).click());
  const edited = await customer.read('/customer/addresses');
  assert.equal(edited.items.filter(v => v.is_default).length, 1);
  assert.equal(edited.items[0].address.address_line, '虚构入驻路2号');
  const stable = await customer.read('/customer/orders/' + oldOrder.id);
  for (const key of ['address', 'lines', 'total_minor']) assert.deepEqual(stable[key], oldDetail[key]);
  passed.push('O-B03 address-book prefills checkout; editing saved default preserves existing order address, lines and money snapshots');

  stage = 'application and independent reviewer approval';
  const shopName = '虚构入驻店铺 ' + suffix;
  for (const [label, value] of [['店铺名称', shopName], ['经营范围', '虚构日用品'], ['联系人', '虚构店主'], ['联系手机', '13800000000'], ['店铺介绍', '仅本地验收的模拟商家']]) await c.getByLabel(label, { exact: true }).fill(value);
  const application = await write(c, '/customer/merchant-applications', () => c.getByRole('button', { name: '提交入驻申请', exact: true }).click(), 201);
  assert.equal(application.state, 'PENDING');
  const reviewer = await login('reviewer'), r = reviewer.page;
  await r.getByRole('button', { name: '入驻审核', exact: true }).click();
  const reviewCard = r.getByRole('article').filter({ has: r.getByRole('heading', { name: shopName + ' · 等待审核', exact: true }) });
  await reviewCard.getByLabel('审核决定').selectOption('APPROVE');
  await reviewCard.getByLabel('审核理由（拒绝时必填）', { exact: true }).fill('虚构验收批准');
  const approved = await write(r, `/review/merchant-applications/${application.id}/decision`, () => reviewCard.getByRole('button', { name: '提交审核决定', exact: true }).click());
  assert.equal(approved.state, 'APPROVED');
  const identity = c.waitForResponse(v => v.request().method() === 'GET' && v.url().endsWith('/auth/me'));
  await c.getByRole('button', { name: '刷新账户与店铺资格', exact: true }).click();
  assert.equal((await identity).status(), 200);
  await c.getByRole('button', { name: '店铺工作台', exact: true }).waitFor();
  const member = (await customer.read('/auth/me')).shops.find(v => v.shop_id === approved.shop_id);
  assert.equal(member.role, 'OWNER');
  passed.push('O-B04 independent reviewer approves application; explicit server identity refresh grants the new shop OWNER interface');

  stage = 'new owner publishes product and another customer buys';
  await c.getByRole('button', { name: '店铺工作台', exact: true }).click();
  await c.getByRole('button', { name: '商品与库存', exact: true }).click();
  await c.getByText('＋ 创建商品草稿', { exact: true }).click();
  const productTitle = '虚构入驻商品 ' + suffix;
  for (const [label, value] of [['商品名称', productTitle], ['SKU 编码', 'ONBOARD-' + suffix], ['款式', '虚构款'], ['单价（整数分）', '2300'], ['初始库存', '3'], ['商品描述', '虚构模拟商品']]) await c.getByLabel(label, { exact: true }).fill(value);
  const product = await write(c, `/merchant/shops/${approved.shop_id}/products`, () => c.getByRole('button', { name: '创建草稿', exact: true }).click(), 201);
  await write(c, `/products/${product.id}/publish`, () => c.getByRole('button', { name: '上架', exact: true }).click());
  const buyer = await login('customer.b'), b = buyer.page;
  await write(b, '/lines', () => b.getByRole('article').filter({ has: b.getByRole('heading', { name: productTitle, exact: true }) }).getByRole('button', { name: /加入购物车/ }).click(), 201);
  await fillAddress(b, '虚构第二买家路1号');
  await write(b, '/checkouts', () => b.getByRole('button', { name: '使用地址下单', exact: true }).click(), 201);
  const bought = (await buyer.read('/customer/orders')).items[0];
  const detail = await buyer.read('/customer/orders/' + bought.id);
  assert.equal(detail.shop_id, approved.shop_id);
  assert.equal(detail.total_minor, 2300);
  assert.equal(detail.lines[0].sku_id, product.skus[0].id);
  const stock = await customer.read(`/merchant/shops/${approved.shop_id}/inventory/${product.skus[0].id}`);
  assert.equal(stock.on_hand, 3); assert.equal(stock.reserved, 1);
  await b.getByRole('button', { name: '我的订单', exact: true }).click();
  await b.locator('.order-summary').first().click();
  await b.locator('.order-detail').waitFor();
  await b.screenshot({ path: path.join(screenshots, 'onboarding-new-shop-purchase.png'), fullPage: true });
  passed.push('O-B05 approved owner creates and publishes a real product; independent customer buys it with exact price and one stock reservation');

  stage = 'password reset revokes old sessions';
  const recovery = await surface(), p = recovery.page;
  await p.getByRole('button', { name: '登录 →', exact: true }).click();
  await p.getByRole('button', { name: '忘记密码', exact: true }).click();
  await p.getByLabel('邮箱', { exact: true }).fill(email);
  assert.deepEqual(await write(p, '/auth/password-reset/request', () => p.getByRole('button', { name: '提交', exact: true }).click(), 202), { accepted: true, simulation: true });
  const resetCode = mailCode('RESET');
  await p.getByRole('button', { name: '重置密码', exact: true }).click();
  await p.getByLabel('邮箱', { exact: true }).fill(email);
  await p.getByLabel('邮件验证码', { exact: true }).fill(resetCode);
  await p.getByLabel('新密码', { exact: true }).fill(resetPassword);
  assert.deepEqual(await write(p, '/auth/password-reset/confirm', () => p.getByRole('button', { name: '提交', exact: true }).click()), { changed: true });
  assert.equal(await customer.stale(), 401);
  await p.getByLabel('账号', { exact: true }).fill(username);
  await p.getByLabel('密码', { exact: true }).fill(newPassword);
  await write(p, '/auth/login', () => p.getByRole('button', { name: '登录', exact: true }).click(), 401);
  const renewed = await login(username, resetPassword);
  assert.equal((await renewed.read('/auth/me')).shops[0].shop_id, approved.shop_id);
  passed.push('O-B06 UI reset revokes old authenticated session and old password; new password restores customer and merchant identity');
  stage = 'one-time reset credential rejects reuse';
  await p.getByLabel('新密码', { exact: true }).fill(crypto.randomBytes(32).toString('base64url'));
  await write(p, '/auth/password-reset/confirm', () => p.getByRole('button', { name: '提交', exact: true }).click(), 400);
  await p.getByLabel('邮件验证码', { exact: true }).fill('');
  assert.equal((await renewed.read('/account/profile')).email_verified, true);
  passed.push('O-B07 consumed reset code rejects a changed new password and leaves the renewed session active');
  stage = 'browser privacy and persistence';
  for (const s of [anonymous, customer, reviewer, buyer, recovery, renewed]) {
   assert.deepEqual(await s.page.evaluate(() => Object.keys(localStorage)), []);
   assert.deepEqual(await s.page.evaluate(() => Object.keys(sessionStorage)), []);
  }
  assert.equal(errors.length, 0);
  await renewed.page.getByRole('button', { name: '我的账户', exact: true }).click();
  await renewed.page.getByRole('heading', { name: '我的账户', exact: true }).waitFor();
  assert.equal((await renewed.read('/account/profile')).display_name, '虚构入驻店主');
  assert.equal((await renewed.read('/customer/addresses')).items[0].address.address_line, '虚构入驻路2号');
  assert.equal((await renewed.read('/customer/merchant-applications')).items[0].state, 'APPROVED');
  await renewed.page.screenshot({ path: path.join(screenshots, 'onboarding-persistent-account.png'), fullPage: true });
  passed.push('O-B08 fresh login retains profile/default address/application; zero page errors and no browser storage credentials');
  console.log(JSON.stringify({ status: 'PASS', checks: passed, count: passed.length, screenshots }));
 } finally { await browser.close(); }
})().catch(error => {
 const site = String(error.stack || '').match(/commerce-onboarding-browser-acceptance\.cjs:\d+:\d+/);
 console.error('Browser acceptance failed at ' + stage + ' (' + error.name + ', ' + (site?.[0] || 'no script callsite') + '); credentials and payloads omitted.');
 process.exitCode = 1;
});
