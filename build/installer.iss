; Inno Setup script for ordinate.
;
; Compiled by `scripts/build_installer.ps1` after PyInstaller has produced
; `dist/ordinate.exe`. Paths and version come through /D defines so the
; .iss hardcodes no absolute path.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\ordinate"
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
AppName=Ordinate
AppVersion={#AppVersion}
AppVerName=Ordinate {#AppVersion}
AppPublisher=Lauri Rekola
AppPublisherURL=https://github.com/Mcrauli/Ordinate
AppSupportURL=https://github.com/Mcrauli/Ordinate/issues
AppUpdatesURL=https://github.com/Mcrauli/Ordinate/releases
DefaultDirName={autopf}\Ordinate
DefaultGroupName=Ordinate
DisableProgramGroupPage=yes
DisableDirPage=auto
; Per-user install by default → no UAC prompt → less SmartScreen friction.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
OutputDir={#OutputDir}
OutputBaseFilename=Ordinate-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Ordinate {#AppVersion}
UninstallDisplayIcon={app}\Ordinate.exe
; Sulje kaynnissa oleva sovellus ENNEN tiedostojen korvausta → ei Windows-virhe 32
; ("tiedosto toisen prosessin kaytossa") kun kayttaja asentaa uuden version appin
; ollessa auki. AppMutex-nimi = gui/app.py:n luoma mutex (luotettava tunnistus,
; Restart Manager ei aina huomaa Qt-appia). RestartApplications=no: ei kaynnista
; appia yllattaen kesken asennuksen.
CloseApplications=yes
RestartApplications=no
AppMutex=OrdinateAppMutex,Scan2BimAppMutex
VersionInfoVersion={#AppNumericVersion}
VersionInfoCompany=Lauri Rekola
VersionInfoDescription=Ordinate point cloud to IFC/DXF installer
VersionInfoProductName=Ordinate
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
Name: "{autoprograms}\Ordinate"; Filename: "{app}\Ordinate.exe"
Name: "{autodesktop}\Ordinate"; Filename: "{app}\Ordinate.exe"; Tasks: desktopicon

[InstallDelete]
Type: files; Name: "{autoprograms}\scan2bim.lnk"
Type: files; Name: "{autodesktop}\scan2bim.lnk"

[Run]
Filename: "{app}\Ordinate.exe"; Description: "{cm:LaunchProgram,Ordinate}"; Flags: nowait postinstall skipifsilent
