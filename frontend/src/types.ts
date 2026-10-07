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
    can_dispute?: boolean;
    dispute_open?: boolean;
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

export interface ProfileView { account_id: string; username: string; version: number; display_name: string; phone: string; email: string | null; email_verified: boolean; review_enabled: boolean; }
export interface AddressBookView { id: string; version: number; address: Address; is_default: boolean; created_at: string; updated_at: string; }
export interface MerchantApplicationView { id: string; version: number; state: 'PENDING' | 'APPROVED' | 'REJECTED' | 'WITHDRAWN'; shop_name: string; business_scope: string; contact_name: string; contact_phone: string; description: string; created_at: string; updated_at: string; decision_reason: string | null; shop_id: string | null; }

export interface Category {id:string;name:string;active:boolean;version:number}
export interface ShopView {id:string;name:string;status:string;version:number}
export interface ProductImage {id:string;url:string;alt:string;position:number}
export interface ProductCardView extends Product {category_id:string|null;category_name:string|null;images:ProductImage[];rating:number|null;review_count:number}
export interface Review {id:string;product_id:string;shop_id:string;order_id:string;order_line_id:string;rating:number;body:string;reply:string|null;visible:boolean;version:number;created_at:string;updated_at:string;financial_status:string}
export interface Favorite {id:string;product_id:string;active:boolean;version:number;purchasable:boolean;product:ProductCardView|null}
export interface ReportView {id:string;version:number;target_type:string;target_id:string;reason:string;state:string;decision_reason:string|null;created_at:string}
export interface Dispute {case_state:string;can_refund:boolean;id:string;version:number;customer_id:string;order_id:string;case_id:string;shop_id:string;reason:string;state:string;customer_evidence:string|null;merchant_evidence:string|null;decision_reason:string|null;created_at:string}
export interface Analytics {offset:number;limit:number;shops_has_more:boolean;sales_has_more:boolean;simulation:true;currency:string;start:string;end:string;shop_id:string|null;payment_total_minor:number;refund_total_minor:number;net_total_minor:number;orders_created:number;orders_completed:number;backlog:{unpaid:number;awaiting_shipment:number;in_transit:number;after_sales:number};daily:Record<string,string|number>[];shops:Record<string,string|number>[];sales:Record<string,string|number>[]}

export interface ConversationAIResult {customer_needs: string; conditions: string; commitments: string; unresolved: string; draft: string; source_ids: string[]}
export interface ConversationAIAttempt {id: string; state: 'RUNNING' | 'SUCCEEDED' | 'FAILED'; message_count: number; source_ids: string[]; model: string; prompt_version: string; created_at: string; finished_at: string | null; result: ConversationAIResult | null; error_code: string | null; usage: Record<string, number>[]}
export interface ConversationAssistance {available: boolean; latest_success: ConversationAIAttempt | null; latest_attempt: ConversationAIAttempt | null; stale: boolean}
