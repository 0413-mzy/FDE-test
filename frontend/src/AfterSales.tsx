import { useState } from 'react';
import { ApiError, CommerceClient } from './client';
import type { CaseType, CaseView, Order } from './types';
import { hasActiveCase, label, money, refundableQuantity, time } from './helpers';
import { ErrorBox, Status } from './ui';

export function AfterSales({client, order: o, path, merchant, owner, onChange}: {client: CommerceClient; order: Order; path: string; merchant: boolean; owner: boolean; onChange: () => void}) {
    const [type, setType] = useState<CaseType>('UNSHIPPED_REFUND'), [reason,setReason] = useState(''), [quantities,setQuantities] = useState<Record<string,number>>({}), [error,setError] = useState<unknown>(), [busy,setBusy] = useState(false);
    async function action(suffix: string, body: unknown) {
        setBusy(true); setError(undefined);
        try {await client.request(path + '/after-sales' + suffix, 'POST', body); setReason(''); setQuantities({}); onChange();}
        catch (e) {
            setError(e);
            // Reconcile the authorized record without replaying a stale write.
            if (e instanceof ApiError && e.code === 'VERSION_CONFLICT') onChange();
        }
        finally {setBusy(false);}
    }
    const canRequest = !merchant && !hasActiveCase(o) && ['PAID','PARTIALLY_REFUNDED'].includes(o.financial_status);
    const lines = o.lines ?? [];
    return <section className="after-sales">
        <h2>售后与退款 <small>SIMULATED REFUNDS</small></h2>
        <p className="muted">金额由服务器按购买时单价与申请数量计算。退货需相关包裹全部送达，申请窗口为送达后 14 天。</p>
        <ErrorBox error={error}/>
        {!o.after_sale_cases?.length && <p className="muted">还没有售后记录。</p>}
        {o.after_sale_cases?.map(c => <CaseCard key={`${c.id}-${c.version}`} c={c} order={o} merchant={merchant} owner={owner} busy={busy} onAction={(suffix,body) => action(`/${c.id}${suffix}`,body)}/>)}
        {merchant && !owner && <p className="muted">员工可读取售后与发送消息；审核、收退货和退款由店主处理。</p>}
        {hasActiveCase(o) && <p className="warning">当前售后处理完成、拒绝或撤销后，才可再次申请；活动售后期间不能修改地址或确认收货。</p>}
        {canRequest && <form className="panel" data-testid="after-sale-request" onSubmit={e => {e.preventDefault(); action('',{expected_version:o.version,type,reason,lines:Object.entries(quantities).filter(([,n])=>n>0).map(([order_line_id,quantity])=>({order_line_id,quantity}))});}}>
            <h3>申请售后</h3>
            <label>售后类型<select value={type} onChange={e => {setType(e.target.value as CaseType);setQuantities({});}}><option value="UNSHIPPED_REFUND">未发货退款</option><option value="RETURN_REFUND">退货退款</option></select></label>
            <div className="field-grid">{lines.map(l => {const max=refundableQuantity(o,l,type); return <label key={l.id}>{l.title} · 可申请 {max} 件<input aria-label={`${l.title}售后数量`} type="number" min={0} max={max} disabled={max===0} value={quantities[l.id]??0} onChange={e=>setQuantities({...quantities,[l.id]:Number(e.target.value)})}/></label>;})}</div>
            <label>售后原因<textarea required maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/></label>
            <button disabled={busy || !reason.trim() || !Object.values(quantities).some(n=>n>0)}>提交售后申请</button>
        </form>}
    </section>;
}
function CaseCard({c,order,merchant,owner,busy,onAction}: {c:CaseView;order:Order;merchant:boolean;owner:boolean;busy:boolean;onAction:(suffix:string,body:unknown)=>void}) {
    const [reason,setReason] = useState(''), [tracking,setTracking]=useState(''), [restock,setRestock]=useState('');
    const pending = c.refund_attempts.some(a=>a.state==='PENDING');
    const failed = c.refund_attempts.some(a=>a.state==='FAILED');
    return <article className="case-card panel" data-testid="after-sale-case" data-case-id={c.id}>
        <div className="section-head"><h3>{label(c.type)}</h3><Status value={c.state}/></div>
        <small>售后 {c.id} · 版本 {c.version} · {time(c.created_at)}</small>
        <p>申请退款 {money(c.requested_amount_minor)} · {c.reason}</p>
        <ul>{c.lines.map(l=><li key={l.order_line_id}>{order.lines?.find(x=>x.id===l.order_line_id)?.title??l.order_line_id} × {l.quantity}</li>)}</ul>
        {c.decision_reason && <p>商家审核说明：{c.decision_reason}</p>}
        {!merchant && ['REQUESTED','AWAITING_RETURN'].includes(c.state) && <button className="subtle" disabled={busy} onClick={()=>onAction('/withdraw',{expected_version:c.version})}>撤销售后申请</button>}
        {!merchant && c.state==='AWAITING_RETURN' && <form onSubmit={e=>{e.preventDefault();onAction('/return',{expected_version:c.version,tracking_number:tracking});}}><label>模拟退货运单<input required maxLength={100} value={tracking} onChange={e=>setTracking(e.target.value)}/></label><button disabled={busy || !tracking.trim()}>登记模拟退货</button></form>}
        {owner && c.state==='REQUESTED' && <div><label>审核说明<textarea required maxLength={500} value={reason} onChange={e=>setReason(e.target.value)}/></label><div className="case-actions"><button disabled={busy || !reason.trim()} onClick={()=>onAction('/decision',{expected_version:c.version,decision:'APPROVE',reason})}>批准售后申请</button><button className="subtle" disabled={busy || !reason.trim()} onClick={()=>onAction('/decision',{expected_version:c.version,decision:'REJECT',reason})}>拒绝售后申请</button></div></div>}
        {c.return_shipment && <p>模拟退货：{c.return_shipment.tracking_number} · {c.return_shipment.state==='RECEIVED'?'已收货':'运输中'}{c.return_shipment.restock!==null ? ` · ${c.return_shipment.restock?'已回库':'不回库'}`:''}</p>}
        {owner && c.state==='RETURN_IN_TRANSIT' && <form onSubmit={e=>{e.preventDefault();onAction('/receive-return',{expected_version:c.version,restock:restock==='yes'});}}><label>退货回库决定<select required value={restock} onChange={e=>setRestock(e.target.value)}><option value="">请明确选择</option><option value="yes">可售 · 回库</option><option value="no">不可售 · 不回库</option></select></label><p className="muted">一次确认收到全部申请数量；回库发生于收退货时，退款失败不会撤销收货事实。</p><button disabled={busy || !restock}>确认收到全部退货</button></form>}
        {owner && c.state==='REFUND_PENDING' && <button disabled={busy || pending} onClick={()=>onAction('/refunds',{expected_version:c.version})}>{failed?'重新发起模拟退款':'发起模拟退款'}</button>}
        {c.state==='REFUND_PENDING' && <p className="muted">店主发起退款后，PENDING 不会自动成功。需独立登录 demo 账号，在模拟事件台手动提交成功或失败结果，再刷新订单。</p>}
        {c.refund_attempts.map(a=><div className="attempt" key={a.id}><span className="simulation">模拟退款</span><Status value={a.state}/><strong>{money(a.amount_minor)}</strong><small>尝试 {a.id} · {time(a.created_at)}{a.failure_code?` · ${a.failure_code}`:''}</small></div>)}
    </article>;
}
