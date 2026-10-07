import tempfile
import unittest
from pathlib import Path
from bridge_store import Store, make_event
from presentation_layout import PresentationLayout, reunion_offset
from travel import Travel
from workstations import Workers


class SharedLayoutTests(unittest.TestCase):
    def row(self,key,order,gathered=False,closing=False):
        return dict(id=key,order=order,gathered=gathered,needs_desk=not gathered or closing)

    def test_sparse_historical_slots_and_sources_share_dense_desks(self):
        layout=PresentationLayout()
        rows=[{**self.row(str(i),i*20),'source':['codex','cursor','claude','zcode','local'][i%5]} for i in range(8)]
        views=layout.update(rows)
        self.assertEqual(sorted(v['desk_slot'] for v in views.values()),list(range(8)))
        self.assertEqual(layout.pages(6),2)
        self.assertEqual([views[str(i)]['desk_slot'] for i in range(5)],list(range(5)))

    def test_closing_keeps_desk_departure_frees_it_and_only_last_desk_moves(self):
        layout=PresentationLayout();rows=[self.row(str(i),i) for i in range(7)]
        layout.update(rows)
        rows[1]=self.row('1',1,True,True);layout.update(rows)
        self.assertEqual(layout.views['1']['desk_slot'],1)
        rows[1]=self.row('1',1,True);layout.update(rows)
        self.assertIsNone(layout.views['1']['desk_slot'])
        self.assertEqual(layout.views['6']['desk_slot'],1)
        self.assertEqual([layout.views[str(i)]['desk_slot'] for i in (0,2,3,4,5)],[0,2,3,4,5])
        self.assertEqual(layout.pages(6),1)
        self.assertEqual(layout.views['1']['origin_slot'],1)

    def test_global_pile_order_ignores_pages_and_reordered_provider_rows(self):
        layout=PresentationLayout();rows=[self.row('a',0,True),self.row('b',7,True),self.row('c',19,True)]+[self.row(str(i),30+i) for i in range(8)]
        first=layout.update(rows)
        self.assertEqual([first[k]['gather_index'] for k in ('a','b','c')],[0,1,2])
        layout.update(list(reversed(rows)))
        self.assertEqual([layout.views[k]['gather_index'] for k in ('a','b','c')],[0,1,2])
        self.assertEqual(layout.pages(6),2)
        layout.update([r for r in rows if r['gathered']])
        self.assertEqual(layout.pages(6),1)
        self.assertEqual([layout.views[k]['gather_index'] for k in ('a','b','c')],[0,1,2])

    def test_returning_worker_acquires_shared_slot_without_duplicate_companion(self):
        layout=PresentationLayout();rows=[self.row('done',20,True),self.row('active',100)]
        layout.update(rows);rows[0]=self.row('done',20);layout.update(rows)
        self.assertEqual(layout.views['active']['desk_slot'],0)
        self.assertEqual(layout.views['done']['desk_slot'],1)
        self.assertIsNone(layout.views['done']['gather_index'])
        self.assertEqual(layout.gathered,[])

    def test_many_companions_remain_within_available_pile_height(self):
        for count in (1,3,6,9,24,100):
            offsets=[reunion_offset(i,count,45) for i in range(count)]
            self.assertEqual(len(set(offsets)),count)
            self.assertTrue(all(0<=x<=92 and 0<=y<=45 for x,y in offsets))

    def test_travel_has_one_global_follow_order(self):
        workers=Workers()
        for i in range(8):workers.ingest({'thread_id':str(i),'state':'running'},0)
        for i in (0,7):workers.items[str(i)].set_state('completed',1)
        travel=Travel();indices={}
        def follow(worker,index):indices[worker.key]=index;return [100+index*46,250]
        travel.update(workers,[150,220],3,6,.1,2,follow_resolver=follow)
        self.assertEqual(indices,{'0':0,'7':1})

    def test_store_projects_dense_desks_without_rewriting_task_identity_or_read(self):
        with tempfile.TemporaryDirectory() as directory:
            now=[1000];store=Store(Path(directory)/'state.sqlite3',clock=lambda:now[0])
            try:
                ids=[]
                for i in range(9):
                    source=['codex','cursor','claude','zcode','local'][i%5]
                    ids.append(store.ingest(make_event(source,str(i),'started',run_id='r1',managed=True))['task_id'])
                store.snapshot()
                for i in (0,6):
                    task=store.task(ids[i]);store.ingest(make_event(task['source'],str(i),'completed',run_id='r1'))
                self.assertEqual(sum(t['desk_slot'] is not None for t in store.snapshot()['tasks']),9)
                now[0]+=4
                snap=store.snapshot()
                self.assertEqual(sorted(t['desk_slot'] for t in snap['tasks'] if t['desk_slot'] is not None),list(range(7)))
                self.assertEqual(snap['unread_count'],2)
                self.assertEqual([store.task(key)['slot'] for key in ids],list(range(9)))
                self.assertNotIn('desk_slot',store.task(ids[0]))
                for _ in range(3):self.assertEqual(store.snapshot()['unread_count'],2)
            finally:store.close()


if __name__=='__main__':unittest.main()
