import math
import random
import tempfile
import unittest
from pathlib import Path
from workstations import Workers,CLOSING_DURATION
from travel import Travel,desk_position,phase_frame


class TravelTests(unittest.TestCase):
    def board(self,count=1):
        board=Workers()
        for i in range(count):
            board.ingest({'thread_id':str(i),'state':'running'},0)
        board.update(3)
        return board

    def advance(self,board,motion,start,end):
        for step in range(round((end-start)*30)):
            now=start+(step+1)/30
            board.update(now)
            motion.update(board,[150,220],4,12,1/30,now)

    def test_close_then_walk_then_return_and_reuse_computer(self):
        board=self.board();motion=Travel();w=board.items['0']
        motion.update(board,[150,220],4,12,.016,3)
        w.set_state('completed',4)
        self.assertTrue(w.unread)
        self.assertEqual(w.phase,'closing')
        origin=motion.positions['0'].xy[:]
        self.advance(board,motion,4,5.5)
        self.assertEqual(motion.positions['0'].xy,origin)
        self.advance(board,motion,5.5,12)
        self.assertEqual(w.phase,'following')
        self.assertFalse(w.at_desk)
        self.assertFalse(motion.positions['0'].moving)
        w.set_state('running',12)
        self.assertEqual(w.phase,'returning')
        self.assertTrue(w.unread)  # a new run does not acknowledge the old result
        self.advance(board,motion,12,19)
        self.assertTrue(w.at_desk)
        self.assertEqual(motion.positions['0'].xy,origin)
        self.assertIn(w.phase,{'typing','blink','drink'})

    def test_hidden_workers_advance_and_removed_slots_do_not_shift(self):
        board=self.board(15);motion=Travel();hidden=board.items['14']
        slot=hidden.slot
        for w in board.items.values():w.set_state('completed',4)
        self.advance(board,motion,4,14)
        self.assertEqual(hidden.phase,'following')
        board.ingest({'agent_id':'0','method':'agent/removed'},15)
        self.assertEqual(hidden.slot,slot)
        hidden.set_state('running',15)
        self.advance(board,motion,15,23)
        self.assertEqual(motion.positions['14'].xy,desk_position(slot,4,12))

    def test_house_completion_comes_down_then_returns_to_upper_desk(self):
        board=self.board();motion=Travel();worker=board.items['0']
        desk=lambda w:[550,125]
        downstairs=lambda w,index:[100,370]
        motion.update(board,[161,260],3,6,.016,3,desk,downstairs)
        worker.set_state('completed',4)
        for n in range(360):
            now=4+n/30;board.update(now);motion.update(board,[161,260],3,6,1/30,now,desk,downstairs)
        self.assertEqual(motion.positions['0'].xy,[100,370])
        self.assertEqual(worker.phase,'following')
        self.assertTrue(worker.unread)
        worker.set_state('running',16)
        for n in range(360):
            now=16+n/30;board.update(now);motion.update(board,[161,260],3,6,1/30,now,desk,downstairs)
        self.assertEqual(motion.positions['0'].xy,[550,125])
        self.assertTrue(worker.at_desk)

    def test_interrupt_closing_reopens_and_duplicate_does_not_reroll_egg(self):
        board=self.board();w=board.items['0'];w.rng=random.Random(31)
        w.set_state('completed',4)
        self.assertTrue(w.easter_egg)
        state=w.rng.getstate()
        w.set_state('completed',4.8)
        self.assertEqual(w.rng.getstate(),state)
        self.assertEqual(w.phase_at,4)
        self.assertEqual(phase_frame(w,4.8,None)[0],'easter')
        w.set_state('running',5)
        self.assertEqual(w.phase,'open')
        self.assertTrue(w.has_computer)
        self.assertTrue(w.unread)

    def test_restore_keeps_read_completion_and_resumes_cold_running(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'state.json'
            board=Workers()
            board.ingest({'thread_id':'new','state':'running'},0)
            board.ingest({'thread_id':'done','state':'completed','read':True},0)
            board.save(path)
            restored=Workers();restored.restore(path,100)
            self.assertEqual(restored.items['new'].phase,'drop')
            self.assertEqual(restored.items['done'].phase,'following')
            self.assertFalse(restored.items['done'].unread)
            restored.update(103)
            self.assertEqual(restored.items['new'].phase,'typing')

    def test_motion_never_overshoots_with_long_tick_and_gait_stops_at_rest(self):
        board=self.board();motion=Travel();w=board.items['0']
        motion.update(board,[150,220],4,12,.016,3)
        w.set_state('completed',4);board.update(6)
        before=motion.positions['0'].xy[:]
        motion.update(board,[150,220],4,12,20,6)
        after=motion.positions['0'].xy
        self.assertLessEqual(math.dist(before,after),105*.25+.001)
        self.assertEqual(phase_frame(w,6,motion.positions['0'])[0],'walk')
        self.advance(board,motion,6,20)
        self.assertEqual(phase_frame(w,20,motion.positions['0'])[0],'rest')

    def test_failed_and_waiting_freeze_typing_without_completing(self):
        board=self.board();w=board.items['0']
        for status,group in [('waiting','waiting'),('review','waiting'),('failed','failure'),('disconnected','failure')]:
            w.set_state(status,4)
            self.assertEqual(phase_frame(w,4.8,None)[0],group)
            self.assertTrue(w.at_desk)
            self.assertFalse(w.completed)


if __name__=='__main__':unittest.main()
