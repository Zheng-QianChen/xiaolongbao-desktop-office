"""Explicit, local Codex session selection. Discovery never opens conversation logs."""
import os
from pathlib import Path
import sqlite3

from codex_clones import UUID

LIMIT = 100


class ConnectionError(ValueError):
    def __init__(self, message, status=503):
        super().__init__(message)
        self.status = status


def session_path(home, text):
    if not isinstance(text, str) or not text:
        raise ValueError('invalid rollout path')
    if text.startswith('\\\\?\\'):
        text = text[4:]
    path = Path(text).resolve()
    if (home / 'sessions').resolve() not in path.parents:
        raise ValueError('outside sessions')
    return path


class CodexConnections:
    def __init__(self, observer):
        self.observer = observer

    def config(self):
        try:
            config = self.observer.read_config()
        except (OSError, ValueError):
            raise ConnectionError('无法读取本地连接配置，请检查后重试。')
        home = Path(config.get('codex_home') or os.environ.get('CODEX_HOME') or
                    Path.home() / '.codex').resolve()
        return config, home

    def database(self, home):
        try:
            db = sqlite3.connect((home / 'state_5.sqlite').as_uri() + '?mode=ro',
                                 uri=True, timeout=.5)
            db.execute('PRAGMA query_only=ON')
            return db
        except sqlite3.Error:
            raise ConnectionError('未能读取本机 Codex 会话列表，请先启动 Codex 后重试。')

    def session(self, home, row, selected):
        ident, title, updated_at, path = row
        if not isinstance(ident, str) or not UUID.fullmatch(ident):
            return None
        try:
            if not session_path(home, path).is_file():
                return None
        except (ValueError, OSError):
            return None
        title = title if isinstance(title, str) and title.strip() else '未命名会话'
        return {'id': ident, 'label': ' '.join(title.split())[:120],
                'updated_at': updated_at, 'selected': ident in selected}

    def discover(self, query=''):
        if not isinstance(query, str) or len(query) > 100:
            raise ConnectionError('搜索文字最多 100 个字符。', 400)
        with self.observer.lock:
            config, home = self.config()
            selected = {t['id'] for t in config.get('threads', [])}
        # Only named list metadata is queried; never SELECT * or first_user_message.
        pattern = '%' + query.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        db = self.database(home)
        try:
            rows = db.execute("SELECT id,title,updated_at,rollout_path FROM threads "
                              "WHERE archived=0 AND (title LIKE ? ESCAPE '\\' OR id LIKE ? ESCAPE '\\') "
                              'ORDER BY updated_at DESC,id LIMIT ?',
                              (pattern, pattern, LIMIT + 1)).fetchall()
        except sqlite3.Error:
            raise ConnectionError('当前 Codex 会话索引暂时不可用，请稍后刷新。')
        finally:
            db.close()
        sessions = [self.session(home, row, selected) for row in rows[:LIMIT]]
        sessions = [session for session in sessions if session is not None]
        return {'sessions': sessions, 'truncated': len(rows) > LIMIT,
                'source_enabled': self.observer.store.enabled('codex')}

    def add(self, value):
        if (not isinstance(value, dict) or set(value) != {'ids'} or
                not isinstance(value['ids'], list) or not 1 <= len(value['ids']) <= 20 or
                any(not isinstance(i, str) or not UUID.fullmatch(i) for i in value['ids'])):
            raise ConnectionError('请选择 1–20 个有效会话。', 400)
        ids = list(dict.fromkeys(value['ids']))
        with self.observer.lock:
            config, home = self.config()
            threads = list(config.get('threads', []))
            selected = {t['id'] for t in threads}
            needed = [ident for ident in ids if ident not in selected]
            added = []
            if needed:
                db = self.database(home)
                try:
                    for ident in needed:
                        row = db.execute('SELECT id,title,updated_at,rollout_path FROM threads '
                                         'WHERE id=? AND archived=0', (ident,)).fetchone()
                        candidate = self.session(home, row, selected) if row else None
                        if candidate is None:
                            raise ConnectionError('有会话已归档、移走或不可用，请刷新列表后重新选择。', 409)
                        added.append({'id': ident, 'label': candidate['label'],
                                      'status': 'unknown', 'unread': False, 'selected_at': None})
                except sqlite3.Error:
                    raise ConnectionError('当前 Codex 会话索引暂时不可用，请稍后重试。')
                finally:
                    db.close()
                # Validate the complete batch before changing anything. Retries are idempotent.
                config.update(codex_home=str(home), threads=threads + added)
                self.observer.write_json(self.observer.config_path, config)
                self.observer.last_poll = 0
            return {'added': len(added), 'registered': len(ids),
                    'source_enabled': self.observer.store.enabled('codex')}
