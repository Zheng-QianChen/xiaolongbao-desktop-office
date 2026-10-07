import concurrent.futures
from contextlib import closing
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from bridge import build_server
from bridge_client import BridgeClient
from bridge_store import Store, make_event
from codex_clones import CloneObserver
from codex_connections import CodexConnections, ConnectionError
from test_codex_clones import record

FIRST = '00000000-0000-7000-8000-000000000001'
SECOND = '00000000-0000-7000-8000-000000000002'


class Fixture:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / 'codex'
        (self.home / 'sessions').mkdir(parents=True)
        self.runtime = self.root / 'bridge'
        self.runtime.mkdir()
        self.store = Store(self.runtime / 'state.sqlite3')
        # These cases exercise the optional manual picker, separately from discovery.
        self.store.update_settings({'auto_discover':False})
        self.observer = CloneObserver(self.runtime, self.store)
        self.connections = CodexConnections(self.observer)
        self.observer.write_json(self.observer.config_path, {'codex_home': str(self.home), 'threads': []})
        with closing(sqlite3.connect(str(self.home / 'state_5.sqlite'))) as db:
            db.execute('CREATE TABLE threads (id TEXT PRIMARY KEY,title TEXT,updated_at INTEGER,'
                       'rollout_path TEXT,archived INTEGER,first_user_message TEXT)')
        self.add_thread(FIRST, '会话一 <img src=x onerror=alert(1)>', completed=True)
        self.add_thread(SECOND, '会话二', completed=False)

    def add_thread(self, ident, title, completed=True, archived=0, updated=100, outside=False):
        path = (self.root if outside else self.home / 'sessions') / (ident + '.jsonl')
        path.write_bytes(record('task_started') + (record('task_complete') if completed else b''))
        with closing(sqlite3.connect(str(self.home / 'state_5.sqlite'))) as db:
            db.execute('INSERT INTO threads VALUES (?,?,?,?,?,?)',
                       (ident, title, updated, str(path), archived, 'PRIVATE-PROMPT'))
            db.commit()
        return path

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()


