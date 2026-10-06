import { money, time } from './helpers';
import { useQuery } from './useQuery';
import { useState } from 'react';
import { CommerceClient, uncertain } from './client';
import type { Cart, Page, Product, SKU, Order } from './types';
import { AddressForm, ErrorBox, Status, Pagination } from './ui';
import { OrderDetail } from './Orders';
export function Catalog({ client, customer, onCart }: {
    client: CommerceClient;
    customer: boolean;
    onCart: () => void;
}) {
    const [offset, setOffset] = useState(0);
    const [q, setQ] = useState(''), [shop, setShop] = useState(''), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false);
    const shops = useQuery<Page<Product>>(client, '/catalog/products?limit=100');
    const result = useQuery<Page<Product>>(client, `/catalog/products?limit=20&offset=${offset}${q ? `&q=${encodeURIComponent(q)}` : ''}${shop ? `&shop_id=${encodeURIComponent(shop)}` : ''}`);
    const [pendingAdd,setPendingAdd]=useState<{sku_id:string;expected_version:number;quantity:number;seen_price_version:number}>();
    async function add(sku: Pick<SKU,'id'|'price_version'>) { setBusy(true); setError(undefined); try {
        let body=pendingAdd;
        if(!body) {const cart = await client.request<Cart>('/customer/cart');body={ expected_version: cart.version, sku_id: sku.id, quantity: (cart.lines.find(l => l.sku_id === sku.id)?.quantity ?? 0) + 1, seen_price_version: sku.price_version };setPendingAdd(body)}
        await client.request('/customer/cart/lines', 'POST', body);
        setPendingAdd(undefined);
        onCart();
    }
    catch (e) {
        setError(e);
        if(!uncertain(e))setPendingAdd(undefined);
    }
    finally {
        setBusy(false);
    } }
    return <>
    <section className="hero">
    <div>
    <span className="eyebrow">THE EVERYDAY COLLECTION · 日常选物</span>
    <h1>让好物，<br />
    <em>走进日常。</em>
    </h1>
    <p>来自不同店铺的生活提案。真实库存记录，独立订单履约。</p>
    <span className="simulation">演示商城 · 付款与物流均为模拟</span>
    </div>
    <div className="hero-art" aria-hidden="true">
    <div className="vase"/>
    <div className="sun"/>
    <span>寻常 / 不寻常</span>
    </div>
    </section>
    <div className="section-head">
    <h2>选物集 <small>COLLECTION</small>
    </h2>
    <button className="subtle" onClick={result.refresh}>刷新商品</button>
    </div>
    <div className="filters">
    <label>搜索商品<input placeholder="搜索名称或描述" value={q} maxLength={100} onChange={e => { setQ(e.target.value); setOffset(0); }}/>
    </label>
    <label>店铺筛选<select value={shop} onChange={e => { setShop(e.target.value); setOffset(0); }}>
    <option value="">全部店铺</option>
        {Array.from(new Map(shops.data?.items.map(p => [p.shop_id, p.shop_name]) ?? [])).map(([id, name]) => <option key={id} value={id}>
        {name}</option>)}</select>
    </label>
    </div>
    <ErrorBox error={error ?? result.error}/>{error&&pendingAdd&&<div className="warning">上次加入操作的结果尚未确认。请保持相同请求重试。<button disabled={busy} onClick={()=>add({id:pendingAdd.sku_id,price_version:pendingAdd.seen_price_version})}>重试上次加入操作</button></div>}
    {result.loading && <p className="muted">正在读取选物…</p>}<div className="products">
        {result.data?.items.map((p, i) => <ProductCard key={p.id} product={p} index={i} disabled={busy || !customer || !!pendingAdd} onAdd={add}/>)}</div>
    {result.data?.items.length === 0 && <div className="empty">没有符合条件的商品。试试其他关键词。</div>}<Pagination offset={offset} hasMore={result.data?.has_more ?? false} onChange={setOffset}/>
    {!customer && <p className="muted">登录具有客户资格的账号后，可以加入购物车。</p>}</>;
}
function ProductCard({ product: p, index, disabled, onAdd }: {
    product: Product;
    index: number;
    disabled: boolean;
    onAdd: (s: SKU) => void;
}) {
    const [selected, setSelected] = useState(p.skus[0]?.id ?? '');
    const sku = p.skus.find(s => s.id === selected) ?? p.skus[0];
    return <article className="product">
    <div className={`product-art art-${index % 3}`} aria-label="商品本地占位插画">
    <div className="object"/>
    <span>商品示意 · 非实物照片</span>
    </div>
    <div className="product-body">
    <span className="eyebrow">
    {p.shop_name}</span>
    <h3>
    {p.title}</h3>
    <p>
    {p.description || '店铺尚未提供商品描述。'}</p>
        {sku && <>
        <label>款式<select value={sku.id} onChange={e => setSelected(e.target.value)}>
            {p.skus.map(s => <option key={s.id} value={s.id}>
            {Object.values(s.options).join(' / ') || s.sku_code}</option>)}</select>
        </label>
        <div className="price-row">
        <strong>
        {money(sku.unit_price_minor)}</strong>
        <small>可售 {sku.available} 件</small>
        </div>
        <button disabled={disabled || sku.available < 1} onClick={() => onAdd(sku)}>
        {sku.available < 1 ? '暂时缺货' : '加入购物车'} <span>＋</span>
        </button>
        </>}</div>
    </article>;
}
export function CartPage({ client, onOrders }: {
    client: CommerceClient;
    onOrders: () => void;
}) {
    const query = useQuery<Cart>(client, '/customer/cart'), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false);
    async function mutate(path: string, method: string, body: unknown) { setBusy(true); setError(undefined); try {
        await client.request(path, method, body);
        query.refresh();
    }
    catch (e) {
        setError(e);
    }
    finally {
        setBusy(false);
    } }
    const cart = query.data;
    return <>
    <div className="section-head">
    <h1>购物袋</h1>
    <button className="subtle" onClick={query.refresh}>刷新购物袋</button>
    </div>
    <p className="muted">下单将按店铺拆成独立订单。价格变动需再次确认；付款期限为 15 分钟。</p>
    <ErrorBox error={error ?? query.error}/>
    {query.loading && <p>正在读取购物袋…</p>}{cart && <>
            {cart.lines.length === 0 ? <div className="empty">购物袋还是空的。去选物集寻找喜欢的商品。</div> : <>
            <div className="cart-lines">
                {cart.lines.map(l => <CartRow key={`${l.sku_id}-${cart.version}`} line={l} disabled={busy} onSet={quantity => mutate('/customer/cart/lines', 'POST', { expected_version: cart.version, sku_id: l.sku_id, quantity, seen_price_version: l.current_price_version })} onRemove={() => mutate(`/customer/cart/lines/${l.sku_id}`, 'DELETE', { expected_version: cart.version })}/>)}</div>
            <div className="checkout-summary">
            <h2>当前展示价格合计 <strong>
            {money(cart.lines.reduce((n, l) => n + l.current_price_minor * l.quantity, 0))}</strong>
            </h2>
            <p>运费 / 税费 ¥0.00 · 最终金额由服务器校验。</p>
            <AddressForm disabled={busy} onSave={async (address) => { setBusy(true); setError(undefined); try {
                    await client.request('/customer/checkouts', 'POST', { expected_version: cart.version, address });
                    onOrders();
                }
                catch (e) {
                    setError(e);
                }
                finally {
                    setBusy(false);
                } }}/>
            </div>
            </>}</>}</>;
}
function CartRow({ line: l, disabled, onSet, onRemove }: {
    line: Cart['lines'][number];
    disabled: boolean;
    onSet: (q: number) => void;
    onRemove: () => void;
}) {
    const [qty, setQty] = useState(l.quantity);
    return <article className="cart-row">
    <div>
    <h3>{l.product_title}</h3>
    <small>{l.shop_name} · {Object.values(l.options).join(' / ')}</small>
    <p>
    {money(l.current_price_minor)} / 件 · 可售 {l.available}</p>
    {l.current_price_version !== l.seen_price_version && <p className="warning">价格已由 {money(l.seen_price_minor)} 变为 {money(l.current_price_minor)}。点击“确认数量与价格”接受当前价格。</p>}{!l.purchasable && <p className="warning">当前无法购买，请移除或等待店铺恢复。</p>}</div>
    <form onSubmit={e => { e.preventDefault(); onSet(qty); }}>
    <label>数量<input type="number" required min={1} max={99} value={qty} onChange={e => setQty(Number(e.target.value))}/>
    </label>
    <button className="subtle" disabled={disabled || !l.purchasable}>确认数量与价格</button>
    </form>
    <button className="subtle" disabled={disabled} onClick={onRemove}>移除</button>
    </article>;
}
export function Orders({ client, shop }: {
    client: CommerceClient;
    shop?: string;
}) {
    const [offset, setOffset] = useState(0);
    const [id, setId] = useState(''), [status, setStatus] = useState('');
    const base = shop ? `/merchant/shops/${shop}/orders` : '/customer/orders';
    const query = useQuery<Page<Order>>(client, `${base}?limit=20&offset=${offset}${status ? `&status=${status}` : ''}`);
    return <>
    <div className="section-head">
    <h1>
    {shop ? '订单工作台' : '我的订单'}</h1>
    <button className="subtle" onClick={query.refresh}>刷新订单</button>
    </div>
    <label className="inline-label">订单状态<select value={status} onChange={e => { setStatus(e.target.value); setOffset(0); setId(''); }}>
    <option value="">全部</option>
        {['PENDING_PAYMENT', 'READY_TO_SHIP', 'PARTIALLY_SHIPPED', 'SHIPPED', 'COMPLETED', 'CANCELLED'].map(s => <option key={s} value={s}>
        {s === 'PENDING_PAYMENT' ? '待付款' : s === 'READY_TO_SHIP' ? '待发货' : s === 'PARTIALLY_SHIPPED' ? '部分发货' : s === 'SHIPPED' ? '已发货' : s === 'COMPLETED' ? '已完成' : '已取消'}</option>)}</select>
    </label>
    <ErrorBox error={query.error}/>
    {query.loading && <p>正在读取订单…</p>}<div className="order-list">
        {query.data?.items.map(o => <button key={o.id} className={`order-summary ${id === o.id ? 'selected' : ''}`} onClick={() => setId(o.id)}>
        <span>
        <Status value={o.status}/>
        <small>
        {o.id.slice(0, 8)} · {time(o.created_at)}</small>
        </span>
        <strong>
        {money(o.total_minor)} →</strong>
        </button>)}</div>
    {query.data?.items.length === 0 && <div className="empty">暂无订单。</div>}<Pagination offset={offset} hasMore={query.data?.has_more ?? false} onChange={n => { setOffset(n); setId(''); }}/>
    {id && <OrderDetail key={`${shop ?? 'customer'}-${id}`} client={client} path={`${base}/${id}`} merchant={!!shop} onChange={query.refresh}/>}</>;
}
