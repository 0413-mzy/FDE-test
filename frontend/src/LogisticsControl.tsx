import {useState} from 'react';
import {CommerceClient} from './client';
import {label, time, logisticsActions, logisticsPayload, logisticsReplay} from './helpers';
import type {LogisticsAction, LogisticsPayload} from './helpers';
import type {DemoShipment, Page, TrackingEvent} from './types';
import {useQuery} from './useQuery';
import {ErrorBox, Pagination, Status} from './ui';

export function TrackingTimeline({events}: {events: TrackingEvent[]}) {
    return <ol className="timeline">{events.map(e => <li key={e.id}>
        <strong>{e.kind === 'SHIPPED' ? '已发货 · 待揽收' : label(e.kind)}{e.reason ? ` · ${label(e.reason)}` : ''}</strong>
        <p>{e.description}{e.location ? ` · 地点：${e.location}` : ''}</p>
        <time>发生：{time(e.occurred_at)} · 上报：{time(e.created_at)} · 序号 {e.sequence}</time>
        <small className="muted">模拟承运商 · 操作者 {e.actor_id ? e.actor_id.slice(0,8) : '历史记录未保存'}{e.status_applied === false ? ' · 延迟上报，仅补充轨迹，未改变当前状态' : e.status_applied === null ? ' · 历史记录未保存状态应用标记' : ''}</small>
    </li>)}</ol>;
}

export function LogisticsControl({client}: {client: CommerceClient}) {
    const [offset,setOffset] = useState(0), [filter,setFilter] = useState(''), [selected,setSelected] = useState('');
    const list = useQuery<Page<DemoShipment>>(client,`/demo/shipments?limit=20&offset=${offset}${filter ? `&status=${filter}` : ''}`);
    const detail = useQuery<DemoShipment>(client,`/demo/shipments/${selected}`, !!selected, "", true);
    return <section className="panel logistics-control">
        <div className="section-head"><h2>物流场景控制</h2><button className="subtle" onClick={()=>{list.refresh();detail.refresh();}}>刷新包裹</button></div>
        <p className="muted">demo 账号手动模拟承运商。物流签收后，客户仍需单独确认订单收货。这里可查看所有包裹，包括已签收包裹。</p>
        <label>包裹状态筛选<select value={filter} onChange={e=>{setFilter(e.target.value);setOffset(0);}}><option value="">全部包裹</option>{['SHIPPED','COLLECTED','IN_TRANSIT','OUT_FOR_DELIVERY','EXCEPTION','DELIVERED'].map(s=><option key={s} value={s}>{label(s)}</option>)}</select></label>
        <ErrorBox error={list.error ?? detail.error}/>{list.loading && <p>正在读取包裹…</p>}
        <div className="list">{list.data?.items.map(s=><button className="subtle parcel-select" key={s.id} data-shipment-id={s.id} onClick={()=>setSelected(s.id)} aria-pressed={selected===s.id}>{s.tracking_number} · {label(s.status)}</button>)}</div>
        {list.data?.items.length===0 && <p>没有符合筛选条件的包裹。</p>}
        <Pagination offset={offset} hasMore={list.data?.has_more ?? false} onChange={setOffset}/>
        {selected && detail.loading && <p>正在读取物流详情…</p>}
        {detail.data && <ParcelControl key={detail.data.id} client={client} shipment={detail.data} refreshing={detail.loading || !!detail.error} onChange={()=>{list.refresh();detail.refresh();}}/>}
    </section>;
}

