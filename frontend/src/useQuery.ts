import { useEffect, useState } from 'react';
import { CommerceClient } from './client';
import { queryRefreshState } from './helpers';
export function useQuery<T>(client: CommerceClient, path: string, enabled = true, refreshKey = "", retainData = false) {
    const [state, setState] = useState<{
        data?: T;
        error?: unknown;
        loading: boolean;
        client?: CommerceClient;
        path?: string;
    }>({ loading: true });
    const [revision, setRevision] = useState(0);
    useEffect(() => { if (!enabled) return; let active = true; client.request<T>(path).then(data => { if (active)
        setState({ data, loading: false, client, path }); }).catch(error => { if (active)
        setState(previous => queryRefreshState(previous, client, path, retainData, error)); }); return () => { active = false; }; }, [client, path, revision, enabled, refreshKey, retainData]);
    const visible = enabled && state.client === client && state.path === path ? state : {loading: enabled};
    return { ...visible, refresh: () => { setState(previous => queryRefreshState(previous, client, path, retainData)); setRevision(n => n + 1); } };
}

export function useAllPages<T>(client: CommerceClient, path: string, enabled = true) {
    const [state,setState]=useState<{items:T[];error?:unknown;loading:boolean;client?:CommerceClient;path?:string}>({items:[],loading:true});
    const [revision,setRevision]=useState(0);
    useEffect(()=>{
        if(!enabled)return;
        let active=true;
        async function read(){
            const items:T[]=[];
            let offset=0,hasMore=true;
            while(hasMore){
                const page=await client.request<{items:T[];has_more:boolean}>(`${path}${path.includes('?')?'&':'?'}limit=100&offset=${offset}`);
                items.push(...page.items); hasMore=page.has_more; offset+=100;
            }
            if(active)setState({items,loading:false,client,path});
        }
        read().catch(error=>{if(active)setState({items:[],error,loading:false,client,path});});
        return()=>{active=false;};
    },[client,path,enabled,revision]);
    const visible=enabled&&state.client===client&&state.path===path?state:{items:[] as T[],loading:enabled};
    return {...visible,refresh:()=>{setState({items:[],loading:true,client,path});setRevision(n=>n+1);}};
}
