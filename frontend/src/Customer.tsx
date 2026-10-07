import { money, time } from './helpers';
import { useAllPages, useQuery } from './useQuery';
import { useState } from 'react';
import { CommerceClient, uncertain } from './client';
import type { Address, AddressBookView, Cart, Page, ProductCardView, Category, ShopView, Favorite, SKU, Order } from './types';
import { AddressForm, ErrorBox, Status, Pagination } from './ui';
import { Photo, FavoriteButton, ProductDetails } from './Shopping';
import { ContactShop } from './Messages';
import { OrderDetail } from './Orders';
export function Catalog({ client, customer, onCart }: {
    client: CommerceClient;
    customer: boolean;
    onCart: () => void;
}) {
    const [offset, setOffset] = useState(0);
    const [q, setQ] = useState(''), [shop, setShop] = useState(''), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false);
    const [category,setCategory]=useState(''),[minimum,setMinimum]=useState(''),[maximum,setMaximum]=useState(''),[stock,setStock]=useState(false),[sort,setSort]=useState('newest');
    const shops = useAllPages<ShopView>(client, '/shopping/shops');
    const favorites=useAllPages<Favorite>(client,'/customer/favorites',customer);
    const categories = useAllPages<Category>(client, '/shopping/categories');
    const result = useQuery<Page<ProductCardView>>(client, `/shopping/products?limit=20&offset=${offset}${q ? `&q=${encodeURIComponent(q)}` : ''}${shop ? `&shop_id=${encodeURIComponent(shop)}` : ''}${category?`&category_id=${category}`:''}${minimum?`&min_price_minor=${minimum}`:''}${maximum?`&max_price_minor=${maximum}`:''}${stock?'&in_stock=true':''}&sort=${sort}`);
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
    <button className="subtle" onClick={()=>{result.refresh();categories.refresh();shops.refresh();favorites.refresh();}}>刷新商品</button>
    </div>
    <div className="filters">
    <label>搜索商品<input placeholder="搜索名称或描述" value={q} maxLength={100} onChange={e => { setQ(e.target.value); setOffset(0); }}/>
    </label>
    <label>店铺筛选<select value={shop} onChange={e => { setShop(e.target.value); setOffset(0); }}>
    <option value="">全部店铺</option>
        {shops.items.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select>
    </label>
    <label>商品分类<select aria-label="商品分类" value={category} onChange={e=>{setCategory(e.target.value);setOffset(0);}}><option value="">全部分类</option>{categories.items.map(c=><option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
    <label>最低价格（分）<input type="number" min={0} value={minimum} onChange={e=>{setMinimum(e.target.value);setOffset(0);}}/></label>
    <label>最高价格（分）<input type="number" min={0} value={maximum} onChange={e=>{setMaximum(e.target.value);setOffset(0);}}/></label>
    <label>排序<select aria-label="排序" value={sort} onChange={e=>{setSort(e.target.value);setOffset(0);}}><option value="newest">最新商品</option><option value="price_asc">价格从低到高</option><option value="price_desc">价格从高到低</option><option value="rating">购买评分</option></select></label>
    <label className="check"><input type="checkbox" checked={stock} onChange={e=>{setStock(e.target.checked);setOffset(0);}}/>仅显示有货商品</label>
    </div>
    <ErrorBox error={shops.error??categories.error}/>
    <ErrorBox error={error ?? result.error}/>{error&&pendingAdd&&<div className="warning">上次加入操作的结果尚未确认。请保持相同请求重试。<button disabled={busy} onClick={()=>add({id:pendingAdd.sku_id,price_version:pendingAdd.seen_price_version})}>重试上次加入操作</button></div>}
    {result.loading && <p className="muted">正在读取选物…</p>}<div className="products">
        {result.data?.items.map((p, i) => <ProductCard key={p.id} client={client} customer={customer} product={p} index={i} disabled={busy || !customer || !!pendingAdd} onAdd={add} favorite={favorites.items.some(f=>f.product_id===p.id&&f.active)} onFavorite={favorites.refresh}/>)}</div>
    {result.data?.items.length === 0 && <div className="empty">没有符合条件的商品。试试其他关键词。</div>}<Pagination offset={offset} hasMore={result.data?.has_more ?? false} onChange={setOffset}/>
    {!customer && <p className="muted">登录具有客户资格的账号后，可以加入购物车。</p>}</>;
}
function ProductCard({ client, customer, product: p, index, disabled, onAdd, favorite, onFavorite }: {
    product: ProductCardView;
    favorite:boolean;
    onFavorite:()=>void;
    client: CommerceClient;
    customer: boolean;
    index: number;
    disabled: boolean;
    onAdd: (s: SKU) => void;
}) {
    const [selected, setSelected] = useState(p.skus[0]?.id ?? '');
    const sku = p.skus.find(s => s.id === selected) ?? p.skus[0];
    return <article className="product">
    {p.images?.[0]?<Photo client={client} image={p.images[0]}/>:<div className={`product-art art-${index % 3}`} aria-label="商品本地占位插画">
    <div className="object"/>
    <span>商品示意 · 非实物照片</span>
    </div>}
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
        </>}<ProductDetails client={client} product={p} customer={customer}/>{customer&&<FavoriteButton key={`${p.id}-${favorite}`} client={client} productId={p.id} initial={favorite} onChange={onFavorite}/>} {customer && <ContactShop client={client} shopId={p.shop_id} shopName={p.shop_name}/>}</div>
    </article>;
}
export function CartPage({ client, onOrders }: {
    client: CommerceClient;
    onOrders: () => void;
}) {
    const [addressDraft, setAddressDraft] = useState<Address>();
    const [addressSelection, setAddressSelection] = useState(0);
    const addresses = useQuery<Page<AddressBookView>>(client, '/customer/addresses?limit=20&offset=0');
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
            <ErrorBox error={addresses.error}/><label>从地址簿预填<select value="" onChange={e => { const chosen=addresses.data?.items.find(a=>a.id===e.target.value); if(chosen){setAddressDraft(chosen.address);setAddressSelection(n=>n+1);} }}><option value="">选择已保存地址（可继续编辑）</option>{addresses.data?.items.map(a=><option key={a.id} value={a.id}>{a.address.recipient_name} · {a.address.city} · {a.address.address_line}{a.is_default?' · 默认':''}</option>)}</select></label>
            <AddressForm key={addressSelection} initial={addressDraft} onDraftChange={setAddressDraft} disabled={busy} onSave={async (address) => { setBusy(true); setError(undefined); try {
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
export function Orders({ client, shop, owner = false }: {
    client: CommerceClient;
    shop?: string;
    owner?: boolean;
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
        {o.shop_name ?? `店铺 ${o.shop_id.slice(0,8)}`} · {o.id.slice(0, 8)} · {time(o.created_at)}</small>
        </span>
        <strong>
        {money(o.total_minor)} →</strong>
        </button>)}</div>
    {query.data?.items.length === 0 && <div className="empty">暂无订单。</div>}<Pagination offset={offset} hasMore={query.data?.has_more ?? false} onChange={n => { setOffset(n); setId(''); }}/>
    {id && <OrderDetail key={`${shop ?? 'customer'}-${id}`} client={client} path={`${base}/${id}`} merchant={!!shop} owner={owner} onChange={query.refresh}/>}</>;
}
