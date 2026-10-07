import tempfile
import unittest
from pathlib import Path
from events import EventTail, normalize, publish
from motion import pose


class ContractTests(unittest.TestCase):
    def test_motion_remains_in_window_and_failure_settles(self):
        for state in ['idle', 'running', 'waiting', 'review', 'failed', 'disconnected']:
            for frame in range(600):
                x, y = pose(state, frame/60, frame/60)
                self.assertLessEqual(abs(x), 8)
                self.assertLessEqual(abs(y), 14)
        self.assertEqual(pose('failed', 1, 1)[0], 0)

    def test_thread_isolation_and_failed_turn(self):
        event = {'method': 'turn/completed', 'params': {'threadId': 'a', 'turn': {'status': 'failed'}}}
        self.assertEqual(normalize(event, 'a'), 'failed')
        self.assertIsNone(normalize(event, 'b'))
        self.assertEqual(normalize({'method': 'item/tool/requestUserInput', 'params': {'threadId': 'a'}}, 'a'), 'waiting')
        self.assertIsNone(normalize({'thread_id': 'a', 'state': 'made-up'}, 'a'))

    def test_partial_line_and_no_history_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'events.jsonl'
            publish(path, 'a', 'failed')
            tail = EventTail(path)
            self.assertEqual(tail.read(), [])
            with path.open('ab') as stream:
                stream.write(b'{"thread_id":"a",')
            self.assertEqual(tail.read(), [])
            with path.open('ab') as stream:
                stream.write(b'"state":"running"}\ninvalid\n')
            self.assertEqual(tail.read(), [{'thread_id': 'a', 'state': 'running'}])
            path.write_text('', encoding='utf-8')
            self.assertEqual(tail.read(), [])
            publish(path, 'a', 'idle')
            self.assertEqual(tail.read()[0]['state'], 'idle')

    def test_unknown_terminal_status_is_not_success(self):
        for status in [None, 'inProgress', 'unknown']:
            self.assertIsNone(normalize({'method':'turn/completed',
                'params':{'threadId':'a','turn':{'status':status}}},'a'))

    def test_rotation_before_first_read_uses_new_file_start(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl'
            publish(path,'a','failed')
            tail=EventTail(path)
            path.replace(path.with_suffix('.old'))
            publish(path,'a','running')
            self.assertEqual(tail.read()[0]['state'],'running')


if __name__ == '__main__':
    unittest.main()
