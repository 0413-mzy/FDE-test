import { useEffect, useState } from 'react';
import { CommerceClient } from './client';
export function useQuery<T>(client: CommerceClient, path: string) {
    const [state, setState] = useState<{
        data?: T;
        error?: unknown;
        loading: boolean;
    }>({ loading: true });
    const [revision, setRevision] = useState(0);
    useEffect(() => { let active = true; client.request<T>(path).then(data => { if (active)
        setState({ data, loading: false }); }).catch(error => { if (active)
        setState({ error, loading: false }); }); return () => { active = false; }; }, [client, path, revision]);
    return { ...state, refresh: () => { setState({ loading: true }); setRevision(n => n + 1); } };
}
