"""Small, provider-neutral event contract for cmd-harness and the pet."""
import json
from pathlib import Path

METHODS = {
    'turn/started': 'running', 'turn/completed': 'completed',
    'item/commandExecution/requestApproval': 'waiting',
    'item/fileChange/requestApproval': 'waiting',
    'item/tool/requestUserInput': 'waiting',
    'serverRequest/resolved': 'running',
}
STATES = {'idle', 'running', 'waiting', 'review', 'failed', 'disconnected', 'completed'}


def normalize(event, thread_id):
    """Ignore events from other conversations and unrecognized methods."""
    if not isinstance(event, dict):
        return None
    params = event.get('params') or {}
    if not isinstance(params, dict):
        return None
    target = event.get('thread_id') or params.get('threadId')
    if target != thread_id:
        return None
    state = event.get('state')
    method = event.get('method')
    if state is None:
        state = METHODS.get(method)
        if method == 'turn/completed':
            turn = params.get('turn') or {}
            if not isinstance(turn, dict):
                return None
            state = {'failed':'failed', 'interrupted':'idle', 'completed':'completed'}.get(turn.get('status'))
    return state if state in STATES else None


def publish(path, thread_id, state, *, agent_id=None, label=None, sequence=None):
    """For a harness lifecycle callback. Pass metadata only, never message text."""
    if state not in STATES:
        raise ValueError('unknown pet state')
    event = {'thread_id': thread_id, 'state': state}
    if agent_id is not None:
        event['agent_id'] = agent_id
    if label is not None:
        event['label'] = label
    if sequence is not None:
        event['sequence'] = sequence
    with Path(path).open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, ensure_ascii=False) + '\n')


class EventTail:
    """Read only newly appended events. Existing history never replays."""
    def __init__(self, path):
        self.path = Path(path)
        stat = self.path.stat() if self.path.exists() else None
        self.offset = stat.st_size if stat else 0
        self.pending = b''
        self.identity = (stat.st_dev, stat.st_ino) if stat else None

    def read(self):
        try:
            stat = self.path.stat()
            identity = (stat.st_dev, stat.st_ino)
            if self.identity is not None and identity != self.identity:
                self.offset, self.pending = 0, b''
            self.identity = identity
            if stat.st_size < self.offset:
                self.offset, self.pending = 0, b''
            with self.path.open('rb') as stream:
                stream.seek(self.offset)
                chunk = stream.read(65536)
                self.offset = stream.tell()
        except FileNotFoundError:
            return []
        lines = (self.pending + chunk).split(b'\n')
        self.pending = lines.pop()
        if len(self.pending) > 65536:
            self.pending = b''
        result = []
        for line in lines:
            try:
                result.append(json.loads(line))
            except (ValueError, UnicodeError):
                pass
        return result
