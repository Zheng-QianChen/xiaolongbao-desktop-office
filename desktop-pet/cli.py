"""Console companion: clean stdio for MCP and explicit integration commands."""
import sys


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ('-h', '--help'):
        print('WangBun-cli: mcp | notify | publish | setup-hooks | run-job | --version')
        return 0
    command = sys.argv.pop(1)
    if command == '--version':
        from app_paths import VERSION
        print(VERSION)
        return 0
    if command == 'mcp':
        from pet_mcp import main as run
    elif command == 'notify':
        from notify import main as run
    elif command == 'publish':
        from publish_notification import main as run
    elif command == 'setup-hooks':
        from setup_hooks import main as run
    elif command == 'run-job':
        from run_job import main as run
    else:
        print('Unknown command: '+command, file=sys.stderr)
        return 2
    return run() or 0


if __name__ == '__main__': sys.exit(main())
