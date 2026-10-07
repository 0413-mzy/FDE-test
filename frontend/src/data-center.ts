export function dataQuery(values:Record<string,string|number|undefined>) {
    const params = new URLSearchParams();
    Object.entries(values).forEach(([key,value])=>{if(value!=='' && value!==undefined)params.set(key,String(value));});
    return params.size ? `?${params}` : '';
}
export function fieldChanges(before:Record<string,unknown>|null,after:Record<string,unknown>|null) {
    return [...new Set([...Object.keys(before??{}),...Object.keys(after??{})])].filter(field=>JSON.stringify(before?.[field])!==JSON.stringify(after?.[field])).map(field=>({field,before:before?.[field],after:after?.[field]}));
}
export function createReadRefresh(load:()=>Promise<unknown>,visible:()=>boolean,schedule:(fn:()=>void,ms:number)=>unknown,cancel:(id:unknown)=>void) {
    let busy=false, disposed=false;
    const id=schedule(()=>{if(disposed||busy||!visible())return;busy=true;Promise.resolve().then(load).catch(()=>{}).finally(()=>{busy=false;});},15000);
    return ()=>{disposed=true;cancel(id);};
}
export function createLatestRead<T>(success:(v:T)=>void,failure:(e:unknown)=>void) {
    let running=false, disposed=false, version=0;
    let pending:{task:()=>Promise<T>;version:number;done:()=>void}|undefined;
    async function drain() {
        if(running||disposed)return;
        running=true;
        while(pending&&!disposed) {
            const next=pending;pending=undefined;
            try {const result=await next.task();if(!disposed&&next.version===version)success(result);}
            catch(e){if(!disposed&&next.version===version)failure(e);}
            finally{next.done();}
        }
        running=false;
    }
    const read=(task:()=>Promise<T>)=>new Promise<void>(done=>{
        if(disposed){done();return;}
        pending?.done();pending={task,version:++version,done};void drain();
    });
    read.resume=()=>{disposed=false;};
    read.dispose=()=>{disposed=true;version++;pending?.done();pending=undefined;};
    return read;
}
type ListingFilters={q:string;status:string;from:string;to:string;relation?:{field:string;value:string}};
export function recordNavigationFilters(current:string,target:string,filters:ListingFilters):ListingFilters {
    return current===target?filters:resetListingFilters();
}

export function resetListingFilters():ListingFilters { return {q:'',status:'',from:'',to:'',relation:undefined}; }
