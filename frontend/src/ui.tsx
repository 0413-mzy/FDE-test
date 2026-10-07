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
    {error instanceof Error ? error.message : '请求失败'}{error instanceof ApiError && error.code === 'MAILBOX_DELIVERY_FAILED' && <p>申请已记录，但本机模拟邮件投递失败。请先恢复本机邮件服务，再选择“重发验证”；恢复密码请重新选择“忘记密码”提交。原请求重试不会投递新邮件。</p>}{error instanceof ApiError && <>
        <small>
        {error.code} · 请求 {error.requestId || '未返回编号'}</small>
            {Object.keys(error.details).length > 0 && <small>
            {JSON.stringify(error.details)}</small>}</>}{error instanceof ApiError && ['DEMO_ACTION_DISABLED', 'PUBLIC_DEMO_DISABLED'].includes(error.code) && <p>公开演示已关闭此账号修改操作。请使用共享访客账号体验购物、店铺与模拟业务。</p>}{error instanceof ApiError && ['IMAGE_STORAGE_LIMIT', 'DEMO_STORAGE_QUOTA_EXCEEDED', 'IMAGE_STORAGE_QUOTA_EXCEEDED', 'DEMO_QUOTA_EXCEEDED'].includes(error.code) && <p>共享演示存储已满，请删除不用的商品图片后重试，或联系演示管理员。</p>}{error instanceof ApiError && ['VERSION_CONFLICT', 'PRICE_CHANGED', 'ORDER_EXPIRED'].includes(error.code) && <p>请刷新当前记录，核实最新状态或价格后再次明确提交。</p>}</div>;
}
export function AddressForm({ initial, onSave, button = '使用地址下单', disabled = false, onDraftChange }: {
    initial?: Address;
    onSave: (a: Address) => void;
    button?: string;
    disabled?: boolean;
    onDraftChange?: (a: Address) => void;
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
        {name}<input required value={a[key]} maxLength={key === 'address_line' ? 300 : key === 'phone' ? 32 : key === 'postal_code' ? 20 : 100} onChange={e => { const next = { ...a, [key]: e.target.value }; setA(next); onDraftChange?.(next); }}/>
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
