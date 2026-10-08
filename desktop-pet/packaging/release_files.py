"""Explicit publication manifest: no runtime, art history or personal config."""
import json
from pathlib import Path

MODULES = '''app_paths asset_config desktop_app cli bounce bridge bridge_adapters bridge_client
bridge_store codex_clones codex_connections codex_read_state events extension_hub extension_io
family gui_observers cursor_navigation launch_bridge motion native_connections native_labels native_scene
native_settings native_zoom notify pet_mcp presentation_layout provider_links publish_notification
rendering run_job setup_hooks subscription_readers travel workstations'''.split()
TESTS = '''bridge codex_clones codex_connections events extensions family lifecycle native_scene
presentation_layout rendering travel workstations packaging cursor_navigation'''.split()
ART_JS = ['renderer.js','geometry.js','layer-turn.js','motions.js']


def resources(root):
    root = Path(root)
    paths = list((root/'assets/animation-frames-v9').glob('*.png'))
    paths += list((root/'assets/animation-frames-v10').glob('*/*.png'))
    paths += [root/'assets/closed-laptop-v2.png']
    paths += [p for p in (root/'bridge-ui').iterdir() if p.suffix in ('.js','.html','.css')]
    paths += [root/'layered-poc'/p for p in ART_JS+['rig.json','spatial-rig-v7.json']]
    rig = json.loads((root/'layered-poc/rig.json').read_text(encoding='utf-8'))
    for layer in rig['layers']:
        path = root/'layered-poc'/layer['file']
        if not path.resolve().is_relative_to((root/'layered-poc/layers').resolve()):
            raise ValueError('Rig layer outside the published layers directory')
        paths.append(path)
    for path in paths:
        if not path.is_file(): raise FileNotFoundError(path)
    return sorted(set(paths))


def source_files(root):
    root = Path(root)
    paths = resources(root)
    paths += [root/(name+'.py') for name in MODULES]
    paths += [root/('test_'+name+'.py') for name in TESTS]
    paths += [root/p for p in ['requirements.txt','requirements-build.txt','.gitignore',
                               'LICENSE','ASSETS.md','THIRD_PARTY_NOTICES.md','test_provider_plugins.cjs']]
    paths += [root/'packaging'/p for p in ['release_files.py','export_source.py','build_windows.py',
              'wangbun.spec','installer.iss','README.public.md','release-notes.md','ci.yml','verify_package.py']]
    paths += list((root/'packaging/licenses').glob('*.txt'))
    paths += [root/'integrations'/p for p in ['cursor/package.json','cursor/extension.cjs',
                    'cursor/build_vsix.py','dsh/wang-bun.mjs']]
    return sorted(set(paths))
