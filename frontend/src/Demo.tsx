import { LogisticsControl } from './LogisticsControl';
import { time } from './helpers';
import { useQuery } from './useQuery';
import { useState } from 'react';
import { CommerceClient } from './client';
import type { DemoItem, Page } from './types';
import { ErrorBox, Status, Pagination } from './ui';
export function Demo({ client }: {
    client: CommerceClient;
}) {
    const [offset, setOffset] = useState(0);
    const q = useQuery<Page<DemoItem>>(client, `/demo/pending?limit=20&offset=${offset}`), [error, setError] = useState<unknown>(), [busy, setBusy] = useState(false), [result, setResult] = useState('');
    async function action(path: string, body: unknown) { setBusy(true); setError(undefined); setResult(''); try {
        const r = await client.request<unknown>(path, 'POST', body);
        q.refresh();
        setResult(JSON.stringify(r));
    }
    catch (e) {
        setError(e);
    }
    finally {
        setBusy(false);
    } }
    return <>
    <div className="section-head">
    <h1>模拟事件台</h1>
    <button className="subtle" onClick={q.refresh}>刷新队列</button>
    </div>
    <div className="demo-note">
    <span className="simulation">仅演示环境 · 不产生真实支付与配送</span>
    <p>处理客户已发起的模拟付款、店主已发起的模拟退款，以及商家已创建的包裹。付款与退款 PENDING 不会自动完成，请手动明确提交结果。此视图只显示脱敏事件编号。</p>
    </div>
    <ErrorBox error={error ?? q.error}/>
    {result && <p role="status" className="success">事件已记录：{result}</p>}{q.loading && <p>正在读取待处理事件…</p>}{q.data?.items.filter(i => i.kind !== 'SHIPMENT').map(i => <DemoCard key={`${i.id}-${i.version}`} item={i} busy={busy} onSubmit={body => action(i.kind === 'PAYMENT' ? `/demo/payments/${i.id}/result` : i.kind === 'REFUND' ? `/demo/refunds/${i.id}/result` : `/demo/shipments/${i.id}/events`, body)}/>)}{q.data?.items.filter(i => i.kind !== 'SHIPMENT').length === 0 && <div className="empty">没有待处理的模拟付款或退款。</div>}<Pagination offset={offset} hasMore={q.data?.has_more ?? false} onChange={setOffset}/>
    <LogisticsControl client={client}/>
    <details className="panel">
    <summary>结算指定到期订单</summary>
    <form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); action('/demo/orders/expire', { order_ids: String(f.get('ids')).split(/[\s,]+/).filter(Boolean) }); }}>
    <label>订单 UUID（逗号或换行分隔）<textarea required name="ids"/>
    </label>
    <button disabled={busy}>结算这些订单的到期预留</button>
    </form>
    </details>
    </>;
}
function DemoCard({ item: i, busy, onSubmit }: {
    item: DemoItem;
    busy: boolean;
    onSubmit: (body: unknown) => void;
}) {
    const [eventId] = useState(() => crypto.randomUUID());
    return <article className="panel" data-demo-kind={i.kind} data-demo-id={i.id}>
    <div className="section-head">
    <h3>
    {i.kind === 'PAYMENT' ? '模拟付款' : '模拟退款'} <Status value={i.state}/>
    </h3>
    <small>
    {time(i.created_at)}</small>
    </div>
    <p className="mono">
    {i.id}</p>
    <form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); onSubmit({ expected_version: i.version, result: f.get('result'), event_id: f.get('event_id') }); }}>
    <label>事件编号<input required name="event_id" defaultValue={eventId} maxLength={100}/></label>
    <label>模拟支付 / 退款结果<select name="result"><option value="SUCCEEDED">成功</option><option value="FAILED">失败</option></select></label>
    <button disabled={busy}>提交模拟结果</button>
    </form>
    </article>;
}
