import { useMemo, useState, useSyncExternalStore } from 'react';
import { CommerceClient } from './client';
import type { Session } from './types';
import { ErrorBox } from './ui';
import { CartPage, Catalog, Orders } from './Customer';
import { MerchantProducts } from './Merchant';
import { Demo } from './Demo';
import './styles.css';
const apiBase = (import.meta as ImportMeta & {
    env: Record<string, string | undefined>;
}).env.VITE_API_BASE_URL ?? 'http://localhost:8000';
type View = 'catalog' | 'cart' | 'orders' | 'merchant' | 'products' | 'demo';
export default function App() {
    const [session, setSession] = useState<Session>(), [view, setView] = useState<View>('catalog'), [loginOpen, setLoginOpen] = useState(false), [shop, setShop] = useState(''), [epoch, setEpoch] = useState(0), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false);
    const client = useMemo(() => new CommerceClient(apiBase, session?.token), [session]);
    const pending = useSyncExternalStore(client.subscribe, client.getPending);
    const [retryError,setRetryError]=useState<unknown>();
    async function retryOriginal() {
        setRetryError(undefined);
        try { await client.retryPending(); }
        catch (e) { setRetryError(e); }
        finally { if(!client.getPending()) setEpoch(n=>n+1); }
    }
    const account = session?.account;
    const member = account?.shops.find(s => s.shop_id === shop);
    async function login(e: React.FormEvent<HTMLFormElement>) { e.preventDefault(); const f = new FormData(e.currentTarget); setError(undefined); setBusy(true); try {
        const s = await client.request<Session>('/auth/login', 'POST', { username: f.get('username'), password: f.get('password') });
        client.dispose();
        setRetryError(undefined);
        setSession(s);
        setShop(s.account.shops[0]?.shop_id ?? '');
        setLoginOpen(false);
        setView(s.account.customer_enabled ? 'catalog' : s.account.shops.length ? 'merchant' : s.account.demo_enabled ? 'demo' : 'catalog');
        setEpoch(n => n + 1);
    }
    catch (e) {
        setError(e);
    }
    finally {
        setBusy(false);
    } }
    async function logout() { const old = new CommerceClient(apiBase, session?.token); client.dispose(); setRetryError(undefined); setSession(undefined); setShop(''); setView('catalog'); setEpoch(n => n + 1); setError(undefined); try {
        await old.request('/auth/logout', 'POST', {});
    }
    catch { /* Local session is invalidated even when the server cannot be reached. */ } }
    return <div className="app">
    <header>
    <a className="brand" href="#" onClick={e => { e.preventDefault(); setView('catalog'); }}>
    <span className="brand-mark">拾</span>
    <span>拾物集<small>SHIWU / EVERYDAY OBJECTS</small>
    </span>
    </a>
    <nav aria-label="主要导航">
    <button className={view === 'catalog' ? 'active' : ''} onClick={() => setView('catalog')}>选物集</button>
        {account?.customer_enabled && <>
        <button className={view === 'cart' ? 'active' : ''} onClick={() => setView('cart')}>购物袋</button>
        <button className={view === 'orders' ? 'active' : ''} onClick={() => setView('orders')}>我的订单</button>
        </>}{!!account?.shops.length && <button className={['merchant', 'products'].includes(view) ? 'active' : ''} onClick={() => setView('merchant')}>店铺工作台</button>}{account?.demo_enabled && <button className={view === 'demo' ? 'active' : ''} onClick={() => setView('demo')}>模拟事件</button>}</nav>
    <div className="account">
        {account ? <>
        <span>
        {account.username}</span>
        <button className="subtle" onClick={logout}>退出</button>
        </> : <button onClick={() => setLoginOpen(!loginOpen)}>登录 →</button>}</div>
    </header>
        {loginOpen && !session && <section className="login-panel">
        <div>
        <span className="eyebrow">WELCOME BACK</span>
        <h2>登录，继续你的日常。</h2>
        <p>刷新页面后需重新登录，业务记录保存在服务端。</p>
        <p className="muted">演示账号：customer.a / customer.b / owner.a / owner.b / staff.a / demo / dual.a。密码由演示环境配置。</p>
        </div>
        <form onSubmit={login}>
        <ErrorBox error={error}/>
        <label>账号<input name="username" required autoComplete="username" pattern="[a-z0-9_.-]{1,80}" maxLength={80}/>
        </label>
        <label>密码<input name="password" type="password" required minLength={12} maxLength={128} autoComplete="current-password"/>
        </label>
        <button disabled={busy}>登录</button>
        </form>
        </section>}
        {pending && <section className="pending-operation" role="status">
            <strong>{pending.uncertain?'上次操作的结果尚未确认':'正在确认操作结果…'}</strong>
            <p>确认前已暂停新的业务提交。可以浏览或刷新记录；请使用原请求重试，避免重复购买、调整库存或发货。</p>
            <button disabled={!pending.uncertain} onClick={retryOriginal}>重试原操作</button>
            <ErrorBox error={retryError}/>
        </section>}
        {!pending && !!retryError && <div className="pending-operation"><ErrorBox error={retryError}/></div>}
        <main key={epoch}>
        {['merchant', 'products'].includes(view) && account && <div className="merchant-nav">
        <label>当前店铺<select value={shop} onChange={e => { setShop(e.target.value); setView('merchant'); }}>
            {account.shops.map(s => <option key={s.shop_id} value={s.shop_id}>
            {s.shop_name} · {s.role === 'OWNER' ? '店主' : '员工'}{s.shop_status === 'SUSPENDED' ? ' · 已暂停' : ''}</option>)}</select>
        </label>
        <button className={view === 'merchant' ? 'active' : ''} onClick={() => setView('merchant')}>处理订单</button>
        {member?.role === 'OWNER' && <button className={view === 'products' ? 'active' : ''} onClick={() => setView('products')}>商品与库存</button>}</div>}<div key={`${account?.id ?? 'public'}-${shop}-${view}`}>
    {view === 'catalog' && <Catalog client={client} customer={!!account?.customer_enabled} onCart={() => setView('cart')}/>} {view === 'cart' && account?.customer_enabled && <CartPage client={client} onOrders={() => setView('orders')}/>} {view === 'orders' && account?.customer_enabled && <Orders client={client}/>} {view === 'merchant' && member && <Orders client={client} shop={shop}/>} {view === 'products' && member?.role === 'OWNER' && <MerchantProducts client={client} shop={shop}/>} {view === 'demo' && account?.demo_enabled && <Demo client={client}/>}</div>
    </main>
    <footer>
    <div className="brand">拾物集 <span>把生活，过成喜欢的样子。</span>
    </div>
    <p>COMMERCE LAB / 模拟交易与配送 · 无真实资金流转</p>
    </footer>
    </div>;
}
