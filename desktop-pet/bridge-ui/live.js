import {createScene,drawHouse} from './scene.js';
import {setupConnections} from './connections.js';
const $=id=>document.getElementById(id), ctx=$('office').getContext('2d');
let token='', snapshot=null, online=false, renderer, animator, lastFrame=-1, leaderState='', leaderAt=0;
let revision=-1, lastSuccess=0, lostAt=null, landingAt=-100, polling=false;
const tracks=new Map();
let deskPage=0;
let artworkError='';
let settingsDraft=null,settingsSaving=false;
let settingsTaskSignature='';
const PAGE_SIZE=6;
const scene=createScene($('office'),{onChange:()=>{lastFrame=-1;updateMode();}});
function updateMode(){
  const free=scene.mode==='free';
  $('free-mode').setAttribute('aria-pressed',String(free));$('house-mode').setAttribute('aria-pressed',String(!free));
  $('reunite').hidden=!free;$('scene-title').textContent=free?'望包的自由时间':'望包小屋 · 黑工模式';
  $('scene-hint').textContent=scene.locked?'移动已锁定，任务动作和通知继续更新。':free?'直接拖动大望包或任意分身，可以把它们叠在一起。选中后也可用方向键微调。':'工作时进入小屋；完成后合上电脑，下来和大望包待在一起。';
  $('office').dataset.mode=scene.mode;
  $('office').dataset.locked=String(scene.locked);
  $('lock-movement').textContent=scene.locked?'解锁移动':'锁定移动';
  $('lock-movement').setAttribute('aria-pressed',String(scene.locked));
  $('reunite').disabled=scene.locked;
}
function visibleTasks(){return snapshot?.tasks??[];}
function deskSlot(t){return 'desk_slot' in t?t.desk_slot:t.slot;}
function gathered(t){return deskSlot(t)===null&&t.gather_index!==null;}
function pageTasks(){
  return visibleTasks().filter(t=>gathered(t)||Math.floor(deskSlot(t)/PAGE_SIZE)===deskPage)
    .sort((a,b)=>Number(gathered(a))-Number(gathered(b))||(gathered(a)?a.gather_index-b.gather_index:deskSlot(a)-deskSlot(b)));
}
const names={running:'工作中',waiting:'等候确认',completed:'本轮完成',failed:'任务失败',cancelled:'已取消',disconnected:'连接断开',idle:'休息'};

