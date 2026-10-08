const assert=require('node:assert/strict');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
(async()=>{
  const dsh=await import(pathToFileURL(path.join(__dirname,'integrations/dsh/wang-bun.mjs')));
  const session={id:'session-1',prompt:'PRIVATE'},event={seq:1,time:1000,type:'turn/start',data:{turn:1,prompt:'PRIVATE'}};
  const start=dsh.project(session,event);assert.equal(start.kind,'started');assert.equal(start.run_id,'1');
  assert(!JSON.stringify(start).includes('PRIVATE'));
  for(const [reason,kind] of Object.entries({completed:'completed',error:'failed',blocked:'waiting',aborted:'cancelled','max-tokens':'failed'})){
    assert.equal(dsh.project(session,{...event,type:'turn/end',data:{turn:1,reason:{kind:reason,error:'PRIVATE'}}}).kind,kind);
  }
  assert.equal(dsh.project(session,{...event,type:'assistant/message'}),null);
  let handler,commands=[];
  const vscode={window:{registerUriHandler:h=>(handler=h,{}),showInformationMessage:()=>{}},
    commands:{executeCommand:async(...args)=>commands.push(args)}};
  require('./integrations/cursor/extension.cjs').register({subscriptions:[]},vscode);
  const id='01a1084f-58f0-7100-82c7-248853266b30';
  await handler.handleUri({path:'/open',query:'id='+id+'&windowId=2'});
  assert.deepEqual(commands,[['composer.openComposerFromNotification',{composerId:id}]]);
  await handler.handleUri({path:'/open',query:'id='+id+'&command=delete'});
  await handler.handleUri({path:'/open',query:'id=../../evil'});
  for(const query of ['id='+id,'id='+id+'&windowId=2&windowId=3','id='+id+'&windowId=-1',
      'id='+id+'&windowId=2&id='+id,'id='+id+'&windowId=_blank'])await handler.handleUri({path:'/open',query});
  assert.equal(commands.length,1);
  console.log(JSON.stringify({passed:true,checks:10}));
})().catch(e=>{console.error(e);process.exitCode=1});
