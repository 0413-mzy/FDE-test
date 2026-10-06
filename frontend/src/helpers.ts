export const money = (n: number) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(n / 100);
export const time = (s: string) => new Date(s).toLocaleString('zh-CN', { hour12: false });
const names: Record<string, string> = { PENDING_PAYMENT: '待付款', READY_TO_SHIP: '待发货', PARTIALLY_SHIPPED: '部分发货', SHIPPED: '已发货', COMPLETED: '已完成', CANCELLED: '已取消', UNPAID: '未付款', PAID: '已付款', PENDING: '处理中', SUCCEEDED: '成功', FAILED: '失败', IN_TRANSIT: '运输中', DELIVERED: '已送达', EXCEPTION: '物流异常', DRAFT: '草稿', PUBLISHED: '已上架', ARCHIVED: '已归档' };
export const label = (s: string) => names[s] ?? s;
