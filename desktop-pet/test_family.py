import unittest
import tempfile
from pathlib import Path
from workstations import Workers


class FamilyTests(unittest.TestCase):
    def test_completed_unread_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'pets-state.json'
            board=Workers()
            board.ingest({'agent_id':'a','thread_id':'t','state':'completed'},1)
            board.save(path)
            restored=Workers()
            restored.restore(path,50)
            self.assertTrue(restored.items['a'].completed)
            self.assertEqual(restored.unread_count,1)
            restored.ingest({'agent_id':'a','thread_id':'t','method':'agent/read'},51)
            restored.save(path)
            final=Workers()
            final.restore(path,100)
            self.assertEqual(final.unread_count,0)

    def test_unread_alert_persists_until_each_agent_is_read(self):
        board = Workers()
        for key in ['a','b']:
            board.ingest({'thread_id':key,'state':'running'},0)
            board.ingest({'thread_id':key,'state':'completed'},3)
        self.assertEqual(board.unread_count,2)
        self.assertEqual(board.overall_state,'unread')
        board.ingest({'thread_id':'a','method':'agent/read'},4)
        self.assertEqual(board.unread_count,1)
        board.ingest({'thread_id':'b','method':'agent/read'},4)
        self.assertEqual(board.overall_state,'idle')
        self.assertTrue(all(w.completed for w in board.items.values()))
        board.ingest({'thread_id':'a','state':'completed'},5)
        self.assertEqual(board.unread_count,0)  # duplicate completion cannot resurrect a read result

    def test_idle_does_not_mean_completed_and_new_task_returns_to_desk(self):
        board = Workers()
        board.ingest({'thread_id':'a','state':'idle'},0)
        self.assertFalse(board.items['a'].completed)
        board.ingest({'thread_id':'a','method':'turn/completed','params':{'turn':{'status':'completed'}}},1)
        self.assertTrue(board.items['a'].completed)
        board.ingest({'thread_id':'a','state':'running'},2)
        self.assertFalse(board.items['a'].completed)
        self.assertTrue(board.items['a'].unread)

    def test_failed_or_interrupted_turn_stays_at_desk(self):
        board = Workers()
        for status in ['failed','interrupted']:
            board.ingest({'thread_id':status,'method':'turn/completed',
                          'params':{'turn':{'status':status}}},0)
            self.assertFalse(board.items[status].completed)
        self.assertEqual(board.unread_count,0)


if __name__ == '__main__':
    unittest.main()
