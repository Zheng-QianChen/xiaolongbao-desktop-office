import unittest
from workstations import Workers


def event(state, thread='t', agent=None, **extra):
    out = {'thread_id':thread,'state':state,**extra}
    if agent:
        out['agent_id'] = agent
    return out


class WorkerTests(unittest.TestCase):
    def test_entrance_duplicate_and_resume(self):
        board = Workers()
        board.ingest(event('running'),0)
        worker = board.items['t']
        board.ingest(event('running'),.4)
        self.assertEqual(worker.phase_at,0)
        board.update(2.4)
        self.assertEqual(worker.phase,'typing')
        board.ingest(event('waiting'),3)
        board.update(20)
        self.assertEqual(worker.phase,'rest')
        board.ingest(event('running'),21)
        self.assertEqual(worker.phase,'typing')

    def test_independent_agents_and_late_id(self):
        board = Workers()
        board.ingest(event('running'),0)
        board.ingest(event('running',agent='a'),.2)
        self.assertEqual(len(board.items),1)
        self.assertEqual(board.items['a'].phase_at,0)
        board.ingest(event('running',agent='b'),.4)
        board.ingest(event('failed',agent='a'),.5)
        self.assertEqual(board.items['b'].state,'running')
        board.ingest({'method':'agent/removed','agent_id':'a'},1)
        self.assertEqual(list(board.items),['b'])

    def test_out_of_order_and_interrupted_entrance(self):
        board = Workers()
        board.ingest(event('running',sequence=3),0)
        board.ingest(event('idle',sequence=2),.1)
        self.assertEqual(board.items['t'].state,'running')
        board.ingest(event('failed',sequence=4),.3)
        board.update(4)
        self.assertEqual(board.items['t'].phase,'rest')
        self.assertFalse(board.items['t'].has_computer)

    def test_random_breaks_repeatable_and_terminate(self):
        logs=[]
        for _ in range(2):
            board=Workers()
            board.ingest(event('running'),0)
            log=[]
            for tick in range(500):
                board.update(tick/10)
                log.append(board.items['t'].phase)
            self.assertIn('drink',log)
            self.assertIn('blink',log)
            logs.append(log)
        self.assertEqual(logs[0],logs[1])


if __name__ == '__main__':
    unittest.main()
