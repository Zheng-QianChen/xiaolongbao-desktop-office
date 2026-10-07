// Explicit session discovery and selection. Labels always enter the DOM as text.
export function setupConnections({api,onAdded}){
  const $=id=>document.getElementById(id);
  let busy=false, choices=new Map();
  function selection(){
    const count=[...choices.values()].filter(input=>input.checked).length;
    $('add-codex').disabled=busy||count<1||count>20;
    $('codex-count').textContent=count?`已选择 ${count} 个 · 每次最多 20 个`:'';
  }
  function setBusy(value){
    busy=value;
    $('refresh-codex').disabled=value;$('codex-query').disabled=value;
    for(const input of choices.values())input.disabled=value;
    selection();
  }
  function render(data){
    const list=$('codex-candidates');list.replaceChildren();choices=new Map();
    for(const session of data.sessions){
      const label=document.createElement('label');label.className='setting-row';
      const input=document.createElement('input');input.type='checkbox';input.disabled=session.selected;
      input.dataset.sessionId=session.id;input.setAttribute('aria-label',session.label+' · '+session.id.slice(0,8));
      const caption=document.createElement('span');caption.className='connection-caption';caption.textContent=session.label;
      const details=document.createElement('small');details.textContent=session.id.slice(0,8)+'…'+session.id.slice(-6)+(session.selected?' · 已登记':'');
      caption.append(details);label.append(input,caption);list.append(label);
      if(!session.selected){choices.set(session.id,input);input.onchange=selection;}
    }
    selection();list.scrollTop=0;
    let message=!data.sessions.length?'没有找到可接入的会话，请换个关键词或先在 Codex 中创建会话。':
      data.truncated?'仅显示最近 100 个会话，可输入标题或 ID 搜索。':`找到 ${data.sessions.length} 个会话。`;
    if(!data.source_enabled)message+='\nCodex 来源已暂停；接入后需在上级设置中开启并保存。';
    return message;
  }
  async function refresh(notice=''){
    if(busy)return;
    setBusy(true);$('codex-message').textContent='正在读取本机会话列表…';
    try{
      const data=await api('codex/sessions?q='+encodeURIComponent($('codex-query').value));
      $('codex-message').textContent=(notice?notice+'\n':'')+render(data);
    }catch(error){$('codex-message').textContent=(notice?notice+'\n':'')+error.message;}
    finally{setBusy(false);}
  }
  $('open-codex').onclick=()=>{$('codex-dialog').showModal();refresh();};
  $('refresh-codex').onclick=()=>refresh();
  $('codex-query').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();refresh();}};
  $('close-codex').onclick=()=>$('codex-dialog').close();
  $('add-codex').onclick=async()=>{
    const ids=[...choices].filter(([,input])=>input.checked).map(([id])=>id);
    if(busy||!ids.length||ids.length>20)return;
    setBusy(true);$('codex-message').textContent='正在接入选中会话…';
    let notice='';
    try{
      const result=await api('codex/sessions',{ids});
      notice=`已登记 ${result.registered} 个会话。`;
      await onAdded();
    }catch(error){$('codex-message').textContent=error.message;}
    finally{setBusy(false);}
    if(notice)await refresh(notice);
  };
}
