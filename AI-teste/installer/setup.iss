; setup.iss — Inno Setup 6 script for XcosGen
; Build via Inno Setup Compiler: iscc installer\setup.iss
; (Run from project root after PyInstaller has produced dist\XcosGen\)

#define AppName      "XcosGen"
#define AppVersion   "1.0.0"
#define AppPublisher "XcosGen"
#define AppURL       "https://github.com/xcosgen"
#define AppExeName   "XcosGen.exe"
#define DistDir      "..\dist\XcosGen"

[Setup]
; Unique AppId — regenerate this GUID for your release
AppId={{A3B7C2D1-E4F5-4A6B-8C9D-0EA1B2C3D4E5}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; OutputDir is relative to the .iss file location (installer/)
OutputDir=..\dist\installer
OutputBaseFilename=XcosGen-{#AppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
PrivilegesRequired=lowest       ; install per-user; change to admin for system-wide
UninstallDisplayIcon={app}\{#AppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Bundle entire PyInstaller output folder
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}";  Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove the user config directory on uninstall (optional — comment out to preserve settings)
; Type: filesandordirs; Name: "{localappdata}\XcosGen\XcosGen"
