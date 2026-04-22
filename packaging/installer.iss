; Inno Setup script for ACB Tool
;
; Mirrors the XWB Tool installer conventions (compression, privilege level,
; {autopf} install dir, Start menu group + optional desktop icon, post-install
; launch). Version number is supplied on the command line from the PowerShell
; build script (packaging\build_installer.ps1) which reads the single source
; of truth at core\version.py, so the installer's AppVersion and the running
; tool's About dialog can never drift.

#define MyAppName "ACB Tool"
#ifndef AcbVersion
  #define AcbVersion "0.0.0-dev"
#endif
#ifndef AcbPublisher
  #define AcbPublisher "unknown"
#endif
#define MyAppPublisher AcbPublisher
#define MyAppExeName "ACB Tool.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#AcbVersion}
AppVerName={#MyAppName} {#AcbVersion}
AppPublisher={#MyAppPublisher}
VersionInfoVersion={#AcbVersion}
VersionInfoProductVersion={#AcbVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#AcbVersion}
OutputDir=dist
OutputBaseFilename=ACB_Tool_Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
LicenseFile=LICENSE.txt

[Files]
Source: "dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\LICENSE";          DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";            Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}";  Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";      Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
