"""Fast local hook receiver and generic notification CLI; standard library only."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import uuid
from bridge_adapters import hook_event
from bridge_store import clean_event, make_event, KINDS

ROOT = Path(__file__).resolve().parent
from app_paths import runtime_dir


def enqueue(event, runtime):
    event = clean_event(event)
    inbox = Path(runtime) / 'inbox'
    inbox.mkdir(parents=True, exist_ok=True)
    # Time order survives a stopped bridge; independent temp files are safe across processes.
    name = '{:020d}-{}.json'.format(time.time_ns(), uuid.uuid4().hex)
    target = inbox / name
    temporary = target.with_suffix('.tmp')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(event, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=runtime_dir()/'bridge')
    sub = parser.add_subparsers(dest='command', required=True)
    hook = sub.add_parser('hook')
    hook.add_argument('source', choices=['codex', 'cursor', 'claude', 'zcode'])
    hook.add_argument('payload', nargs='?', help='legacy Codex notify JSON argv')
    send = sub.add_parser('send')
    send.add_argument('--source', default='local')
    send.add_argument('--thread', required=True)
    send.add_argument('--kind', choices=sorted(KINDS), required=True)
    send.add_argument('--run')
    send.add_argument('--agent')
    send.add_argument('--label')
    send.add_argument('--summary')
    send.add_argument('--request')
    send.add_argument('--sequence', type=int)
    send.add_argument('--event-id')
    args = parser.parse_args()
    if args.command == 'hook':
        payload = None
        try:
            raw = args.payload if args.payload is not None else sys.stdin.buffer.read(1024*1024+1).decode('utf-8')
            if len(raw.encode('utf-8')) > 1024*1024:
                raise ValueError('hook input too large')
            payload = json.loads(raw)
            event = hook_event(args.source, payload)
            if event:
                enqueue(event, args.runtime)
        except (OSError, ValueError, UnicodeError):
            print('Desktop pet notification unavailable; agent behavior unchanged.', file=sys.stderr)
        # No approval decisions, followups, or messages are injected by this observer.
        if args.source == 'cursor' and isinstance(payload, dict) and payload.get('hook_event_name') == 'beforeSubmitPrompt':
            print('{"continue":true}')
        else:
            print('{}')
        return
    fields = {key: value for key, value in {
        'run_id': args.run, 'agent_id': args.agent, 'label': args.label,
        'summary': args.summary, 'request_id': args.request, 'sequence': args.sequence}.items() if value is not None}
    event = make_event(args.source, args.thread, args.kind, **fields)
    if args.event_id:
        event['event_id'] = args.event_id
    enqueue(event, args.runtime)
    print(json.dumps({'queued': True, 'event_id': event['event_id']}))


if __name__ == '__main__':
    main()
