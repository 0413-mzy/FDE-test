import { money } from './helpers';
import { useQuery } from './useQuery';
import { useState } from 'react';
import { CommerceClient } from './client';
import type { Inventory, Page, Product, SKU } from './types';
import { ErrorBox, Status, Pagination } from './ui';
export function MerchantProducts({ client, shop }: {
    client: CommerceClient;
    shop: string;
}) {
    const [offset, setOffset] = useState(0);
    const q = useQuery<Page<Product>>(client, `/merchant/shops/${shop}/products?limit=20&offset=${offset}`), [selected, setSelected] = useState(''), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false);
    const base = `/merchant/shops/${shop}`;
    async function create(e: React.FormEvent<HTMLFormElement>) { e.preventDefault(); const f = new FormData(e.currentTarget); setBusy(true); setError(undefined); try {
        const p = await client.request<Product>(base + '/products', 'POST', { title: f.get('title'), description: f.get('description'), sku: { sku_code: f.get('sku_code'), options: { 款式: String(f.get('option')) }, unit_price_minor: Number(f.get('price')), initial_stock: Number(f.get('stock')) } });
        q.refresh();
        setSelected(p.id);
    }
    catch (e) {
        setError(e);
    }
    finally {
        setBusy(false);
    } }
    return <>
    <div className="section-head">
    <h1>商品与库存</h1>
    <button className="subtle" onClick={q.refresh}>刷新商品</button>
    </div>
    <ErrorBox error={error ?? q.error}/>
    <details className="panel">
    <summary>＋ 创建商品草稿</summary>
    <form onSubmit={create}>
    <div className="field-grid">
    <label>商品名称<input name="title" required maxLength={200}/>
    </label>
    <label>SKU 编码<input name="sku_code" required maxLength={80}/>
    </label>
    <label>款式<input name="option" required maxLength={80}/>
    </label>
    <label>单价（整数分）<input name="price" type="number" required min={1}/>
    </label>
    <label>初始库存<input name="stock" type="number" required min={0} max={1000000}/>
    </label>
    <label>商品描述<textarea name="description" maxLength={5000}/>
    </label>
    </div>
    <button disabled={busy}>创建草稿</button>
    </form>
    </details>
    {q.loading && <p>正在读取商品…</p>}<div className="order-list">
        {q.data?.items.map(p => <button className="order-summary" key={p.id} onClick={() => setSelected(p.id)}>
        <span>
        <strong>
        {p.title}</strong>
        <small>
        {p.skus.length} 个款式</small>
        </span>
        <Status value={p.status}/>
        </button>)}</div>
    {q.data?.items.length === 0 && <div className="empty">还没有商品。创建第一个商品草稿。</div>}<Pagination offset={offset} hasMore={q.data?.has_more ?? false} onChange={n => { setOffset(n); setSelected(''); }}/>
    {selected && <ProductEditor key={selected} client={client} path={`${base}/products/${selected}`} inventoryBase={`${base}/inventory`} onChange={q.refresh}/>}</>;
}
function ProductEditor({ client, path, inventoryBase, onChange }: {
    client: CommerceClient;
    path: string;
    inventoryBase: string;
    onChange: () => void;
}) {
    const q = useQuery<Product>(client, path), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false);
    async function action(suffix: string, body: unknown) { setBusy(true); setError(undefined); try {
        await client.request(path + suffix, 'POST', body);
        q.refresh();
        onChange();
    }
    catch (e) {
        setError(e);
    }
    finally {
        setBusy(false);
    } }
    const p = q.data;
    if (!p)
        return <ErrorBox error={q.error}/>;
    return <section className="panel">
    <h2>
    {p.title} <Status value={p.status}/>
    </h2>
    <ErrorBox error={error}/>
    <form key={p.version} onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); action('/edit', { expected_version: p.version, title: f.get('title'), description: f.get('description') }); }}>
    <label>商品标题<input name="title" required maxLength={200} defaultValue={p.title}/>
    </label>
    <label>描述<textarea name="description" maxLength={5000} defaultValue={p.description}/>
    </label>
    <div className="button-row">
    <button disabled={busy}>保存商品信息</button>
    <button type="button" className="subtle" disabled={busy || p.status === 'PUBLISHED'} onClick={() => action('/publish', { expected_version: p.version })}>上架</button>
    <button type="button" className="subtle" disabled={busy || p.status === 'ARCHIVED'} onClick={() => action('/archive', { expected_version: p.version })}>归档停售</button>
    <button type="button" className="subtle" onClick={q.refresh}>刷新详情</button>
    </div>
    </form>
        {p.skus.map(s => <SkuEditor key={`${s.id}-${s.version}`} sku={s} client={client} path={`${path}/skus/${s.id}/edit`} inventoryPath={`${inventoryBase}/${s.id}`} onChange={() => { q.refresh(); onChange(); }}/>)}<details>
    <summary>＋ 添加款式</summary>
    <form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); action('/skus', { expected_version: p.version, sku_code: f.get('code'), options: { 款式: String(f.get('option')) }, unit_price_minor: Number(f.get('price')), initial_stock: Number(f.get('stock')) }); }}>
    <div className="field-grid">
    <label>SKU 编码<input name="code" required maxLength={80}/>
    </label>
    <label>款式<input name="option" required maxLength={80}/>
    </label>
    <label>单价（分）<input name="price" type="number" required min={1}/>
    </label>
    <label>初始库存<input name="stock" type="number" required min={0} max={1000000}/>
    </label>
    </div>
    <button disabled={busy}>添加款式</button>
    </form>
    </details>
    </section>;
}
function SkuEditor({ sku: s, client, path, inventoryPath, onChange }: {
    sku: SKU;
    client: CommerceClient;
    path: string;
    inventoryPath: string;
    onChange: () => void;
}) {
    const q = useQuery<Inventory>(client, inventoryPath), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false);
    async function save(endpoint: string, body: unknown) { setBusy(true); setError(undefined); try {
        await client.request(endpoint, 'POST', body);
        q.refresh();
        onChange();
    }
    catch (e) {
        setError(e);
    }
    finally {
        setBusy(false);
    } }
    return <div className="sku-panel">
    <h3>
    {s.sku_code} · {Object.values(s.options).join(' / ')}</h3>
    <p>
    {money(s.unit_price_minor)} · {s.active ? '在售款式' : '已停用'}</p>
    <ErrorBox error={error ?? q.error}/>
    <form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); save(path, { expected_version: s.version, unit_price_minor: Number(f.get('price')), active: f.get('active') === 'on' }); }}>
    <div className="button-row">
    <label>价格（分）<input type="number" min={1} required name="price" defaultValue={s.unit_price_minor}/>
    </label>
    <label className="check">
    <input type="checkbox" name="active" defaultChecked={s.active}/>启用款式</label>
    <button disabled={busy || !s.version}>保存款式</button>
    </div>
    </form>
        {q.data && <>
        <p>实物库存 {q.data.on_hand} · 预留 {q.data.reserved} · 可售 {q.data.available}</p>
        <form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); save(inventoryPath + '/adjust', { expected_version: q.data!.version, delta: Number(f.get('delta')), reason: f.get('reason') }); }}>
        <div className="field-grid">
        <label>调整数量（正增 / 负减）<input type="number" name="delta" required min={-1000000} max={1000000}/>
        </label>
        <label>调整原因<input name="reason" required maxLength={200}/>
        </label>
        </div>
        <button className="subtle" disabled={busy}>提交库存调整</button>
        <button type="button" className="subtle" onClick={q.refresh}>刷新库存</button>
        </form>
        </>}</div>;
}
