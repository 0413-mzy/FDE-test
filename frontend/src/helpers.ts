import type { CaseType, Order, OrderLine } from './types';
export const money = (n: number) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(n / 100);
export const time = (s: string) => new Date(s).toLocaleString('zh-CN', { hour12: false });
const names: Record<string, string> = { ACTIVE:'有效', SUSPENDED:'已暂停', HIDDEN:'已隐藏', OPEN:'待平台处理', RESOLVED:'已处理', DISMISSED:'已驳回', UPHELD:'维持原决定', OVERTURNED:'支持售后申请', WITHDRAWN:'已撤回', REQUESTED: '待商家审核', REJECTED: '已拒绝', REFUND_PENDING: '待完成退款', AWAITING_RETURN: '待登记退货', RETURN_IN_TRANSIT: '退货运输中', UNSHIPPED_REFUND: '未发货退款', RETURN_REFUND: '退货退款', PARTIALLY_REFUNDED: '部分退款', REFUNDED: '已退款', PENDING_PAYMENT: '待付款', READY_TO_SHIP: '待发货', PARTIALLY_SHIPPED: '部分发货', SHIPPED: '已发货', COMPLETED: '已完成', CANCELLED: '已取消', UNPAID: '未付款', PAID: '已付款', PENDING: '处理中', SUCCEEDED: '成功', FAILED: '失败', COLLECTED: '已揽收', OUT_FOR_DELIVERY: '派送中', TRANSPORT_DELAY: '运输延误', DELIVERY_FAILED: '派送失败', IN_TRANSIT: '运输中', DELIVERED: '已送达', EXCEPTION: '物流异常', DRAFT: '草稿', PUBLISHED: '已上架', ARCHIVED: '已归档' };
export const label = (s: string) => names[s] ?? s;

export const hasActiveCase = (order: Pick<Order, 'after_sale_cases'>) =>
    !!order.after_sale_cases?.some(c => !['COMPLETED', 'REJECTED', 'CANCELLED'].includes(c.state));
export function refundableQuantity(order: Pick<Order, 'shipments'>, line: OrderLine, type: CaseType, now = Date.now()) {
    if (type === 'UNSHIPPED_REFUND') return Math.max(0, line.quantity - line.shipped_qty - line.refunded_unshipped_qty);
    const shipments = order.shipments?.filter(s => s.lines.some(l => l.order_line_id === line.id)) ?? [];
    if (!shipments.length || shipments.some(s => s.status !== 'DELIVERED' || !s.delivered_at)) return 0;
    const delivered = Math.max(...shipments.map(s => Date.parse(s.delivered_at!)));
    if (!Number.isFinite(delivered) || now > delivered + 14 * 24 * 60 * 60 * 1000) return 0;
    return Math.max(0, line.shipped_qty - line.refunded_shipped_qty);
}

export type DemoInfo = { enabled: boolean; accounts: string[]; password: string | null };
export function demoPolicy(info?: DemoInfo) {
    return { publicDemo: info?.enabled === true, allowAccountWrites: info?.enabled === false };
}

export type LogisticsAction = {kind: string; reason?: string | null; title: string};
export type LogisticsPayload = {expected_version: number; event_id: string; kind: string; reason: string | null; description: string; location: string | null; occurred_at: string};
export function logisticsActions(shipment: {status: string; exception_reason?: string | null; exception_from_status?: string | null}): LogisticsAction[] {
    switch(shipment.status) {
        case 'SHIPPED': return [{kind:'COLLECTED',title:'模拟揽收'}];
        case 'COLLECTED': return [{kind:'IN_TRANSIT',title:'开始运输'}, {kind:'EXCEPTION',reason:'TRANSPORT_DELAY',title:'运输延误'}];
        case 'IN_TRANSIT': return [{kind:'IN_TRANSIT',title:'记录运输轨迹'}, {kind:'OUT_FOR_DELIVERY',title:'开始派送'}, {kind:'EXCEPTION',reason:'TRANSPORT_DELAY',title:'运输延误'}];
        case 'OUT_FOR_DELIVERY': return [{kind:'DELIVERED',title:'模拟签收'}, {kind:'EXCEPTION',reason:'DELIVERY_FAILED',title:'派送失败'}];
        case 'EXCEPTION': return [{kind: shipment.exception_reason === 'DELIVERY_FAILED' ? 'OUT_FOR_DELIVERY' : shipment.exception_from_status ?? 'IN_TRANSIT',title: shipment.exception_reason === 'DELIVERY_FAILED' ? '重新派送' : '恢复物流'}];
        default: return [];
    }
}
export function logisticsPayload(version: number, action: Pick<LogisticsAction,'kind'|'reason'>, description: string, location: string, localTime: string, now = new Date(), eventId = crypto.randomUUID()): LogisticsPayload {
    return {expected_version:version,event_id:eventId,kind:action.kind,reason:action.reason ?? null,description:description.trim(),location:location.trim() || null,occurred_at:localTime ? new Date(localTime).toISOString() : now.toISOString()};
}
export function logisticsReplay(event: {kind: string; request_version: number | null; event_id: string; reason: string | null; description: string; location: string | null; occurred_at: string}): LogisticsPayload | null {
    if(event.request_version === null || event.kind === 'SHIPPED') return null;
    return {expected_version:event.request_version,event_id:event.event_id,kind:event.kind,reason:event.reason,description:event.description,location:event.location,occurred_at:event.occurred_at};
}

export type QuerySnapshot<T, C> = {data?: T; loading: boolean; error?: unknown; client?: C; path?: string};
export function queryRefreshState<T,C>(previous: QuerySnapshot<T,C>, client: C, path: string, retainData: boolean, error?: unknown): QuerySnapshot<T,C> {
    const data = retainData && previous.client === client && previous.path === path ? previous.data : undefined;
    return {data,client,path,loading:error === undefined,error};
}
