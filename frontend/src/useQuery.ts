import { useEffect, useState } from 'react';
import { CommerceClient } from './client';
export function useQuery<T>(client: CommerceClient, path: string, enabled = true) {
    const [state, setState] = useState<{
        data?: T;
        error?: unknown;
        loading: boolean;
    }>({ loading: true });
    const [revision, setRevision] = useState(0);
    useEffect(() => { if (!enabled) return; let active = true; client.request<T>(path).then(data => { if (active)
        setState({ data, loading: false }); }).catch(error => { if (active)
        setState({ error, loading: false }); }); return () => { active = false; }; }, [client, path, revision, enabled]);
    return { ...state, refresh: () => { setState({ loading: true }); setRevision(n => n + 1); } };
}
