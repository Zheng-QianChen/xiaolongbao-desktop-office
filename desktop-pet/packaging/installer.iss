#ifndef AppVersion
  #define AppVersion "0.1.1"
#endif
[Setup]
AppId={{C074DA51-C0E3-41B3-A3D2-33D12715BD09}
AppName=小笼包桌面事务所
AppVersion={#AppVersion}
AppPublisher=Wang Bun contributors
DefaultDirName={localappdata}\Programs\WangBun
DefaultGroupName=小笼包桌面事务所
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=小笼包桌面事务所-{#AppVersion}-windows-x64-setup
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
Name: "{group}\小笼包桌面事务所"; Filename: "{app}\WangBun.exe"
Name: "{group}\卸载小笼包桌面事务所"; Filename: "{uninstallexe}"
Name: "{autodesktop}\小笼包桌面事务所"; Filename: "{app}\WangBun.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\WangBun.exe"; Description: "启动小笼包桌面事务所"; Flags: nowait postinstall skipifsilent
; User state in {localappdata}\WangBun intentionally survives uninstall.
