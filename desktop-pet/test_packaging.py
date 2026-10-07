import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

import app_paths
from bridge import BridgeService
from desktop_app import InstanceLock
from setup_hooks import definition


class PackagingTests(unittest.TestCase):
    def test_frozen_paths_do_not_write_to_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ, {'LOCALAPPDATA':folder}, clear=True), patch.object(sys,'frozen',True,create=True):
                self.assertEqual(app_paths.runtime_dir(),Path(folder)/'WangBun/runtime')
                with patch.dict(os.environ, {'WANG_BUN_DATA_DIR':str(Path(folder)/'custom')}):
                    self.assertEqual(app_paths.runtime_dir(),Path(folder)/'custom/runtime')

    def test_frozen_mcp_and_hooks_use_console_dispatch(self):
        with patch.object(sys,'frozen',True,create=True), patch.object(sys,'executable',str(Path('C:/Pets/Wang Bun/WangBun.exe'))):
            config=app_paths.mcp_config(Path('test-runtime'))
            self.assertTrue(config['command'].endswith('WangBun-cli.exe'))
            self.assertEqual(config['args'][0],'mcp')
            hook=definition('zcode')['hooks']['events']['Stop'][0]['hooks'][0]
            self.assertTrue(hook['command'].endswith('WangBun-cli.exe'))
            self.assertEqual(hook['args'][0],'notify')
            self.assertIn('--runtime',hook['args'])
            self.assertEqual(hook['args'][-2:],['hook','zcode'])

    def test_instance_lock_releases_without_deleting_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'desktop.lock'
            first=InstanceLock(path)
            try:
                with self.assertRaises(OSError): InstanceLock(path)
            finally: first.close()
            second=InstanceLock(path);second.close()
            self.assertTrue(path.exists())

    def test_service_owns_and_closes_its_http_port(self):
        with tempfile.TemporaryDirectory() as folder:
            service=BridgeService(folder,port=0,discovery=False)
            port=service.server.server_port
            try:
                client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with client.open(service.config['url']+'/health',timeout=3) as response:
                    self.assertEqual(json.load(response)['service'],'wang-bun-bridge')
                self.assertEqual(json.loads((Path(folder)/'connection.json').read_text()),service.config)
            finally: service.close()
            service.close()
            with socket.socket() as check:
                self.assertNotEqual(check.connect_ex(('127.0.0.1',port)),0)

    def test_resource_manifest_excludes_local_state(self):
        root=Path(__file__).resolve().parent
        spec=importlib.util.spec_from_file_location('release_files',root/'packaging/release_files.py')
        manifest=importlib.util.module_from_spec(spec);spec.loader.exec_module(manifest)
        paths=manifest.resources(root)
        self.assertGreater(len(paths),70)
        for path in paths:
            relative=path.relative_to(root)
            self.assertFalse(set(relative.parts)&{'runtime','sources','history','.codex','.claude','.cursor'})
            self.assertNotIn(path.suffix,('.sqlite3','.log','.jsonl','.psd'))
        self.assertIn(root/'bridge-ui/extensions.html',paths)


if __name__=='__main__': unittest.main()
