export class ApiError extends Error {
    constructor(public code: string, message: string, public status: number, public details: Record<string, unknown> = {}, public requestId = '') { super(message); }
}
export const uncertain = (error: unknown) => !(error instanceof ApiError) || (error.code !== 'MAILBOX_DELIVERY_FAILED' && (error.status >= 500 || error.code === 'OPERATION_BUSY'));
function freezeBody(value: unknown): unknown {
    if(value && typeof value==='object') {
        Object.values(value).forEach(freezeBody);
        Object.freeze(value);
    }
    return value;
}
export interface PendingAction {
    readonly path: string;
    readonly method: string;
    readonly body: unknown;
    readonly key: string;
    readonly fingerprint: string;
    readonly uncertain: boolean;
}
export class CommerceClient {
    private disposed = false;
    private pending: PendingAction | null = null;
    private listeners = new Set<() => void>();
    constructor(private base: string, private token = '') { }
    imageUrl(path: string) { return `${this.base}${path}`; }
    async imageBlob(path: string) {
        if (this.disposed) throw new Error('会话已切换');
        const response = await fetch(this.imageUrl(path), {headers: this.token ? {Authorization: `Bearer ${this.token}`} : {}, cache: 'no-store'});
        if (!response.ok) throw new ApiError('IMAGE_READ_FAILED', '图片暂时无法读取', response.status);
        if (this.disposed) throw new Error('会话已切换');
        return response.blob();
    }
    subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
    getPending = () => this.pending;
    private updatePending(pending: PendingAction | null) {
        this.pending = pending ? Object.freeze(pending) : null;
        this.listeners.forEach(listener => listener());
    }
    dispose() { this.disposed = true; this.updatePending(null); this.listeners.clear(); }
    async retryPending(): Promise<unknown> {
        if (!this.pending?.uncertain) throw new Error('当前没有需要重试的未确认操作');
        return this.request(this.pending.path, this.pending.method, this.pending.body);
    }
    async request<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
        if (this.disposed) throw new Error('会话已切换，请重新读取当前账号记录');
        const fingerprint = JSON.stringify([path, method, body]);
        const write = method !== 'GET' && !['/auth/login', '/auth/logout', '/account/password'].includes(path);
        if (write && this.pending && (this.pending.fingerprint !== fingerprint || !this.pending.uncertain)) {
            throw new ApiError('CLIENT_OPERATION_PENDING', '上次操作的结果尚未确认。请先使用页面顶部的原请求重试，避免重复扣减或发货。', 409);
        }
        const action: PendingAction | null = write ? {
            path, method,
            // Clone the intent once: later form edits cannot mutate the retry body.
            body: body === undefined ? undefined : freezeBody(JSON.parse(JSON.stringify(body))),
            key: this.pending?.key ?? crypto.randomUUID(), fingerprint, uncertain: false,
        } : null;
        if (action) this.updatePending(action);
        try {
            const response = await fetch(`${this.base}/api/commerce/v1${path}`, {
                method, cache: 'no-store', headers: {
                    ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
                    ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
                    ...(action ? { 'Idempotency-Key': action.key } : {}),
                }, ...(body !== undefined ? { body: JSON.stringify(action ? action.body : body) } : {}),
            });
            if (this.disposed) throw new Error('会话已切换，请重新读取当前账号记录');
            if (!response.ok) {
                const data = await response.json().catch(() => null);
                throw new ApiError(data?.error?.code ?? 'HTTP_ERROR', data?.error?.message ?? '服务暂时无法完成请求', response.status, data?.error?.details ?? {}, data?.error?.request_id ?? response.headers.get('X-Request-Id') ?? '');
            }
            const result = response.status === 204 ? undefined as T : await response.json() as T;
            if (this.disposed) throw new Error('会话已切换，请重新读取当前账号记录');
            if (write) this.updatePending(null);
            return result;
        } catch (error) {
            if (action && !this.disposed) this.updatePending(uncertain(error) ? { ...action, uncertain: true } : null);
            throw error;
        }
    }
}
