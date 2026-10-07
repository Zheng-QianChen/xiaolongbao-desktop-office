"""Read-only lifecycle observer for explicitly selected local Codex conversations.

Only task_started/task_complete/turn_aborted metadata is projected. Assistant text,
tool arguments/results, prompt text, settings, credentials, and approvals are not copied.
"""
from datetime import datetime
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

from bridge_store import make_event,task_key
from codex_read_state import read_blue_dots
from provider_links import conversation_url

LIFECYCLE = {'task_started': 'started', 'task_complete': 'completed', 'turn_aborted': 'cancelled'}
MAX_LINE = 1024 * 1024
BOOTSTRAP_BYTES = 8 * 1024 * 1024
UUID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)


def lifecycle(line, thread):
    """Return a minimal event; no free-text field from a rollout enters the bridge."""
    try:
        record = json.loads(line)
        if not isinstance(record, dict) or record.get('type') != 'event_msg':
            return None
        payload = record.get('payload')
        if not isinstance(payload, dict) or payload.get('type') not in LIFECYCLE:
            return None
        run = payload.get('turn_id')
        if not isinstance(run, str) or not run:
            return None
        timestamp = record.get('timestamp')
        at = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp()
        event = make_event('codex', thread['id'], LIFECYCLE[payload['type']],
                           run_id=run, label=thread['label'], clone=True, observed_at=at)
        identity = [thread['id'], run, payload['type'], timestamp]
        event['event_id'] = 'rollout-' + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        return event
    except (ValueError, UnicodeError, AttributeError, TypeError):
        return None


def scan(path, offset, limit=BOOTSTRAP_BYTES):
    """Bounded incremental JSONL reads, preserving partial records across polls."""
    result = []
    with path.open('rb') as stream:
        stream.seek(offset)
        end = offset + limit
        while stream.tell() < end:
            start = stream.tell()
            line = stream.readline(MAX_LINE + 1)
            if not line:
                break
            if len(line) > MAX_LINE:
                # Oversized records cannot be lifecycle metadata. Skip without decoding.
                while line and not line.endswith(b'\n'):
                    line = stream.readline(MAX_LINE + 1)
                if not line:
                    stream.seek(start)
                    break
                continue
            if not line.endswith(b'\n'):
                stream.seek(start)
                break
            result.append(line)
        return result, stream.tell()


def bootstrap(path, thread, end=None):
    size = path.stat().st_size
    if end is not None:size=min(size,end)
    start = max(0, size - BOOTSTRAP_BYTES)
    if start:
        with path.open('rb') as stream:
            stream.seek(start)
            stream.readline()
            start = stream.tell()
    lines, offset = scan(path, start,max(0,size-start))
    latest = None
    for line in lines:
        event = lifecycle(line, thread)
        if event:
            latest = event
    return latest, offset


