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
; The folder can be chosen, but only an empty one or an earlier Argus folder is taken: an
; upgrade clears folders in it and the uninstaller more, so a folder that holds other things
; could lose them (see PrepareToInstall). auto: the page is skipped when an earlier install's
; folder is known, so an upgrade goes where it was.
DisableDirPage=auto
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
; Inno Setup 6.7, as on the GitHub runners, has no Chinese of its own: the file is kept here.
Name: "zh"; MessagesFile: "inno\ChineseSimplified.isl"

[CustomMessages]
en.ArgusGcs=Argus Ground Station
zh.ArgusGcs=Argus 地面站
en.ArgusSimulator=Argus Simulator
zh.ArgusSimulator=Argus 仿真器
en.NotItsOwn=%1 holds other files and no Argus. Argus needs a folder of its own: an upgrade and the uninstaller clear folders in it.
zh.NotItsOwn=%1 里已有其他文件，且没有 Argus。Argus 需要单独的文件夹：升级和卸载会清理其中的文件夹。

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
; What Argus made while it ran: compiled modules, caches and the access token. Flight logs
; (logs), map files of your own (mbtiles) and firmware files, uploaded ones among them
; (firmware), stay.
Type: filesandordirs; Name: "{app}\backend"
Type: filesandordirs; Name: "{app}\dist"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\tile_cache"
Type: filesandordirs; Name: "{app}\srtm_cache"
Type: filesandordirs; Name: "{app}\param_cache"
Type: files; Name: "{app}\.gcs_token"
Type: dirifempty; Name: "{app}"

[Code]
// The folder given with /DIR, or kept from an earlier install, must be Argus's own or empty:
// [InstallDelete] would clear backend, dist, python and LICENSES in any other.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Dir: String;
  Found: TFindRec;
begin
  Result := '';
  Dir := AddBackslash(ExpandConstant('{app}'));
  if FileExists(Dir + 'backend\server.py') then
    Exit;
  if FindFirst(Dir + '*', Found) then
  try
    repeat
      if (Found.Name <> '.') and (Found.Name <> '..') then
      begin
        Result := FmtMessage(CustomMessage('NotItsOwn'), [RemoveBackslash(Dir)]);
        Exit;
      end;
    until not FindNext(Found);
  finally
    FindClose(Found);
  end;
end;