async function api(path,body){
  const response=await fetch('/api/'+path,{method:body?'POST':'GET',cache:'no-store',
    headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
  if(!response.ok){
    const data=await response.json().catch(()=>({}));
    throw new Error(data.error||'连接暂时不可用，请稍后重试。');
  }
  return response.json();
}
function node(tag,text,className){const el=document.createElement(tag);el.textContent=text;if(className)el.className=className;return el;}
function taskUrl(t){
  if(t.open_url){try{const u=new URL(t.open_url);
    if(t.source==='local'&&t.thread_id?.startsWith('extension:')&&['http:','https:'].includes(u.protocol)&&!u.username&&!u.password)return u.href;
    if(u.protocol==='codex:'&&u.host==='threads'||u.protocol==='zcode:'&&u.host==='workspace'&&u.pathname==='/open'||u.protocol==='cursor:'&&u.host==='wang-bun.local-monitor'&&u.pathname==='/open')return u.href;
  }catch{}}
  return t.source==='codex'&&/^[0-9a-f-]{36}$/i.test(t.thread_id)?'codex://threads/'+encodeURIComponent(t.thread_id):null;
}
$('office').addEventListener('dblclick',event=>{
  const t=snapshot?.tasks.find(t=>t.id===scene.taskAt(event)),url=t&&taskUrl(t);
  if(url)window.location.href=url;
  else if(t)$('error').textContent='此来源暂不支持会话跳转，请在原软件打开对应任务。未读状态会保留。';
});
async function acknowledge(ids){
  try{await api('read',{ids});await poll();}catch{$('error').textContent='已读状态尚未保存，请在连接恢复后重试。';}
}
function renderInbox(){
  const notes=snapshot.notifications, list=$('notifications');list.replaceChildren();
  if(!notes.length)list.append(node('p','暂时没有通知。','muted'));
  // Unread first; the server retains the full acknowledged history separately.
  const visible=[...notes.filter(n=>!n.read),...notes.filter(n=>n.read)].slice(0,100);
  for(const n of visible){
    const card=node('article','','notice'+(n.read?' read':''));
    card.append(node('strong',n.label+' · '+(names[n.kind]??'新消息')));
    card.append(node('p',n.summary));
    const row=node('div','','actions');
    if(!n.read&&n.read_mode!=='app'){const b=node('button','确认已查看');b.onclick=()=>acknowledge([n.id]);row.append(b);}
    if(!n.read&&n.read_mode==='app')row.append(node('small','已读跟随原软件'));
    if(taskUrl(n)){
      const link=node('a',n.source==='zcode'?'打开所在工作区':n.source==='local'?'查看原文':'打开会话','action');link.href=taskUrl(n);if(n.source==='local'){link.target='_blank';link.rel='noopener noreferrer';}row.append(link);
    }
    row.append(node('small',new Date(n.created_at*1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})));
    card.append(row);list.append(card);
  }
  $('count').textContent=snapshot.unread_count+' 条未读';
  $('read-all').disabled=!notes.some(n=>!n.read&&n.read_mode!=='app');
}
function renderTasks(){
  const panel=$('tasks');panel.replaceChildren();
  const tasks=visibleTasks(),desks=tasks.filter(t=>deskSlot(t)!==null),companions=tasks.filter(gathered),pages=Math.max(1,Math.ceil(desks.length/PAGE_SIZE));
  deskPage=Math.min(deskPage,pages-1);
  $('page-status').textContent=`第 ${deskPage+1} / ${pages} 面 · ${desks.length} 个工位 · ${companions.length} 只归队`;
  $('previous-page').disabled=deskPage===0;$('next-page').disabled=deskPage===pages-1;
  $('empty').hidden=!!tasks.length;
  for(const t of pageTasks()){const card=node('div','','task');card.dataset.taskId=t.id;card.dataset.group=gathered(t)?'gathered':'desk';card.append(node('b',t.label));
    card.append(node('span',names[t.display_state]??t.display_state));
    if(gathered(t))card.append(node('small',' · 在大包子身边'));
    if(t.bubble)card.append(node('p',t.bubble));
    if(t.unread_ids.length)card.append(node('p',t.unread_ids.length+' 条未读'));
    if(t.retire_at)card.append(node('small','收工归队，稍后离开'));
    else if(t.read_mode==='app'&&!t.read_known)card.append(node('small','等待原软件的已读状态'));
    if(taskUrl(t)){
      const link=node('a',t.source==='zcode'?'打开所在工作区':'打开对应会话','action');link.href=taskUrl(t);card.append(link);
    }
    panel.append(card);
  }
}
async function poll(){
  if(polling)return;
  polling=true;
  try{
    if(!token)token=(await(await fetch('/api/session',{cache:'no-store'})).json()).token;
    const next=await api('snapshot');
    const now=performance.now()/1000;
    for(const task of next.tasks){
      const old=tracks.get(task.id);
      if(!old||old.actionId!==task.action_id){
        const entering=!old||old.runId!==task.run_id;
        const returning=entering&&old&&(old.gathered||['completed','following'].includes(old.state));
        tracks.set(task.id,{actionId:task.action_id,runId:task.run_id,state:task.display_state,returning,entering,
          start:now-Math.max(0,next.server_time-task.state_at),readAt:-100,offlineAt:now,unread:task.unread_ids.length,
          gathered:task.gather_index!==null,returnFrom:old?.lastPosition,lastPosition:old?.lastPosition});
      }else{
        if(old.unread&&!task.unread_ids.length)old.readAt=now;
        if(old.state!==task.display_state&&task.display_state==='disconnected')old.offlineAt=now;
        old.unread=task.unread_ids.length;old.state=task.display_state;
        old.gathered=task.gather_index!==null;
      }
    }
    const stateSignature=JSON.stringify(next.tasks.map(t=>[t.id,t.display_state,t.desk_slot,t.gather_index]));
    const changed=!snapshot||revision!==next.revision||stateSignature!==snapshot.stateSignature;
    next.stateSignature=stateSignature;snapshot=next;revision=next.revision;
    scene.setLocked(next.settings?.movement_locked??false);
    online=true;lostAt=null;lastSuccess=now;$('status').textContent='本地连接正常';$('status').classList.remove('offline');$('error').textContent=artworkError;
    if(changed){renderInbox();renderTasks();}
    if($('settings-dialog').open&&settingsDraft)renderSettingTasks(next.connections.tasks);
  }catch{online=false;lostAt??=performance.now()/1000;token='';$('status').textContent='连接中断 · 正在重试';$('status').classList.add('offline');}
  finally{polling=false;}
}
function taskMotion(task,now){
  if(!online)return ['disconnected',Math.max(0,now-(lostAt??lastSuccess))];
  if(task.display_state==='disconnected')return ['disconnected',Math.max(0,now-tracks.get(task.id).offlineAt)];
  const track=tracks.get(task.id), age=Math.max(0,now-track.start), state=task.display_state;
  if(state==='running'){
    if(!track.entering)return ['typing',age];
    if(track.returning&&age<4.5)return ['return',age];
    const t=age-(track.returning?4.5:0);return t<3?['entry',t]:['typing',t-3];
  }
  if(state==='completed'||task.retire_at){
    if(age<3.5)return ['closing',age];if(age<6.5)return ['walk',age-3.5];
    if(now-track.readAt<8)return ['read',now-track.readAt];return ['following',age-6.5];
  }
  return [{waiting:'waiting',failed:'failed'}[state]??'idle',age];
}
function animate(ms){
  const frame=Math.floor(ms*12/1000), now=ms/1000;
  if(frame!==lastFrame&&renderer){
    lastFrame=frame;ctx.clearRect(0,0,720,460);
    const house=scene.mode==='house';if(house)drawHouse(ctx);
    const records=[],leader=scene.leader();
    let state=!online?'disconnected':snapshot?.leader_state??'idle';
    if($('quiet').checked&&state==='unread')state='idle';
    if(state!==leaderState){if(leaderState==='unread'&&state==='idle')landingAt=now;leaderState=state;leaderAt=now;}
    const leaderAction=state==='idle'&&now-landingAt<8?'read':({running:'typing',waiting:'waiting',failed:'failed',unread:'unread',disconnected:'disconnected'}[state]??'idle');
    const latest=(snapshot?.tasks??[]).find(t=>t.display_state===state);
    const lp=animator.sample(leaderAction,now-leaderAt,{fps:12,agentName:latest?.label??'望包',failureRoll:latest?.failure_roll??.4});
    const leaderRecord={key:'leader',...leader,scale:1,paint:c=>renderer.drawModel(c,lp,{companion:leaderAction==='read'})};
    scene.selection(ctx,leaderRecord);renderer.drawModel(ctx,lp,{...leader,companion:leaderAction==='read'});records.push(leaderRecord);
    const tasks=visibleTasks();
    // House pages share desks; the reunion pile is rendered on every page.
    pageTasks().forEach(t=>{
      const i=(deskSlot(t)??t.origin_slot??t.slot)%PAGE_SIZE;
      let [action,age]=taskMotion(t,now);
      const desk=house?{x:360+i%3*110,y:140+Math.floor(i/3)*153}:{x:360+i%3*112,y:96+Math.floor(i/3)*170};
      const count=tasks.filter(t=>t.gather_index!==null).length,index=t.gather_index??t.return_index??0;
      const step=Math.min(46,Math.max(0,460-(leader.y+130)-85-12)/Math.max(1,Math.ceil(count/3)-1));
      const follow={x:leader.x+164+index%3*46,y:leader.y+130+Math.floor(index/3)*step};
      let pos=gathered(t)?follow:desk;
      if(['following','read'].includes(action))pos=follow;
      if(action==='walk'){const u=Math.min(1,age/3);pos={x:desk.x+(follow.x-desk.x)*u,y:desk.y+(follow.y-desk.y)*u};}
      if(action==='return'){const u=Math.min(1,age/4.5),from=tracks.get(t.id).returnFrom??follow;pos={x:from.x+(desk.x-from.x)*u,y:from.y+(desk.y-from.y)*u};}
      if(deskSlot(t)!==null&&action==='return')renderer.drawModel(ctx,animator.sample('closing',3.5),{...desk,scale:1/3,only:['laptop_screen','laptop_keyboard','glasses','cup'],effects:false});
      pos=scene.position(t.id,pos);
      tracks.get(t.id).lastPosition={...pos};
      const p=animator.sample(action,age,{fps:12,agentName:t.label,seed:i+1,failureRoll:t.failure_roll});
      const record={key:t.id,...pos,scale:1/3,paint:c=>renderer.drawModel(c,p,{companion:false})};
      scene.selection(ctx,record);renderer.drawModel(ctx,p,{...pos,scale:1/3,companion:false});records.push(record);
      const labelAt=desk, labelY=house?84:88;
      if(snapshot?.settings?.show_labels===false||gathered(t))return;
      ctx.fillStyle=house?'#76654e':'#273d39';ctx.fillRect(labelAt.x,labelAt.y+labelY,106,house?25:32);ctx.fillStyle='#f7f5eb';ctx.font='10px sans-serif';ctx.textAlign='center';
      ctx.fillText(t.label.slice(0,12),labelAt.x+53,labelAt.y+labelY+11,101);ctx.fillText(names[t.display_state]??'',labelAt.x+53,labelAt.y+labelY+22);
    });
    scene.setRecords(records);
  }
  requestAnimationFrame(animate);
}
$('read-all').onclick=()=>acknowledge((snapshot?.notifications??[]).filter(n=>!n.read).map(n=>n.id));
$('quiet').checked=localStorage.getItem('wang-bun-quiet')==='true';
$('quiet').onchange=()=>localStorage.setItem('wang-bun-quiet',String($('quiet').checked));
$('previous-page').onclick=()=>{scene.cancel();deskPage=Math.max(0,deskPage-1);renderTasks();};
$('next-page').onclick=()=>{scene.cancel();deskPage++;renderTasks();};
$('free-mode').onclick=()=>scene.setMode('free');$('house-mode').onclick=()=>scene.setMode('house');
$('reunite').onclick=()=>scene.reset();updateMode();
$('lock-movement').onclick=async()=>{
  $('lock-movement').disabled=true;
  try{await api('settings',{movement_locked:!scene.locked});await poll();}
  catch{$('error').textContent='移动锁定尚未保存，请在连接恢复后重试。';}
  finally{$('lock-movement').disabled=false;}
};
function settingToggle(parent,text,checked,onchange){
  const label=node('label','','setting-row'),input=document.createElement('input');input.type='checkbox';input.checked=checked;
  input.onchange=()=>onchange(input.checked);label.append(input,node('span',text));parent.append(label);return input;
}
function renderSettingTasks(catalog){
  const signature=JSON.stringify(catalog.map(t=>[t.id,t.label]));
  if(signature===settingsTaskSignature)return;
  settingsTaskSignature=signature;
  const tasks=$('settings-tasks');tasks.replaceChildren();
  for(const t of catalog)settingToggle(tasks,t.source+' · '+t.label,!settingsDraft.disabled_tasks.includes(t.id),v=>{
    const disabled=new Set(settingsDraft.disabled_tasks);if(v)disabled.delete(t.id);else disabled.add(t.id);settingsDraft.disabled_tasks=[...disabled];
  });
  if(!catalog.length)tasks.append(node('p','接入 Codex 分身或收到软件事件后，会话会出现在这里。','muted'));
}
setupConnections({api,onAdded:poll});
$('open-settings').onclick=async()=>{
  try{
    const data=await api('settings');settingsDraft=structuredClone(data.settings);
    const general=$('settings-general'),sources=$('settings-sources'),tasks=$('settings-tasks');
    general.replaceChildren();sources.replaceChildren();tasks.replaceChildren();
    for(const [key,title] of [['movement_locked','锁定移动'],['always_on_top','桌面版置顶'],['show_labels','显示工位文字'],['auto_discover','自动发现 Codex / Cursor / ZCode 任务']])
      settingToggle(general,title,settingsDraft[key],v=>settingsDraft[key]=v);
    const scaleRow=node('label','','setting-row');scaleRow.append(node('span','桌面版缩放'));
    const scaleSelect=node('select','');scaleSelect.id='desktop-scale';scaleSelect.setAttribute('aria-label','桌宠缩放');
    for(const value of [50,75,100,125,150]){
      const option=node('option',value+'%');option.value=String(value);scaleSelect.append(option);
    }
    scaleSelect.value=String(settingsDraft.desktop_scale??100);
    scaleSelect.onchange=()=>settingsDraft.desktop_scale=Number(scaleSelect.value);
    scaleRow.append(scaleSelect);general.append(scaleRow);
    for(const s of data.connections.sources){
      settingToggle(sources,s.label+' · '+(!s.enabled?'已暂停':s.status??'等待软件事件'),s.enabled,v=>settingsDraft.sources[s.id]=v);
      sources.append(node('p',s.method,'muted settings-note'));
    }
    settingsTaskSignature='';renderSettingTasks(data.connections.tasks);
    $('settings-message').textContent='';$('settings-dialog').showModal();
  }catch{$('error').textContent='暂时无法读取设置，请等待本地连接恢复。';}
};
$('close-settings').onclick=()=>{if(!settingsSaving)$('settings-dialog').close();};
$('save-settings').onclick=async()=>{
  if(!settingsDraft||settingsSaving)return;settingsSaving=true;$('save-settings').disabled=true;
  try{await api('settings',settingsDraft);await poll();$('settings-dialog').close();}
  catch{$('settings-message').textContent='保存失败，设置尚未生效，请重试。';}
  finally{settingsSaving=false;$('save-settings').disabled=false;}
};
async function boot(){
  try{
    const [{createAnimator},{createRenderer}]=await Promise.all([import('/art/motions.js'),import('/art/renderer.js')]);
    const rig=await(await fetch('/art/rig.json')).json(),images={};
    await Promise.all(rig.layers.map(l=>new Promise((resolve,reject)=>{const im=new Image();im.onload=()=>{images[l.id]=im;resolve();};im.onerror=reject;im.src='/art/'+l.file;})));
    const spatial=await(await fetch('/art/spatial-rig-v7.json')).json();
    animator=createAnimator(rig);renderer=createRenderer(rig,images,animator,new Set(),spatial);
  }catch{artworkError='动作资源正在更新，消息收件箱仍可使用；稍后刷新可重载动作。';$('error').textContent=artworkError;}
  await poll();setInterval(poll,750);requestAnimationFrame(animate);
}
boot();
