import {useCallback, useEffect, useState} from 'react';
import type {CommerceClient} from './client';
import {ErrorBox} from './ui';
import {createLatestRead,createReadRefresh,dataQuery,fieldChanges,recordNavigationFilters,resetListingFilters} from './data-center';

type RecordData=Record<string,unknown>;
type Page<T>={items:T[];total:number;limit:number;offset:number};
type Resource={resource:string;label:string;count:number;fields:string[];history_mode:string};
type History={id:number;entity_table:string;entity_id:string;operation:string;before_data:RecordData|null;after_data:RecordData|null;actor_username:string|null;recorded_at:string;action:string;reason:string|null;changed_fields:string[]};
type Relation={resource:string;id?:string;filter?:{field:string;value:string};field:string;direction:string};
type Detail={resource:string;record:RecordData|null;deleted:boolean;fields:string[];related:Relation[];history:Page<History>;history_mode:string};
const base='/platform/data';
const time=(value:string)=>`${new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Kuala_Lumpur',dateStyle:'short',timeStyle:'medium'}).format(new Date(value))} (马来西亚) · ${value}`;
const fieldLabels:Record<string,string>={location:'物流地点',reason:'原因',exception_reason:'物流异常原因',exception_from_status:'异常前状态',status_applied:'是否影响当前状态',request_version:'请求版本',occurred_at:'事件发生时间',source:'来源',id:'编号',created_at:'创建时间',updated_at:'更新时间',status:'状态',state:'处理状态',title:'商品名',body:'正文',quantity:'数量',username:'账号名',display_name:'显示名称',phone:'电话',email:'邮箱',name:'名称',description:'说明',currency:'币种',total_minor:'订单总额',amount_minor:'金额',unit_price_minor:'单价',on_hand:'现有库存',reserved:'预留库存',active:'有效',version:'版本',role:'角色',rating:'评分',reply:'店铺回复',model:'AI模型',result:'AI结果',usage:'AI用量',finished_at:'完成时间',financial_status:'财务状态',tracking_number:'物流编号',simulation:'模拟事件',actor_id:'操作者编号',customer_id:'顾客编号',shop_id:'店铺编号',product_id:'商品编号',order_id:'订单编号',conversation_id:'会话编号',sku_id:'规格编号',order_line_id:'订单明细编号',case_id:'售后编号',message_count:'消息数'};
const fieldLabel=(field:string)=>fieldLabels[field]??(field.endsWith('_id')?'关联编号':field.endsWith('_at')?'业务时间':field.endsWith('_minor')?'金额分值':field);
function displayValue(field:string,value:unknown,row:RecordData):string {
 if(typeof value==='string'&&field.endsWith('_at')&&!Number.isNaN(Date.parse(value)))return time(value);
 if(typeof value==='number'&&field.endsWith('_minor'))return `${row.currency??'币种见关联记录'} · ${(value/100).toFixed(2)}（${value} 分）`;
 return valueText(value);
}
function valueText(value:unknown):string {return value===undefined?'未记录':value===null?'空':typeof value==='object'?JSON.stringify(value,null,2):String(value);}
function HistoryRows({page,onRecord}:{page:Page<History>;onRecord:(name:string,id:string)=>void}) {
 return <div className="data-history">{page.items.map(row=><article className="account-section" key={row.id}><button onClick={()=>onRecord(row.entity_table,row.entity_id)}>{row.entity_table} · {row.entity_id}</button><p>{time(row.recorded_at)} · {row.operation} · {row.actor_username??'未记录操作者'} · {row.action}</p>{row.operation==='BASELINE'&&<p>升级当时的当前状态基线；更早的值未记录。</p>}<p>原因：{row.reason??'未记录'}</p><table><thead><tr><th>字段</th><th>修改前</th><th>修改后</th></tr></thead><tbody>{fieldChanges(row.before_data,row.after_data).map(change=><tr key={change.field}><td>{fieldLabel(change.field)}<small> · {change.field}</small></td><td><pre>{displayValue(change.field,change.before,row.before_data??{})}</pre></td><td><pre>{displayValue(change.field,change.after,row.after_data??{})}</pre></td></tr>)}</tbody></table>{!fieldChanges(row.before_data,row.after_data).length&&<p>可见业务字段没有变化。</p>}</article>)}</div>;
}
export function DataCenter({client}:{client:CommerceClient}) {
 const [resources,setResources]=useState<Resource[]>([]),[environment,setEnvironment]=useState(''),[resource,setResource]=useState('commerce_orders'),[recordId,setRecordId]=useState(''),[global,setGlobal]=useState(false),[offset,setOffset]=useState(0),[relation,setRelation]=useState<{field:string;value:string}>(),[loadedKey,setLoadedKey]=useState(''),[q,setQ]=useState(''),[status,setStatus]=useState(''),[from,setFrom]=useState(''),[to,setTo]=useState(''),[actor,setActor]=useState(''),[operation,setOperation]=useState(''),[automatic,setAutomatic]=useState(false),[last,setLast]=useState(''),[error,setError]=useState<unknown>(),[loading,setLoading]=useState(false),[page,setPage]=useState<Page<RecordData>>(),[detail,setDetail]=useState<Detail>(),[history,setHistory]=useState<Page<History>>();
 const selected=resources.find(r=>r.resource===resource);
 const key=JSON.stringify([global,resource,recordId,offset,q,status,from,to,actor,operation,relation]);
 type Loaded={key:string;access:{environment:string;public_demo:boolean};directory:{items:Resource[]};result:Page<RecordData>|Detail|Page<History>;global:boolean;recordId:string};
 const [reader]=useState(()=>createLatestRead<Loaded>(loaded=>{
  setEnvironment(`${loaded.access.environment} · ${loaded.access.public_demo?'公开演示环境 / 私有入口':'本地私有环境'} · 只读 · 模拟交易`);setResources(loaded.directory.items);
  if(loaded.global)setHistory(loaded.result as Page<History>);else if(loaded.recordId)setDetail(loaded.result as Detail);else setPage(loaded.result as Page<RecordData>);
  setLoadedKey(loaded.key);setLast(new Date().toISOString());setError(undefined);setLoading(false);
 },e=>{setError(e);setLoading(false);}));
 const load=useCallback(()=>{
  setLoading(true);
  return reader(async()=>{
   const iso=(v:string)=>v?new Date(v).toISOString():'';
   const filters=global?{limit:50,offset,actor,operation,from:iso(from),to:iso(to)}:{limit:50,offset,q,status,from:iso(from),to:iso(to),...relation};
   const path=global?`${base}/history${dataQuery(filters)}`:recordId?`${base}/resources/${resource}/${encodeURIComponent(recordId)}${dataQuery({limit:50,offset})}`:`${base}/resources/${resource}${dataQuery(filters)}`;
   const [access,directory,result]=await Promise.all([client.request<{environment:string;public_demo:boolean}>(`${base}/access`),client.request<{items:Resource[]}>(`${base}/resources`),client.request<Page<RecordData>|Detail|Page<History>>(path)]);
   return {key,access,directory,result,global,recordId};
  });
 },[client,global,resource,recordId,offset,q,status,from,to,actor,operation,relation,reader,key]);
 useEffect(()=>{const id=window.setTimeout(()=>void load(),0);return()=>window.clearTimeout(id);},[load]);
 useEffect(()=>{if(!automatic)return;return createReadRefresh(load,()=>document.visibilityState==='visible', (fn,ms)=>window.setInterval(fn,ms),id=>window.clearInterval(id as number));},[automatic,load]);
 useEffect(()=>{reader.resume();return()=>reader.dispose();},[reader]);
 const current=loadedKey===key;
 const openRecord=(name:string,id:string)=>{const filters=recordNavigationFilters(resource,name,{q,status,from,to,relation});setQ(filters.q);setStatus(filters.status);setFrom(filters.from);setTo(filters.to);setRelation(filters.relation);setGlobal(false);setResource(name);setRecordId(id);setOffset(0);};
 const choose=(name:string)=>{const filters=resetListingFilters();setResource(name);setRecordId('');setOffset(0);setGlobal(false);setQ(filters.q);setStatus(filters.status);setFrom(filters.from);setTo(filters.to);setRelation(filters.relation);};
 const total=global?history?.total:recordId?detail?.history.total:page?.total;
 return <section className="data-center"><span className="eyebrow">PRIVATE BUSINESS RECORDS</span><h1>私有数据中心</h1><p>{environment||'正在确认私有权限…'}</p><p>最后成功读取：{last?time(last):'尚未成功读取'}{loading?' · 读取中…':''}</p><label><input type="checkbox" checked={automatic} onChange={e=>setAutomatic(e.target.checked)}/>每15秒自动刷新（页面隐藏时暂停）</label><button onClick={()=>void load()} disabled={loading}>刷新 / 重试</button><ErrorBox error={error}/>
 <div className="data-layout"><aside aria-label="数据目录"><button onClick={()=>{setGlobal(true);setRecordId('');setOffset(0);}}>全局记录历史</button>{resources.map(r=><button className={r.resource===resource&&!global?'active':''} key={r.resource} onClick={()=>choose(r.resource)}>{r.label} <small>{r.count} 条</small></button>)}</aside><div className="data-content"><h2>{global?'全局记录历史':selected?.label??resource}</h2>
 {!recordId&&<form className="data-filters" onSubmit={e=>{e.preventDefault();setOffset(0);void load();}}>{global?<><label>操作者<input value={actor} onChange={e=>{setActor(e.target.value);setOffset(0);}} placeholder="账号名或完整ID"/></label><label>操作<select value={operation} onChange={e=>{setOperation(e.target.value);setOffset(0);}}><option value="">全部</option>{['BASELINE','INSERT','UPDATE','DELETE'].map(v=><option key={v}>{v}</option>)}</select></label></>:<><label>ID / 姓名 / 正文关键词<input value={q} maxLength={200} onChange={e=>{setQ(e.target.value);setOffset(0);}}/></label><label>状态<input value={status} maxLength={80} onChange={e=>{setStatus(e.target.value);setOffset(0);}} disabled={!selected?.fields.some(f=>['status','state','financial_status'].includes(f))}/></label></>}<label>{global?'历史记录时间起':'创建时间起'}<input type="datetime-local" value={from} onChange={e=>{setFrom(e.target.value);setOffset(0);}}/></label><label>{global?'历史记录时间止':'创建时间止'}<input type="datetime-local" value={to} onChange={e=>{setTo(e.target.value);setOffset(0);}}/></label><button>读取筛选结果</button></form>}
 {current&&global&&history&&<HistoryRows page={history} onRecord={openRecord}/>}
 {current&&!global&&!recordId&&page&&<div className="data-table"><table><thead><tr>{selected?.fields.map(f=><th key={f}>{fieldLabel(f)}<small> · {f}</small></th>)}</tr></thead><tbody>{page.items.map(row=><tr key={String(row.id)}>{selected?.fields.map(f=><td key={f}>{f==='id'?<button onClick={()=>openRecord(resource,String(row.id))}>{String(row.id)}</button>:<pre>{displayValue(f,row[f],row)}</pre>}</td>)}</tr>)}</tbody></table>{!page.items.length&&<p>没有符合条件的记录。</p>}</div>}
 {current&&!global&&recordId&&detail&&<><button onClick={()=>{setRecordId('');setOffset(0);}}>返回记录列表</button><h3>记录详情 · {recordId}</h3>{detail.deleted&&<p>当前记录已删除；保留的历史仍可查阅。</p>}<dl>{detail.record&&Object.entries(detail.record).map(([f,v])=><div key={f}><dt>{fieldLabel(f)}<small> · {f}</small>{f.endsWith('_minor')?'（金额分值）':f.endsWith('_id')?'（关联记录ID）':f.endsWith('_at')?'（ISO时间）':''}</dt><dd><pre>{displayValue(f,v,detail.record??{})}</pre></dd></div>)}</dl><h3>关联记录</h3>{detail.related.map((r,i)=><button key={i} onClick={()=>{if(r.id)openRecord(r.resource,r.id);else{choose(r.resource);setRelation(r.filter);}}}>{resources.find(x=>x.resource===r.resource)?.label??r.resource} · {r.field} · {r.direction==='parent'?'关联对象':'关联明细'}</button>)}<h3>记录历史</h3>{detail.history_mode==='attempt_lifecycle'?<p>AI生成尝试保存自身状态、结果与用量；未记录每次状态修改的全行版本历史。</p>:<HistoryRows page={detail.history} onRecord={openRecord}/>}</>}
 <div className="data-pagination"><button disabled={loading||offset===0} onClick={()=>setOffset(Math.max(0,offset-50))}>上一页</button><span>{offset+1}–{Math.min(offset+50,total??0)} / {total??0}{recordId?' 条历史':' 条'}</span><button disabled={loading||offset+50>=(total??0)} onClick={()=>setOffset(offset+50)}>下一页</button></div>
 </div></div></section>;
}
