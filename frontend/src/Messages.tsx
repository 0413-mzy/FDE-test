import { ConversationAI } from './ConversationAI';
import { useState } from 'react';
import { CommerceClient } from './client';
import { useQuery } from './useQuery';
import type { Conversation, Message, Page } from './types';
import { time } from './helpers';
import { ErrorBox, Pagination } from './ui';

export function ContactShop({ client, shopId, orderId = null, shopName }: {client: CommerceClient; shopId: string; orderId?: string | null; shopName?: string}) {
    const [conversation, setConversation] = useState<Conversation>();
    const [error, setError] = useState<unknown>();
    const [busy, setBusy] = useState(false);
    async function open() {
        setBusy(true); setError(undefined);
        try { setConversation(await client.request<Conversation>('/customer/conversations', 'POST', {shop_id: shopId, order_id: orderId})); }
        catch (e) { setError(e); }
        finally { setBusy(false); }
    }
    return <section className="contact-shop">
        <button className="subtle" disabled={busy} onClick={open}>{orderId ? '联系店铺 · 此订单' : '联系店铺'}</button>
        <ErrorBox error={error}/>
        {conversation && <MessageThread key={conversation.id} client={client} conversation={conversation} shopName={shopName}/>}
    </section>;
}
export function Messages({client, shop, shopName}: {client: CommerceClient; shop?: string; shopName?: string}) {
    const [offset, setOffset] = useState(0);
    const [selected, setSelected] = useState<Conversation>();
    const base = shop ? `/merchant/shops/${shop}/conversations` : '/customer/conversations';
    const q = useQuery<Page<Conversation>>(client, `${base}?limit=20&offset=${offset}`);
    return <>
        <div className="section-head"><h1>店铺消息</h1><button className="subtle" onClick={q.refresh}>刷新会话</button></div>
        <p className="muted">消息以纯文本显示。刷新获取最新记录，聊天内容不会自动执行退款或其他业务操作。</p>
        <ErrorBox error={q.error}/>
        {q.loading && <p>正在读取会话…</p>}
        <div className="conversation-list">{q.data?.items.map(c => <button key={c.id} className={`order-summary ${selected?.id === c.id ? 'selected' : ''}`} onClick={() => setSelected(c)}>
            <span><strong>{c.order_id ? `订单 ${c.order_id.slice(0,8)}` : '店铺咨询'}</strong><small>{shopName ?? `店铺 ${c.shop_id.slice(0,8)}`} · {time(c.created_at)}</small></span><small>会话 {c.id.slice(0,8)} →</small>
        </button>)}</div>
        {q.data?.items.length === 0 && <div className="empty">暂无会话。客户可以从商品或订单详情联系店铺。</div>}
        <Pagination offset={offset} hasMore={q.data?.has_more ?? false} onChange={n => {setOffset(n); setSelected(undefined);}}/>
        {selected && <MessageThread key={selected.id} client={client} conversation={selected} shop={shop} shopName={shopName}/>}
    </>;
}
function MessageThread({client, conversation: c, shop, shopName}: {client: CommerceClient; conversation: Conversation; shop?: string; shopName?: string}) {
    const [offset, setOffset] = useState(0), [body, setBody] = useState(''), [busy,setBusy] = useState(false), [error,setError] = useState<unknown>();
    const base = shop ? `/merchant/shops/${shop}/conversations/${c.id}/messages` : `/customer/conversations/${c.id}/messages`;
    const q = useQuery<Page<Message>>(client, `${base}?limit=20&offset=${offset}`);
    async function send(e: React.FormEvent) {
        e.preventDefault(); setBusy(true); setError(undefined);
        try {await client.request(base, 'POST', {body}); setBody(''); q.refresh();}
        catch (e) {setError(e);}
        finally {setBusy(false);}
    }
    return <section className="message-thread panel" data-testid="conversation-thread">
        <div className="section-head"><h2>{shopName ?? '店铺会话'}</h2><button className="subtle" onClick={q.refresh}>刷新消息</button></div>
        <p className="muted">{c.order_id ? `关联订单 ${c.order_id}` : '一般店铺咨询'} · 会话 {c.id}</p>
        <ErrorBox error={error ?? q.error}/>
        {q.loading && <p>正在读取消息…</p>}
        <ol className="message-list">{q.data?.items.map(m => <li key={m.id} className={`message message-${m.sender_side}`}><small>{m.sender_side === 'CUSTOMER' ? '客户' : '店铺'} · {time(m.created_at)}</small><p>{m.body}</p></li>)}</ol>
        {q.data?.items.length === 0 && <p className="muted">还没有消息。</p>}
        <p className="muted">按发送时间从早到晚排列。发送后刷新当前页；较新的消息可在下一页查看。</p>
        <Pagination offset={offset} hasMore={q.data?.has_more ?? false} onChange={setOffset}/>
        {shop && <ConversationAI client={client} shop={shop} conversation={c.id} revision={JSON.stringify(q.data)} onInsert={setBody}/>}
        <form onSubmit={send}><label>消息内容<textarea required maxLength={2000} value={body} onChange={e => setBody(e.target.value)}/></label><button disabled={busy || !body.trim()}>发送消息</button></form>
    </section>;
}
