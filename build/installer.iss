; Inno Setup script for scan2bim.
;
; Compiled by `scripts/build_installer.ps1` after PyInstaller has produced
; `dist/scan2bim.exe`. Paths and version come through /D defines so the
; .iss hardcodes no absolute path.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\scan2bim"
#endif
#ifndef LicensesFile
  #define LicensesFile "..\dist\LICENSES.md"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef AppNumericVersion
  #define AppNumericVersion "0.0.0.0"
#endif

[Setup]
; Stable AppId — required for upgrade/uninstall identity. Do not change.
AppId={{B7B0F2A1-9D3C-4E8A-9C1F-2E6A4D7F0C55}
AppName=scan2bim
AppVersion={#AppVersion}
AppVerName=scan2bim {#AppVersion}
AppPublisher=Lauri Rekola
AppPublisherURL=https://github.com/Mcrauli/scan2bim
AppSupportURL=https://github.com/Mcrauli/scan2bim/issues
AppUpdatesURL=https://github.com/Mcrauli/scan2bim/releases
DefaultDirName={autopf}\scan2bim
DefaultGroupName=scan2bim
DisableProgramGroupPage=yes
DisableDirPage=auto
; Per-user install by default → no UAC prompt → less SmartScreen friction.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir={#OutputDir}
OutputBaseFilename=scan2bim-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=scan2bim {#AppVersion}
UninstallDisplayIcon={app}\scan2bim.exe
VersionInfoVersion={#AppNumericVersion}
VersionInfoCompany=Lauri Rekola
VersionInfoDescription=scan2bim point cloud to IFC/DXF installer
VersionInfoProductName=scan2bim
VersionInfoProductVersion={#AppNumericVersion}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoCopyright=(c) 2026 Lauri Rekola
#ifdef IconFile
SetupIconFile={#IconFile}
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "finnish"; MessagesFile: "compiler:Languages\Finnish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; ONE-DIR: koko hakemisto, jotta LGPL-kirjastot (IfcOpenShell, Qt) ovat
; kayttajan vaihdettavissa omina tiedostoinaan.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#LicensesFile}"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\scan2bim"; Filename: "{app}\scan2bim.exe"
Name: "{autodesktop}\scan2bim"; Filename: "{app}\scan2bim.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\scan2bim.exe"; Description: "{cm:LaunchProgram,scan2bim}"; Flags: nowait postinstall skipifsilent
