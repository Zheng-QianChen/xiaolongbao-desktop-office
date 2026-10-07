"""Start the local bridge hidden, reusing a healthy instance; optionally open the native pet."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parent


def healthy(port):
    try:
        req = urllib.request.Request('http://127.0.0.1:{}/health'.format(port))
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=.5) as response:
            return json.load(response).get('service') == 'wang-bun-bridge'
    except (OSError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--desktop', action='store_true')
    args = parser.parse_args()
    runtime = ROOT/'runtime'
    runtime.mkdir(exist_ok=True)
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
    if not healthy(args.port):
        with (runtime/'bridge-stdout.log').open('ab') as out, (runtime/'bridge-stderr.log').open('ab') as err:
            process = subprocess.Popen([sys.executable, str(ROOT/'bridge.py'), '--port', str(args.port)],
                cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=out, stderr=err, creationflags=flags,
                start_new_session=sys.platform != 'win32')
        for _ in range(30):
            if healthy(args.port):
                break
            if process.poll() is not None:
                raise SystemExit('Bridge startup failed. See desktop-pet/runtime/bridge-stderr.log')
            time.sleep(.2)
        else:
            raise SystemExit('Bridge not ready. See desktop-pet/runtime/bridge-stderr.log')
    if args.desktop:
        with (runtime/'bridge-pet.log').open('ab') as output:
            subprocess.Popen([sys.executable, str(ROOT/'family.py'), '--bridge'], cwd=str(ROOT),
                stdin=subprocess.DEVNULL, stdout=output, stderr=output, creationflags=flags)
    print('http://127.0.0.1:{}'.format(args.port))


if __name__ == '__main__':
    main()
