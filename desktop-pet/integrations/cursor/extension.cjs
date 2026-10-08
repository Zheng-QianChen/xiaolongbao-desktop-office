const validId=/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
function register(context,vscode){
  context.subscriptions.push(vscode.window.registerUriHandler({async handleUri(uri){
    if(uri.path!=='/open')return;
    const params=new URLSearchParams(uri.query),id=params.get('id');
      if(!id||!validId.test(id)||[...params.keys()].some(k=>!['id','windowId'].includes(k)))return;
      if(params.getAll('id').length!==1||params.getAll('windowId').length!==1||
         !/^[1-9]\d{0,8}$/.test(params.get('windowId')))return;
    try{
      // The same native command Cursor's own completion notification uses.
      // It owns navigation/read-state changes; the pet never writes them.
      await vscode.commands.executeCommand('composer.openComposerFromNotification',{composerId:id});
    }catch{
      vscode.window.showInformationMessage('无法打开此 Cursor 会话，请从会话列表查看。望包会保留未读状态。');
    }
  }}));
}
exports.activate=context=>register(context,require('vscode'));
exports.register=register;
exports.deactivate=()=>{};
