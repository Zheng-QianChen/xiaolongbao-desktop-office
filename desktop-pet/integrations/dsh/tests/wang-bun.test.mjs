// Fabricated-event self-check for the DSH -> WangBun spool adapter.
// Run: node --test desktop-pet/integrations/dsh/tests/wang-bun.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import {readdir,readFile,rm,writeFile,mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {apply,createInboxWriter,inject,name,project} from '../wang-bun.mjs';

const SESSION={id:'session-01234567',title:'PRIVATE TITLE',prompt:'PRIVATE PROMPT'};
const TIME=1760000000123;
const START={seq:7,time:TIME,type:'turn/start',data:{turn:3,prompt:'PRIVATE PROMPT'}};
const END={seq:8,time:TIME+1000,type:'turn/end',data:{turn:3,reason:{kind:'completed'}}};

async function temporary(t,prefix='wang-bun-dsh-'){
  const directory=await mkdtemp(join(tmpdir(),prefix));
  t.after(()=>rm(directory,{recursive:true,force:true}));
  return directory;
}

async function waitFor(check,{timeout=2000,interval=25}={}){
  const deadline=Date.now()+timeout;
  let last;
  while(Date.now()<deadline){
    try{
      const value=await check();
      if(value)return value;
    }catch(error){last=error;}
    await new Promise(resolve=>setTimeout(resolve,interval));
  }
  throw last??new Error('timed out waiting for the inbox');
}

test('plugin exports the Cordis identity and only the session service',()=>{
  assert.equal(name,'wang-bun-local-observer');
  assert.deepEqual(inject,['session']);
  assert.equal(typeof apply,'function');
});

test('turn boundaries project to the pet event contract',()=>{
  const start=project(SESSION,START);
  assert.deepEqual(start,{
    event_id:start.event_id,source:'dsh',thread_id:SESSION.id,run_id:'3',kind:'started',
    label:'DeepSeekHarness · session-',managed:true,observed_at:TIME/1000,
  });
  assert.match(start.event_id,/^[0-9a-f]{64}$/);
  assert.equal(start.label.length<=60,true);
  assert.equal(project(SESSION,{...END,data:{turn:3,reason:{kind:'completed'}}}).kind,'completed');
  assert.equal(project(SESSION,{...END,data:{turn:3,reason:{kind:'aborted'}}}).kind,'cancelled');
  assert.equal(project(SESSION,{...END,data:{turn:3,reason:{kind:'interrupted'}}}).kind,'cancelled');
  assert.equal(project(SESSION,{...END,data:{turn:3,reason:{kind:'error'}}}).kind,'failed');
  assert.equal(project(SESSION,{...END,data:{turn:3,reason:{kind:'max-tokens'}}}).kind,'failed');
  assert.equal(project(SESSION,{...END,data:{turn:3,reason:{kind:'blocked'}}}).kind,'waiting');
  // Fork seeds are history, not live work; unknown future endings stay unprojected.
  assert.equal(project(SESSION,{...END,data:{turn:3,reason:{kind:'forked'}}}),null);
  assert.equal(project(SESSION,{...END,data:{turn:3,reason:{kind:'future-reason'}}}),null);
  assert.equal(project(SESSION,{...END,data:{turn:3}}),null);
});

test('event ids are deterministic and identity-bound',()=>{
  const first=project(SESSION,START);
  assert.equal(project(SESSION,START).event_id,first.event_id);
  assert.notEqual(project(SESSION,{...START,seq:8}).event_id,first.event_id);
  assert.notEqual(project(SESSION,{...START,type:'turn/end',data:{turn:3,reason:{kind:'completed'}}}).event_id,first.event_id);
  assert.notEqual(project({...SESSION,id:'session-other'},START).event_id,first.event_id);
});

test('malformed and non-boundary events are ignored',()=>{
  assert.equal(project(null,START),null);
  assert.equal(project({},START),null);
  assert.equal(project({id:3},START),null);
  assert.equal(project(SESSION,null),null);
  assert.equal(project(SESSION,{...START,data:{turn:'3'}}),null);
  assert.equal(project(SESSION,{type:'turn/start',data:{}}),null);
  assert.equal(project(SESSION,{...START,type:'assistant/message'}),null);
  assert.equal(project(SESSION,{...START,type:'step/start'}),null);
});

test('projected records carry metadata only',()=>{
  const record=project(SESSION,{...START,data:{turn:3,prompt:'PRIVATE PROMPT',error:{message:'PRIVATE PROMPT'}}});
  const serialized=JSON.stringify(record);
  assert.equal(serialized.includes('PRIVATE'),false);
  assert.deepEqual(Object.keys(record).sort(),
    ['event_id','kind','label','managed','observed_at','run_id','source','thread_id']);
  assert.equal(record.source,'dsh');
  assert.equal(record.managed,true);
  assert.equal(record.thread_id,SESSION.id);
  assert.equal(typeof record.observed_at,'number');
  assert.equal(Number.isFinite(record.observed_at),true);
});

test('missing or invalid time omits observed_at instead of leaking it',()=>{
  assert.equal('observed_at' in project(SESSION,{...START,time:undefined}),false);
  assert.equal('observed_at' in project(SESSION,{...START,time:Number.NaN}),false);
  assert.equal('observed_at' in project(SESSION,{...START,time:'1760000000123'}),false);
});

test('the writer serializes atomic JSON files in the configured inbox',async(t)=>{
  const runtime=await temporary(t);
  const records=[project(SESSION,START),project(SESSION,END)];
  const writer=createInboxWriter({runtime});
  records.forEach(record=>writer.write(record));
  await writer.flush();
  const files=(await readdir(writer.inbox)).sort();
  assert.equal(files.length,2);
  assert.equal(files.every(file=>/^\d{20}-[0-9a-f-]{36}\.json$/.test(file)),true);
  assert.equal(files.some(file=>file.endsWith('.tmp')),false);
  const restored=[];
  for(const file of files)restored.push(JSON.parse(await readFile(join(writer.inbox,file),'utf8')));
  assert.deepEqual(restored.map(record=>record.kind).sort(),['completed','started']);
  for(const record of restored)assert.equal(JSON.stringify(record).includes('PRIVATE'),false);
});

test('a write failure is logged and never interrupts the next event',async(t)=>{
  const runtime=join(await temporary(t),'not-a-directory');
  await writeFile(runtime,'blocked');
  const warnings=[];
  const writer=createInboxWriter({runtime,logger:{warn:message=>warnings.push(message)}});
  await writer.write(project(SESSION,START));
  await writer.write(project(SESSION,END));
  await writer.flush();
  assert.equal(warnings.length,2);
  assert.match(warnings[0],/暂未写入/);
});

test('apply subscribes to session/event and spools only projected records',async(t)=>{
  const runtime=await temporary(t);
  let handler;
  const ctx={on:(event,callback)=>{assert.equal(event,'session/event');handler=callback;},
    logger:{warn:()=>{}}};
  apply(ctx,{runtime});
  assert.equal(typeof handler,'function');
  handler(SESSION,START);
  handler(SESSION,{...START,seq:8,type:'assistant/message'});
  handler({id:3},{...START,seq:9});
  handler(SESSION,END);
  const files=await waitFor(async()=>{
    const found=(await readdir(join(runtime,'inbox'))).filter(file=>file.endsWith('.json'));
    return found.length===2?found:null;
  });
  const records=await Promise.all(files.map(async file=>JSON.parse(await readFile(join(runtime,'inbox',file),'utf8'))));
  assert.deepEqual(records.map(record=>record.kind).sort(),['completed','started']);
});