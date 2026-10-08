# Reproducible onedir layout; both launchers share the same read-only resources.
from pathlib import Path
import sys
root = Path(SPEC).resolve().parent.parent
sys.path.insert(0, str(root/'packaging'))
sys.path.insert(0, str(root))
from app_paths import APP_NAME, VERSION
from release_files import resources
from PyInstaller.utils.hooks.tcl_tk import tcltk_info
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct

def version_info(filename):
    version = tuple(map(int, VERSION.split('.'))) + (0,)
    return VSVersionInfo(ffi=FixedFileInfo(filevers=version, prodvers=version, mask=0x3f,
        flags=0, OS=0x40004, fileType=1, subtype=0, date=(0,0)), kids=[
        StringFileInfo([StringTable('040904B0',[
            StringStruct('ProductName',APP_NAME),StringStruct('FileDescription',APP_NAME),
            StringStruct('FileVersion',VERSION),StringStruct('ProductVersion',VERSION),
            StringStruct('OriginalFilename',filename)])]),
        VarFileInfo([VarStruct('Translation',[1033,1200])])])

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
              console=False, debug=False, strip=False, upx=False, version=version_info('WangBun.exe'))
cli_exe = EXE(PYZ(console.pure), console.scripts, [], exclude_binaries=True, name='WangBun-cli',
              console=True, debug=False, strip=False, upx=False, version=version_info('WangBun-cli.exe'))
bundle = COLLECT(gui_exe, cli_exe, gui.binaries, gui.datas, console.binaries, console.datas,
                 name='WangBun', strip=False, upx=False)
