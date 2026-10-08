"""Only verified navigation routes; never execute text supplied by an event."""
import re
from urllib.parse import quote, urlsplit, parse_qs

UUID = re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$',re.I)


def conversation_url(source, thread_id, workspace=''):
    if source=='codex' and UUID.fullmatch(thread_id):
        return 'codex://threads/'+thread_id
    if source=='cursor' and UUID.fullmatch(thread_id):
        return 'cursor://wang-bun.local-monitor/open?id='+thread_id
    if source=='zcode' and workspace and not workspace.startswith(('http:', 'https:')):
        # ZCode 3.14 exposes workspace/open but no task-specific deep link.
        return 'zcode://workspace/open?path='+quote(workspace,safe='')
    return None


def allowed_url(value, external=False):
    if not isinstance(value,str) or len(value)>8192:return False
    u=urlsplit(value)
    if u.username or u.password or u.fragment:return False
    if external and u.scheme in ('http','https'):
        return bool(u.hostname) and not any(ord(c)<33 for c in value)
    if u.scheme=='codex':
        return u.netloc=='threads' and not u.query and bool(UUID.fullmatch(u.path.lstrip('/')))
    if u.scheme=='zcode':
        q=parse_qs(u.query)
        return u.netloc=='workspace' and u.path=='/open' and set(q)=={'path'} and len(q['path'])==1
    if u.scheme=='cursor':
        q=parse_qs(u.query)
        return (u.netloc=='wang-bun.local-monitor' and u.path=='/open' and set(q)=={'id'}
                and len(q['id'])==1 and bool(UUID.fullmatch(q['id'][0])))
    return False


def open_conversation(task, opener=None):
    if task['source']=='cursor':
        from cursor_navigation import CursorNavigator
        return CursorNavigator(opener=opener).open(task['thread_id'])
    url=task.get('open_url') or conversation_url(task['source'],task['thread_id'])
    if not allowed_url(url, external=task['source']=='local' and task['thread_id'].startswith('extension:')):return False
    if opener is None:
        import os,webbrowser
        opener=os.startfile if os.name=='nt' else webbrowser.open
    opener(url)
    return True
