"""Durable, local-only task and notification reducer (no GUI dependencies)."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from presentation_layout import PresentationLayout

KINDS = {'started', 'working', 'waiting', 'resolved', 'completed', 'failed',
         'cancelled', 'idle', 'disconnected', 'connected', 'heartbeat', 'message', 'metadata',
         'archived', 'unarchived'}
TERMINAL = {'completed', 'failed', 'cancelled'}
FIELDS = {'event_id', 'source', 'thread_id', 'agent_id', 'run_id', 'kind',
          'label', 'summary', 'request_id', 'sequence', 'heartbeat_timeout',
          'silent', 'observed_at', 'clone', 'managed', 'link'}
LABELS = {'idle': '休息', 'running': '工作中', 'waiting': '等候确认',
          'completed': '本轮完成', 'failed': '任务失败', 'cancelled': '已取消',
          'disconnected': '连接断开'}
SOURCES = {'codex': 'Codex', 'cursor': 'Cursor', 'claude': 'Claude Code',
           'zcode': 'ZCode', 'dsh': 'DeepSeekHarness', 'local': '本地脚本'}
DEFAULT_SETTINGS = {'movement_locked': False, 'always_on_top': True, 'show_labels': True,
                    'desktop_scale': 100, 'auto_discover': True,
                    'sources': {key: True for key in SOURCES}, 'disabled_tasks': []}
REUNION_SECONDS = 9


def clean_event(value):
    if not isinstance(value, dict):
        raise ValueError('event must be an object')
    event = {k: v for k, v in value.items() if k in FIELDS}
    for key in ('event_id', 'source', 'thread_id', 'kind'):
        if not isinstance(event.get(key), str) or not event[key].strip():
            raise ValueError('missing ' + key)
    for key in ('event_id', 'source', 'thread_id', 'agent_id', 'run_id', 'request_id'):
        if key in event and (not isinstance(event[key], str) or len(event[key]) > 256
                             or any(ord(c) < 32 for c in event[key])):
            raise ValueError('invalid ' + key)
    if event['kind'] not in KINDS:
        raise ValueError('unknown kind')
    if 'link' in event:
        from extension_io import check_url
        if event['source'] != 'local' or not event['thread_id'].startswith('extension:'):
            raise ValueError('links only supported for extensions')
        check_url(event['link'])
    for key in ('silent', 'clone', 'managed'):
        if key in event and type(event[key]) is not bool:
            raise ValueError('invalid ' + key)
    if 'observed_at' in event and (type(event['observed_at']) not in (int, float) or
            not math.isfinite(event['observed_at']) or event['observed_at'] < 0):
        raise ValueError('invalid observed_at')
    for key, limit in [('label', 60), ('summary', 160)]:
        if key in event:
            if not isinstance(event[key], str):
                raise ValueError('invalid ' + key)
            event[key] = ' '.join(event[key].split())[:limit]
    if 'sequence' in event and (type(event['sequence']) is not int or event['sequence'] < 0):
        raise ValueError('invalid sequence')
    if 'heartbeat_timeout' in event:
        val = event['heartbeat_timeout']
        if type(val) not in (int, float) or not math.isfinite(val) or not 5 <= val <= 86400:
            raise ValueError('heartbeat_timeout must be 5..86400 seconds')
    return event


def task_key(event):
    identity = json.dumps([event['source'], event['thread_id'], event.get('agent_id') or 'main'],
                          ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(identity.encode('utf-8')).hexdigest()


class Store:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self.lock = threading.RLock()
        self.provider_status={}
        self.presentation = PresentationLayout()
        self.db = sqlite3.connect(str(self.path), timeout=5, check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, at REAL);
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notices (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS meta (id TEXT PRIMARY KEY, value INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS preferences (id TEXT PRIMARY KEY, data TEXT NOT NULL);
            INSERT OR IGNORE INTO meta VALUES ('revision', 0);
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    def settings(self):
        with self.lock:
            row=self.db.execute("SELECT data FROM preferences WHERE id='settings'").fetchone()
            defaults=json.loads(json.dumps(DEFAULT_SETTINGS))
            if row:
                saved=json.loads(row[0])
                defaults.update(saved)
                defaults['sources']={**DEFAULT_SETTINGS['sources'],**saved.get('sources',{})}
            return defaults

    def update_settings(self, patch):
        if not isinstance(patch,dict) or set(patch)-set(DEFAULT_SETTINGS):
            raise ValueError('unknown settings')
        with self.lock, self.db:
            current=self.settings()
            previous=json.loads(json.dumps(current))
            for key in ('movement_locked','always_on_top','show_labels','auto_discover'):
                if key in patch:
                    if type(patch[key]) is not bool:raise ValueError('invalid '+key)
                    current[key]=patch[key]
            if 'desktop_scale' in patch:
                scale=patch['desktop_scale']
                if type(scale) is not int or scale not in (50,75,100,125,150):
                    raise ValueError('invalid desktop_scale')
                current['desktop_scale']=scale
            if 'sources' in patch:
                sources=patch['sources']
                if (not isinstance(sources,dict) or set(sources)-set(SOURCES) or
                        any(type(value) is not bool for value in sources.values())):
                    raise ValueError('invalid sources')
                current['sources'].update(sources)
            if 'disabled_tasks' in patch:
                ids=patch['disabled_tasks']
                known={row[0] for row in self.db.execute('SELECT id FROM tasks')}
                if not isinstance(ids,list) or len(ids)>1000 or any(not isinstance(i,str) or i not in known for i in ids):
                    raise ValueError('unknown task selection')
                current['disabled_tasks']=sorted(set(ids))
            for task in self._all('tasks'):
                was_enabled=previous['sources'].get(task['source'],True) and task['id'] not in previous['disabled_tasks']
                is_enabled=current['sources'].get(task['source'],True) and task['id'] not in current['disabled_tasks']
                if is_enabled and not was_enabled:
                    # A paused hook may have missed a terminal event. Do not
                    # present its old phase as live until fresh evidence arrives.
                    task['needs_refresh']=True
                    self._put('tasks',task)
            self.db.execute("INSERT OR REPLACE INTO preferences VALUES ('settings',?)",(json.dumps(current),))
            self._bump()
            return current

    def enabled(self, source, key=None):
        settings=self.settings()
        return settings['sources'].get(source,True) and key not in settings['disabled_tasks']

    def _all(self, table):
        return [json.loads(row[0]) for row in self.db.execute('SELECT data FROM ' + table)]

    def _put(self, table, value):
        self.db.execute('INSERT OR REPLACE INTO ' + table + ' VALUES (?, ?)',
                        (value['id'], json.dumps(value, ensure_ascii=False)))

    def _bump(self):
        self.db.execute("UPDATE meta SET value=value+1 WHERE id='revision'")

    def _free_slot(self, excluding=None):
        occupied={t['slot'] for t in self._all('tasks')
                  if t['id'] != excluding and t.get('present',True)}
        slot=0
        while slot in occupied:slot+=1
        return slot

    def task(self, key):
        with self.lock:
            row=self.db.execute('SELECT data FROM tasks WHERE id=?',(key,)).fetchone()
            return json.loads(row[0]) if row else None

    def sync_presentation(self, key, *, unread=None, read_mode='manual', open_url=None, historical=False):
        """Apply provider metadata; opening a conversation never calls this method.

        None means unknown, including a missing/corrupt provider read-state file.
        A grace period allows the source GUI to persist its terminal blue dot.
        """
        with self.lock, self.db:
            task=self.task(key)
            if not task or not self.enabled(task['source'],key):return
            # Archive is independent of the provider's blue dot. A late read
            # observation must not cancel departure or resurrect the pet.
            if task.get('archived'):return
            before=json.dumps(task,sort_keys=True)
            now=self.clock()
            task['managed']=True
            task['read_mode']=read_mode
            if open_url is not None:task['open_url']=open_url
            task['read_known']=type(unread) is bool
            if unread is True:
                task.pop('retire_at',None)
                if not task.get('present',True):task['slot']=self._free_slot(key)
                task['present']=True
                if task['state'] in TERMINAL:
                    self._notice(task,task['state'],now)
                    # Source application may explicitly mark an old result unread again.
                    for n in self._all('notices'):
                        if n['task_id']==key and n['run_id']==task['run_id'] and n['kind'] in TERMINAL:
                            if n['read']:n['read']=False;self._put('notices',n);self._bump()
            elif unread is False and (historical or now-task.get('terminal_seen_at',now)>=3):
                for n in self._all('notices'):
                    if n['task_id']==key and not n['read'] and n['kind']!='waiting':
                        n['read']=True;self._put('notices',n);self._bump()
                if task['state'] in TERMINAL or task['state']=='idle':
                    task.setdefault('retire_at',now+(0 if historical else REUNION_SECONDS))
            elif unread is None and read_mode=='app':
                task.pop('retire_at',None)
            if json.dumps(task,sort_keys=True)!=before:self._put('tasks',task);self._bump()

    def set_archived(self, key, archived):
        """Apply an explicit provider flag, never infer archive from absence.

        Keep source read state and history intact. Only an explicit unarchive
        can make this conversation eligible for presentation again.
        """
        with self.lock, self.db:
            task=self.task(key)
            if not task or bool(task.get('archived'))==archived:return
            now=self.clock()
            task['archived']=archived
            if archived:
                task.update(archive_at=now,retire_at=now+REUNION_SECONDS,
                            action_id='archive-'+uuid.uuid4().hex)
            else:
                task.pop('retire_at',None)
                task.pop('archive_at',None)
                task['action_id']='unarchive-'+uuid.uuid4().hex
                unread=any(not n['read'] and n['task_id']==key for n in self._all('notices'))
                if task['state'] in {'running','waiting'} or unread:
                    if not task.get('present',True):task['slot']=self._free_slot(key)
                    task['present']=True
            self._put('tasks',task);self._bump()

    def _retire(self):
        now=self.clock()
        with self.db:
            for task in self._all('tasks'):
                if (task.get('present',True) and task.get('retire_at',float('inf'))<=now
                        and (task.get('archived') or task['state'] in TERMINAL|{'idle'})):
                    task['present']=False
                    self._put('tasks',task);self._bump()

    def _notice(self, task, kind, now, request_id='', summary='', link=None):
        identity = [task['id'], task['run_id'], kind, request_id]
        key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:32]
        row = self.db.execute('SELECT data FROM notices WHERE id=?', (key,)).fetchone()
        if row:  # A retry must not resurrect an acknowledged notification.
            return
        self._put('notices', {'id': key, 'task_id': task['id'], 'source': task['source'],
                  'thread_id': task['thread_id'], 'run_id': task['run_id'], 'kind': kind,
                  'label': task['label'], 'summary': summary or LABELS.get(kind, '有新消息'),
                  'created_at': now, 'read': False, 'resolved': False,
                  'request_id': request_id, 'open_url': link})

    def _resolve(self, task, request_id=None):
        for notice in self._all('notices'):
            if (notice['task_id'] == task['id'] and notice['kind'] == 'waiting'
                    and (request_id is None or notice['request_id'] == request_id)):
                notice.update(read=True, resolved=True)
                self._put('notices', notice)

    def ingest(self, value):
        event = clean_event(value)
        now, key = self.clock(), task_key(event)
        # Namespace idempotency by source; two providers may use the same event ID.
        eid = json.dumps([event['source'], event['event_id']])
        with self.lock, self.db:
            if not self.enabled(event['source'],key):
                return {'accepted': False, 'reason': 'connection_disabled'}
            if self.db.execute('SELECT 1 FROM events WHERE id=?', (eid,)).fetchone():
                return {'accepted': False, 'reason': 'duplicate'}
            row = self.db.execute('SELECT data FROM tasks WHERE id=?', (key,)).fetchone()
            task = json.loads(row[0]) if row else {
                'id': key, 'source': event['source'], 'thread_id': event['thread_id'],
                'agent_id': event.get('agent_id') or 'main', 'run_id': '', 'retired_runs': [],
                'label': event.get('label') or event['source'] + ' · ' + event['thread_id'][:8],
                'state': 'idle', 'summary': '', 'requests': {}, 'sequence': -1,
                'online': True, 'heartbeat_timeout': 0, 'last_seen': now,
                'state_at': now, 'action_id': event['event_id'], 'slot':
                self._free_slot()}
            kind, run = event['kind'], event.get('run_id') or task['run_id']
            if kind in {'archived','unarchived'}:
                if not row:return {'accepted':False,'reason':'unknown_task'}
                self.set_archived(key,kind=='archived')
                self.db.execute('INSERT INTO events VALUES (?,?)',(eid,now))
                return {'accepted':True,'task_id':key}
            if task.get('archived'):
                return {'accepted':False,'reason':'archived'}
            new_run = bool(run and run != task['run_id'])
            if row and new_run and 'observed_at' in event and event['observed_at'] < task['state_at']:
                return {'accepted': False, 'reason': 'stale_observation'}
            if run in task['retired_runs']:
                return {'accepted': False, 'reason': 'old_run'}
            if new_run and task['run_id'] and kind != 'started':
                return {'accepted': False, 'reason': 'run_mismatch'}
            if kind == 'started' and not event.get('run_id'):
                run, new_run = event['event_id'], True
            if new_run:
                if task['run_id']:
                    task['retired_runs'] = (task['retired_runs'] + [task['run_id']])[-128:]
                self._resolve(task)
                task.update(run_id=run, sequence=-1, requests={})
                if not task.get('present',True):task['slot']=self._free_slot(key)
                task['present']=True
                task.pop('retire_at',None)
                task.pop('terminal_seen_at',None)
                task['read_known']=False
            elif not task['run_id']:
                task['run_id'] = run or event['event_id']
            sequence = event.get('sequence')
            if sequence is not None and sequence <= task['sequence']:
                return {'accepted': False, 'reason': 'out_of_order'}
            if (not new_run and task['state'] in TERMINAL and
                    (kind in {'started', 'working', 'waiting', 'resolved', 'idle'} or
                     kind in TERMINAL and kind != task['state'])):
                return {'accepted': False, 'reason': 'terminal_run'}
            previous = task['state']
            if sequence is not None:
                task['sequence'] = sequence
            if kind != 'metadata':
                task.update(last_seen=now, online=kind != 'disconnected',needs_refresh=False)
            for name in ('label', 'summary', 'heartbeat_timeout', 'clone', 'managed'):
                if name in event:
                    task[name] = event[name]
            if event['source'] == 'local' and event['thread_id'].startswith('extension:'):
                task['open_url'] = event.get('link')
            if kind in {'started', 'working'}:
                task['state'] = 'waiting' if task['requests'] else 'running'
            elif kind == 'waiting':
                request = event.get('request_id') or 'confirmation'
                task['requests'][request] = event.get('summary') or task['label'] + ' 等候确认'
                task['state'] = 'waiting'
                self._notice(task, 'waiting', now, request, task['requests'][request])
            elif kind == 'resolved':
                request = event.get('request_id')
                if request and request in task['requests']:
                    task['requests'].pop(request)
                    self._resolve(task, request)
                    task['state'] = 'waiting' if task['requests'] else 'running'
            elif kind in TERMINAL or kind == 'idle':
                task['state'], task['requests'] = kind, {}
                task.setdefault('terminal_seen_at',now)
                if kind in TERMINAL:
                    task['heartbeat_timeout'] = 0
                self._resolve(task)
                if kind in {'completed', 'failed'} and not event.get('silent'):
                    self._notice(task, kind, now, summary=event.get('summary', ''), link=event.get('link'))
            elif kind == 'message':
                self._notice(task, kind, now, event.get('request_id') or event['event_id'],
                             event.get('summary', ''))
            if task['state'] != previous or new_run:
                task.update(state_at=min(now, event.get('observed_at', now)), action_id=event['event_id'])
            self._put('tasks', task)
            self.db.execute('INSERT INTO events VALUES (?,?)', (eid, now))
            # Keep unacknowledged results indefinitely. Bound only disposable history.
            self.db.execute('DELETE FROM events WHERE id IN (SELECT id FROM events ORDER BY at DESC LIMIT -1 OFFSET 20000)')
            read = sorted((n for n in self._all('notices') if n['read']),
                          key=lambda n: n['created_at'], reverse=True)
            for notice in read[1000:]:
                self.db.execute('DELETE FROM notices WHERE id=?', (notice['id'],))
            self._bump()
            return {'accepted': True, 'task_id': key}

    def acknowledge(self, ids):
        if not isinstance(ids, list) or len(ids) > 1000 or not all(isinstance(i, str) for i in ids):
            raise ValueError('ids must be a list of notification IDs')
        with self.lock, self.db:
            changed = 0
            for notice in self._all('notices'):
                if notice['id'] in ids and not notice['read']:
                    task=self.task(notice['task_id'])
                    if task and task.get('read_mode')=='app':continue
                    notice['read'] = True
                    self._put('notices', notice)
                    changed += 1
                    if task and task.get('managed') and task['state'] in TERMINAL:
                        remaining=any(not n['read'] and n['task_id']==task['id'] for n in self._all('notices'))
                        if not remaining:
                            task.setdefault('retire_at',self.clock()+REUNION_SECONDS)
                            self._put('tasks',task)
            if changed:
                self._bump()
            return {'acknowledged': changed}

    def snapshot(self):
        with self.lock:
            self._retire()
            now = self.clock()
            tasks, notices = self._all('tasks'), self._all('notices')
            settings=self.settings()
            catalog=[{'id':t['id'],'source':t['source'],'label':t['label'],'thread_id':t['thread_id'],
                      'last_seen':t['last_seen'],'enabled':t['id'] not in settings['disabled_tasks']}
                     for t in sorted(tasks,key=lambda t:(not t.get('clone',False),t['slot']))]
            sources=[{'id':key,'label':label,'enabled':settings['sources'][key],
                      'status':self.provider_status.get(key,'等待本地事件'),
                      'last_seen':max((t['last_seen'] for t in tasks if t['source']==key),default=None),
                      'method':{'codex':'自动发现本地任务；已读跟随 Codex 蓝点',
                                'cursor':'自动发现 GUI 会话；已读跟随 Cursor',
                                'zcode':'自动发现 GUI 任务；已读跟随 ZCode',
                                'claude':'用户级 hooks 自动接收任务；已读需手动确认',
                                'dsh':'本地插件接收任务；已读需手动确认',
                                'local':'通过通知命令或任务包装器接收事件'}[key]}
                     for key,label in SOURCES.items()]
            tasks=[t for t in tasks if settings['sources'].get(t['source'],True) and t['id'] not in settings['disabled_tasks']]
            active={t['id'] for t in tasks if not t.get('archived')}
            notices=[n for n in notices if n['task_id'] in active]
            modes={t['id']:t.get('read_mode','manual') for t in tasks}
            urls={t['id']:t.get('open_url') for t in tasks}
            for n in notices:
                n['read_mode']=modes[n['task_id']]
                n['open_url']=n.get('open_url') or (urls[n['task_id']] if n['source'] != 'local' else None)
            tasks=[t for t in tasks if t.get('present',True)]
            notices.sort(key=lambda n: n['created_at'], reverse=True)
            for task in tasks:
                offline = (task.get('needs_refresh',False) or not task['online'] or bool(task['heartbeat_timeout'] and
                           now - task['last_seen'] > task['heartbeat_timeout']))
                task['display_state'] = 'completed' if task.get('archived') else 'disconnected' if offline else task['state']
                if task.get('archived'):
                    # Presentation clock only: retain the original event time
                    # in storage for stale-event protection after unarchive.
                    task['state_at']=task['archive_at']
                task['unread_ids'] = [n['id'] for n in notices if n['task_id'] == task['id'] and not n['read']]
                task['bubble'] = next(iter(task['requests'].values()), '')
                state = task['display_state']
                age = max(0, now - task['state_at'])
                if state == 'completed':
                    action = 'closing' if age < 3.5 else 'walk' if age < 6.5 else 'following'
                    action_age = age if age < 3.5 else age - (3.5 if age < 6.5 else 6.5)
                else:
                    action = {'running': 'typing', 'waiting': 'waiting', 'failed': 'failed',
                              'disconnected': 'disconnected'}.get(state, 'idle')
                    action_age = age
                task.update(action=action, action_age=action_age)
                task['failure_roll'] = int(hashlib.sha256((task['id'] + task['action_id']).encode()).hexdigest()[:8], 16) / 2**32
                task.pop('retired_runs', None)
            tasks.sort(key=lambda t: (not t.get('clone', False), t['slot']))
            views = self.presentation.update([{'id':t['id'], 'order':t['slot'],
                'gathered':t['state']=='completed' or bool(t.get('retire_at')),
                'needs_desk':not (t['state']=='completed' or t.get('retire_at')) or now-t['state_at']<3.5}
                for t in tasks])
            for task in tasks: task.update(views[task['id']])
            unread = sum(not n['read'] for n in notices)
            states = {t['display_state'] for t in tasks}
            # Actionable blocks take priority; unread count remains separately visible.
            leader = next((s for s in ['waiting', 'failed'] if s in states), None)
            leader = leader or ('unread' if unread else next((s for s in ['running', 'disconnected'] if s in states), 'idle'))
            return {'version': 1, 'revision': self.db.execute("SELECT value FROM meta WHERE id='revision'").fetchone()[0],
                    'server_time': now, 'tasks': tasks, 'notifications': notices,
                    'unread_count': unread, 'leader_state': leader,
                    'settings': settings, 'connections': {'sources': sources, 'tasks': catalog}}


def make_event(source, thread_id, kind, **fields):
    return dict(event_id=uuid.uuid4().hex, source=source, thread_id=thread_id, kind=kind, **fields)
