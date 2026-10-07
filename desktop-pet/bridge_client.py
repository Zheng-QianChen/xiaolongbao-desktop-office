"""Nonblocking Tk bridge client. Network calls stay off the animation thread."""
import json
from pathlib import Path
import queue
import threading
import urllib.request
import urllib.error
from urllib.parse import urlsplit


class BridgeClient:
    def __init__(self, runtime):
        self.runtime = Path(runtime)
        self.pending_reads = queue.Queue()
        self.pending_settings = queue.Queue()
        self.settings_serial = 0
        self.pending_codex = queue.Queue()
        self.codex_serial = 0
        self.latest = queue.Queue(maxsize=1)
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._poll, daemon=True)
        self.thread.start()

    def request(self, endpoint, data=None):
        config = json.loads((self.runtime/'connection.json').read_text(encoding='utf-8'))
        url = urlsplit(config['url'])
        if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.username or url.path:
            raise ValueError('bridge must be loopback')
        body = None if data is None else json.dumps(data).encode('utf-8')
        req = urllib.request.Request(config['url']+endpoint, body,
                                     {'Authorization': 'Bearer '+config['token'], 'Content-Type': 'application/json'})
        # Ignore global proxies for the private loopback endpoint.
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=1.5) as response:
            return json.load(response)

    def _publish(self, result):
        try:
            self.latest.get_nowait()
        except queue.Empty:
            pass
        self.latest.put_nowait(result)

    def _poll(self):
        retry = None
        setting_retry=None
        setting_result=None
        codex_retry = None
        codex_result = None
        while not self.stopped.is_set():
            try:
                if retry is None:
                    try:
                        retry = self.pending_reads.get_nowait()
                    except queue.Empty:
                        pass
                if retry is not None:
                    self.request('/api/read', {'ids': retry})
                    retry = None
                if setting_retry is None:
                    try:setting_retry=self.pending_settings.get_nowait()
                    except queue.Empty:pass
                if setting_retry is not None:
                    serial,patch=setting_retry
                    try:
                        self.request('/api/settings',patch)
                        setting_result={'serial':serial,'ok':True}
                        setting_retry=None
                    except urllib.error.HTTPError as error:
                        if error.code!=400:raise
                        setting_result={'serial':serial,'ok':False}
                        setting_retry=None
                if codex_retry is None:
                    try:codex_retry=self.pending_codex.get_nowait()
                    except queue.Empty:pass
                if codex_retry is not None:
                    serial, endpoint, body = codex_retry
                    try:
                        data = self.request(endpoint, body)
                        codex_result = {'serial': serial, 'ok': True, 'data': data}
                        codex_retry = None
                    except urllib.error.HTTPError as error:
                        if error.code == 401:raise
                        try:message = json.load(error).get('error', '会话连接暂时不可用。')
                        except (ValueError, OSError):message = '会话连接暂时不可用。'
                        codex_result = {'serial': serial, 'ok': False, 'error': message}
                        codex_retry = None
                snap=self.request('/api/snapshot')
                snap['settings_result']=setting_result
                snap['codex_result']=codex_result
                self._publish(snap)
            except (OSError, ValueError, KeyError):
                self._publish({'offline': True})
            self.stopped.wait(.5)

    def read(self, ids):
        if ids:
            self.pending_reads.put(list(ids))

    def open_extensions(self):
        import webbrowser
        config = json.loads((self.runtime/'connection.json').read_text(encoding='utf-8'))
        url = urlsplit(config['url'])
        if url.scheme != 'http' or url.hostname != '127.0.0.1' or url.username or url.password or url.path or url.query or url.fragment:
            raise ValueError('bridge must be loopback')
        webbrowser.open(config['url']+'/extensions')

    def update_settings(self, patch):
        self.settings_serial+=1
        self.pending_settings.put((self.settings_serial,patch))
        return self.settings_serial

    def codex_sessions(self, query='', ids=None):
        from urllib.parse import urlencode
        self.codex_serial += 1
        endpoint = '/api/codex/sessions'
        body = {'ids': list(ids)} if ids is not None else None
        if body is None:
            endpoint += '?' + urlencode({'q': query})
        self.pending_codex.put((self.codex_serial, endpoint, body))
        return self.codex_serial

    def poll(self):
        try:
            return self.latest.get_nowait()
        except queue.Empty:
            return None

    def close(self):
        self.stopped.set()


def worker_events(snapshot):
    for task in snapshot['tasks']:
        state = task['display_state']
        yield {'agent_id': task['id'], 'thread_id': task['thread_id'], 'label': task['label'],
               'state': 'completed' if task.get('retire_at') else 'idle' if state == 'cancelled' else state,
               'summary': task['bubble'] or task['summary'], 'unread': bool(task['unread_ids'])}
