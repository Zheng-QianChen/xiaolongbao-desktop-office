"""Build an offline Windows app and optional per-user installer."""
import argparse
import hashlib
import importlib.metadata
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app_paths import APP_NAME, VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--iscc', type=Path, help='Optional Inno Setup compiler')
    args = parser.parse_args()
    subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean',
        '--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'build'),
        str(ROOT/'packaging/wangbun.spec')], check=True, cwd=ROOT)
    bundle = ROOT/'dist/WangBun'
    for name in ('LICENSE','ASSETS.md','THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name, bundle/name)
    readme=(ROOT/'packaging/README.public.md').read_text(encoding='utf-8')
    for name in ('LICENSE','ASSETS.md','THIRD_PARTY_NOTICES.md'):
        readme=readme.replace('(desktop-pet/'+name+')','('+name+')')
    (bundle/'README.md').write_text(readme,encoding='utf-8')
    # Ship upstream notices alongside the redistributed interpreter/libraries.
    licenses=bundle/'licenses';licenses.mkdir(exist_ok=True)
    for source in (ROOT/'packaging/licenses').glob('*.txt'):
        shutil.copy2(source,licenses/source.name)
    for package in ('Pillow','pyinstaller'):
        distribution=importlib.metadata.distribution(package)
        for entry in distribution.files or []:
            if 'license' in str(entry).lower() or entry.name in ('COPYING.txt','COPYING'):
                source=Path(distribution.locate_file(entry))
                if source.is_file(): shutil.copy2(source,licenses/(package+'-'+source.name))
    for source in [Path(sys.base_prefix)/'LICENSE.txt',Path(sys.base_prefix)/'tcl/tcl8.6/license.terms',
                   Path(sys.base_prefix)/'tcl/tk8.6/license.terms']:
        if source.is_file(): shutil.copy2(source,licenses/(source.parent.name+'-'+source.name))
    release = ROOT/'release'
    release.mkdir(exist_ok=True)
    archive = release/f'{APP_NAME}-{VERSION}-windows-x64-portable.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as zipped:
        for path in sorted(bundle.rglob('*')):
            if path.is_file(): zipped.write(path,path.relative_to(bundle.parent))
    if args.iscc:
        subprocess.run([str(args.iscc),'/DAppVersion='+VERSION,str(ROOT/'packaging/installer.iss')],check=True)
    artifacts = [archive]
    if args.iscc: artifacts.append(release/f'{APP_NAME}-{VERSION}-windows-x64-setup.exe')
    (release/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in artifacts))
    print('RELEASE_READY '+str(release))


if __name__ == '__main__': main()
