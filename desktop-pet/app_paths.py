"""Read-only application resources and per-user writable state."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
APP_NAME = '小笼包桌面事务所'
PACKAGE_NAME = 'Xiaolongbao-Desktop-Office'
VERSION = '0.1.1'


def data_root():
    override = os.environ.get('WANG_BUN_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, 'frozen', False):
        local = os.environ.get('LOCALAPPDATA')
        return (Path(local) if local else Path.home()/'AppData/Local')/'WangBun'
    return ROOT


def runtime_dir():
    return data_root()/'runtime'


def cli_command(module):
    commands = {'pet_mcp':'mcp', 'notify':'notify', 'publish_notification':'publish',
                'setup_hooks':'setup-hooks', 'run_job':'run-job'}
    if getattr(sys, 'frozen', False):
        return [str(Path(sys.executable).with_name('WangBun-cli.exe')), commands[module]]
    return [sys.executable, str(ROOT/(module+'.py'))]


def mcp_config(runtime):
    command = cli_command('pet_mcp')
    return {'command':command[0], 'args':command[1:]+['--runtime', str(Path(runtime).resolve())]}
