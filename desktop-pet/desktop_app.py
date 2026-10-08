"""Windowed distribution entry point. One pet and bridge per data directory."""
import argparse
import contextlib
import os
from pathlib import Path
import sys
import traceback


class InstanceLock:
    """OS-owned lock; a crashed process cannot leave a stale active instance."""
    def __init__(self, path):
        self.file = Path(path).open('a+b')
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b'0'); self.file.flush()
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise

    def close(self):
        self.file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--no-discovery', action='store_true')
    parser.add_argument('--smoke-test', action='store_true')
    args = parser.parse_args()
    if args.data_dir:
        os.environ['WANG_BUN_DATA_DIR'] = str(args.data_dir.resolve())
    from app_paths import APP_NAME, runtime_dir
    runtime = runtime_dir()
    runtime.mkdir(parents=True, exist_ok=True)
    try:
        instance = InstanceLock(runtime/'desktop.lock')
    except OSError:
        # Double-clicking the shortcut must not spawn another house/service.
        return 0
    result = 0
    with (runtime/'desktop.log').open('a', encoding='utf-8', buffering=1) as log:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            service = None
            try:
                from bridge import BridgeService
                try:
                    service = BridgeService(runtime/'bridge', args.port, not args.no_discovery)
                except OSError as error:
                    if error.errno not in (98, 10048): raise
                    service = BridgeService(runtime/'bridge', 0, not args.no_discovery)
                if args.smoke_test:
                    from bridge_store import make_event
                    service.store.ingest(make_event('local','package-fixture','started',label='打包验证'))
                import family
                sys.argv = [sys.argv[0], '--bridge', '--bridge-runtime', str(runtime/'bridge')]
                if args.smoke_test: sys.argv.append('--smoke-test')
                family.main()
            except BaseException as error:
                if isinstance(error, SystemExit): result = error.code or 0
                else:
                    result = 1
                    traceback.print_exc()
                if result and not args.smoke_test:
                    import tkinter as tk
                    from tkinter import messagebox
                    root = tk.Tk(); root.withdraw()
                    messagebox.showerror(APP_NAME+' · 启动失败', '请查看本地日志：\n'+str(runtime/'desktop.log'))
                    root.destroy()
            finally:
                if service: service.close()
                instance.close()
    return result


if __name__ == '__main__': sys.exit(main())