class CloneObserver:
    def __init__(self, runtime, store):
        self.runtime, self.store = Path(runtime), store
        self.config_path = self.runtime/'codex-clones.json'
        self.cursor_path = self.runtime/'codex-clone-cursors.json'
        self.report_path = self.runtime/'codex-clone-status.json'
        self.last_poll = 0
        self.initial_sync=set()
        self.lock = threading.RLock()
        try:
            self.cursors = json.loads(self.cursor_path.read_text(encoding='utf-8'))
            if not isinstance(self.cursors, dict):
                self.cursors = {}
        except (OSError, ValueError):
            self.cursors = {}

    def write_json(self, path, value):
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        tmp.replace(path)

    def read_config(self):
        if not self.config_path.exists():
            return {'threads': []}
        config = json.loads(self.config_path.read_text(encoding='utf-8'))
        if not isinstance(config, dict) or not isinstance(config.get('threads'), list):
            raise ValueError('invalid selected conversations')
        if any(not isinstance(t, dict) or not isinstance(t.get('id'), str) or
               not UUID.fullmatch(t['id']) or not isinstance(t.get('label'), str)
               for t in config['threads']):
            raise ValueError('invalid selected conversation')
        if 'codex_home' in config and not isinstance(config['codex_home'], str):
            raise ValueError('invalid Codex home')
        return config

    def poll(self, force=False):
        with self.lock:
            self._poll(force)

    def _poll(self, force=False):
        if not force and time.monotonic() - self.last_poll < 1:
            return
        self.last_poll = time.monotonic()
        report = {'checked_at': time.time(), 'watching': [], 'errors': []}
        try:
            config = self.read_config()
            home = Path(config.get('codex_home') or os.environ.get('CODEX_HOME') or Path.home()/'.codex').resolve()
            config['codex_home']=str(home)
            automatic=False
            blue_dots=None
            if self.store.settings()['auto_discover'] and self.store.enabled('codex') and (home/'state_5.sqlite').exists():
                with closing(sqlite3.connect((home/'state_5.sqlite').as_uri()+'?mode=ro',uri=True,timeout=1)) as discovery:
                    discovery.execute('PRAGMA query_only=ON')
                    columns={r[1] for r in discovery.execute('PRAGMA table_info(threads)')}
                    if {'title','archived','updated_at'}<=columns:
                        automatic=True
                        blue_dots=read_blue_dots(home)
                        rows=discovery.execute('SELECT id,title FROM threads WHERE archived=0 ORDER BY updated_at DESC').fetchall()
                        known={t['id']:t for t in config['threads']}
                        for ident,label in rows:
                            if UUID.fullmatch(ident):known[ident]={'id':ident,'label':label or 'Codex 会话','automatic':True,
                                                                'unread':ident in (blue_dots or set())}
                        config['threads']=list(known.values())
                        self.store.provider_status['codex']='已连接 · 已读跟随蓝点' if blue_dots is not None else '已连接 · 已读状态暂不可用'
            # Persist paused markers so re-enabling catches up silently, even after restart.
            enabled=[]
            for thread in config['threads']:
                key=task_key({'source':'codex','thread_id':thread['id']})
                if self.store.enabled('codex',key):enabled.append(thread)
                else:
                    self.cursors.setdefault(thread['id'],{})['paused']=True
            if not enabled:
                self.write_json(self.cursor_path,self.cursors)
                self.write_json(self.report_path,report)
                return
            con = sqlite3.connect((home/'state_5.sqlite').as_uri()+'?mode=ro', uri=True, timeout=1)
            try:
                for thread in enabled:
                    thread = dict(thread, selected_at=thread.get('selected_at', config.get('selected_at')))
                    ident = thread['id']
                    if not UUID.fullmatch(ident) or not isinstance(thread.get('label'), str):
                        raise ValueError('invalid selected conversation')
                    row = con.execute('SELECT rollout_path FROM threads WHERE id=?', (ident,)).fetchone()
                    if not row:
                        report['errors'].append({'thread_id': ident, 'reason': 'rollout_not_found'})
                        continue
                    path_text = row[0]
                    if path_text.startswith('\\\\?\\'):
                        path_text = path_text[4:]
                    path = Path(path_text).resolve()
                    if (home/'sessions').resolve() not in path.parents:
                        report['errors'].append({'thread_id': ident, 'reason': 'outside_sessions'})
                        continue
                    try:
                        first=ident not in self.initial_sync
                        self.observe(path, thread)
                        if automatic:
                            key=task_key({'source':'codex','thread_id':ident})
                            current=self.store.task(key)
                            old=bool(current and time.time()-current['state_at']>30)
                            self.store.sync_presentation(key,unread=None if blue_dots is None else ident in blue_dots,
                                read_mode='app',open_url=conversation_url('codex',ident),historical=first and old)
                            if self.store.task(key):self.initial_sync.add(ident)
                        report['watching'].append(ident)
                    except (OSError, ValueError):
                        report['errors'].append({'thread_id': ident, 'reason': 'rollout_unavailable'})
            finally:
                con.close()
            self.write_json(self.cursor_path, self.cursors)
        except (OSError, sqlite3.Error, ValueError, KeyError, TypeError):
            report['errors'].append({'reason': 'observer_unavailable'})
        self.write_json(self.report_path, report)

    def observe(self, path, thread):
        ident, stat = thread['id'], path.stat()
        identity = [stat.st_dev, stat.st_ino]
        previous = self.cursors.get(ident)
        if previous and previous.get('paused'):
            if not previous.get('pause_search_started'):
                previous['history_before']=max(0,stat.st_size-BOOTSTRAP_BYTES)
                previous['pause_search_started']=True
            latest,offset=bootstrap(path,thread)
            if latest is None and previous.get('history_before'):
                latest,_=bootstrap(path,thread,previous['history_before'])
                previous['history_before']=max(0,previous['history_before']-BOOTSTRAP_BYTES)
            if latest is None:
                # Keep needs_refresh until actual lifecycle evidence is found.
                # Each poll searches one older bounded window plus the current tail.
                return
            if latest:
                latest['silent']=True
                result=self.store.ingest(latest)
                if result.get('reason')=='run_mismatch' and latest['kind'] in {'completed','cancelled'}:
                    self.store.ingest(dict(latest,kind='started',event_id=latest['event_id']+'-resume-start'))
                    self.store.ingest(latest)
                self.store.ingest(make_event('codex',ident,'connected',label=thread['label'],clone=True))
            self.cursors[ident]={'offset':offset,'identity':identity,'path':str(path),'label':thread['label']}
            return
        if not previous:
            event, offset = bootstrap(path, thread)
            if event is None:
                if thread.get('automatic'):
                    self.cursors[ident]={'offset':offset,'identity':identity,'path':str(path),'label':thread['label'],
                                        'history_before':max(0,stat.st_size-BOOTSTRAP_BYTES)}
                    return
                # No trustworthy terminal event was found; the app snapshot supplies only idle/running.
                kind = {'active': 'started', 'unknown': 'disconnected'}.get(thread.get('status'), 'idle')
                event = make_event('codex', ident, kind,
                    run_id='snapshot-'+ident, label=thread['label'], clone=True)
                event['event_id'] = 'snapshot-'+ident
            elif thread.get('selected_at') and not thread.get('automatic'):
                selected = datetime.fromisoformat(thread['selected_at'].replace('Z', '+00:00')).timestamp()
                if event['observed_at'] <= selected:
                    if thread.get('status') == 'idle' and event['kind'] == 'started':
                        event.update(kind='idle', event_id=event['event_id']+'-idle-snapshot')
                    elif thread.get('status') == 'active' and event['kind'] in {'completed','cancelled'}:
                        event.update(kind='started', run_id='snapshot-'+ident,
                                     event_id='active-snapshot-'+ident, observed_at=selected)
            event['silent'] = not thread.get('unread', False)
            result = self.store.ingest(event)
            if result.get('reason') == 'run_mismatch' and event['kind'] in {'completed', 'cancelled'}:
                # A hook may already know an older run of this newly selected session.
                # The store's observation-time guard still rejects historical rollbacks.
                self.store.ingest(dict(event, kind='started', event_id=event['event_id']+'-initial-start'))
                self.store.ingest(event)
            self.cursors[ident] = {'offset': offset, 'identity': identity, 'path': str(path), 'label': thread['label']}
            return
        rotated = previous['identity'] != identity or previous['path'] != str(path) or stat.st_size < previous['offset']
        if rotated:
            latest, offset = bootstrap(path, thread)
            lines = []
            if latest:
                self.ingest_lifecycle(latest)
            previous['history_before']=0 if latest else max(0,stat.st_size-BOOTSTRAP_BYTES)
        else:
            lines, offset = scan(path, previous['offset'])
        saw_event=False
        for line in lines:
            event = lifecycle(line, thread)
            if event:
                saw_event=True
                self.ingest_lifecycle(event)
        before=0 if saw_event else previous.get('history_before',0)
        if before:
            historical,_=bootstrap(path,thread,before)
            before=max(0,before-BOOTSTRAP_BYTES)
            if historical:
                historical['silent']=not thread.get('unread',False)
                self.ingest_lifecycle(historical)
                before=0
        if previous.get('label') != thread['label']:
            self.store.ingest(make_event('codex', ident, 'metadata', label=thread['label'], clone=True))
        self.cursors[ident] = {'offset': offset, 'identity': identity, 'path': str(path), 'label': thread['label'],
                              'history_before':before}

    def ingest_lifecycle(self,event):
        result=self.store.ingest(event)
        if result.get('reason')=='run_mismatch' and event['kind'] in {'completed','cancelled'}:
            # Observation timestamps and retired-run checks still reject old history.
            self.store.ingest(dict(event,kind='started',event_id=event['event_id']+'-adopt',silent=True))
            self.store.ingest(event)
