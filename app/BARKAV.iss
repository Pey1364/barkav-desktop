; Inno Setup script for BARKAV 19.1.1.
;
; Installs the exact same layout build_portable.py produces (app/ holding
; the PyInstaller onedir output, with secrets.local.json/data/.brk files at
; the install root next to it) - see build_portable.py's own docstring for
; why that nesting matters. Per-user install (no admin, HKCU only) since
; this is a single operator's own tool, not shared machine software.
;
; Build with: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" BARKAV.iss
; (run build_portable.py first - this script packages its dist\BARKAV_Portable\ output)

#define MyAppName "Barkav"
#define MyAppVersion "19.1.1"
#define MyAppExeName "BARKAV.exe"
#define MyPortableDir "dist\BARKAV_Portable"

[Setup]
AppId={{B4RK4V-1872-ENGINEERING-CONSTRUCTION-PEYMAAN}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist\installer
OutputBaseFilename=BARKAV_{#MyAppVersion}_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=assets\BARKAV.ico
WizardImageFile=assets\installer_banner.bmp
WizardSmallImageFile=assets\installer_small.bmp
UninstallDisplayIcon={app}\app\assets\BARKAV.ico
; Data (secrets.local.json, data\, runtime\, .brk files) lives at {app}, next
; to app\ - never touched by the uninstaller so a re-install/upgrade keeps it.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#MyPortableDir}\app\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#MyPortableDir}\README.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyPortableDir}\secrets.local.example.json"; DestDir: "{app}"; Flags: ignoreversion
; The real secrets.local.json is NEVER part of the installer - same as the
; portable package, the operator copies the example and fills it in
; themselves after install (see README.txt).

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExeName}"; WorkingDir: "{app}\app"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; {commondesktop} (all-users Desktop) needs admin - this install is
; PrivilegesRequired=lowest, so it must be {userdesktop} (this user's own
; Desktop) instead, or icon creation fails with IPersistFile::Save /
; Access is denied mid-install.
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExeName}"; WorkingDir: "{app}\app"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Registry]
; .brk file association, current-user only (HKCU\Software\Classes) - no
; admin needed, mirrors REGISTER_BARKAV_FILE_ICON.ps1's own registry shape.
Root: HKCU; Subkey: "Software\Classes\.brk"; ValueType: string; ValueName: ""; ValueData: "BARKAVProjectFile"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\BARKAVProjectFile"; ValueType: string; ValueName: ""; ValueData: "BARKAV Project Shortcut"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\BARKAVProjectFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\app\assets\BARKAV.ico"
Root: HKCU; Subkey: "Software\Classes\BARKAVProjectFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\app\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\app\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Uninstall only removes app\ (the program itself) - {app}'s own root
; (secrets.local.json, data\, runtime\, every project's .brk) is left
; alone, same principle as build_portable.py's README already states.
Type: filesandordirs; Name: "{app}\app"
