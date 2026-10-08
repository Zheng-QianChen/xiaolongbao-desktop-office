import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from bridge_store import Store,make_event,task_key,REUNION_SECONDS
from codex_read_state import read_blue_dots
from codex_clones import CloneObserver
from gui_observers import GuiObservers,cursor_rows,zcode_rows
from provider_links import open_conversation,allowed_url

class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.now=1000
        self.store=Store(self.root/'state.sqlite',clock=lambda:self.now)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def event(self,kind,thread='a',run='run-1'):
        return self.store.ingest(make_event('codex',thread,kind,run_id=run,managed=True))['task_id']
    def test_unread_stays_then_read_reunites_retires_and_reuses_slot(self):
        key=self.event('started');self.event('completed')
        self.store.sync_presentation(key,unread=True,read_mode='app')
        other=self.event('started','b')
        self.now+=100
        self.assertEqual(len(self.store.snapshot()['tasks']),2)
        self.store.sync_presentation(key,unread=False,read_mode='app')
        self.assertEqual(self.store.snapshot()['unread_count'],0)
        self.now+=REUNION_SECONDS-1
        self.assertEqual(len(self.store.snapshot()['tasks']),2)
        self.now+=2
        self.assertEqual([t['id'] for t in self.store.snapshot()['tasks']],[other])
        third=self.event('started','c')
        self.assertEqual(self.store.task(third)['slot'],0)
        self.assertEqual(self.store.task(other)['slot'],1)
    def test_new_turn_cancels_departure_and_gets_available_desk(self):
        key=self.event('started');self.event('completed');self.now+=5
        self.store.sync_presentation(key,unread=False,read_mode='app')
        self.event('started',run='run-2');self.now+=20
        self.assertEqual(self.store.snapshot()['tasks'][0]['state'],'running')
        self.assertNotIn('retire_at',self.store.task(key))
    def test_unknown_or_corrupt_read_state_never_dismisses(self):
        key=self.event('completed');self.now+=5
        self.store.sync_presentation(key,unread=False,read_mode='app')
        self.store.sync_presentation(key,unread=None,read_mode='app');self.now+=20
        self.assertEqual(len(self.store.snapshot()['tasks']),1)
    def test_local_ack_cannot_override_app_blue_dot(self):
        key=self.event('completed');self.store.sync_presentation(key,unread=True,read_mode='app')
        ids=self.store.snapshot()['tasks'][0]['unread_ids']
        self.assertEqual(self.store.acknowledge(ids)['acknowledged'],0)
        self.assertEqual(self.store.snapshot()['unread_count'],1)
    def test_terminal_grace_does_not_consume_old_false(self):
        key=self.event('completed');self.store.sync_presentation(key,unread=False,read_mode='app')
        self.assertNotIn('retire_at',self.store.task(key))
        self.store.sync_presentation(key,unread=True,read_mode='app')
        self.now+=100;self.assertEqual(len(self.store.snapshot()['tasks']),1)
    def test_open_only_navigates_does_not_ack(self):
        key=self.event('completed',thread='01a1084f-58f0-7100-82c7-248853266b30')
        opened=[]
        self.assertTrue(open_conversation(self.store.task(key),opened.append))
        self.assertTrue(opened[0].startswith('codex://threads/'))
        self.assertEqual(self.store.snapshot()['unread_count'],1)
        for url in ['file:///c:/evil','powershell:cmd','https://example.com','codex://threads/not-an-id']:
            self.assertFalse(allowed_url(url))
    def test_manual_fallback_retires_only_after_explicit_ack(self):
        key=self.event('completed');ids=self.store.snapshot()['tasks'][0]['unread_ids']
        self.store.acknowledge(ids);self.now+=REUNION_SECONDS+1
        self.assertEqual(self.store.snapshot()['tasks'],[])
    def test_source_mark_unread_resurrects_once_and_survives_restart(self):
        key=self.event('completed');self.now+=5
        self.store.sync_presentation(key,unread=False,read_mode='app');self.now+=20
        self.assertEqual(self.store.snapshot()['tasks'],[])
        self.store.sync_presentation(key,unread=True,read_mode='app')
        self.assertEqual(len(self.store.snapshot()['tasks']),1)
        self.assertEqual(self.store.snapshot()['unread_count'],1)

    def test_idle_read_has_finite_grace_period(self):
        key=self.event('idle');self.now+=4
        self.store.sync_presentation(key,unread=False,read_mode='app')
        self.assertIn('retire_at',self.store.task(key))
        self.now+=REUNION_SECONDS+1;self.assertEqual(self.store.snapshot()['tasks'],[])

    def test_archive_overrides_unread_and_disconnect_without_marking_read(self):
        key=self.event('started');self.event('completed');self.event('disconnected')
        self.store.sync_presentation(key,unread=True,read_mode='app')
        original=self.store.task(key)['state_at']
        self.event('archived')
        departure=self.store.task(key)['retire_at']
        self.now+=4
        self.store.sync_presentation(key,unread=True,read_mode='app')
        self.store.sync_presentation(key,unread=None,read_mode='app')
        self.event('archived')  # does not extend the grace period
        snap=self.store.snapshot()
        self.assertEqual(snap['unread_count'],0)
        self.assertEqual(snap['tasks'][0]['display_state'],'completed')
        self.assertIsNone(snap['tasks'][0]['desk_slot'])
        self.assertEqual(self.store.task(key)['retire_at'],departure)
        self.assertEqual(self.store.task(key)['state_at'],original)
        self.assertFalse(self.store._all('notices')[0]['read'])
        self.now+=REUNION_SECONDS
        self.assertEqual(self.store.snapshot()['tasks'],[])
        self.store.close();self.store=Store(self.root/'state.sqlite',clock=lambda:self.now)
        for kind in ['connected','working','started']:
            result=self.store.ingest(make_event('codex','a',kind,run_id='new'))
            self.assertEqual(result['reason'],'archived')
        self.store.sync_presentation(key,unread=True,read_mode='app')
        self.assertEqual(self.store.snapshot()['tasks'],[])
        self.event('unarchived')
        self.assertEqual(len(self.store.snapshot()['tasks']),1)
        self.assertEqual(self.store.snapshot()['unread_count'],1)

    def test_archive_running_releases_slot_even_without_completion(self):
        key=self.event('started');slot=self.store.task(key)['slot']
        self.event('archived');self.now+=REUNION_SECONDS+1
        self.assertEqual(self.store.snapshot()['tasks'],[])
        other=self.event('started','b')
        self.assertEqual(self.store.task(other)['slot'],slot)

