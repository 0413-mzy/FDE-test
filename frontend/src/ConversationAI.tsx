import { useState } from 'react';
import type { CommerceClient } from './client';
import type { ConversationAssistance } from './types';
import { useQuery } from './useQuery';
import { ErrorBox } from './ui';
import { time } from './helpers';

export function ConversationAI({client, shop, conversation, onInsert, revision}: {client: CommerceClient; shop: string; conversation: string; onInsert: (draft: string) => void; revision: string}) {
    const path = `/merchant/shops/${shop}/conversations/${conversation}/ai-assistance`;
    const q = useQuery<ConversationAssistance>(client, path, true, revision);
    const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>();
    async function generate() {
        setBusy(true); setError(undefined);
        try {await client.request<ConversationAssistance>(path, 'POST', {}); q.refresh();}
        catch (e) {setError(e);}
        finally {setBusy(false);}
    }
    const states: Record<string, string> = {PENDING_PAYMENT: '待模拟付款', READY_TO_SHIP: '待发货', PARTIALLY_SHIPPED: '部分发货', SHIPPED: '已发货', COMPLETED: '已确认收货', CANCELLED: '已取消', COLLECTED: '已揽收', IN_TRANSIT: '运输中', OUT_FOR_DELIVERY: '派送中', EXCEPTION: '运输异常', DELIVERED: '承运商已签收', TRANSPORT_DELAY: '运输延迟', DELIVERY_FAILED: '派送失败'};
    const failures: Record<string, string> = {AI_TIMEOUT: '服务响应超时', AI_AUTH_FAILED: '服务认证失败，请联系管理员', AI_BALANCE_REQUIRED: '服务余额不足，请联系管理员', AI_RATE_LIMITED: '请求较频繁', AI_PROVIDER_FAILED: '服务暂时失败', AI_INVALID_RESPONSE: '输出未通过校验', AI_INTERRUPTED: '上次生成被中断', AI_INPUT_LIMIT: '会话超过处理范围'};
    const success = q.data?.latest_success, result = success?.result;
    const labels = {customer_needs: '客户诉求', conditions: '明确条件', commitments: '商家已承诺', unresolved: '未解决问题'} as const;
    return <section className="panel" data-testid="conversation-ai">
        <div className="section-head"><h3>AI 会话摘要</h3><button disabled={busy || !q.data?.available || q.data?.latest_attempt?.state === 'RUNNING'} onClick={generate}>{busy ? '正在生成…' : '生成／更新摘要'}</button></div>
        <p className="muted">会话和关联订单的安全物流事实交由 DeepSeek 处理。AI 生成，需人工核对；建议回复不会自动发送。</p>
        <button className="subtle" onClick={q.refresh}>刷新 AI 状态</button>
        <ErrorBox error={error ?? q.error}/>
        {q.data && !q.data.available && <p>AI 暂不可用，请联系平台管理员配置服务。</p>}
        {q.data?.stale && <p role="status">会话消息或物流已有变化，摘要待更新。</p>}
        {q.data?.latest_attempt?.state === 'RUNNING' && <p role="status">正在处理，请稍后刷新消息。</p>}
        {q.data?.latest_attempt?.state === 'FAILED' && <p role="alert">生成失败（{failures[q.data.latest_attempt.error_code ?? ''] ?? '服务暂时失败'}），可重新尝试。上次成功摘要仍保留。</p>}
        {result && <><p className="muted">生成于 {time(success!.finished_at!)} · 覆盖 {success!.message_count} 条消息</p>
            {success?.logistics_context ? <div><h4>本次使用的物流事实</h4>
                <p className="muted">生成请求时间 {time(success.created_at)} · 承运商签收与客户确认收货分开。</p>
                <p>{success.logistics_context.state === 'NO_LINKED_ORDER' ? '未关联订单；仅分析会话。' : success.logistics_context.state === 'NO_SHIPMENTS' ? '关联订单暂无包裹。' : `订单 ${success.logistics_context.order?.id} · ${states[success.logistics_context.order?.status ?? ''] ?? success.logistics_context.order?.status}`}</p>
                {success.logistics_context.shipments.map(parcel => <div key={parcel.id}><p>包裹 {parcel.id} · {states[parcel.status] ?? parcel.status} · {parcel.simulation ? '模拟物流' : '来源未明确'} {states[parcel.exception_reason ?? ''] ?? parcel.exception_reason ?? ''}</p><p className="muted">发货 {time(parcel.shipped_at)} · 承运商签收 {parcel.delivered_at ? time(parcel.delivered_at) : '暂无'}</p>{parcel.events.map(event => <p key={event.source_id} className="muted">{event.source_id} · {states[event.kind] ?? event.kind} · 发生 {time(event.occurred_at)} · 接收 {time(event.received_at)}</p>)}{parcel.events_truncated && <p>轨迹有截断，未覆盖全部历史。</p>}</div>)}
                {success.logistics_context.shipments_truncated && <p>包裹资料有截断，未覆盖全部包裹。</p>}
            </div> : <p className="muted">历史摘要的物流依据未知。</p>}
            <dl>{Object.entries(labels).map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{result[key as keyof typeof labels]}</dd></div>)}</dl>
            <h4>建议回复</h4><p>{result.draft}</p><button className="subtle" onClick={() => onInsert(result.draft)}>插入回复输入框</button>
        </>}
    </section>;
}
