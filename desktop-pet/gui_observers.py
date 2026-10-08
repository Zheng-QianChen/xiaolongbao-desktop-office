"""Read-only GUI metadata projections. No message bodies or tool inputs leave SQLite."""
import hashlib
import json
from pathlib import Path
import sqlite3
import time

from bridge_store import make_event,task_key,TERMINAL
from provider_links import conversation_url


def readonly(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=.5)
    db.execute('PRAGMA query_only=ON')
    return db


def cursor_rows(path):
    db=readonly(path)
    try:
        # Current Cursor keeps the lifecycle in composerData and the sidebar's
        # read indicator in composerHeaders. SQL projects only named metadata.
        rows=db.execute('''SELECT h.composerId,
            json_extract(h.value,'$.name'),json_extract(k.value,'$.status'),
            json_extract(h.value,'$.hasUnreadMessages'),
            COALESCE(json_extract(k.value,'$.latestChatGenerationUUID'),json_extract(k.value,'$.chatGenerationUUID')),
            h.lastUpdatedAt,json_extract(h.value,'$.hasBlockingPendingActions'),COALESCE(h.isArchived,0)
            FROM composerHeaders h LEFT JOIN cursorDiskKV k ON k.key='composerData:'||h.composerId
            WHERE COALESCE(json_extract(h.value,'$.isDraft'),0)=0''').fetchall()
        mapping={'generating':'running','completed':'completed','aborted':'cancelled','error':'failed','failed':'failed'}
        return [dict(id=i,label=label or 'Cursor · '+i[:8],state='waiting' if waiting and status=='generating' else mapping.get(status),
                     unread=bool(unread) if unread in (0,1) else None,run=run,updated=(updated or 0)/1000,archived=bool(archived))
                for i,label,status,unread,run,updated,waiting,archived in rows]
    finally:db.close()


def zcode_rows(path):
    db=readonly(path)
    try:
        rows=db.execute('''SELECT task_id,title,task_status,unread_at,last_unread_at,updated_at,workspace_path,
            json_extract(meta_json,'$.runId'),archived,deleted FROM tasks''').fetchall()
        mapping={'running':'running','waiting':'waiting','completed':'completed','error':'failed',
                 'failed':'failed','cancelled':'cancelled','canceled':'cancelled','idle':'idle'}
        return [dict(id=i,label=label or 'ZCode · '+i[:8],state=mapping.get(status),unread=unread is not None,
                     run=run,terminal_marker=marker,updated=(updated or 0)/1000,workspace=workspace,archived=bool(archived or deleted))
                for i,label,status,unread,marker,updated,workspace,run,archived,deleted in rows]
    finally:db.close()


class GuiObservers:
    def __init__(self,runtime,store,home=None):
        self.runtime=Path(runtime);self.store=store;self.home=Path(home or Path.home())
        self.last_poll=0
        self.path=self.runtime/'gui-observer-cursors.json'
        try:self.cursors=json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError,ValueError):self.cursors={}
        self.initial=set()

    def project(self,source,row):
        if not isinstance(row.get('id'),str):return
        key=task_key({'source':source,'thread_id':row['id']})
        if not self.store.enabled(source,key):return
        if 'archived' in row:self.store.set_archived(key,row['archived'])
        if row.get('archived') or not row.get('state'):return
        old=self.cursors.get(key,{})
        task=self.store.task(key)
        state=row['state']
        historical=not task and state in TERMINAL|{'idle'} and row['unread'] is not True
        if historical:
            # Establish a baseline without summoning every old conversation.
            self.cursors[key]=dict(state=state,run=row.get('run'),marker=row.get('terminal_marker'))
            return
        marker=row.get('terminal_marker')
        run=row.get('run') or old.get('run') or ('gui-'+hashlib.sha256((key+str(row['updated'])).encode()).hexdigest()[:24])
        if not row.get('run') and old and (state in {'running','waiting'} and old.get('state') in TERMINAL|{'idle'}
                or state in TERMINAL and marker and marker!=old.get('marker')):
            run='gui-'+hashlib.sha256((key+str(row['updated'])+str(marker)).encode()).hexdigest()[:24]
        kind={'running':'started','waiting':'waiting'}.get(state,state)
        fingerprint=[state,run,row['label']]
        if old.get('fingerprint')!=fingerprint or not task or task.get('needs_refresh'):
            fields=dict(run_id=str(run),label=row['label'],managed=True,silent=row['unread'] is False,
                        observed_at=row['updated'] or time.time())
            if task and task['run_id']!=run:
                self.store.ingest(make_event(source,row['id'],'started',**fields))
            self.store.ingest(make_event(source,row['id'],kind,**fields))
            # A paused connection resumes only from this fresh GUI observation.
            self.store.ingest(make_event(source,row['id'],'connected'))
        self.cursors[key]=dict(state=state,run=run,marker=marker,fingerprint=fingerprint)
        self.store.sync_presentation(key,unread=row['unread'],read_mode='app',
            open_url=conversation_url(source,row['id'],row.get('workspace','')),
            historical=key not in self.initial and row['updated']<time.time()-30)
        self.initial.add(key)

    def poll(self,force=False):
        if not force and time.monotonic()-self.last_poll<2:return
        self.last_poll=time.monotonic()
        if not self.store.settings()['auto_discover']:return
        for source,path,reader in [
            ('cursor',self.home/'AppData/Roaming/Cursor/User/globalStorage/state.vscdb',cursor_rows),
            ('zcode',self.home/'.zcode/v2/tasks-index.sqlite',zcode_rows)]:
            if not self.store.enabled(source):continue
            try:
                if not path.exists():
                    self.store.provider_status[source]='尚未发现本机数据'
                    self.unavailable(source)
                    continue
                rows=reader(path)
                for row in rows:self.project(source,row)
                self.store.provider_status[source]='已连接 · 自动发现任务' if path.exists() else '尚未发现本机数据'
            except (OSError,sqlite3.Error,ValueError,TypeError):
                self.store.provider_status[source]='暂时无法读取状态，保留未读结果'
                self.unavailable(source)
        temporary=self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.cursors,ensure_ascii=False),encoding='utf-8');temporary.replace(self.path)

    def unavailable(self,source):
        with self.store.lock:
            for task in self.store._all('tasks'):
                if task['source']==source and task.get('read_mode')=='app':
                    self.store.sync_presentation(task['id'],unread=None,read_mode='app')
