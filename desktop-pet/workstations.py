"""Per-agent animation clocks, independent of the GUI and event transport."""
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import random
from events import normalize

CLOSING_DURATION = 1.8
EASTER_EGG_CHANCE = .05


@dataclass
class Worker:
    key: str
    thread_id: str
    label: str
    state: str = 'idle'
    phase: str = 'rest'
    phase_at: float = 0
    has_computer: bool = False
    next_break: float = 0
    rng: random.Random = field(default_factory=random.Random)
    sequence: int = -1
    completed: bool = False
    unread: bool = False
    summary: str = ''
    at_desk: bool = True
    slot: int = 0
    easter_egg: bool = False

    def set_state(self, state, now):
        if state == self.state:
            return
        previous_phase = self.phase
        self.state = state
        self.completed = state == 'completed'
        if self.completed:
            self.unread = True
        self.phase_at = now
        if self.completed:
            self.easter_egg = self.rng.random() < EASTER_EGG_CHANCE
            if self.at_desk and self.has_computer:
                self.phase = 'closing'
            else:
                self.at_desk = False
                self.phase = 'departing'
        elif not self.at_desk:
            self.phase = 'returning'
        elif state == 'running':
            self.phase = ('open' if previous_phase == 'closing' else 'typing') if self.has_computer else 'drop'
            self.next_break = now+self.rng.uniform(4, 8)
        else:
            # Never leave a half-open laptop frozen after an interrupted entrance.
            self.phase = 'rest'

    def update(self, now):
        if self.phase == 'closing' and self.completed:
            if now-self.phase_at >= CLOSING_DURATION:
                self.phase_at += CLOSING_DURATION
                self.at_desk = False
                self.phase = 'departing'
            return
        if self.state != 'running':
            return
        durations = {'drop': .85, 'open': .65, 'glasses': .75, 'blink': .5, 'drink': 2.4}
        while self.phase in durations and now-self.phase_at >= durations[self.phase]:
            self.phase_at += durations[self.phase]
            self.phase = {'drop': 'open', 'open': 'glasses', 'glasses': 'typing',
                          'blink': 'typing', 'drink': 'typing'}[self.phase]
            if self.phase == 'open':
                self.has_computer = True
            if self.phase == 'typing':
                self.has_computer = True
                self.next_break = self.phase_at+self.rng.uniform(4, 8)
        if self.phase == 'typing' and now >= self.next_break:
            self.phase = self.rng.choices(['blink', 'drink'], weights=[3, 2])[0]
            self.phase_at = now

    def arrive(self, now):
        """Called by motion, including for workers on hidden pages."""
        if self.phase == 'departing':
            self.phase = 'following'
            self.phase_at = now
        elif self.phase == 'returning':
            self.at_desk = True
            self.phase_at = now
            self.phase = ('open' if self.has_computer else 'drop') if self.state == 'running' else 'rest'


class Workers:
    def __init__(self):
        self.items = {}
        self.next_slot = 0

    def ingest(self, event, now):
        if not isinstance(event, dict):
            return False
        params = event.get('params') or {}
        if not isinstance(params, dict):
            return False
        thread = event.get('thread_id') or params.get('threadId')
        explicit = event.get('agent_id') or params.get('agentId')
        key = explicit or thread
        if not isinstance(key, str) or not key or len(key) > 256:
            return False
        if event.get('method') == 'agent/removed':
            return self.items.pop(key, None) is not None
        is_read = event.get('method') == 'agent/read'
        state = normalize(event, thread)
        if is_read and key in self.items:
            worker = self.items[key]
            sequence = event.get('sequence')
            if isinstance(sequence, int):
                if sequence <= worker.sequence:
                    return False
                worker.sequence = sequence
            worker.unread = False
            return True
        if state is None or not isinstance(thread, str) or not thread:
            return False
        # An explicit id arriving later adopts its thread-only placeholder.
        if key not in self.items and explicit and thread in self.items:
            worker = self.items[thread]
            if worker.key == worker.thread_id:
                self.items = {(key if k == thread else k): v for k, v in self.items.items()}
                worker.key = key
        if key not in self.items:
            seed = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big')
            label = event.get('label')
            label = label[:40] if isinstance(label, str) else key[:12]
            self.items[key] = Worker(key, thread, label, rng=random.Random(seed), slot=self.next_slot)
            self.next_slot += 1
        worker = self.items[key]
        if isinstance(event.get('label'),str):worker.label=event['label'][:60]
        sequence = event.get('sequence')
        if isinstance(sequence, int):
            if sequence <= worker.sequence:
                return False
            worker.sequence = sequence
        worker.set_state(state, now)
        if isinstance(event.get('summary'),str):
            worker.summary=' '.join(event['summary'].split())[:160]
        if isinstance(event.get('unread'), bool):
            worker.unread = event['unread']
        elif event.get('read') is True:
            worker.unread = False
        return True

    @property
    def unread_count(self):
        return sum(worker.unread for worker in self.items.values())

    @property
    def overall_state(self):
        states = {worker.state for worker in self.items.values()}
        for state in ['waiting', 'failed']:
            if state in states:
                return state
        if self.unread_count:
            return 'unread'
        for state in ['failed', 'waiting', 'running', 'review', 'disconnected']:
            if state in states:
                return state
        return 'idle'

    def update(self, now):
        for worker in self.items.values():
            worker.update(now)

    def save(self, path):
        """Persist only pet status metadata, never transcript contents."""
        fields=['key','thread_id','label','state','completed','unread','has_computer','sequence','summary',
                'at_desk','slot','phase','easter_egg']
        data=[{name:getattr(worker,name) for name in fields} for worker in self.items.values()]
        path=Path(path)
        temporary=path.with_suffix(path.suffix+'.tmp')
        temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        temporary.replace(path)

    def restore(self, path, now):
        try:
            data=json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError,ValueError):
            return
        if not isinstance(data,list):return
        for entry in data:
            if not isinstance(entry,dict):continue
            event={**entry,'agent_id':entry.get('key')}
            if event.get('sequence') == -1:event.pop('sequence')
            self.ingest(event,now)
            worker=self.items.get(entry.get('key'))
            if worker:
                worker.has_computer=entry.get('has_computer') is True
                worker.at_desk=entry.get('at_desk',not worker.completed) is True
                slot=entry.get('slot')
                if isinstance(slot,int) and 0<=slot<10000:worker.slot=slot
                self.next_slot=max(self.next_slot,worker.slot+1)
                worker.easter_egg=entry.get('easter_egg') is True
                if worker.completed:
                    if worker.at_desk and worker.has_computer and entry.get('phase')=='closing':
                        worker.phase='closing'
                    else:
                        worker.at_desk=False
                        worker.phase='following'
                elif not worker.at_desk:worker.phase='returning'
                elif worker.state=='running':worker.phase='typing' if worker.has_computer else 'drop'
                else:worker.phase='rest'
                worker.phase_at=now
                worker.next_break=now+worker.rng.uniform(4,8)
