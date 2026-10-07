"""Install nonblocking metadata observer hooks, preserving unrelated configuration."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time
from app_paths import cli_command, runtime_dir

ROOT = Path(__file__).resolve().parent
EVENTS = {
    'cursor': ['beforeSubmitPrompt', 'stop', 'sessionEnd'],
    'codex': ['UserPromptSubmit', 'PermissionRequest', 'PostToolUse', 'Stop', 'Interrupt', 'SessionEnd'],
    'claude': ['UserPromptSubmit', 'PermissionRequest', 'PostToolUse', 'Stop', 'StopFailure', 'SessionEnd'],
    'zcode': ['UserPromptSubmit', 'PermissionRequest', 'PostToolUse', 'Stop'],
}


def definition(source, executable=None):
    command_args = ([executable, str(ROOT/'notify.py')] if executable else cli_command('notify'))
    command_args += ['--runtime', str((runtime_dir()/'bridge').resolve()), 'hook', source]
    command = (' '.join('"'+p.replace('\\','/')+'"' for p in command_args)
               if os.name == 'nt' else ' '.join(shlex.quote(p) for p in command_args))
    hooks = {}
    for event in EVENTS[source]:
        command_hook = {'command': command, 'timeout': 3}
        if source=='zcode':
            hooks[event]=[{'hooks':[{'type':'process','command':command_args[0],
                'args':command_args[1:],'enabled':True,'timeoutMs':3000}]}]
        elif source == 'cursor':
            hooks[event] = [dict(command_hook, failClosed=False)]
        else:
            hooks[event] = [{'hooks': [dict(command_hook, type='command')]}]
    if source=='zcode':return {'hooks':{'enabled':True,'events':hooks}}
    return dict(version=1, hooks=hooks) if source == 'cursor' else {'hooks': hooks}


def merge(existing, added):
    result = json.loads(json.dumps(existing))
    if not isinstance(result, dict) or not isinstance(result.get('hooks', {}), dict):
        raise ValueError('existing hooks config must be an object')
    hooks = result.setdefault('hooks', {})
    additions=added['hooks']
    if 'events' in additions:
        hooks['enabled']=True
        hooks=hooks.setdefault('events',{})
        additions=additions['events']
    if 'version' in added:
        result.setdefault('version', added['version'])
    for event, entries in additions.items():
        current = hooks.setdefault(event, [])
        if not isinstance(current, list):
            raise ValueError('existing event hooks must be an array')
        for entry in entries:
            if entry not in current:
                current.append(entry)
    return result


def install(project, source, user=False):
    if source=='zcode' and not user:raise ValueError('ZCode only executes user-level or plugin hooks; use --user')
    relative = {'codex': '.codex/hooks.json', 'cursor': '.cursor/hooks.json',
                'claude': '.claude/settings.json' if user else '.claude/settings.local.json',
                'zcode':'.zcode/cli/config.json'}[source]
    target = Path(project).resolve()/relative
    existing = json.loads(target.read_text(encoding='utf-8-sig')) if target.exists() else {}
    merged = merge(existing, definition(source))
    if existing == merged:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, target.with_name(target.name + '.pet-backup-' + str(time.time_ns())))
    tmp = target.with_suffix('.pet-tmp')
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    tmp.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    scope=parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--project', type=Path)
    scope.add_argument('--user', action='store_true')
    parser.add_argument('--source', choices=sorted(EVENTS), required=True)
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    if args.preview:
        print(json.dumps(definition(args.source), ensure_ascii=False, indent=2))
    else:
        print(install(Path.home() if args.user else args.project, args.source,args.user))


if __name__ == '__main__': main()