class BlueDotTests(unittest.TestCase):
    def test_identity_scope_and_ambiguous_host_are_not_merged(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)
            (home/'config.toml').write_text('model_provider="local"\n[model_providers.local]\nrequires_openai_auth=false\n')
            key=hashlib.sha256(b'["execution-storage","none"]').hexdigest()
            data={'electron-thread-read-state-v1':{'version':1,'unreadByIdentity':{
                key:{'local:host':['current']},'old-account':{'local:host':['private-old']}}}}
            path=home/'.codex-global-state.json';path.write_text(json.dumps(data))
            self.assertEqual(read_blue_dots(home),{'current'})
            data['electron-thread-read-state-v1']['unreadByIdentity'][key]['local:other']=[]
            path.write_text(json.dumps(data));self.assertIsNone(read_blue_dots(home))
            path.write_text('{');self.assertIsNone(read_blue_dots(home))

class DiscoveryTests(unittest.TestCase):
    def test_unknown_historical_read_state_does_not_summon_old_cursor_tasks(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'state.sqlite');observer=GuiObservers(directory,store)
            observer.project('cursor',dict(id='old',label='old',state='completed',unread=None,updated=1))
            self.assertEqual(store.snapshot()['tasks'],[])
            self.assertEqual(store.snapshot()['unread_count'],0);store.close()

    def test_reenabled_gui_accepts_fresh_unchanged_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'state.sqlite');observer=GuiObservers(directory,store)
            row=dict(id='fresh',label='fresh',state='running',unread=False,updated=1,run='a')
            observer.project('cursor',row)
            store.update_settings({'sources':{'cursor':False}});store.update_settings({'sources':{'cursor':True}})
            observer.project('cursor',row)
            self.assertEqual(store.snapshot()['tasks'][0]['display_state'],'running');store.close()

    def test_large_codex_log_searches_backward_and_rotation_adopts_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);store=Store(root/'state.sqlite');observer=CloneObserver(root,store)
            log=root/'rollout.jsonl';thread={'id':'01a1084f-58f0-7100-82c7-248853266b30','label':'large','automatic':True}
            def record(kind,run,at):return json.dumps({'type':'event_msg','timestamp':at,'payload':{'type':kind,'turn_id':run}})+'\n'
            log.write_text(record('task_started','r1','2026-10-08T01:00:00Z')+('{"type":"other"}\n'*100))
            with patch('codex_clones.BOOTSTRAP_BYTES',256):
                for _ in range(10):observer.observe(log,thread)
                self.assertEqual(store.snapshot()['tasks'][0]['run_id'],'r1')
                store.update_settings({'sources':{'codex':False}});store.update_settings({'sources':{'codex':True}})
                observer.cursors[thread['id']]['paused']=True
                for _ in range(10):observer.observe(log,thread)
                self.assertEqual(store.snapshot()['tasks'][0]['display_state'],'running')
                log.write_text(record('task_complete','r2','2026-10-08T02:00:00Z'))
                observer.observe(log,thread)
                self.assertEqual(store.snapshot()['tasks'][0]['run_id'],'r2')
                self.assertEqual(store.snapshot()['tasks'][0]['state'],'completed')
            store.close()

    def test_cursor_terminal_wins_over_stale_block_and_only_projects_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cursor.sqlite';db=sqlite3.connect(path)
            db.execute('CREATE TABLE composerHeaders (composerId, value, lastUpdatedAt, isArchived)')
            db.execute('CREATE TABLE cursorDiskKV (key,value)')
            db.execute('INSERT INTO composerHeaders VALUES (?,?,?,0)',('id',json.dumps({
                'name':'Cursor任务','hasUnreadMessages':False,'hasBlockingPendingActions':True}),1000))
            db.execute('INSERT INTO cursorDiskKV VALUES (?,?)',('composerData:id',json.dumps({
                'status':'completed','latestChatGenerationUUID':'run-1','text':'PRIVATE','conversationMap':'PRIVATE'})))
            db.commit();db.close()
            rows=cursor_rows(path)
            self.assertEqual(rows[0]['state'],'completed')
            self.assertFalse(rows[0]['unread'])
            self.assertNotIn('PRIVATE',json.dumps(rows))

    def test_zcode_reads_unread_at_not_merely_updated_at(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'zcode.sqlite';db=sqlite3.connect(path)
            db.execute('CREATE TABLE tasks (task_id,title,task_status,unread_at,last_unread_at,updated_at,workspace_path,meta_json,archived,deleted)')
            db.execute('INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,0,0)',('id','ZCode任务','completed',2000,2000,3000,'C:/project',json.dumps({'transcript':'PRIVATE'})))
            db.commit();db.close()
            row=zcode_rows(path)[0]
            self.assertTrue(row['unread']);self.assertNotIn('PRIVATE',json.dumps(row))
            db=sqlite3.connect(path);db.execute('UPDATE tasks SET unread_at=NULL,updated_at=4000');db.commit();db.close()
            self.assertFalse(zcode_rows(path)[0]['unread'])

    def test_codex_new_task_is_discovered_without_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);home=root/'codex';(home/'sessions').mkdir(parents=True)
            runtime=root/'runtime';runtime.mkdir()
            (runtime/'codex-clones.json').write_text(json.dumps({'codex_home':str(home),'threads':[]}))
            ident='01a1084f-58f0-7100-82c7-248853266b30';log=home/'sessions/a.jsonl'
            log.write_text(json.dumps({'type':'event_msg','timestamp':'2026-10-08T12:00:00Z','payload':{'type':'task_started','turn_id':'run'}})+'\n')
            with sqlite3.connect(home/'state_5.sqlite') as db:
                db.execute('CREATE TABLE threads (id, title, rollout_path, updated_at, archived)')
                db.execute('INSERT INTO threads VALUES (?,?,?,?,0)',(ident,'自动发现',str(log),100))
            db.close()
            store=Store(runtime/'state.sqlite');observer=CloneObserver(runtime,store);observer.poll(force=True)
            self.assertEqual(store.snapshot()['tasks'][0]['label'],'自动发现')
            self.assertEqual(store.snapshot()['tasks'][0]['state'],'running')
            with sqlite3.connect(home/'state_5.sqlite') as db:
                db.execute('UPDATE threads SET archived=1,rollout_path=?',('not-present-after-archive',))
            db.close()
            observer.poll(force=True)
            self.assertTrue(store.snapshot()['tasks'][0]['archived'])
            self.assertEqual(store.snapshot()['unread_count'],0)
            store.close()

    def test_gui_archive_is_explicit_and_missing_database_cannot_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'state.sqlite');observer=GuiObservers(directory,store)
            for source in ['cursor','zcode']:
                row=dict(id='gui-archive',label='演示任务',state='running',unread=True,updated=1,run='one',archived=False)
                observer.project(source,row)
                key=task_key({'source':source,'thread_id':row['id']})
                observer.unavailable(source)
                self.assertFalse(store.task(key).get('archived',False))
                row.update(archived=True,state=None)
                observer.project(source,row)
                self.assertTrue(store.task(key)['archived'])
                row.update(archived=False,state='running')
                observer.project(source,row)
                self.assertFalse(store.task(key)['archived'])
            store.close()
    def test_gui_baseline_ignores_old_read_tasks_then_starts_new_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'state.sqlite');observer=GuiObservers(directory,store)
            row=dict(id='gui-1',label='窗口',state='completed',unread=False,updated=1,run='old')
            observer.project('cursor',row);self.assertEqual(store.snapshot()['tasks'],[])
            row.update(state='running',run='new',updated=2)
            observer.project('cursor',row)
            self.assertEqual(store.snapshot()['tasks'][0]['run_id'],'new')
            row.update(state='completed',unread=True,updated=3);observer.project('cursor',row)
            self.assertEqual(store.snapshot()['unread_count'],1)
            store.close()

if __name__=='__main__':unittest.main()