class SelectionTests(Fixture, unittest.TestCase):
    def test_discovery_only_reads_named_metadata_and_never_opens_logs(self):
        original = Path.open
        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path.suffix, '.jsonl', 'Discovery read a conversation log')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded):
            result = self.connections.discover()
        self.assertEqual(len(result['sessions']), 2)
        self.assertFalse(any(s['selected'] for s in result['sessions']))
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('rollout_path', json.dumps(result))
        self.assertEqual(self.store.snapshot()['tasks'], [])

    def test_search_is_literal_and_archived_or_outside_sessions_are_excluded(self):
        self.add_thread('00000000-0000-7000-8000-000000000003', '归档', archived=1)
        self.add_thread('00000000-0000-7000-8000-000000000004', '外部', outside=True)
        self.assertEqual(len(self.connections.discover()['sessions']), 2)
        self.assertEqual(self.connections.discover('%')['sessions'], [])
        self.assertEqual([s['id'] for s in self.connections.discover('会话二')['sessions']], [SECOND])
        self.assertEqual([s['id'] for s in self.connections.discover(FIRST)['sessions']], [FIRST])

    def test_connect_is_persistent_idempotent_and_initial_completion_is_silent(self):
        result = self.connections.add({'ids': [FIRST, FIRST]})
        self.assertEqual(result['added'], 1)
        self.assertEqual(self.connections.add({'ids': [FIRST]})['added'], 0)
        observer = CloneObserver(self.runtime, self.store)
        observer.poll(force=True)
        snap = self.store.snapshot()
        self.assertEqual(len(snap['tasks']), 1)
        self.assertEqual(snap['tasks'][0]['state'], 'completed')
        self.assertEqual(snap['unread_count'], 0)
        path = self.home / 'sessions' / (FIRST + '.jsonl')
        with path.open('ab') as stream:
            stream.write(record('task_started', 'new-run', '2026-10-07T01:00:00Z'))
            stream.write(record('task_complete', 'new-run', '2026-10-07T01:01:00Z'))
        observer.poll(force=True)
        self.assertEqual(self.store.snapshot()['unread_count'], 1)
        CodexConnections(observer).add({'ids': [FIRST]})
        observer.poll(force=True)
        self.assertEqual(self.store.snapshot()['unread_count'], 1)

    def test_invalid_batch_changes_nothing(self):
        before = self.observer.config_path.read_bytes()
        for value in ({'ids': []}, {'ids': [FIRST, 'invalid']}, {'ids': [FIRST] * 21},
                      {'ids': [FIRST], 'codex_home': str(self.root)},
                      {'ids': [FIRST, '00000000-0000-7000-8000-000000000099']}):
            with self.assertRaises(ConnectionError):
                self.connections.add(value)
            self.assertEqual(self.observer.config_path.read_bytes(), before)
        self.assertEqual(self.store.snapshot()['tasks'], [])

    def test_parallel_connect_and_poll_do_not_lose_selections(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results = [pool.submit(self.connections.add, {'ids': [ident]}) for ident in (FIRST, SECOND)]
            results.append(pool.submit(self.observer.poll, True))
            for result in results:
                result.result()
        self.observer.poll(force=True)
        self.assertEqual(len(self.observer.read_config()['threads']), 2)
        self.assertEqual(len(self.store.snapshot()['tasks']), 2)

    def test_disabled_source_stays_paused_and_resume_imports_silently(self):
        self.store.update_settings({'sources': {'codex': False}})
        self.assertFalse(self.connections.add({'ids': [FIRST]})['source_enabled'])
        self.observer.poll(force=True)
        self.assertEqual(self.store.snapshot()['tasks'], [])
        self.store.update_settings({'sources': {'codex': True}})
        CloneObserver(self.runtime, self.store).poll(force=True)
        self.assertEqual(self.store.snapshot()['tasks'][0]['state'], 'completed')
        self.assertEqual(self.store.snapshot()['unread_count'], 0)

    def test_new_connection_does_not_inherit_old_app_snapshot(self):
        config = self.observer.read_config()
        config['selected_at'] = '2026-10-08T00:00:00Z'
        self.observer.write_json(self.observer.config_path, config)
        self.connections.add({'ids': [SECOND]})
        self.observer.poll(force=True)
        self.assertEqual(self.store.snapshot()['tasks'][0]['state'], 'running')

    def test_no_lifecycle_is_not_presented_as_a_live_connection(self):
        (self.home / 'sessions' / (FIRST + '.jsonl')).write_bytes(b'')
        self.connections.add({'ids': [FIRST]})
        self.observer.poll(force=True)
        self.assertEqual(self.store.snapshot()['tasks'][0]['display_state'], 'disconnected')

    def test_existing_hook_task_adopts_a_newer_completion_when_selected(self):
        self.store.ingest(make_event('codex', FIRST, 'started', run_id='older-hook-run',
                                    observed_at=1, label='旧工位'))
        self.connections.add({'ids': [FIRST]})
        self.observer.poll(force=True)
        task = self.store.snapshot()['tasks'][0]
        self.assertEqual(task['state'], 'completed')
        self.assertEqual(task['run_id'], 'r1')
        self.assertEqual(self.store.snapshot()['unread_count'], 0)

    def test_corrupted_selection_file_is_not_overwritten(self):
        data = '{"threads":[null]}'
        self.observer.config_path.write_text(data, encoding='utf-8')
        with self.assertRaisesRegex(ConnectionError, '无法读取本地连接配置'):
            self.connections.add({'ids': [FIRST]})
        self.assertEqual(self.observer.config_path.read_text(encoding='utf-8'), data)

    def test_missing_database_gives_actionable_error_without_creating_it(self):
        path = self.home / 'state_5.sqlite'
        path.unlink()
        with self.assertRaisesRegex(ConnectionError, '请先启动 Codex'):
            self.connections.discover()
        self.assertFalse(path.exists())

    def test_default_home_works_without_preexisting_selection_file(self):
        self.observer.config_path.unlink()
        with patch.dict('os.environ', {'CODEX_HOME': str(self.home)}):
            self.assertEqual(len(self.connections.discover()['sessions']), 2)
            self.connections.add({'ids': [FIRST]})
        self.observer.poll(force=True)
        self.assertEqual(len(self.store.snapshot()['tasks']), 1)

    def test_discovery_is_bounded_and_search_can_find_older_sessions(self):
        for index in range(3, 104):
            self.add_thread('00000000-0000-7000-8000-{:012d}'.format(index),
                            '列表会话 {}'.format(index), updated=1000+index)
        result = self.connections.discover()
        self.assertEqual(len(result['sessions']), 100)
        self.assertTrue(result['truncated'])
        self.assertEqual(self.connections.discover('会话二')['sessions'][0]['id'], SECOND)


class ConnectionHttpTests(Fixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server = build_server(self.store, 'selection-test', clones=self.observer)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def request(self, method, value=None, headers=None, path='/api/codex/sessions'):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=2)
        try:
            merged = {'Authorization': 'Bearer selection-test', 'Content-Type': 'application/json'}
            merged.update(headers or {})
            conn.request(method, path, None if value is None else json.dumps(value), merged)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_discovery_and_selection_require_same_origin_and_token(self):
        for method in ('GET', 'POST'):
            for headers, code in (({'Authorization': ''}, 401), ({'Host': 'evil.example'}, 403),
                                  ({'Origin': 'https://evil.example'}, 403)):
                self.assertEqual(self.request(method, {'ids': [FIRST]} if method == 'POST' else None, headers)[0], code)
        self.assertEqual(self.observer.read_config()['threads'], [])

    def test_http_round_trip_validation_and_conflict(self):
        status, body = self.request('GET')
        self.assertEqual(status, 200)
        self.assertEqual(len(body['sessions']), 2)
        self.assertEqual(self.request('POST', {'ids': [FIRST]})[1]['added'], 1)
        self.assertEqual(self.request('POST', {'ids': []})[0], 400)
        self.assertEqual(self.request('POST', {'ids': ['00000000-0000-7000-8000-000000000099']})[0], 409)
        self.assertTrue(next(s for s in self.request('GET')[1]['sessions'] if s['id'] == FIRST)['selected'])

    def test_native_client_receives_success_and_terminal_error(self):
        self.observer.write_json(self.runtime / 'connection.json',
            {'url': 'http://127.0.0.1:' + str(self.server.server_port), 'token': 'selection-test'})
        client = BridgeClient(self.runtime)
        def wait(serial):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                result = (client.poll() or {}).get('codex_result') or {}
                if result.get('serial') == serial:
                    return result
                time.sleep(.05)
            self.fail('native client result timed out')
        try:
            self.assertEqual(len(wait(client.codex_sessions())['data']['sessions']), 2)
            self.assertTrue(wait(client.codex_sessions(ids=[FIRST]))['ok'])
            self.assertFalse(wait(client.codex_sessions(ids=[]))['ok'])
        finally:
            client.close()
            client.thread.join(timeout=3)


if __name__ == '__main__':
    unittest.main()
