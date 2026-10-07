# Reproducible onedir layout; both launchers share the same read-only resources.
from pathlib import Path
import sys
root = Path(SPEC).resolve().parent.parent
sys.path.insert(0, str(root/'packaging'))
from release_files import resources
from PyInstaller.utils.hooks.tcl_tk import tcltk_info

datas = [(str(p),str(p.relative_to(root).parent)) for p in resources(root)]
datas += [(str(root/p),'.') for p in ['LICENSE','ASSETS.md','THIRD_PARTY_NOTICES.md']]
if not tcltk_info.available or not tcltk_info.data_files:
    raise RuntimeError('A working Python installation with Tcl/Tk is required')
# Explicitly include GUI data/plugins as well as relying on automatic hooks;
# some embedded Python distributions omit their normal hook discovery paths.
datas += [(source,str(Path(target).parent)) for target,source,kind in tcltk_info.data_files]
gui = Analysis([str(root/'desktop_app.py')], pathex=[str(root)], datas=datas,
               hiddenimports=['PIL.PngImagePlugin','PIL.IcoImagePlugin'],
               excludes=['numpy','pytest','IPython','matplotlib'], noarchive=False)
console = Analysis([str(root/'cli.py')], pathex=[str(root)], datas=[],
                   excludes=['numpy','pytest','IPython','matplotlib'], noarchive=False)
gui_exe = EXE(PYZ(gui.pure), gui.scripts, [], exclude_binaries=True, name='WangBun',
              console=False, debug=False, strip=False, upx=False)
cli_exe = EXE(PYZ(console.pure), console.scripts, [], exclude_binaries=True, name='WangBun-cli',
              console=True, debug=False, strip=False, upx=False)
bundle = COLLECT(gui_exe, cli_exe, gui.binaries, gui.datas, console.binaries, console.datas,
                 name='WangBun', strip=False, upx=False)
