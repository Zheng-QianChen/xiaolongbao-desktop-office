"""Loopback service for local hooks, native pets and the layered renderer."""
import argparse
import hmac
import json
import mimetypes
from pathlib import Path
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit
from bridge_store import Store
from codex_clones import CloneObserver
from codex_connections import CodexConnections, ConnectionError
from gui_observers import GuiObservers
from extension_hub import ExtensionHub, PushAuthError
from extension_io import ExtensionError
from app_paths import runtime_dir
from cursor_navigation import CursorNavigator, NavigationError

ROOT = Path(__file__).resolve().parent
DEFAULT_RUNTIME = runtime_dir() / 'bridge'
MAX_BODY = 65536


def connection_file(runtime):
    return Path(runtime) / 'connection.json'


def build_server(store, token, port=0, clones=None, extensions=None, cursor_navigator=None):
    connections = CodexConnections(clones) if clones else None
    cursor_navigator = cursor_navigator or CursorNavigator()
    class Handler(BaseHTTPRequestHandler):
        def handle_one_request(self):
            try:
                super().handle_one_request()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                # Closing/reloading the panel can abandon an in-flight snapshot
                # or model response. The durable result is already saved.
                self.close_connection = True

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass  # Event bodies and tokens never enter access logs.

        def reply(self, status, value):
            data = json.dumps(value, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def local_request(self):
            # Reject DNS rebinding and cross-site requests, including browser writes.
            authority = '127.0.0.1:' + str(self.server.server_port)
            if self.headers.get('Host') != authority:
                self.reply(403, {'error': 'loopback Host required'})
                return False
            origin = self.headers.get('Origin')
            if origin and origin != 'http://' + authority:
                self.reply(403, {'error': 'same-origin requests only'})
                return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                self.reply(403, {'error': 'same-origin requests only'})
                return False
            return True

        def do_GET(self):
            if not self.local_request():
                return
            path = urlsplit(self.path).path
            if path == '/health':
                return self.reply(200, {'ok': True, 'service': 'wang-bun-bridge', 'version': 1})
            if path == '/api/session':
                return self.reply(200, {'token': token})
            if path.startswith('/api/'):
                if not self.authorized():
                    return
                if path == '/api/snapshot':
                    return self.reply(200, store.snapshot())
                if path == '/api/extensions':
                    if extensions is None: return self.reply(503, {'error':'订阅服务未启动。'})
                    return self.reply(200, extensions.snapshot())
                if path == '/api/settings':
                    snap=store.snapshot()
                    return self.reply(200, {'settings':snap['settings'],'connections':snap['connections']})
                if path == '/api/codex/sessions':
                    if connections is None:
                        return self.reply(503, {'error': '当前桥服务未启用会话管理。'})
                    try:
                        query = parse_qs(urlsplit(self.path).query).get('q', [''])[0]
                        return self.reply(200, connections.discover(query))
                    except ConnectionError as error:
                        return self.reply(error.status, {'error': str(error)})
                    except (OSError, ValueError, KeyError, TypeError):
                        return self.reply(503, {'error': '无法读取本地连接配置，请检查后重试。'})
                return self.reply(404, {'error': 'unknown endpoint'})
            static = {'/': ROOT/'bridge-ui/index.html', '/live.js': ROOT/'bridge-ui/live.js',
                      '/scene.js': ROOT/'bridge-ui/scene.js',
                      '/connections.js': ROOT/'bridge-ui/connections.js',
                      '/extensions': ROOT/'bridge-ui/extensions.html',
                      '/extensions.js': ROOT/'bridge-ui/extensions.js',
                      '/extensions.css': ROOT/'bridge-ui/extensions.css'}
            target = static.get(path)
            if path.startswith('/art/'):
                relative = unquote(path[len('/art/'):])
                candidate = (ROOT/'layered-poc'/relative).resolve()
                base = (ROOT/'layered-poc').resolve()
                # Never expose source metadata, history, runtime or arbitrary files.
                allowed_root = {'rig.json', 'spatial-rig-v7.json', 'motions.js', 'renderer.js',
                                'geometry.js', 'articulation.js', 'spatial.js', 'layer-turn.js'}
                if (base in candidate.parents and
                        (candidate.parent == base and candidate.name in allowed_root or
                         candidate.parent == base/'layers' and candidate.suffix.lower() == '.png')):
                    target = candidate
            if target is None or not target.is_file():
                return self.reply(404, {'error': 'not found'})
            data = target.read_bytes()
            content_type = 'text/javascript' if target.suffix == '.js' else mimetypes.guess_type(str(target))[0] or 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def authorized(self):
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.reply(401, {'error': 'local bridge token required'})
                return False
            return True

        def do_POST(self):
            if not self.local_request():
                return
            push_id = self.path[len('/api/push/'):] if self.path.startswith('/api/push/') else None
            credential = self.headers.get('Authorization','').removeprefix('Bearer ')
            if not (push_id and extensions and extensions.authenticate_push(push_id, credential)):
                if not self.authorized(): return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY:
                    return self.reply(413, {'error': 'body must be 1..65536 bytes'})
                if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    return self.reply(415, {'error': 'JSON required'})
                value = json.loads(self.rfile.read(length))
                if push_id:
                    if extensions is None: return self.reply(503, {'error':'订阅服务未启动。'})
                    admin = hmac.compare_digest(self.headers.get('Authorization',''), 'Bearer '+token)
                    return self.reply(200, extensions.publish(push_id, value, push_token=None if admin else credential))
                if self.path.startswith('/api/extensions/'):
                    if extensions is None: return self.reply(503, {'error':'订阅服务未启动。'})
                    if not isinstance(value, dict): raise ExtensionError('需要 JSON 对象。')
                    route = self.path[len('/api/extensions/'):]
                    if route == 'connectors': result = extensions.save_connector(value)
                    elif route in ('delete','poll','key'):
                        identifier = value.get('id')
                        if not isinstance(identifier, str): raise ExtensionError('请指定连接 ID。')
                        result = {'delete':extensions.remove_connector,'poll':extensions.schedule,'key':extensions.rotate_key}[route](identifier)
                    elif route == 'model': result = extensions.save_model(value)
                    elif route == 'chat': result = extensions.chat(value)
                    elif route == 'publish': result = extensions.publish(value.get('connector_id'), value.get('item'))
                    else: return self.reply(404, {'error':'unknown endpoint'})
                    return self.reply(200, result)
                if self.path == '/api/events':
                    return self.reply(200, store.ingest(value))
                if self.path == '/api/open':
                    key = value.get('task_id') if isinstance(value, dict) else None
                    if not isinstance(key, str): return self.reply(400, {'error':'请指定会话。'})
                    task = store.task(key)
                    if not task or task['source'] != 'cursor':
                        return self.reply(404, {'error':'未找到对应的 Cursor 会话。'})
                    return self.reply(200, {'opened':cursor_navigator.open(task['thread_id'])})
                if self.path == '/api/read' and isinstance(value, dict):
                    return self.reply(200, store.acknowledge(value.get('ids')))
                if self.path == '/api/settings':
                    return self.reply(200, {'settings':store.update_settings(value)})
                if self.path == '/api/codex/sessions':
                    if connections is None:
                        return self.reply(503, {'error': '当前桥服务未启用会话管理。'})
                    return self.reply(200, connections.add(value))
                self.reply(404, {'error': 'unknown endpoint'})
            except NavigationError as error:
                self.reply(409, {'error':str(error)})
            except ConnectionError as error:
                self.reply(error.status, {'error': str(error)})
            except ExtensionError as error:
                self.reply(400, {'error':str(error)})
            except PushAuthError:
                self.reply(401, {'error':'push credential expired or disabled'})
            except OSError:
                self.reply(503, {'error': '本地连接配置未能保存，请稍后重试。'})
            except (ValueError, UnicodeError, TypeError):
                self.reply(400, {'error': 'invalid event or JSON body'})

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    return server


def drain_spool(store, runtime):
    """Each hook owns one atomically renamed file, so concurrent writers cannot interleave."""
    inbox = Path(runtime) / 'inbox'
    if not inbox.exists():
        return
    for path in sorted(inbox.glob('*.json'))[:256]:
        try:
            if path.stat().st_size > MAX_BODY:
                raise ValueError('oversized spool event')
            store.ingest(json.loads(path.read_text(encoding='utf-8')))
        except (ValueError, UnicodeError):
            path.replace(path.with_suffix('.invalid'))
        except OSError:
            continue
        else:
            path.unlink()  # Only this bridge's successfully ingested event files.


class BridgeService:
    """Owned service lifecycle for both CLI and the packaged desktop process."""
    def __init__(self, runtime, port=8768, discovery=True):
        runtime = Path(runtime)
        runtime.mkdir(parents=True, exist_ok=True)
        self.stop = threading.Event()
        self.closed = False
        self.store = Store(runtime/'state.sqlite3')
        if not discovery: self.store.update_settings({'auto_discover':False})
        self.clones = CloneObserver(runtime, self.store)
        self.guis = GuiObservers(runtime, self.store)
        self.cursor_navigator = CursorNavigator()
        self.guis.cursor_navigator = self.cursor_navigator
        self.extensions = ExtensionHub(runtime, self.store)
        token = secrets.token_urlsafe(32)
        try:
            self.server = build_server(self.store, token, port, clones=self.clones, extensions=self.extensions,
                                       cursor_navigator=self.cursor_navigator)
        except Exception:
            self.extensions.close()
            self.store.close()
            raise
        self.config = {'url':'http://127.0.0.1:'+str(self.server.server_port), 'token':token}
        path = connection_file(runtime)
        try:
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.config), encoding='utf-8')
            temporary.replace(path)
        except Exception:
            self.server.server_close()
            self.extensions.close()
            self.store.close()
            raise
        def consume():
            while not self.stop.is_set():
                drain_spool(self.store, runtime)
                self.clones.poll()
                self.guis.poll()
                self.stop.wait(.25)
        def consume_subscriptions():
            while not self.stop.is_set():
                try:
                    self.extensions.poll()
                except Exception:
                    print('Subscription cycle unavailable; retrying without advancing its cursor.', file=sys.stderr)
                    self.stop.wait(10)
                self.stop.wait(1)
        self.threads = [threading.Thread(target=consume, daemon=True),
                        threading.Thread(target=consume_subscriptions, daemon=True),
                        threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.25), daemon=True)]
        for thread in self.threads: thread.start()

    def close(self):
        if self.closed: return
        self.closed = True
        self.stop.set()
        self.server.shutdown()
        self.server.server_close()
        for thread in self.threads: thread.join(timeout=5)
        # An in-flight network operation can finish after shutdown. Do not close
        # a database still used by its thread; process exit will release it.
        if not any(t.is_alive() for t in self.threads):
            self.extensions.close()
            self.store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--runtime', type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument('--no-discovery',action='store_true',help='Disable GUI observers for isolated fixtures or hook-only use')
    args = parser.parse_args()
    service = BridgeService(args.runtime, args.port, not args.no_discovery)
    print(service.config['url'], flush=True)
    try:
        while not service.stop.wait(.5): pass
    except KeyboardInterrupt:
        pass
    finally:
        service.close()


if __name__ == '__main__':
    main()
