"""Resolve Cursor navigation against live windows, without changing read state.

Cursor 3.14 redirects third-party extension URLs to an IDE window. Agents
windows instead handle the built-in background-agent route before extensions.
Only send that route after verifying a live Agents window, never as a fallback.
"""
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import threading
import time
from urllib.parse import unquote, urlsplit

UUID = re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$', re.I)


class NavigationError(ValueError):
    pass


def parse_status(text):
    """The official --status output supplies live Electron window IDs."""
    main = re.search(r'^\s*\d+\s+\d+\s+(\d+)\s+cursor main\s*$', text, re.M | re.I)
    windows = []
    for match in re.finditer(r'^\s*\d+\s+\d+\s+\d+\s+window \[(\d+)\] \((.*)\)\s*$', text, re.M):
        wid, title = match.groups()
        windows.append({'id': int(wid), 'title': title,
                        'surface': 'agents' if title == 'Cursor Agents' else 'editor'})
    if not main:
        raise NavigationError('无法确认 Cursor 的运行实例，请保持原窗口打开后重试。')
    return int(main.group(1)), windows


def live_windows():
    if os.name != 'nt':
        raise NavigationError('当前原窗口定位支持 Windows 版 Cursor。')
    app = Path(os.environ.get('LOCALAPPDATA', ''))/'Programs/cursor'
    if not (app/'Cursor.exe').is_file():
        raise NavigationError('没有找到 Cursor 安装目录。')
    try:
        result = subprocess.run([str(app/'Cursor.exe'), str(app/'resources/app/out/cli.js'), '--status'],
            env={**os.environ, 'ELECTRON_RUN_AS_NODE': '1'}, capture_output=True,
            encoding='utf-8', errors='replace', timeout=8, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise NavigationError('Cursor 暂时没有返回窗口信息，请稍后重试。')
        return parse_status(result.stdout)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise NavigationError('Cursor 窗口暂时无法定位，请保持原窗口打开后重试。') from error


def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=.5)
    db.execute('PRAGMA query_only=ON')
    return db


def origin_metadata(home):
    """Project membership + IDE composer indexes; no prompts or responses."""
    root = Path(home)/'AppData/Roaming/Cursor/User'
    agents, editors = set(), {}
    db = readonly(root/'globalStorage/state.vscdb')
    try:
        row = db.execute("SELECT value FROM ItemTable WHERE key='glass.localAgentProjectMembership.v1'").fetchone()
        if row:
            data = json.loads(row[0])
            if isinstance(data, dict): agents.update(k for k in data if UUID.fullmatch(k))
        row = db.execute("SELECT value FROM ItemTable WHERE key='cursor/glass.selectedAgent'").fetchone()
        if row and isinstance(row[0], str) and UUID.fullmatch(row[0]): agents.add(row[0])
    finally:
        db.close()
    for path in (root/'workspaceStorage').glob('*/state.vscdb'):
        workspace = path.parent/'workspace.json'
        if not workspace.is_file(): continue
        try:
            metadata = json.loads(workspace.read_text(encoding='utf-8'))
            uri = metadata.get('folder') or metadata.get('workspace')
            if not isinstance(uri, str): continue
            name = Path(unquote(urlsplit(uri).path)).name
            if name.endswith('.code-workspace'): name = name[:-15]
            db = readonly(path)
            try:
                row = db.execute("SELECT value FROM ItemTable WHERE key='composer.composerData'").fetchone()
            finally: db.close()
            if row:
                for composer in json.loads(row[0]).get('allComposers', []):
                    cid = composer.get('composerId', '')
                    if UUID.fullmatch(cid): editors.setdefault(cid, set()).add(name)
        except (OSError, ValueError, TypeError, sqlite3.Error):
            continue
    return agents, editors


class CursorNavigator:
    def __init__(self, home=None, inventory=live_windows, metadata=None, opener=None):
        self.home = Path(home or Path.home())
        self.inventory = inventory
        self.metadata = metadata or (lambda: origin_metadata(self.home))
        self.opener = opener or getattr(os, 'startfile', None)
        self.origins = {}  # live-process affinity only; IDs are not valid after restart
        self.lock = threading.RLock()
        self.last_observe = 0
        self.observer = None

    def schedule_observe(self, rows):
        # Window discovery can take several seconds; keep lifecycle polling free.
        if self.observer and self.observer.is_alive(): return
        self.observer = threading.Thread(target=self.observe, args=(rows,), daemon=True)
        self.observer.start()

    def choose(self, thread_id, pid, windows, agents, editors):
        previous = self.origins.get(thread_id)
        if previous and previous['pid'] == pid:
            match = next((w for w in windows if w['id'] == previous['window_id']
                          and w['surface'] == previous['surface']), None)
            if match: return match
            raise NavigationError('这个会话原来的 Cursor 窗口已关闭，本次没有跳转到其它窗口。')
        candidates = []
        if thread_id in agents:
            candidates += [w for w in windows if w['surface'] == 'agents']
        for name in editors.get(thread_id, set()):
            candidates += [w for w in windows if w['surface'] == 'editor'
                           and (w['title'] == name+' - Cursor' or w['title'].endswith(' - '+name+' - Cursor'))]
        unique = {w['id']: w for w in candidates}
        if len(unique) != 1:
            raise NavigationError('无法唯一确定这个会话原来的 Cursor 窗口，请先保留该会话所在窗口后重试。')
        window = next(iter(unique.values()))
        self.origins[thread_id] = {'pid': pid, 'window_id': window['id'], 'surface': window['surface']}
        return window

    def observe(self, rows):
        """Capture affinity while a new task runs, not only after completion."""
        ids = [r['id'] for r in rows if r.get('state') in ('running', 'waiting') and r['id'] not in self.origins]
        if not ids or time.monotonic()-self.last_observe < 15: return
        self.last_observe = time.monotonic()
        try:
            pid, windows = self.inventory()
            agents, editors = self.metadata()
            with self.lock:
                for cid in ids:
                    try: self.choose(cid, pid, windows, agents, editors)
                    except NavigationError: pass
        except (NavigationError, OSError, sqlite3.Error, ValueError):
            pass  # Discovery must keep working when navigation is unavailable.

    def open(self, thread_id):
        if not isinstance(thread_id, str) or not UUID.fullmatch(thread_id):
            raise NavigationError('Cursor 会话标识无效。')
        with self.lock:
            try:
                pid, windows = self.inventory()  # no cached window IDs at click time
                agents, editors = self.metadata()
                window = self.choose(thread_id, pid, windows, agents, editors)
                wid = window['id']
                if window['surface'] == 'agents':
                    url = f'cursor://anysphere.cursor-deeplink/background-agent?bcId={thread_id}&windowId={wid}'
                else:
                    url = f'cursor://wang-bun.local-monitor/open?id={thread_id}&windowId={wid}'
                if not self.opener: raise NavigationError('此系统暂不支持 Cursor 原窗口跳转。')
                self.opener(url)
                return True
            except (OSError, sqlite3.Error, json.JSONDecodeError) as error:
                raise NavigationError('暂时无法读取 Cursor 的窗口归属，请稍后重试。') from error
