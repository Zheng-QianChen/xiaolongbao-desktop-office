"""Wrap an explicitly supplied local command with pet start/completion/failure events."""
import argparse
from pathlib import Path
import subprocess
import sys
import uuid
from bridge_store import make_event
from notify import enqueue
from app_paths import runtime_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=runtime_dir()/'bridge')
    parser.add_argument('--thread', required=True, help='Stable local job or project identifier')
    parser.add_argument('--label', default='本地任务')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('provide a command after --')
    run = uuid.uuid4().hex
    def emit(kind, summary):
        fields = {'heartbeat_timeout': 15} if kind == 'started' else {}
        enqueue(make_event('local', args.thread, kind, run_id=run, label=args.label, summary=summary, **fields), args.runtime)
    emit('started', args.label+'正在运行')
    try:
        # No shell interpretation; the command comes from this CLI invocation, never HTTP.
        child = subprocess.Popen(command)
        while True:
            try:
                result = child.wait(timeout=5)
                break
            except subprocess.TimeoutExpired:
                emit('heartbeat', args.label+'正在运行')
    except KeyboardInterrupt:
        if 'child' in locals() and child.poll() is None:
            child.terminate()
            child.wait()
        emit('cancelled', args.label+'已取消')
        return 130
    except OSError:
        emit('failed', args.label+'未能启动')
        return 1
    emit('completed' if result == 0 else 'failed', args.label+('已完成' if result == 0 else '失败（退出码 {}）'.format(result)))
    return result


if __name__ == '__main__':
    sys.exit(main())
