import concurrent.futures
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from bridge import build_server, drain_spool
from bridge_adapters import hook_event, app_server_event
from bridge_client import worker_events
from bridge_store import Store, make_event
from notify import enqueue
from setup_hooks import definition, merge
from workstations import Workers

ROOT = Path(__file__).resolve().parent


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 1000
        self.path = Path(self.tmp.name)/'state.sqlite3'
        self.store = Store(self.path, lambda: self.now)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def emit(self, kind, **kw):
        fields = dict(run_id='r1', **kw)
        return self.store.ingest(make_event('codex', 't1', kind, **fields))

    def task(self):
        return self.store.snapshot()['tasks'][0]

    def test_connection_selection_keeps_unread_and_persists(self):
        self.emit('completed')
        key=self.task()['id']
        self.store.update_settings({'disabled_tasks':[key],'movement_locked':True})
        snap=self.store.snapshot()
        self.assertEqual(snap['tasks'],[])
        self.assertEqual(snap['unread_count'],0)
        self.assertFalse(snap['connections']['tasks'][0]['enabled'])
        self.assertEqual(self.emit('message')['reason'],'connection_disabled')
        self.store.close();self.store=Store(self.path,lambda:self.now)
        self.assertTrue(self.store.settings()['movement_locked'])
        self.store.update_settings({'disabled_tasks':[]})
        self.assertEqual(self.store.snapshot()['unread_count'],1)
        self.assertEqual(self.task()['state'],'completed')
        self.assertEqual(self.task()['display_state'],'disconnected')
        self.emit('connected')
        self.assertEqual(self.task()['display_state'],'completed')

    def test_source_disabled_blocks_new_events_and_invalid_patch_is_atomic(self):
        self.store.update_settings({'sources':{'cursor':False}})
        self.assertEqual(self.store.ingest(make_event('cursor','new','started'))['reason'],'connection_disabled')
        before=self.store.settings()
        with self.assertRaises(ValueError):
            self.store.update_settings({'movement_locked':True,'sources':{'cursor':'yes'}})
        self.assertEqual(self.store.settings(),before)
        with self.assertRaises(ValueError):self.store.update_settings({'disabled_tasks':['unknown']})

    def test_desktop_scale_migrates_old_preferences_and_persists(self):
        self.store.db.execute("INSERT INTO preferences VALUES ('settings',?)",(json.dumps({
            'movement_locked':True,'sources':{'codex':False},'disabled_tasks':[]}),))
        self.store.db.commit()
        self.assertEqual(self.store.settings()['desktop_scale'],100)
        self.assertTrue(self.store.settings()['movement_locked'])
        self.store.update_settings({'desktop_scale':75})
        self.store.close();self.store=Store(self.path,lambda:self.now)
        self.assertEqual(self.store.settings()['desktop_scale'],75)
        self.assertFalse(self.store.settings()['sources']['codex'])
        self.assertTrue(self.store.settings()['sources']['cursor'])

    def test_invalid_scale_cannot_partially_change_other_preferences(self):
        before=self.store.settings()
        for value in (0,49,151,75.0,True,'75',None):
            with self.assertRaises(ValueError):
                self.store.update_settings({'movement_locked':True,'desktop_scale':value})
            self.assertEqual(self.store.settings(),before)

    def test_restart_ack_and_duplicate_completion(self):
        self.emit('started')
        self.emit('completed')
        note = self.store.snapshot()['notifications'][0]
        self.store.acknowledge([note['id']])
        self.store.close()
        self.store = Store(self.path, lambda: self.now)
        self.emit('completed')
        self.assertEqual(self.store.snapshot()['unread_count'], 0)
        self.assertEqual(self.task()['state'], 'completed')

    def test_notification_from_previous_run_survives_new_work(self):
        self.emit('completed')
        self.store.ingest(make_event('codex', 't1', 'started', run_id='r2'))
        self.assertEqual(self.task()['state'], 'running')
        self.assertEqual(self.store.snapshot()['unread_count'], 1)
        self.assertEqual(self.emit('failed')['reason'], 'old_run')
        self.assertEqual(self.task()['state'], 'running')

    def test_two_confirmations_resolve_independently_read_is_not_approval(self):
        self.emit('started')
        for request in ('a', 'b'):
            self.emit('waiting', request_id=request)
        self.store.acknowledge([n['id'] for n in self.store.snapshot()['notifications']])
        self.assertEqual(self.task()['state'], 'waiting')
        self.emit('working')
        self.assertEqual(self.task()['state'], 'waiting')
        self.emit('resolved', request_id='a')
        self.assertEqual(self.task()['state'], 'waiting')
        self.emit('resolved', request_id='wrong')
        self.assertEqual(self.task()['state'], 'waiting')
        self.emit('resolved', request_id='b')
        self.assertEqual(self.task()['state'], 'running')

    def test_waiting_takes_priority_without_erasing_unread(self):
        self.emit('completed')
        self.store.ingest(make_event('cursor', 't1', 'waiting', run_id='r2'))
        snap = self.store.snapshot()
        self.assertEqual(snap['leader_state'], 'waiting')
        self.assertEqual(snap['unread_count'], 2)
        board = Workers()
        for event in worker_events(snap):
            board.ingest(event, 0)
        self.assertEqual(len(board.items), 2)
        self.assertEqual(board.overall_state, 'waiting')

    def test_ordering_and_new_run_sequence_reset(self):
        self.emit('started', sequence=4)
        self.assertFalse(self.emit('failed', sequence=3)['accepted'])
        self.emit('completed', sequence=5)
        self.assertFalse(self.emit('working', sequence=6)['accepted'])
        self.assertFalse(self.emit('failed', sequence=7)['accepted'])
        self.assertTrue(self.store.ingest(make_event('codex', 't1', 'started', run_id='r2', sequence=0))['accepted'])
        self.assertEqual(self.task()['state'], 'running')

    def test_idempotency_and_namespace_isolation(self):
        event = make_event('codex', 't1', 'started', run_id='r1')
        self.assertTrue(self.store.ingest(event)['accepted'])
        self.assertFalse(self.store.ingest(event)['accepted'])
        self.assertTrue(self.store.ingest(dict(event, source='cursor'))['accepted'])
        self.assertEqual(len(self.store.snapshot()['tasks']), 2)

    def test_opt_in_heartbeat_and_reconnect_preserve_work_and_notices(self):
        self.emit('started', heartbeat_timeout=10)
        self.now += 11
        self.assertEqual(self.task()['display_state'], 'disconnected')
        self.emit('heartbeat')
        self.assertEqual(self.task()['display_state'], 'running')
        self.emit('completed')
        self.now += 100
        self.assertEqual(self.task()['display_state'], 'completed')
        self.emit('disconnected')
        self.assertEqual(self.task()['display_state'], 'disconnected')
        self.emit('connected')
        self.assertEqual(self.task()['display_state'], 'completed')
        self.assertEqual(self.store.snapshot()['unread_count'], 1)

    def test_silent_hook_source_does_not_fake_disconnect(self):
        self.emit('started')
        self.now += 100000
        self.assertEqual(self.task()['display_state'], 'running')

    def test_failure_skill_is_stable_and_actions_are_timed(self):
        self.emit('failed')
        roll = self.task()['failure_roll']
        self.emit('failed')
        self.assertEqual(self.task()['failure_roll'], roll)
        self.store.ingest(make_event('codex', 't1', 'started', run_id='r2'))
        self.store.ingest(make_event('codex', 't1', 'completed', run_id='r2'))
        self.assertEqual(self.task()['action'], 'closing')
        self.now += 4
        self.assertEqual(self.task()['action'], 'walk')
        self.now += 4
        self.assertEqual(self.task()['action'], 'following')

    def test_unknown_fields_are_not_persisted(self):
        self.emit('started', summary=' hello\nworld ', transcript='secret-content', token='secret-key')
        self.assertEqual(self.task()['summary'], 'hello world')
        serialized = json.dumps(self.store.snapshot())
        self.assertNotIn('secret', serialized)
        self.assertNotIn('transcript', serialized)

    def test_invalid_events_have_no_effect(self):
        for event in [[], {}, make_event('local', 't', 'not-real'),
                      make_event('local', 't', 'working', sequence=True),
                      make_event('local', 't', 'working', heartbeat_timeout=float('nan'))]:
            with self.assertRaises(ValueError):
                self.store.ingest(event)
        self.assertEqual(self.store.snapshot()['revision'], 0)

    def test_spool_offline_concurrent_delivery_and_replay(self):
        runtime = Path(self.tmp.name)
        events = [make_event('local', 'job-'+str(i), 'completed', run_id='1') for i in range(25)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda e: enqueue(e, runtime), events))
        drain_spool(self.store, runtime)
        self.assertEqual(self.store.snapshot()['unread_count'], 25)
        self.assertEqual(list((runtime/'inbox').glob('*.json')), [])
        enqueue(events[0], runtime)
        drain_spool(self.store, runtime)
        self.assertEqual(self.store.snapshot()['unread_count'], 25)


