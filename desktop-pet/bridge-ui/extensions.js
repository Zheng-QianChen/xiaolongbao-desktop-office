const $=id=>document.getElementById(id);
const node=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;};
let token='',state=null,history=[],busy=false,refreshing=false,modelLoaded=false;
function status(text=''){$('message').textContent=text;}
async function api(path,value,retry=true){
  if(!token)token=(await (await fetch('/api/session',{cache:'no-store'})).json()).token;
  const response=await fetch('/api/'+path,{method:value===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:value===undefined?undefined:JSON.stringify(value),cache:'no-store'});
  if(response.status===401&&retry){token='';return api(path,value,false);}
  const data=await response.json();if(!response.ok)throw new Error(data.error||'连接未完成，请稍后重试。');return data;
}
function typeFields(){const kind=$('kind').value;for(const k of ['rss','imap'])$(k+'-fields').hidden=kind!==k;$('push-hint').hidden=kind!=='push';$('interval-label').hidden=kind==='push';$('baseline-hint').hidden=kind==='push';$('feed-url').required=kind==='rss';$('mail-host').required=kind==='imap';$('mail-user').required=kind==='imap';}
function edit(c={}){
  $('connector-form').reset();$('connector-id').value=c.id||'';$('connector-id').readOnly=!!c.id;$('kind').value=c.kind||'rss';$('kind').disabled=!!c.id;
  for(const [id,key] of [['connector-name','name'],['feed-url','url'],['mail-host','host'],['mail-user','username']])$(id).value=c[key]||'';
  $('interval').value=c.interval||300;$('mail-port').value=c.port||993;$('mail-folder').value=c.folder||'INBOX';$('connector-enabled').checked=c.enabled!==false;$('allow-local').checked=!!c.allow_local;
  $('connector-details').open=true;typeFields();
}
function modelForm(model){
  $('model-url').value=model.base_url;$('model-name').value=model.model;$('model-tokens').value=model.max_tokens;$('token-field').value=model.token_field;$('model-enabled').checked=model.enabled;
  $('model-key').value='';$('clear-key').checked=false;$('model-key').placeholder=model.key_set?'已保存密钥，留空保留':'本机无密钥服务可不填';
}
function render(){
  $('connector-list').replaceChildren();if(!state.connectors.length)$('connector-list').append(node('p','还没有订阅。可以先添加一个游戏资讯 RSS，或为自己的项目留一个通知入口。','empty'));
  for(const c of state.connectors){
    const card=node('article','','connector');card.append(node('strong',c.name),node('small',`${c.kind.toUpperCase()} · ${c.id} · ${c.enabled?c.status:'已暂停'}`));
    if(c.last_checked)card.append(node('small','上次检查 '+new Date(c.last_checked*1000).toLocaleString('zh-CN')));
    const actions=node('div','','actions');
    const action=(label,fn)=>{const b=node('button',label);b.onclick=async()=>{try{b.disabled=true;await fn();}catch(e){status(e.message);}finally{b.disabled=false;}};actions.append(b);};
    action('编辑',()=>edit(c));
    action(c.enabled?'暂停':'启用',async()=>{await api('extensions/connectors',{id:c.id,enabled:!c.enabled});await refresh();});
    if(c.kind!=='push')action('检查更新',async()=>{await api('extensions/poll',{id:c.id});status('已安排检查；首次检查只建立历史基线。');});
    else action('生成推送密钥',async()=>{const r=await api('extensions/key',{id:c.id});$('push-secret').hidden=false;$('push-example').textContent=`POST ${location.origin}${r.path}\nAuthorization: Bearer ${r.token}\nContent-Type: application/json\n\n`+JSON.stringify({id:'event-001',title:'项目有新进展',summary:'构建完成，可以查看结果。'},null,2);});
    action('删除',async()=>{if(!confirm('删除这个连接和它的凭据？已经收到的通知会保留。'))return;await api('extensions/delete',{id:c.id});if($('connector-id').value===c.id)edit();await refresh();});
    card.append(actions);$('connector-list').append(card);
  }
  $('mcp-config').textContent=JSON.stringify({mcpServers:{'wang-bun':state.mcp}},null,2);
  $('model-status').textContent=state.model.enabled?'已启用 · '+state.model.model:'未启用';
  $('send-chat').disabled=busy||!state.model.enabled;summaryCount();
}
async function refresh(initial=false){
  if(refreshing)return;refreshing=true;
  try{state=await api('extensions');render();if(initial||!modelLoaded){modelForm(state.model);$('model-details').open=!state.model.enabled;modelLoaded=true;}$('connection').textContent='本机已连接';}
  catch(e){$('connection').textContent='连接中断';status(e.message);}finally{refreshing=false;}
}
$('kind').onchange=typeFields;$('new-connector').onclick=()=>{edit();$('connector-id').focus();};$('reset-connector').onclick=()=>edit();
$('connector-form').onsubmit=async event=>{
  event.preventDefault();const b=event.submitter;b.disabled=true;
  const v={id:$('connector-id').value.trim(),kind:$('kind').value,name:$('connector-name').value.trim(),enabled:$('connector-enabled').checked,interval:Number($('interval').value)};
  if(v.kind==='rss')Object.assign(v,{url:$('feed-url').value.trim(),allow_local:$('allow-local').checked});
  if(v.kind==='imap')Object.assign(v,{host:$('mail-host').value.trim(),port:Number($('mail-port').value),username:$('mail-user').value.trim(),password:$('mail-password').value,folder:$('mail-folder').value});
  try{await api('extensions/connectors',v);edit();$('connector-details').open=false;await refresh();status('连接已保存。');}catch(e){status(e.message);}finally{$('mail-password').value='';b.disabled=false;}
};
$('model-form').onsubmit=async event=>{
  event.preventDefault();const b=event.submitter;b.disabled=true;
  try{await api('extensions/model',{enabled:$('model-enabled').checked,base_url:$('model-url').value.trim(),model:$('model-name').value.trim(),api_key:$('model-key').value,clear_key:$('clear-key').checked,max_tokens:Number($('model-tokens').value),token_field:$('token-field').value});await refresh();modelForm(state.model);status('模型连接已保存。现在可以发送消息；保存本身不会调用模型。');}catch(e){status(e.message);}finally{$('model-key').value='';b.disabled=false;}
};
function bubble(role,text){$('conversation').querySelector('.chat-empty')?.remove();const b=node('div','','bubble '+role);b.append(node('small',role==='user'?'你':'望包'),document.createTextNode(text));$('conversation').append(b);$('conversation').scrollTop=$('conversation').scrollHeight;}
async function chat(body,label){
  if(busy)return;busy=true;render();status();$('chat-status').textContent='望包正在想…';bubble('user',label);
  try{const result=await api('extensions/chat',body);bubble('assistant',result.reply);history=[...(body.notice_ids?[{role:'user',content:label}]:body.messages),{role:'assistant',content:result.reply.slice(0,4000)}].slice(-18);$('chat-status').textContent='对话仅保留在当前页面';}
  catch(e){bubble('assistant','这次没能连上。'+e.message);status(e.message);$('chat-status').textContent='未自动重试，可检查设置后重新发送';}
  finally{busy=false;render();}
}
$('chat-form').onsubmit=event=>{event.preventDefault();const content=$('chat-input').value.trim();if(!content||busy)return;$('chat-input').value='';const messages=[...history.slice(-18),{role:'user',content}];while(messages.reduce((n,m)=>n+m.content.length,0)>16000)messages.shift();chat({messages},content);};
$('clear-chat').onclick=()=>{if(busy){status('请等当前回复结束后再清空。');return;}history=[];$('conversation').replaceChildren(node('p','新的一段聊天，从这里开始。','chat-empty'));};
function summaryCount(){const count=document.querySelectorAll('#summary-notices input:checked').length;$('summarize').textContent=count?`总结选中通知（${count}）`:'总结选中通知';$('summarize').disabled=busy||!state?.model.enabled||count===0||count>20;}
async function notices(){
  const selected=new Set([...document.querySelectorAll('#summary-notices input:checked')].map(n=>n.value));
  try{const snap=await api('snapshot');$('summary-notices').replaceChildren();const notes=snap.notifications.filter(n=>!n.read).slice(0,50);
    if(!notes.length)$('summary-notices').append(node('p','当前没有未读通知。','hint'));
    for(const n of notes){const row=node('label','','summary-item'),check=document.createElement('input');check.type='checkbox';check.value=n.id;check.checked=selected.has(n.id);check.onchange=summaryCount;const description=node('span',n.label);description.append(node('small',n.summary));row.append(check,description);$('summary-notices').append(row);}summaryCount();
  }catch(e){status(e.message);}
}
$('summary-details').ontoggle=()=>{if($('summary-details').open)notices();};$('refresh-notices').onclick=notices;
$('summarize').onclick=()=>chat({notice_ids:[...document.querySelectorAll('#summary-notices input:checked')].map(n=>n.value)},'请帮我整理选中的通知。');
$('copy-mcp').onclick=async()=>{try{await navigator.clipboard.writeText($('mcp-config').textContent);status('MCP 配置已复制。');}catch{status('浏览器未允许复制，请直接选中配置文字复制。');}};
$('hide-secret').onclick=()=>{$('push-example').textContent='';$('push-secret').hidden=true;};
typeFields();await refresh(true);setInterval(()=>refresh(),8000);
