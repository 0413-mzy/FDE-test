import { useMemo, useState, useSyncExternalStore } from 'react';
import { CommerceClient } from './client';
import type { Account, ProfileView, Session } from './types';
import { ErrorBox } from './ui';
import { CartPage, Catalog, Orders } from './Customer';
import { MerchantProducts } from './Merchant';
import { Messages } from './Messages';
import { Favorites, Reviews } from './Shopping';
import { PlatformWorkbench, CustomerCases, Disputes, AnalyticsPanel } from './Platform';
import { Demo } from './Demo';
import './styles.css';
import { AccountCenter, Applications, AuthForms } from './Account';
import { useQuery } from './useQuery';
import { demoPolicy, type DemoInfo } from './helpers';
const apiBase = (import.meta as ImportMeta & {
    env: { VITE_API_BASE_URL?: string; DEV: boolean };
}).env.VITE_API_BASE_URL ?? ((import.meta as ImportMeta & { env: { DEV: boolean } }).env.DEV ? 'http://localhost:8000' : '');
type View = 'catalog' | 'cart' | 'orders' | 'merchant' | 'products' | 'demo' | 'messages' | 'merchant-messages' | 'account' | 'review' | 'favorites' | 'cases' | 'platform' | 'merchant-reviews' | 'merchant-disputes' | 'merchant-analytics';
export default function App() {
    const [session, setSession] = useState<Session>(), [view, setView] = useState<View>('catalog'), [loginOpen, setLoginOpen] = useState(false), [shop, setShop] = useState(''), [epoch, setEpoch] = useState(0), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false);
    const client = useMemo(() => new CommerceClient(apiBase, session?.token), [session?.token]);
    const publicClient = useMemo(() => new CommerceClient(apiBase), []);
    const demoInfo = useQuery<DemoInfo>(publicClient, '/demo-info');
    const policy = demoPolicy(demoInfo.data);
    const access = useQuery<{platform_enabled:boolean}>(client, '/platform/access', !!session);
    const profile = useQuery<ProfileView>(client, '/account/profile', !!session);
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
    async function refreshIdentity() {
        const fresh = await client.request<Account>('/auth/me');
        setSession(old => old ? { ...old, account: fresh } : old);
        setShop(current => fresh.shops.some(s => s.shop_id === current) ? current : fresh.shops[0]?.shop_id ?? '');
    }
    function clearSession() { client.dispose(); setRetryError(undefined); setSession(undefined); setShop(''); setView('catalog'); setLoginOpen(true); setEpoch(n=>n+1); }
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
        <button className={view === 'messages' ? 'active' : ''} onClick={() => setView('messages')}>店铺消息</button>
        <button className={view === 'orders' ? 'active' : ''} onClick={() => setView('orders')}>我的订单</button>
        <button className={view==='favorites'?'active':''} onClick={()=>setView('favorites')}>我的收藏</button><button className={view==='cases'?'active':''} onClick={()=>setView('cases')}>举报与争议</button></>}{!!account?.shops.length && <button className={['merchant', 'products', 'merchant-messages', 'merchant-reviews', 'merchant-disputes', 'merchant-analytics'].includes(view) ? 'active' : ''} onClick={() => setView('merchant')}>店铺工作台</button>}{account?.demo_enabled && <button className={view === 'demo' ? 'active' : ''} onClick={() => setView('demo')}>模拟事件</button>}{account && <button className={view==='account'?'active':''} onClick={()=>setView('account')}>我的账户</button>}{account && !account.demo_enabled && profile.data?.review_enabled && <button className={view==='review'?'active':''} onClick={()=>setView('review')}>入驻审核</button>}{account&&access.data?.platform_enabled&&<button className={view==='platform'?'active':''} onClick={()=>setView('platform')}>平台运营</button>}</nav>
    <div className="account">
        {account ? <>
        <span>
        {account.username}</span>
        <button className="subtle" onClick={logout}>退出</button>
        </> : <button onClick={() => setLoginOpen(!loginOpen)}>登录 →</button>}</div>
    </header>
        {policy.publicDemo && <section className="public-demo-banner" role="note"><strong>公开演示 · 共享虚构数据</strong><p>所有访客共享账号与业务记录。支付、物流及退款均为模拟，无真实资金流转。地址、消息和图片只使用虚构资料，勿填真实个人信息。</p></section>}{!!demoInfo.error && <section className="account-section"><ErrorBox error={demoInfo.error}/><p>无法读取环境配置；注册与账号修改入口暂时隐藏。购物和登录仍可使用。</p><button onClick={demoInfo.refresh}>重试读取环境配置</button></section>}{loginOpen && !session && <section className="login-panel">
        <div>
        <span className="eyebrow">WELCOME BACK</span>
        <h2>登录，继续你的日常。</h2>
        <p>刷新页面后需重新登录，业务记录保存在服务端。</p>
        {policy.publicDemo ? <><p>访客账号：{demoInfo.data?.accounts.join(" / ")}</p><p>公开演示密码：<code>{demoInfo.data?.password}</code></p><p>这是刻意公开的共享演示凭据，请勿使用个人密码。</p></> : <p className="muted">{demoInfo.loading ? "正在读取环境配置…" : "演示密码由环境管理员提供。"}</p>}
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
        {loginOpen && !session && policy.allowAccountWrites && <AuthForms client={client}/>}
        {pending && <section className="pending-operation" role="status">
            <strong>{pending.uncertain?'上次操作的结果尚未确认':'正在确认操作结果…'}</strong>
            <p>{pending.path.startsWith('/auth/') ? '注册、验证或恢复申请的结果尚未确认。请使用原请求重试；确认前已暂停新的提交。' : '确认前已暂停新的业务提交。可以浏览或刷新记录；请使用原请求重试，避免重复购买、退款、发送消息、调整库存或发货。'}</p>
            <button disabled={!pending.uncertain} onClick={retryOriginal}>重试原操作</button>
            <ErrorBox error={retryError}/>
        </section>}
        {!pending && !!retryError && <div className="pending-operation"><ErrorBox error={retryError}/></div>}
        <main key={epoch}>
        {['merchant', 'products', 'merchant-messages', 'merchant-reviews', 'merchant-disputes', 'merchant-analytics'].includes(view) && account && <div className="merchant-nav">
        <label>当前店铺<select value={shop} onChange={e => { setShop(e.target.value); setView('merchant'); }}>
            {account.shops.map(s => <option key={s.shop_id} value={s.shop_id}>
            {s.shop_name} · {s.role === 'OWNER' ? '店主' : '员工'}{s.shop_status === 'SUSPENDED' ? ' · 已暂停' : ''}</option>)}</select>
        </label>
        <button className={view === 'merchant' ? 'active' : ''} onClick={() => setView('merchant')}>处理订单</button>
        <button className={view === 'merchant-messages' ? 'active' : ''} onClick={() => setView('merchant-messages')}>店铺消息</button>
        {member?.role === 'OWNER' && <button className={view === 'products' ? 'active' : ''} onClick={() => setView('products')}>商品与库存</button>}<button className={view==='merchant-disputes'?'active':''} onClick={()=>setView('merchant-disputes')}>售后争议</button>{member?.role==='OWNER'&&<><button className={view==='merchant-reviews'?'active':''} onClick={()=>setView('merchant-reviews')}>购买评价</button><button className={view==='merchant-analytics'?'active':''} onClick={()=>setView('merchant-analytics')}>经营报表</button></>}</div>}<div key={`${account?.id ?? 'public'}-${shop}-${view}`}>
    {view==='platform'&&access.data?.platform_enabled&&<PlatformWorkbench client={client}/>} {view==='favorites'&&account?.customer_enabled&&<Favorites client={client}/>} {view==='cases'&&account?.customer_enabled&&<CustomerCases client={client}/>} {view==='merchant-disputes'&&member&&<Disputes client={client} shop={shop}/>} {view==='merchant-reviews'&&member?.role==='OWNER'&&<><h1>购买评价与回复</h1><Reviews client={client} path={`/merchant/shops/${shop}/reviews`} merchant/></>} {view==='merchant-analytics'&&member?.role==='OWNER'&&<AnalyticsPanel client={client} shop={shop}/>}
    {view === 'account' && account && <AccountCenter client={client} allowAccountWrites={policy.allowAccountWrites} publicDemo={policy.publicDemo} customer={account.customer_enabled} onPasswordChanged={clearSession} onIdentityRefresh={refreshIdentity}/>} {view === 'review' && account && !account.demo_enabled && profile.data?.review_enabled && <Applications client={client} review/>}
    {view === 'catalog' && <Catalog client={client} customer={!!account?.customer_enabled} onCart={() => setView('cart')}/>} {view === 'cart' && account?.customer_enabled && <CartPage client={client} onOrders={() => setView('orders')}/>} {view === 'orders' && account?.customer_enabled && <Orders client={client}/>} {view === 'merchant' && member && <Orders client={client} shop={shop} owner={member.role === 'OWNER'}/>} {view === 'products' && member?.role === 'OWNER' && <MerchantProducts client={client} shop={shop}/>} {view === 'messages' && account?.customer_enabled && <Messages client={client}/>} {view === 'merchant-messages' && member && <Messages client={client} shop={shop} shopName={member.shop_name}/>} {view === 'demo' && account?.demo_enabled && <Demo client={client}/>}</div>
    </main>
    <footer>
    <div className="brand">拾物集 <span>把生活，过成喜欢的样子。</span>
    </div>
    <p>COMMERCE LAB / 模拟交易与配送 · 无真实资金流转</p>
    </footer>
    </div>;
}
