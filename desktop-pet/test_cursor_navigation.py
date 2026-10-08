import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from cursor_navigation import CursorNavigator, NavigationError, origin_metadata, parse_status

ID='11111111-1111-4111-8111-111111111111'


class NavigationTests(unittest.TestCase):
    def navigator(self, agents=True, editors=None):
        self.windows=[{'id':1,'surface':'agents','title':'Cursor Agents'},
                      {'id':2,'surface':'editor','title':'main.py - demo - Cursor'}]
        self.pid=123
        self.urls=[]
        return CursorNavigator(inventory=lambda:(self.pid,self.windows),
            metadata=lambda:({ID} if agents else set(),editors or {}),opener=self.urls.append)

    def test_status_reads_ids_and_process_without_order_assumption(self):
        pid,windows=parse_status(' 0 300 123 cursor main\n 0 100 456 window [9] (demo - Cursor)\n 0 500 789 window [3] (Cursor Agents)\n')
        self.assertEqual(pid,123)
        self.assertEqual([(w['id'],w['surface']) for w in windows],[(9,'editor'),(3,'agents')])
        with self.assertRaises(NavigationError):parse_status('window [1] (Cursor Agents)')

    def test_agent_uses_builtin_route_even_when_editor_is_first(self):
        nav=self.navigator();self.windows.reverse();nav.open(ID)
        self.assertEqual(self.urls,[f'cursor://anysphere.cursor-deeplink/background-agent?bcId={ID}&windowId=1'])

    def test_editor_uses_its_window_not_agent_window(self):
        nav=self.navigator(False,{ID:{'demo'}});nav.open(ID)
        self.assertEqual(self.urls,[f'cursor://wang-bun.local-monitor/open?id={ID}&windowId=2'])

    def test_running_task_remembers_original_before_second_agent_window(self):
        nav=self.navigator();nav.observe([{'id':ID,'state':'running'}])
        self.windows.insert(0,{'id':3,'surface':'agents','title':'Cursor Agents'})
        nav.open(ID)
        self.assertTrue(self.urls[0].endswith('windowId=1'))

    def test_ambiguous_windows_never_use_foreground_or_first(self):
        nav=self.navigator();self.windows.append({'id':3,'surface':'agents','title':'Cursor Agents'})
        with self.assertRaises(NavigationError):nav.open(ID)
        self.assertEqual(self.urls,[])

    def test_closed_original_never_falls_back_to_another_window(self):
        nav=self.navigator();nav.open(ID);self.urls.clear()
        self.windows[0]={'id':3,'surface':'agents','title':'Cursor Agents'}
        with self.assertRaises(NavigationError):nav.open(ID)
        self.assertEqual(self.urls,[])

    def test_restart_does_not_reuse_old_window_number(self):
        nav=self.navigator();nav.open(ID);self.urls.clear();self.pid=456
        self.windows=[{'id':1,'surface':'editor','title':'demo - Cursor'},
                      {'id':9,'surface':'agents','title':'Cursor Agents'}]
        nav.open(ID);self.assertTrue(self.urls[0].endswith('windowId=9'))

    def test_unknown_or_conflicting_origin_is_not_a_guess(self):
        for agents,editors in [(False,{}),(True,{ID:{'demo'}})]:
            nav=self.navigator(agents,editors)
            with self.assertRaises(NavigationError):nav.open(ID)
            self.assertEqual(self.urls,[])

    def test_invalid_id_cannot_dispatch_a_url(self):
        nav=self.navigator()
        with self.assertRaises(NavigationError):nav.open(ID+'&command=delete')
        self.assertEqual(self.urls,[])

    def test_metadata_reads_only_member_and_composer_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'AppData/Roaming/Cursor/User'
            for folder in ('globalStorage','workspaceStorage/project'):
                (root/folder).mkdir(parents=True)
                db=sqlite3.connect(root/folder/'state.vscdb')
                db.execute('CREATE TABLE ItemTable (key TEXT PRIMARY KEY,value TEXT)')
                if folder=='globalStorage':
                    db.execute('INSERT INTO ItemTable VALUES (?,?)',('glass.localAgentProjectMembership.v1',json.dumps({ID:'project'})))
                    db.execute('INSERT INTO ItemTable VALUES (?,?)',('PRIVATE_CHAT','PRIVATE'))
                else:
                    db.execute('INSERT INTO ItemTable VALUES (?,?)',('composer.composerData',json.dumps({'allComposers':[{'composerId':ID}]})))
                    (root/folder/'workspace.json').write_text(json.dumps({'folder':'file:///C:/demo'}))
                db.commit();db.close()
            self.assertEqual(origin_metadata(tmp),({ID},{ID:{'demo'}}))


if __name__=='__main__':unittest.main()
