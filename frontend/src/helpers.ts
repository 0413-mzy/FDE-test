import type { CaseType, Order, OrderLine } from './types';
export const money = (n: number) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(n / 100);
export const time = (s: string) => new Date(s).toLocaleString('zh-CN', { hour12: false });
const names: Record<string, string> = { REQUESTED: '待商家审核', REJECTED: '已拒绝', REFUND_PENDING: '待完成退款', AWAITING_RETURN: '待登记退货', RETURN_IN_TRANSIT: '退货运输中', UNSHIPPED_REFUND: '未发货退款', RETURN_REFUND: '退货退款', PARTIALLY_REFUNDED: '部分退款', REFUNDED: '已退款', PENDING_PAYMENT: '待付款', READY_TO_SHIP: '待发货', PARTIALLY_SHIPPED: '部分发货', SHIPPED: '已发货', COMPLETED: '已完成', CANCELLED: '已取消', UNPAID: '未付款', PAID: '已付款', PENDING: '处理中', SUCCEEDED: '成功', FAILED: '失败', IN_TRANSIT: '运输中', DELIVERED: '已送达', EXCEPTION: '物流异常', DRAFT: '草稿', PUBLISHED: '已上架', ARCHIVED: '已归档' };
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
