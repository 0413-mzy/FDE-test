import { money, time, label, hasActiveCase } from './helpers';
import { useQuery } from './useQuery';
import { useState } from 'react';
import { CommerceClient } from './client';
import type { Order } from './types';
import { AfterSales } from './AfterSales';
import { ContactShop } from './Messages';
import { AddressForm, ErrorBox, Status } from './ui';
export function OrderDetail({ client, path, merchant, owner = false, onChange }: {
    client: CommerceClient;
    path: string;
    merchant: boolean;
    owner?: boolean;
    onChange: () => void;
}) {
    const q = useQuery<Order>(client, path), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false), [editing, setEditing] = useState(false), [reason, setReason] = useState(''), [quantities, setQuantities] = useState<Record<string, number>>({});
    async function action(suffix: string, body: unknown) { setBusy(true); setError(undefined); try {
        await client.request(path + suffix, 'POST', body);
        q.refresh();
        onChange();
        setEditing(false);
        setQuantities({});
    }
    catch (e) {
        setError(e);
    }
    finally {
        setBusy(false);
    } }
    const o = q.data;
    if (!o)
        return <>
        <ErrorBox error={q.error}/>
        {q.loading && <p>正在读取详情…</p>}</>;
    const editable = !merchant && ((o.status === 'PENDING_PAYMENT' && !o.payment_expired) || (o.status === 'READY_TO_SHIP' && !o.shipments?.length && !hasActiveCase(o)));
    const shippingBlocked = o.after_sale_cases?.some(c => c.type === 'UNSHIPPED_REFUND' && !['COMPLETED','REJECTED','CANCELLED'].includes(c.state));
    const pending = o.status === 'PENDING_PAYMENT' && !o.payment_expired;
    return <section className="order-detail">
    <div className="section-head">
    <div>
    <span className="eyebrow">ORDER / {o.id}</span>
    <h2>{o.shop_name ?? `店铺 ${o.shop_id.slice(0,8)}`} · 订单详情 <Status value={o.status}/>
    </h2>
    </div>
    <button className="subtle" onClick={() => { q.refresh(); onChange(); }}>刷新详情</button>
    </div>
    <ErrorBox error={error ?? q.error}/>
    <div className="detail-facts">
    <div>订单金额<strong>
    {money(o.total_minor)}</strong>
    </div>
    <div>财务状态<strong>
    {label(o.financial_status)}</strong>
    </div>
    <div>创建时间<strong>
    {time(o.created_at)}</strong>
    </div>
    </div>
        {o.status === 'PENDING_PAYMENT' && <p className={o.payment_expired ? 'warning' : 'muted'}>
        {o.payment_expired ? '付款期限已到，请刷新并查看到期结算结果。' : `请于 ${time(o.payment_deadline)} 前完成模拟付款。`}</p>}<div className="table-wrap">
    <table>
    <thead>
    <tr>
    <th>商品快照</th>
    <th>单价</th>
    <th>购买 / 已发</th>
    {merchant && <th>本次发货</th>}</tr>
    </thead>
    <tbody>
        {o.lines?.map(l => <tr key={l.id}>
        <td>
        {l.title}<small>
        {Object.values(l.options).join(' / ')}</small>
        </td>
        <td>
        {money(l.unit_price_minor)}</td>
        <td>
        {l.quantity} / {l.shipped_qty}<small>未发退款 {l.refunded_unshipped_qty} · 已发退款 {l.refunded_shipped_qty}</small></td>
            {merchant && <td>
            <input aria-label={`${l.title}本次发货数量`} type="number" min={0} max={l.quantity - l.shipped_qty - l.refunded_unshipped_qty} value={quantities[l.id] ?? 0} onChange={e => setQuantities({ ...quantities, [l.id]: Number(e.target.value) })}/>
            </td>}</tr>)}</tbody>
    </table>
    </div>
    {merchant && shippingBlocked && <p className="warning">未发货退款正在处理中，后续发货暂停；售后拒绝、撤销或完成后可继续。</p>}{merchant && ['READY_TO_SHIP', 'PARTIALLY_SHIPPED'].includes(o.status) && !shippingBlocked && <button disabled={busy || !Object.values(quantities).some(n => n > 0)} onClick={() => action('/shipments', { expected_version: o.version, lines: Object.entries(quantities).filter(([, n]) => n > 0).map(([order_line_id, quantity]) => ({ order_line_id, quantity })) })}>确认模拟出库 · 创建包裹</button>}{o.address && <div className="address-card">
        <h3>收货信息 <small>修订 {o.address_revision}</small>
        </h3>
        <p>
        {o.address.recipient_name} · {o.address.phone}</p>
        <p>
        {o.address.region} {o.address.city} {o.address.address_line} · {o.address.postal_code}</p>
        {editable && <button className="subtle" onClick={() => setEditing(!editing)}>修改收货地址</button>}{editing && <AddressForm initial={o.address} button="保存新地址" disabled={busy} onSave={address => action('/address', { expected_version: o.version, address })}/>}</div>}{!merchant && pending && <div className="action-panel">
        <span className="simulation">模拟付款 · 不产生真实扣款</span>
        <button disabled={busy || o.payment_attempts?.some(a => a.state === 'PENDING')} onClick={() => action('/payments', { expected_version: o.version })}>发起模拟付款</button>
        <p className="muted">发起后显示 PENDING，不会自动成功。请独立登录 demo 账号，在模拟事件台手动提交付款成功或失败，然后刷新订单查看。</p>
        <form onSubmit={e => { e.preventDefault(); action('/cancel', { expected_version: o.version, reason }); }}>
        <label>取消原因<input required maxLength={500} value={reason} onChange={e => setReason(e.target.value)}/>
        </label>
        <button className="subtle" disabled={busy}>取消未付款订单</button>
        </form>
        </div>}{o.payment_attempts?.map(a => <div className="attempt" key={a.id}>
        <span className="simulation">模拟支付</span>
        <Status value={a.state}/>
        <span>
        {money(a.amount_minor)}</span>
        <small>
        {time(a.created_at)}{a.failure_code ? ` · ${a.failure_code}` : ''}</small>
        </div>)}<h3>包裹与物流 <small>SIMULATED DELIVERY</small>
    </h3>
    {!o.shipments?.length && <p className="muted">还没有出库包裹。</p>}{o.shipments?.map(s => <article className="shipment" key={s.id}>
        <div className="section-head">
        <strong>
        {s.tracking_number}</strong>
        <Status value={s.status}/>
        </div>
        <span className="simulation">模拟承运商 · 包裹 {s.id.slice(0, 8)}</span>
        <p>
        {s.lines.map(l => `${o.lines?.find(x => x.id === l.order_line_id)?.title ?? l.order_line_id.slice(0, 8)} × ${l.quantity}`).join(' / ')}</p>
        <ol className="timeline">
            {s.events.map(e => <li key={e.id}>
            <strong>
            {label(e.kind)}</strong>
            <p>
            {e.description}</p>
            <time>
            {time(e.occurred_at)} · 序号 {e.sequence}</time>
            </li>)}</ol>
        </article>)}{!merchant && o.status === 'SHIPPED' && o.shipments?.length && o.shipments.every(s => s.status === 'DELIVERED') && !hasActiveCase(o) && <button disabled={busy} onClick={() => action('/confirm-receipt', { expected_version: o.version })}>所有包裹已送达 · 确认收货</button>}<AfterSales client={client} order={o} path={path} merchant={merchant} owner={owner} onChange={() => {q.refresh(); onChange();}}/>{!merchant && <ContactShop client={client} shopId={o.shop_id} shopName={o.shop_name} orderId={o.id}/>}<small className="muted">记录版本 {o.version} · 状态与金额以服务器记录为准</small>
    </section>;
}
