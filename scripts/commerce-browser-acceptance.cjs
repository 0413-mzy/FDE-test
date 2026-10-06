// Optional real-browser acceptance; requires a fresh isolated commerce seed. Never use real customer data.
const fs = require('fs');
const assert = require('assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const passwordFile = process.env.COMMERCE_PASSWORD_FILE;
if (!passwordFile)
    throw new Error('COMMERCE_PASSWORD_FILE is required');
const password = fs.readFileSync(passwordFile, 'utf8').trim();
const screenshots = process.env.COMMERCE_SCREENSHOT_DIR || '/tmp/fde-commerce-browser-evidence';
const uiUrl = process.env.COMMERCE_UI_URL || 'http://localhost:5173';
fs.mkdirSync(screenshots, { recursive: true });
let stage = 'launch';
(async () => {
    const browser = await chromium.launch({ headless: true, ...(process.env.CHROME_EXECUTABLE ? { executablePath: process.env.CHROME_EXECUTABLE } : {}) });
    try {
        let errors = [];
        async function login(name) { stage = 'login ' + name; const p = await browser.newPage({ viewport: { width: 1440, height: 1100 } }); p.on('pageerror', e => errors.push(e.message)); await p.goto(uiUrl); await p.getByRole('heading', { name: 'Fictional Product A', exact: true }).waitFor(); await p.getByRole('button', { name: '登录 →' }).click(); await p.getByLabel('账号', { exact: true }).fill(name); await p.getByLabel('密码', { exact: true }).fill(password); await p.getByRole('button', { name: '登录', exact: true }).click(); await p.getByText(name, { exact: true }).waitFor(); return p; }
        const c = await login('customer.a');
        stage = 'customer checkout';
        await c.screenshot({ path: screenshots + '/commerce-catalog.png', fullPage: true });
        await c.getByRole('article').filter({ has: c.getByRole('heading', { name: 'Fictional Product A', exact: true }) }).getByRole('button', { name: /加入购物车/ }).click();
        await c.getByRole('heading', { name: '购物袋', exact: true }).waitFor();
        await c.getByRole('button', { name: '选物集', exact: true }).click();
        await c.getByRole('heading', { name: 'Fictional Product B', exact: true }).waitFor();
        await c.getByRole('article').filter({ has: c.getByRole('heading', { name: 'Fictional Product B', exact: true }) }).getByRole('button', { name: /加入购物车/ }).click();
        await c.getByRole('heading', { name: '购物袋', exact: true }).waitFor();
        const arow = c.locator('.cart-row').filter({ has: c.getByRole('heading', { name: 'Fictional Product A', exact: true }) });
        await arow.getByLabel('数量').fill('2');
        await arow.getByRole('button', { name: '确认数量与价格' }).click();
        await c.getByText('当前展示价格合计 ¥40.00').waitFor();
        for (const [label, value] of [['收件人', '演示买家'], ['联系电话', '13800000000'], ['省 / 地区', '上海'], ['城市', '上海'], ['邮编', '200000'], ['详细地址', '虚构演示路1号']])
            await c.getByLabel(label, { exact: true }).fill(value);
        await c.getByRole('button', { name: '使用地址下单' }).click();
        await c.getByRole('heading', { name: '我的订单', exact: true }).waitFor();
        await c.locator('.order-summary').nth(1).waitFor();
        assert.equal(await c.locator('.order-summary').count(), 2);
        for (let i = 0; i < 2; i++) {
            await c.locator('.order-summary').nth(i).click();
            await c.getByRole('button', { name: '发起模拟付款' }).click();
            await c.locator('.attempt').waitFor();
        }
        const demo = await login('demo');
        stage = 'payment results';
        await demo.getByRole('button', { name: '模拟事件' }).click();
        await demo.getByRole('heading', { name: '模拟事件台' }).waitFor();
        for (let i = 0; i < 2; i++) {
            const panel = demo.locator('article.panel').first();
            const id = (await panel.locator('.mono').innerText()).trim();
            const response = demo.waitForResponse(r => r.request().method() === 'POST' && r.url().includes('/demo/payments/' + id + '/result') && r.status() === 200);
            await panel.getByRole('button', { name: '提交模拟结果' }).click();
            await response;
            await demo.waitForFunction(n => document.querySelectorAll('article.panel').length === n, 1 - i);
        }
        assert.equal(await demo.locator('article.panel').count(), 0);
        const ma = await login('owner.a');
        stage = 'shopA partial shipments';
        await ma.getByRole('button', { name: '店铺工作台' }).click();
        await ma.locator('.order-summary').first().click();
        await ma.getByLabel('Fictional Product A本次发货数量').fill('1');
        await ma.getByRole('button', { name: '确认模拟出库 · 创建包裹' }).click();
        await ma.locator('.shipment').first().waitFor();
        assert.equal(await ma.locator('.shipment').count(), 1);
        await ma.getByLabel('Fictional Product A本次发货数量').fill('1');
        await ma.getByRole('button', { name: '确认模拟出库 · 创建包裹' }).click();
        await ma.locator('.shipment').nth(1).waitFor();
        await ma.screenshot({ path: screenshots + '/commerce-merchant.png', fullPage: true });
        const mb = await login('owner.b');
        stage = 'shopB shipment';
        await mb.getByRole('button', { name: '店铺工作台' }).click();
        await mb.locator('.order-summary').first().click();
        await mb.getByLabel('Fictional Product B本次发货数量').fill('1');
        await mb.getByRole('button', { name: '确认模拟出库 · 创建包裹' }).click();
        await mb.locator('.shipment').first().waitFor();
        stage = 'delivery events';
        await demo.getByRole('button', { name: '刷新队列' }).click();
        await demo.locator('article.panel').nth(2).waitFor();
        for (let i = 0; i < 3; i++) {
            const card = demo.locator('article.panel').first();
            await card.locator('select[name=kind]').selectOption('DELIVERED');
            await card.getByLabel('物流描述').fill('模拟送达虚构地址');
            const local = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 23).replace(/0+$/, '').replace(/\.$/, '');
            await card.getByLabel('事件发生时间（本地时间）').fill(local);
            const id = (await card.locator('.mono').innerText()).trim();
            const response = demo.waitForResponse(r => r.request().method() === 'POST' && r.url().includes('/demo/shipments/' + id + '/events') && r.status() === 200);
            await card.getByRole('button', { name: '提交模拟结果' }).click();
            await response;
            await demo.waitForFunction(n => document.querySelectorAll('article.panel').length === n, 2 - i);
        }
        assert.equal(await demo.locator('article.panel').count(), 0);
        stage = 'customer receipt';
        await c.getByRole('button', { name: '刷新订单' }).click();
        await c.waitForTimeout(200);
        for (let i = 0; i < 2; i++) {
            await c.locator('.order-summary').nth(i).click();
            await c.getByRole('button', { name: '刷新详情' }).click();
            await c.getByRole('button', { name: '所有包裹已送达 · 确认收货' }).click();
            await c.locator('.order-detail').getByText('已完成', { exact: true }).waitFor();
        }
        await c.screenshot({ path: screenshots + '/commerce-completed.png', fullPage: true });
        assert.equal(errors.length, 0);
        console.log('PASS: real Chrome customer checkout splits 2 shops,2 payments,3 parcels including partial shipments,3 delivered events,2 confirmed orders; zero page errors.');
    }
    finally {
        await browser.close();
    }
})().catch(() => { console.error('Browser acceptance failed at ' + stage + '; request/credential data omitted.'); process.exitCode = 1; });
