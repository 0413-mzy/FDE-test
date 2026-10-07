export interface Membership {
    shop_id: string;
    shop_name: string;
    role: 'OWNER' | 'STAFF';
    shop_status: string;
}
export interface Account {
    id: string;
    username: string;
    customer_enabled: boolean;
    demo_enabled: boolean;
    shops: Membership[];
}
export interface Session {
    token: string;
    expires_at: string;
    account: Account;
}
export interface Page<T> {
    items: T[];
    limit: number;
    offset: number;
    has_more: boolean;
}
export interface SKU {
    id: string;
    sku_code: string;
    options: Record<string, string>;
    unit_price_minor: number;
    currency: string;
    price_version: number;
    version?: number;
    active: boolean;
    available: number;
}
export interface Product {
    id: string;
    shop_id: string;
    shop_name: string;
    title: string;
    description: string;
    status: string;
    version: number;
    skus: SKU[];
}
export interface CartLine {
    product_title: string;
    shop_name: string;
    options: Record<string,string>;
    sku_id: string;
    shop_id: string;
    quantity: number;
    seen_price_version: number;
    seen_price_minor: number;
    current_price_version: number;
    current_price_minor: number;
    currency: string;
    available: number;
    purchasable: boolean;
}
export interface Cart {
    id: string;
    version: number;
    lines: CartLine[];
}
export interface Address {
    recipient_name: string;
    phone: string;
    country_code: 'CN';
    region: string;
    city: string;
    postal_code: string;
    address_line: string;
}
export interface OrderLine {
    id: string;
    sku_id: string;
    title: string;
    options: Record<string, string>;
    unit_price_minor: number;
    quantity: number;
    shipped_qty: number;
    refunded_unshipped_qty: number;
    refunded_shipped_qty: number;
}
export interface Attempt {
    id: string;
    state: string;
    version: number;
    amount_minor: number;
    currency: string;
    simulation: true;
    created_at: string;
    finished_at: string | null;
    failure_code: string | null;
}
export interface Shipment {
    id: string;
    order_id: string;
    tracking_number: string;
    status: string;
    version: number;
    simulation: true;
    shipped_at: string;
    delivered_at: string | null;
    lines: {
        order_line_id: string;
        quantity: number;
    }[];
    events: {
        id: string;
        event_id: string;
        kind: string;
        description: string;
        occurred_at: string;
        sequence: number;
        source: string;
    }[];
}
export interface Order {
    id: string;
    shop_id: string;
    shop_name?: string; // Historical idempotent snapshots may omit this field.
    status: string;
    financial_status: string;
    total_minor: number;
    currency: string;
    version: number;
    created_at: string;
    payment_deadline: string;
    payment_expired: boolean;
    lines?: OrderLine[];
    address?: Address;
    address_revision?: number;
    shipments?: Shipment[];
    payment_attempts?: Attempt[];
    after_sale_cases?: CaseView[];
}
export interface Inventory {
    sku_id: string;
    on_hand: number;
    reserved: number;
    available: number;
    version: number;
}
export interface DemoItem {
    id: string;
    kind: 'PAYMENT' | 'SHIPMENT' | 'REFUND';
    state: string;
    version: number;
    simulation: true;
    created_at: string;
}

export type CaseType = 'UNSHIPPED_REFUND' | 'RETURN_REFUND';
export interface CaseView {
    id: string;
    order_id: string;
    type: CaseType;
    state: 'REQUESTED' | 'REJECTED' | 'CANCELLED' | 'REFUND_PENDING' | 'AWAITING_RETURN' | 'RETURN_IN_TRANSIT' | 'COMPLETED';
    version: number;
    reason: string;
    requested_amount_minor: number;
    currency: string;
    created_at: string;
    lines: {order_line_id: string; quantity: number}[];
    decision_reason: string | null;
    return_shipment: {tracking_number: string; state: 'IN_TRANSIT' | 'RECEIVED'; restock: boolean | null; registered_at: string; received_at: string | null} | null;
    refund_attempts: Attempt[];
}
export interface Conversation {
    id: string;
    shop_id: string;
    customer_id: string;
    order_id: string | null;
    version: number;
    created_at: string;
}
export interface Message {
    id: string;
    conversation_id: string;
    sender_side: 'CUSTOMER' | 'MERCHANT';
    body: string;
    created_at: string;
}
