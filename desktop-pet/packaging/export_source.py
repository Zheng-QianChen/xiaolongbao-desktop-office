"""Export a reviewable public source tree without copying the parent workspace."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from release_files import source_files

ROOT = Path(__file__).resolve().parent.parent


def export(destination):
    destination=Path(destination).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Use a new empty export directory; existing work is never replaced')
    destination.mkdir(parents=True,exist_ok=True)
    files=source_files(ROOT)
    report=[]
    for source in files:
        relative=source.relative_to(ROOT)
        if set(relative.parts)&{'runtime','history','sources','.build-venv','build-tools'}:
            raise ValueError('Private/build path in publication manifest')
        target=destination/'desktop-pet'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if relative.as_posix()=='layered-poc/spatial-rig-v7.json':
            content=json.loads(source.read_text(encoding='utf-8'))
            content.pop('source',None)
            target.write_text(json.dumps(content,separators=(',',':')),encoding='utf-8')
        else: shutil.copy2(source,target)
        report.append({'path':target.relative_to(destination).as_posix(),
                       'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    shutil.copy2(ROOT/'packaging/README.public.md',destination/'README.md')
    shutil.copy2(ROOT/'LICENSE',destination/'LICENSE')
    (destination/'.gitignore').write_text('__pycache__/\n.venv/\n**/runtime/\n**/build/\n**/dist/\n**/release/\n**/.build-venv/\n**/build-tools/\n*.log\n*.sqlite*\n.env*\n',encoding='utf-8')
    workflows=destination/'.github/workflows'
    workflows.mkdir(parents=True)
    shutil.copy2(ROOT/'packaging/ci.yml',workflows/'windows.yml')
    # Audit is private build output, never part of the public source snapshot.
    report_path=ROOT/'release/source-manifest.json'
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'directory':str(destination),'files':len(report),'bytes':sum(p.stat().st_size for p in destination.rglob('*') if p.is_file())}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    export(parser.parse_args().destination)
