#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
[Setup]
AppId={{C074DA51-C0E3-41B3-A3D2-33D12715BD09}
AppName=望包桌宠
AppVersion={#AppVersion}
AppPublisher=Wang Bun contributors
DefaultDirName={localappdata}\Programs\WangBun
DefaultGroupName=望包桌宠
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=WangBun-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\WangBun.exe
CloseApplications=yes
RestartApplications=no
LicenseFile=..\LICENSE
InfoBeforeFile=..\ASSETS.md

[Tasks]
Name: desktopicon; Description: "创建桌面快捷方式"; Flags: unchecked

[Files]
Source: "..\dist\WangBun\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\望包桌宠"; Filename: "{app}\WangBun.exe"
Name: "{group}\卸载望包桌宠"; Filename: "{uninstallexe}"
Name: "{autodesktop}\望包桌宠"; Filename: "{app}\WangBun.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WangBun.exe"; Description: "启动望包桌宠"; Flags: nowait postinstall skipifsilent
; User state in {localappdata}\WangBun intentionally survives uninstall.
