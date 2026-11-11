; Windows installer of Argus GCS. scripts/build_installer.py builds it from the release zip on
; the Windows jobs of ci.yml and release.yml, where Inno Setup 6 is preinstalled.
;
; It installs what the zip holds, for the current user only and without administrator rights:
; Argus writes its logs, map cache and token beside its program, and a folder under Program
; Files is not writable for it.

#ifndef AppVersion
  #error Pass /DAppVersion=X.Y.Z
#endif
#ifndef SourceDir
  #error Pass /DSourceDir=<the folder the release zip holds>
#endif
#ifndef OutputDir
  #define OutputDir "."
#endif

[Setup]
; Never change it: an upgrade and the uninstaller find an earlier install by it, and
; scripts/smoke_package.py reads the uninstall entry it names.
AppId={{2CDE95AA-A33A-4B5A-9B54-5350EAF7C49D}
AppName=Argus GCS
AppVersion={#AppVersion}
AppVerName=Argus GCS {#AppVersion}
AppPublisher=Argus GCS
AppPublisherURL=https://github.com/L-X-Yao/argus
AppSupportURL=https://github.com/L-X-Yao/argus/issues
AppUpdatesURL=https://github.com/L-X-Yao/argus/releases
; With PrivilegesRequired=lowest this is %LOCALAPPDATA%\Programs.
DefaultDirName={autopf}\Argus GCS
DefaultGroupName=Argus GCS
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile={#SourceDir}\LICENSE
SetupIconFile={#SourceDir}\argus.ico
UninstallDisplayIcon={app}\argus.ico
UninstallDisplayName=Argus GCS {#AppVersion}
OutputDir={#OutputDir}
OutputBaseFilename=Argus_GCS_v{#AppVersion}_amd64_setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ShowLanguageDialog=auto
VersionInfoVersion={#AppVersion}

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "zh"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[CustomMessages]
en.ArgusGcs=Argus Ground Station
zh.ArgusGcs=Argus 地面站
en.ArgusSimulator=Argus Simulator
zh.ArgusSimulator=Argus 仿真器

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; The program of an earlier version: its hashed web assets and removed modules would stay.
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\dist"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\LICENSES"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{cm:ArgusGcs}"; Filename: "{app}\Argus地面站.bat"; WorkingDir: "{app}"; IconFilename: "{app}\argus.ico"
Name: "{group}\{cm:ArgusSimulator}"; Filename: "{app}\启动仿真器.bat"; WorkingDir: "{app}"; IconFilename: "{app}\argus.ico"
Name: "{group}\{cm:UninstallProgram,Argus GCS}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{cm:ArgusGcs}"; Filename: "{app}\Argus地面站.bat"; WorkingDir: "{app}"; IconFilename: "{app}\argus.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\Argus地面站.bat"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,Argus GCS}"; Flags: postinstall nowait skipifsilent shellexec

[UninstallDelete]
; What Argus made while it ran: compiled modules, caches, downloaded firmware and the access
; token. Flight logs (logs) and map files of your own (mbtiles) stay.
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\dist"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\tile_cache"
Type: filesandordirs; Name: "{app}\srtm_cache"
Type: filesandordirs; Name: "{app}\firmware"
Type: files; Name: "{app}\.gcs_token"
Type: dirifempty; Name: "{app}"
