import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from bridge_store import Store, make_event
from codex_clones import CloneObserver, lifecycle, scan

ID='01a1084f-58f0-7100-82c7-248853266b30'


def record(kind, run='r1', at='2026-10-04T19:00:00Z'):
    return json.dumps({'timestamp':at,'type':'event_msg','payload':{
        'type':kind,'turn_id':run,'last_agent_message':'PRIVATE_MESSAGE',
        'tool_arguments':'PRIVATE_ARGUMENTS'}}).encode()+b'\n'


class CloneTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.home=self.root/'codex';self.home.mkdir()
        (self.home/'sessions').mkdir()
        self.log=self.home/'sessions'/'conversation.jsonl'
        self.log.write_bytes(record('task_started'))
        db=sqlite3.connect(str(self.home/'state_5.sqlite'))
        db.execute('CREATE TABLE threads (id TEXT PRIMARY KEY, rollout_path TEXT)')
        db.execute('INSERT INTO threads VALUES (?,?)',(ID,str(self.log)))
        db.commit();db.close()
        self.runtime=self.root/'bridge';self.runtime.mkdir()
        self.thread={'id':ID,'label':'真实会话名','status':'active','unread':False}
        self.configure()
        self.store=Store(self.runtime/'state.sqlite3')
        self.observer=CloneObserver(self.runtime,self.store)

    def configure(self):
        (self.runtime/'codex-clones.json').write_text(json.dumps({
            'codex_home':str(self.home),'threads':[self.thread],
            'selected_at':'2026-10-04T19:01:00Z'}),encoding='utf-8')

    def tearDown(self):
        self.store.close();self.temp.cleanup()

    def append(self,data):
        with self.log.open('ab') as stream:stream.write(data)

    def task(self):return self.store.snapshot()['tasks'][0]

    def test_running_clone_then_real_completion_persists_once(self):
        self.observer.poll(force=True)
        self.assertTrue(self.task()['clone'])
        self.assertEqual(self.task()['state'],'running')
        self.append(record('task_complete',at='2026-10-04T19:02:00Z'))
        self.observer.poll(force=True)
        snap=self.store.snapshot()
        self.assertEqual(snap['unread_count'],1)
        self.assertEqual(self.task()['state'],'completed')
        self.assertNotIn('PRIVATE',json.dumps(snap))
        self.store.acknowledge([snap['notifications'][0]['id']])
        CloneObserver(self.runtime,self.store).poll(force=True)
        self.assertEqual(self.store.snapshot()['unread_count'],0)

    def test_paused_source_does_not_open_codex_and_resumes_latest_silently(self):
        self.observer.poll(force=True)
        self.store.update_settings({'sources':{'codex':False}})
        database=self.home/'state_5.sqlite'
        database.rename(database.with_suffix('.off'))
        self.observer.poll(force=True)
        report=json.loads(self.observer.report_path.read_text())
        self.assertEqual(report['errors'],[])
        self.assertTrue(self.observer.cursors[ID]['paused'])
        self.append(record('task_complete','r2','2026-10-04T19:03:00Z'))
        database.with_suffix('.off').rename(database)
        self.store.update_settings({'sources':{'codex':True}})
        self.observer=CloneObserver(self.runtime,self.store)
        self.observer.poll(force=True)
        self.assertEqual(self.task()['run_id'],'r2')
        self.assertEqual(self.task()['state'],'completed')
        self.assertEqual(self.store.snapshot()['unread_count'],0)
        self.append(record('task_started','r3','2026-10-04T19:04:00Z'))
        self.append(record('task_complete','r3','2026-10-04T19:05:00Z'))
        self.observer.poll(force=True)
        self.assertEqual(self.store.snapshot()['unread_count'],1)

    def test_paused_conversation_keeps_existing_unread(self):
        self.observer.poll(force=True)
        self.append(record('task_complete',at='2026-10-04T19:02:00Z'))
        self.observer.poll(force=True)
        self.store.update_settings({'disabled_tasks':[self.task()['id']]})
        self.observer.poll(force=True)
        self.store.update_settings({'disabled_tasks':[]})
        self.observer.poll(force=True)
        self.assertEqual(self.store.snapshot()['unread_count'],1)

    def test_historical_read_completion_does_not_generate_reminder(self):
        self.append(record('task_complete'))
        self.thread.update(status='idle',unread=False);self.configure()
        self.observer.poll(force=True)
        self.assertEqual(self.task()['state'],'completed')
        self.assertEqual(self.store.snapshot()['unread_count'],0)
        self.assertEqual(self.task()['action'],'following')

    def test_existing_unread_completion_is_imported(self):
        self.append(record('task_complete'))
        self.thread.update(status='idle',unread=True);self.configure()
        self.observer.poll(force=True)
        self.assertEqual(self.store.snapshot()['unread_count'],1)

    def test_idle_app_snapshot_does_not_inherit_stale_running(self):
        self.thread['status']='idle';self.configure()
        self.observer.poll(force=True)
        self.assertEqual(self.task()['state'],'idle')

    def test_partial_and_non_lifecycle_records_are_ignored(self):
        self.observer.poll(force=True)
        data=record('task_complete',at='2026-10-04T19:02:00Z')
        self.append(data[:-5]);self.observer.poll(force=True)
        self.assertEqual(self.task()['state'],'running')
        self.append(data[-5:]);self.observer.poll(force=True)
        self.assertEqual(self.task()['state'],'completed')
        self.assertIsNone(lifecycle(record('agent_message'),self.thread))

    def test_rotation_does_not_roll_back_to_old_run(self):
        self.observer.poll(force=True)
        self.append(record('task_started','r2','2026-10-04T19:03:00Z'))
        self.observer.poll(force=True)
        self.log.replace(self.log.with_suffix('.old'))
        self.log.write_bytes(record('task_started','ancient','2026-10-04T18:00:00Z'))
        self.observer.poll(force=True)
        self.assertEqual(self.task()['run_id'],'r2')

    def test_oversized_record_does_not_hide_next_lifecycle(self):
        self.log.write_bytes(b'x'*(1024*1024+100)+b'\n'+record('task_started'))
        lines,offset=scan(self.log,0)
        self.assertEqual(offset,self.log.stat().st_size)
        self.assertEqual(len(lines),1)

    def test_only_selected_thread_paths_inside_sessions_are_read(self):
        db=sqlite3.connect(str(self.home/'state_5.sqlite'))
        db.execute('UPDATE threads SET rollout_path=?',(str(self.root/'outside.jsonl'),))
        db.commit();db.close()
        self.observer.poll(force=True)
        self.assertEqual(self.store.snapshot()['tasks'],[])
        report=json.loads((self.runtime/'codex-clone-status.json').read_text())
        self.assertEqual(report['errors'][0]['reason'],'outside_sessions')


if __name__=='__main__':unittest.main()
