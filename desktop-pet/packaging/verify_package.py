"""Exercise real frozen binaries in a disposable data directory (Windows only)."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request


def run(bundle, output):
    bundle=Path(bundle).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    original={p.relative_to(bundle).as_posix():p.stat().st_mtime_ns for p in bundle.rglob('*') if p.is_file()}
    checks=[]
    with tempfile.TemporaryDirectory(prefix='望包 package ') as folder:
        root=Path(folder);runtime=root/'runtime/bridge'
        env={**os.environ,'WANG_BUN_DATA_DIR':str(root)}
        command=[str(bundle/'WangBun.exe'),'--data-dir',str(root),'--port','0','--no-discovery','--smoke-test']
        pet=subprocess.Popen(command,cwd=root,env=env)
        def cli(*args, input=None):
            result=subprocess.run([str(bundle/'WangBun-cli.exe'),*args],cwd=root,env=env,
                input=input,capture_output=True,timeout=10,creationflags=subprocess.CREATE_NO_WINDOW)
            assert result.returncode==0,result.stderr.decode('utf-8',errors='replace')
            return result.stdout.decode('utf-8')
        try:
            deadline=time.monotonic()+20
            while not (runtime/'connection.json').exists():
                assert pet.poll() is None,'Desktop exited before bridge startup'
                assert time.monotonic()<deadline,'Bridge startup timeout'
                time.sleep(.1)
            config=json.loads((runtime/'connection.json').read_text())
            client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def api(path, value=None):
                request=urllib.request.Request(config['url']+path,
                    data=json.dumps(value).encode() if value is not None else None,
                    headers={'Authorization':'Bearer '+config['token'],'Content-Type':'application/json'})
                with client.open(request,timeout=4) as response: return response.read()
            assert json.loads(api('/health'))['ok'];checks.append('frozen-bridge-health')
            for path in ['/','/live.js','/extensions','/extensions.js','/art/rig.json','/art/spatial-rig-v7.json',
                         '/art/renderer.js','/art/motions.js','/art/geometry.js','/art/layer-turn.js']:
                assert api(path)
            for layer in json.loads(api('/art/rig.json'))['layers']: assert api('/art/'+layer['file'])
            checks.append('web-and-all-art-resources')
            mcp=json.loads(cli('mcp','--print-config'))['mcpServers']['wang-bun']
            assert Path(mcp['command'])==bundle/'WangBun-cli.exe' and mcp['args'][0]=='mcp'
            requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                      {'jsonrpc':'2.0','method':'notifications/initialized'},
                      {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}]
            responses=[json.loads(line) for line in cli('mcp',input=''.join(json.dumps(r)+'\n' for r in requests).encode()).splitlines()]
            assert [r['id'] for r in responses]==[1,2]
            assert len(responses[1]['result']['tools'])==9;checks.append('frozen-mcp-clean-stdio')
            hooks=json.loads(cli('setup-hooks','--user','--source','claude','--preview'))
            hook=hooks['hooks']['Stop'][0]['hooks'][0]['command']
            assert 'WangBun-cli.exe' in hook and 'notify' in hook and 'notify.py' not in hook
            checks.append('frozen-hook-command-preview')
            cli('publish','--channel','package','--create','Package test','--id','first','--title','Package notification')
            snap=json.loads(api('/api/snapshot'))
            assert any(t['thread_id']=='extension:package' for t in snap['tasks']);checks.append('frozen-publish-notification')
            api('/api/settings',{'always_on_top':False})
            duplicate=subprocess.run(command,cwd=root,env=env,timeout=5)
            assert duplicate.returncode==0 and pet.poll() is None
            checks.append('duplicate-launch-no-second-instance')
            # Capture only the window belonging to this test process.
            deadline=time.monotonic()+6
            hwnd=[]
            callback=ctypes.WINFUNCTYPE(ctypes.c_bool,ctypes.c_void_p,ctypes.c_void_p)
            def find_window(handle,_):
                pid=ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(handle,ctypes.byref(pid))
                if pid.value==pet.pid and ctypes.windll.user32.IsWindowVisible(handle): hwnd.append(handle)
                return True
            while not hwnd and time.monotonic()<deadline:
                ctypes.windll.user32.EnumWindows(callback(find_window),0);time.sleep(.1)
            assert hwnd,'No visible packaged pet window'
            time.sleep(1.6)
            from PIL import ImageGrab
            ImageGrab.grab(window=hwnd[0]).save(output/'packaged-desktop.png')
            assert pet.wait(timeout=25)==0,(root/'runtime/desktop.log').read_text(encoding='utf-8')
            playback=json.loads((root/'runtime/playback-check.json').read_text())
            assert not playback['errors'] and len(playback['scene_checks'])==4
            checks.append('native-window-drag-modes-and-clean-exit')
            with socket.socket() as connection:
                from urllib.parse import urlsplit
                assert connection.connect_ex(('127.0.0.1',urlsplit(config['url']).port))!=0
            checks.append('exit-releases-owned-bridge-port')
            import sqlite3
            db=sqlite3.connect(runtime/'state.sqlite3')
            # Query through source Store so persistence is verified with the same schema.
            db.close()
            import sys
            sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
            from bridge_store import Store
            store=Store(runtime/'state.sqlite3')
            try: assert store.settings()['always_on_top'] is False
            finally: store.close()
            checks.append('per-user-state-persisted')
        finally:
            if pet.poll() is None: pet.terminate();pet.wait(timeout=10)
            log=root/'runtime/desktop.log'
            if log.exists(): (output/'desktop-test.log').write_bytes(log.read_bytes())
    after={p.relative_to(bundle).as_posix():p.stat().st_mtime_ns for p in bundle.rglob('*') if p.is_file()}
    assert original==after,'Packaged app wrote to its installation directory'
    checks.append('installation-files-unchanged')
    (output/'package-report.json').write_text(json.dumps({'checks':checks},indent=2),encoding='utf-8')
    print('PACKAGE_OK '+json.dumps(checks))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.bundle,args.output)
