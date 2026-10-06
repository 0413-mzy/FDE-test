import { label } from './helpers';
import { useState } from 'react';
import type { Address } from './types';
import { ApiError } from './client';
export function ErrorBox({ error }: {
    error: unknown;
}) {
    if (!error)
        return null;
    return <div role="alert" className="error">
    {error instanceof Error ? error.message : '请求失败'}{error instanceof ApiError && <>
        <small>
        {error.code} · 请求 {error.requestId || '未返回编号'}</small>
            {Object.keys(error.details).length > 0 && <small>
            {JSON.stringify(error.details)}</small>}</>}{error instanceof ApiError && ['VERSION_CONFLICT', 'PRICE_CHANGED', 'ORDER_EXPIRED'].includes(error.code) && <p>请刷新当前记录，核实最新状态或价格后再次明确提交。</p>}</div>;
}
export function AddressForm({ initial, onSave, button = '使用地址下单', disabled = false }: {
    initial?: Address;
    onSave: (a: Address) => void;
    button?: string;
    disabled?: boolean;
}) {
    const [a, setA] = useState<Address>(initial ?? { recipient_name: '', phone: '', country_code: 'CN', region: '', city: '', postal_code: '', address_line: '' });
    const fields: [
        keyof Address,
        string
    ][] = [['recipient_name', '收件人'], ['phone', '联系电话'], ['region', '省 / 地区'], ['city', '城市'], ['postal_code', '邮编'], ['address_line', '详细地址']];
    return <form onSubmit={e => { e.preventDefault(); onSave(a); }} className="address-form">
    <h3>收货地址 · 中国</h3>
    <div className="field-grid">
        {fields.map(([key, name]) => <label key={key}>
        {name}<input required value={a[key]} maxLength={key === 'address_line' ? 300 : key === 'phone' ? 32 : key === 'postal_code' ? 20 : 100} onChange={e => setA({ ...a, [key]: e.target.value })}/>
        </label>)}</div>
    <button disabled={disabled}>
    {button}</button>
    </form>;
}
export function Status({ value }: {
    value: string;
}) {
    return <span className={`status status-${value}`}>
    {label(value)}</span>;
}
export function Pagination({ offset, hasMore, onChange }: {
    offset: number;
    hasMore: boolean;
    onChange: (offset: number) => void;
}) {
    return <div className="pagination">
    <button className="subtle" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - 20))}>上一页</button>
    <small>第 {offset / 20 + 1} 页</small>
    <button className="subtle" disabled={!hasMore} onClick={() => onChange(offset + 20)}>下一页</button>
    </div>;
}
