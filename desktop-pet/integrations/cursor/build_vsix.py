"""Package the tiny local URI handler without fetching build dependencies."""
from pathlib import Path
import zipfile
import json
ROOT=Path(__file__).resolve().parent
version=json.loads((ROOT/'package.json').read_text(encoding='utf-8'))['version']
target=ROOT/('wang-bun-local-monitor-'+version+'.vsix')
manifest='''<?xml version="1.0" encoding="utf-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011"><Metadata>
<Identity Language="en-US" Id="local-monitor" Version="0.1.0" Publisher="wang-bun"/>
<DisplayName>望包 Cursor 会话跳转</DisplayName><Description xml:space="preserve">Local conversation navigation.</Description>
<Categories>Other</Categories><GalleryFlags>Public</GalleryFlags><Properties>
<Property Id="Microsoft.VisualStudio.Code.Engine" Value="^1.90.0"/>
<Property Id="Microsoft.VisualStudio.Code.ExtensionKind" Value="ui"/>
</Properties></Metadata><Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
<Dependencies/><Assets><Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/></Assets></PackageManifest>'''
with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('extension.vsixmanifest',manifest.replace('Version="0.1.0"','Version="'+version+'"'))
    archive.writestr('[Content_Types].xml','''<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="cjs" ContentType="application/javascript"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>''')
    for name in ('package.json','extension.cjs'):archive.write(ROOT/name,'extension/'+name)
print(target)