function ParcelControl({client,shipment:s,refreshing,onChange}: {client: CommerceClient; shipment: DemoShipment; refreshing: boolean; onChange:()=>void}) {
    const [description,setDescription] = useState(''), [location,setLocation] = useState(''), [occurred,setOccurred] = useState(''), [lateKind,setLateKind] = useState('');
    const [busy,setBusy] = useState(false), [error,setError] = useState<unknown>(), [result,setResult] = useState(''), [last,setLast] = useState<LogisticsPayload|null>(null);
    const actions = logisticsActions(s);
    const disabled = busy || refreshing;
    const reached = [...new Set(s.events.filter(e=>e.status_applied!==false && ['COLLECTED','IN_TRANSIT','OUT_FOR_DELIVERY','DELIVERED'].includes(e.kind)).map(e=>e.kind))];
    const storedReplay = [...s.events].reverse().map(logisticsReplay).find(p=>p!==null) ?? null;
    const repeat = last ?? storedReplay;
    async function submit(payload: LogisticsPayload) {
        setBusy(true);setError(undefined);setResult('');setLast(payload);
        try {
            const r = await client.request<{status:string;status_applied:boolean}>(`/demo/shipments/${s.id}/events`,'POST',payload);
            setResult(`已记录模拟事件：${label(r.status)}${r.status_applied === false ? '；延迟轨迹未改变当前状态' : ''}`);
            setDescription('');setOccurred('');onChange();
        } catch(e) {setError(e);} finally {setBusy(false);}
    }
    function record(action: LogisticsAction) {
        if(!description.trim()) {setError(new Error('请填写物流描述'));return;}
        try {void submit(logisticsPayload(s.version,action,description,location,occurred));} catch(e){setError(e);}
    }
    return <article className="shipment" data-demo-kind="SHIPMENT" data-demo-id={s.id}>
        <div className="section-head"><h3>{s.tracking_number}</h3><Status value={s.status}/></div><p className="mono">包裹编号：{s.id}</p>
        {s.status==='EXCEPTION' && <p>异常原因：{s.exception_reason ? label(s.exception_reason) : '历史原因未保存'} · 发生前状态：{s.exception_from_status ? label(s.exception_from_status) : '历史状态未保存；可恢复运输'}</p>}
        {refreshing && <p className="muted">物流详情正在刷新或读取失败；新事件暂不可提交，已保存的原事件仍可重复上报。</p>}
        <ErrorBox error={error}/>{result && <p role="status" className="success">{result}</p>}
        {(actions.length>0 || reached.length>0) && <div className="field-grid">
            <label>物流描述<input required maxLength={500} value={description} onChange={e=>setDescription(e.target.value)}/></label>
            <label>事件地点<input maxLength={200} value={location} onChange={e=>setLocation(e.target.value)} placeholder="可选：分拨中心或配送站"/></label>
            <label>事件发生时间（本地时间；留空使用提交时刻）<input type="datetime-local" step="0.001" value={occurred} onChange={e=>setOccurred(e.target.value)}/></label>
        </div>}
        <div className="actions">{actions.map(a=><button key={`${a.kind}-${a.reason}`} disabled={disabled || !description.trim()} onClick={()=>record(a)}>{a.title}</button>)}</div>
        {s.status==='DELIVERED' && <p>包裹已模拟签收，不能重新开启配送。</p>}
        {reached.length>0 && <details><summary>补充延迟上报轨迹</summary><p>仅补充已有阶段，发生时间须早于最新事实，不回退当前状态。</p><label>已记录阶段<select value={lateKind} onChange={e=>setLateKind(e.target.value)}><option value="">请选择已有阶段</option>{reached.map(k=><option key={k} value={k}>{label(k)}</option>)}</select></label><button disabled={disabled || !lateKind || !occurred || !description.trim() || Date.parse(occurred)>=Math.max(...s.events.map(e=>Date.parse(e.occurred_at)))} onClick={()=>record({kind:lateKind,title:'补充轨迹'})}>上报延迟轨迹</button></details>}
        <button className="subtle" disabled={busy || !repeat} onClick={()=>{if(repeat)void submit(repeat);}}>重复上报同一事件</button><small className="muted">复用原事件编号、版本、时间、地点与描述；成功后不会重复写入。</small>
        <TrackingTimeline events={s.events}/>
    </article>;
}
