// Read-only Cordis observer for DeepSeekHarness session metadata.
import {mkdir,writeFile,rename} from 'node:fs/promises';
import {randomUUID,createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve,join} from 'node:path';
export const name='wang-bun-local-observer';
export const inject=['session'];
const defaultRuntime=fileURLToPath(new URL('../../runtime/bridge/',import.meta.url));

export function project(session,event){
  if(!session||typeof session.id!=='string'||!Number.isInteger(event?.data?.turn))return null;
  const kind=event.type==='turn/start'?'started':event.type==='turn/end'?
    ({completed:'completed',aborted:'cancelled',error:'failed','max-tokens':'failed',interrupted:'cancelled',blocked:'waiting'}[event.data.reason?.kind]):null;
  if(!kind)return null;
  const eventId=createHash('sha256').update(JSON.stringify([session.id,event.seq,event.type])).digest('hex');
  return {event_id:eventId,source:'dsh',thread_id:session.id,run_id:String(event.data.turn),kind,
    label:'DeepSeekHarness · '+session.id.slice(0,8),managed:true,
    ...(Number.isFinite(event.time)?{observed_at:event.time/1000}:{})};
}

export function apply(ctx,config={}){
  const inbox=join(resolve(config.runtime??defaultRuntime),'inbox');
  let pending=Promise.resolve();
  ctx.on('session/event',(session,event)=>{
    const record=project(session,event);if(!record)return;
    // Serialize our own writes. The event bus and agent turn never await I/O.
    pending=pending.then(async()=>{
      await mkdir(inbox,{recursive:true});
      const target=join(inbox,`${String(BigInt(Date.now())*1000000n).padStart(20,'0')}-${randomUUID()}.json`);
      await writeFile(target+'.tmp',JSON.stringify(record),{flag:'wx'});
      await rename(target+'.tmp',target);
    }).catch(()=>ctx.logger?.warn('望包本地通知暂未写入；Agent 继续运行。'));
  });
}