class AdapterTests(unittest.TestCase):
    def test_codex_only_forwards_metadata_and_interrupt_is_not_success(self):
        payload = {'hook_event_name': 'UserPromptSubmit', 'session_id': 't', 'turn_id': 'r',
                   'prompt': 'sensitive', 'transcript_path': 'private', 'cwd': 'private'}
        event = hook_event('codex', payload)
        self.assertEqual(event['kind'], 'started')
        self.assertNotIn('sensitive', json.dumps(event))
        self.assertNotIn('private', json.dumps(event))
        self.assertEqual(hook_event('codex', dict(payload, hook_event_name='Interrupt'))['kind'], 'cancelled')
        self.assertEqual(hook_event('codex', payload)['event_id'], event['event_id'])

    def test_cursor_terminal_status_is_explicit(self):
        payload = {'conversation_id': 't', 'generation_id': 'r', 'hook_event_name': 'stop'}
        self.assertIsNone(hook_event('cursor', payload))
        for status, kind in [('completed', 'completed'), ('aborted', 'cancelled'), ('error', 'failed')]:
            self.assertEqual(hook_event('cursor', dict(payload, status=status))['kind'], kind)
        self.assertIsNone(hook_event('cursor', dict(payload, hook_event_name='afterAgentResponse')))

    def test_claude_error_and_correlated_resolution(self):
        payload = {'session_id': 't', 'hook_event_name': 'StopFailure', 'error_details': 'secret'}
        self.assertEqual(hook_event('claude', payload)['kind'], 'failed')
        self.assertIsNone(hook_event('claude', dict(payload, hook_event_name='PostToolUse')))
        event = hook_event('claude', dict(payload, hook_event_name='PostToolUse', tool_use_id='request-1'))
        self.assertEqual(event['request_id'], 'request-1')

    def test_app_server_needs_known_completion_status(self):
        p = {'method': 'turn/completed', 'params': {'threadId': 't', 'turn': {'id': 'r'}}}
        self.assertIsNone(app_server_event(p))
        p['params']['turn']['status'] = 'interrupted'
        self.assertEqual(app_server_event(p)['kind'], 'cancelled')
        approval = app_server_event({'id': 3, 'method': 'item/tool/requestUserInput',
            'params': {'threadId': 't', 'turnId': 'r', 'questions': ['secret']}})
        self.assertEqual(approval['request_id'], '3')
        self.assertNotIn('secret', json.dumps(approval))

    def test_merge_preserves_other_hooks_and_is_idempotent(self):
        original = {'permissions': {'deny': ['something']}, 'hooks': {'Stop': [{'hooks': [{'command': 'existing'}]}]}}
        merged = merge(original, definition('claude'))
        self.assertEqual(merged['permissions'], original['permissions'])
        self.assertEqual(merged['hooks']['Stop'][0], original['hooks']['Stop'][0])
        self.assertEqual(merge(merged, definition('claude')), merged)

    def test_real_hook_process_queues_sanitized_event_without_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = json.dumps({'hook_event_name': 'Stop', 'session_id': 'test-session',
                                  'turn_id': 'test-turn', 'last_assistant_message': 'PRIVATE'})
            result = subprocess.run([sys.executable, str(ROOT/'notify.py'), '--runtime', directory, 'hook', 'codex'],
                                    input=payload.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})
            files = list((Path(directory)/'inbox').glob('*.json'))
            self.assertEqual(len(files), 1)
            self.assertNotIn('PRIVATE', files[0].read_text(encoding='utf-8'))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name)/'state.sqlite3')
        self.server = build_server(self.store, 'test-token')
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.close()
        self.tmp.cleanup()

    def request(self, method, path, value=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=2)
        try:
            h = {'Authorization': 'Bearer test-token', 'Content-Type': 'application/json'}
            h.update(headers or {})
            conn.request(method, path, None if value is None else json.dumps(value), h)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    def test_event_snapshot_ack_round_trip(self):
        status, _ = self.request('POST', '/api/events', make_event('local', 'integration', 'completed'))
        self.assertEqual(status, 200)
        status, body = self.request('GET', '/api/snapshot')
        snap = json.loads(body)
        self.assertEqual(snap['unread_count'], 1)
        note = snap['notifications'][0]
        self.assertEqual(self.request('POST', '/api/read', {'ids': [note['id']]})[0], 200)
        self.assertEqual(json.loads(self.request('GET', '/api/snapshot')[1])['unread_count'], 0)

    def test_settings_authenticated_round_trip(self):
        self.assertEqual(self.request('POST','/api/settings',{'movement_locked':True},{'Authorization':''})[0],401)
        self.assertEqual(self.request('POST','/api/settings',{'movement_locked':True})[0],200)
        data=json.loads(self.request('GET','/api/settings')[1])
        self.assertTrue(data['settings']['movement_locked'])
        self.assertEqual(len(data['connections']['sources']),6)
        self.assertEqual(self.request('POST','/api/settings',{'unknown':True})[0],400)

    def test_cross_origin_rebinding_and_unauthorized_writes_rejected(self):
        event = make_event('local', 'x', 'started')
        for headers, status in [({'Authorization': ''}, 401),
                                ({'Origin': 'https://evil.example'}, 403),
                                ({'Host': 'evil.example'}, 403),
                                ({'Sec-Fetch-Site': 'cross-site'}, 403)]:
            self.assertEqual(self.request('POST', '/api/events', event, headers)[0], status)
        self.assertEqual(self.store.snapshot()['tasks'], [])

    def test_static_boundary_and_malformed_inputs(self):
        for path in ['/art/../bridge.py', '/art/%2e%2e/bridge.py', '/art/sources/x.json', '/connection.json']:
            self.assertEqual(self.request('GET', path)[0], 404)
        self.assertEqual(self.request('POST', '/api/events', [1, 2])[0], 400)
        self.assertEqual(self.request('GET', '/')[0], 200)
        self.assertEqual(self.request('GET', '/art/rig.json')[0], 200)


if __name__ == '__main__':
    unittest.main()
