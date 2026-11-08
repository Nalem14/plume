; Plume for Windows: the PyInstaller folder (plume.spec) in an Inno Setup installer.
; Per user (%LOCALAPPDATA%\Programs\Plume), never an administrator prompt: Plume's updater runs this same installer
; silently (/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER, plus /RELAUNCH to start Plume again).
; Usage: iscc /DVersion=1.0.0 /DBundle=<dist\Plume> /DStage=<stage dir> /O<out dir> plume\windows\plume.iss
; ⚠️ Never change AppId once a version is published: Windows would see another app.

#ifndef Version
  #error Version is required (/DVersion=…)
#endif

[Setup]
AppId={{DD8CA881-5A34-4982-805F-76DCEAF4C0F7}
AppName=Plume
AppVersion={#Version}
AppVerName=Plume {#Version}
AppPublisher=Orneos
AppPublisherURL=https://orneos.eu
AppSupportURL=https://orneos.eu/fr/aide
VersionInfoVersion={#Version}
DefaultDirName={localappdata}\Programs\Plume
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=Plume-{#Version}-x64-setup
SetupIconFile={#Stage}\icons\plume.ico
UninstallDisplayIcon={app}\Plume.exe
UninstallDisplayName=Plume
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; an update while Plume runs: it is closed first (it quits by itself when it starts the update)
CloseApplications=force
RestartApplications=no
ChangesAssociations=yes

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; the files of the previous version: a module removed since must not stay behind
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Bundle}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Plume"; Filename: "{app}\Plume.exe"; AppUserModelID: "Orneos.Plume"
Name: "{userdesktop}\Plume"; Filename: "{app}\Plume.exe"; AppUserModelID: "Orneos.Plume"; Tasks: desktopicon

[Registry]
; orneos:// (links between mails, notes and tasks): Plume's own scheme
Root: HKA; Subkey: "Software\Classes\orneos"; ValueType: string; ValueData: "URL:Orneos"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\orneos"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\orneos\DefaultIcon"; ValueType: string; ValueData: "{app}\Plume.exe,0"
Root: HKA; Subkey: "Software\Classes\orneos\shell\open\command"; ValueType: string; ValueData: """{app}\Plume.exe"" ""%1"""
; mailto:, webcal:, otpauth: and .ics: offered in Windows' default apps (the user chooses; Windows forbids taking them)
Root: HKA; Subkey: "Software\Classes\Orneos.Plume.Url"; ValueType: string; ValueData: "Plume"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Orneos.Plume.Url"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Orneos.Plume.Url\DefaultIcon"; ValueType: string; ValueData: "{app}\Plume.exe,0"
Root: HKA; Subkey: "Software\Classes\Orneos.Plume.Url\shell\open\command"; ValueType: string; ValueData: """{app}\Plume.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Orneos.Plume.ics"; ValueType: string; ValueData: "iCalendar"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Orneos.Plume.ics\DefaultIcon"; ValueType: string; ValueData: "{app}\Plume.exe,0"
Root: HKA; Subkey: "Software\Classes\Orneos.Plume.ics\shell\open\command"; ValueType: string; ValueData: """{app}\Plume.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.ics\OpenWithProgids"; ValueType: string; ValueName: "Orneos.Plume.ics"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Orneos\Plume\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "Plume"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Orneos\Plume\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Mail, calendar and contacts of your Orneos account"
Root: HKA; Subkey: "Software\Orneos\Plume\Capabilities\URLAssociations"; ValueType: string; ValueName: "mailto"; ValueData: "Orneos.Plume.Url"
Root: HKA; Subkey: "Software\Orneos\Plume\Capabilities\URLAssociations"; ValueType: string; ValueName: "webcal"; ValueData: "Orneos.Plume.Url"
Root: HKA; Subkey: "Software\Orneos\Plume\Capabilities\URLAssociations"; ValueType: string; ValueName: "webcals"; ValueData: "Orneos.Plume.Url"
Root: HKA; Subkey: "Software\Orneos\Plume\Capabilities\URLAssociations"; ValueType: string; ValueName: "otpauth"; ValueData: "Orneos.Plume.Url"
Root: HKA; Subkey: "Software\Orneos\Plume\Capabilities\FileAssociations"; ValueType: string; ValueName: ".ics"; ValueData: "Orneos.Plume.ics"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "Plume"; ValueData: "Software\Orneos\Plume\Capabilities"; Flags: uninsdeletevalue
; « Open at startup » (Settings, system.set_autostart): removed with Plume, never written here
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Plume"; Flags: uninsdeletevalue dontcreatekey

[Run]
Filename: "{app}\Plume.exe"; Description: "{cm:LaunchProgram,Plume}"; Flags: nowait postinstall skipifsilent
; « Restart to update »: the silent installer starts Plume again
Filename: "{app}\Plume.exe"; Flags: nowait; Check: Relaunch

[Code]
function Relaunch: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/RELAUNCH') = 0 then
      Result := True;
end;
