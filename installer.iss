; ============================================================================
; NetSentinel — Inno Setup installer script
;
; Builds a standard Windows setup EXE that:
;   • Installs NetSentinel.exe, NetSentinel-cli.exe, NetSentinel-svc.exe
;   • Creates Start Menu shortcut
;   • Optionally creates a Desktop shortcut
;   • Registers in Add / Remove Programs (required for winget)
;   • Adds the install dir to PATH so  `netsentinel-cli`  works from any terminal
;   • Optionally installs the background Windows service
;   • Writes an Uninstaller
;
; Prerequisites (build machine only):
;   Inno Setup 6.x  — https://jrsoftware.org/isdl.php
;   ISPP (preprocessor) — included with Inno Setup 6
;
; Usage:
;   iscc installer.iss
;
; Or run via GitHub Actions (see .github/workflows/release.yml).
; The output file is:  dist\NetSentinel-Setup-{version}.exe
; ============================================================================

#define MyAppName        "NetSentinel"
#define MyAppVersion     "1.0.4"
#define MyAppPublisher   "NetSentinel Project"
#define MyAppURL         "https://github.com/ossianericson/netsentinel"
#define MyAppExeName     "NetSentinel.exe"
#define MyAppCliName     "NetSentinel-cli.exe"
#define MyAppSvcName     "NetSentinel-svc.exe"
#define MyAppID          "com.netsentinel.app"

[Setup]
; ── Identity ────────────────────────────────────────────────────────────────
AppId                     = {#MyAppID}
AppName                   = {#MyAppName}
AppVersion                = {#MyAppVersion}
AppVerName                = {#MyAppName} {#MyAppVersion}
AppPublisher              = {#MyAppPublisher}
AppPublisherURL           = {#MyAppURL}
AppSupportURL             = {#MyAppURL}/issues
AppUpdatesURL             = {#MyAppURL}/releases

; ── Install paths ────────────────────────────────────────────────────────────
DefaultDirName            = {autopf}\{#MyAppName}
DefaultGroupName          = {#MyAppName}
DisableProgramGroupPage   = yes

; ── Output ───────────────────────────────────────────────────────────────────
OutputDir                 = dist
OutputBaseFilename        = NetSentinel-Setup-{#MyAppVersion}
SetupIconFile             = assets\icons\NetSentinel.ico
Compression               = lzma2/ultra64
SolidCompression          = yes
WizardStyle               = modern

; ── Architecture ─────────────────────────────────────────────────────────────
ArchitecturesInstallIn64BitMode = x64compatible

; ── Privilege & UAC ──────────────────────────────────────────────────────────
; STP/Storm modules need raw sockets → installer asks for admin.
; The shortcut uses runas so the app itself elevates on launch.
PrivilegesRequired        = admin
PrivilegesRequiredOverridesAllowed = dialog

; ── Uninstaller ──────────────────────────────────────────────────────────────
UninstallDisplayIcon      = {app}\{#MyAppExeName}
UninstallDisplayName      = {#MyAppName} {#MyAppVersion}
CreateUninstallRegKey     = yes

; ── Misc ──────────────────────────────────────────────────────────────────────
; PATH change requires re-login
ChangesEnvironment        = yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";    Description: "{cm:CreateDesktopIcon}";                GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath";      Description: "Add NetSentinel CLI to system PATH";    GroupDescription: "Command line integration"; Flags: checkedonce
Name: "installservice"; Description: "Install NetSentinel as a background Windows service (requires Administrator)"; GroupDescription: "Background monitoring"; Flags: unchecked

[Files]
; Application icon
Source: "assets\icons\NetSentinel.ico"; DestDir: "{app}"; Flags: ignoreversion

; GUI executable
Source: "dist\{#MyAppExeName}";     DestDir: "{app}"; Flags: ignoreversion

; CLI executable (installed to the same folder so PATH addition works)
Source: "dist\{#MyAppCliName}";     DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Service executable
Source: "dist\{#MyAppSvcName}";     DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist

; Bundled OUI offenders database
Source: "offenders.json";           DestDir: "{app}"; Flags: ignoreversion

; Npcap stub reminder (not bundled — Npcap has its own licence)
Source: "tools\diagnose-network.ps1"; DestDir: "{app}\tools"; Flags: ignoreversion skipifsourcedoesntexist

[Icons]
; Start Menu
Name: "{group}\{#MyAppName}";                     Filename: "{app}\{#MyAppExeName}"; Parameters: ""; WorkingDir: "{app}"; IconFilename: "{app}\NetSentinel.ico"
Name: "{group}\{#MyAppName} CLI";                 Filename: "{app}\{#MyAppCliName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}";           Filename: "{uninstallexe}"

; Desktop (optional)
Name: "{autodesktop}\{#MyAppName}";               Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
; Add install dir to system PATH
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: PathNotInPath('{app}'); Tasks: addtopath; Flags: preservestringtype

[Run]
; Install service after copy (optional task)
Filename: "{app}\{#MyAppSvcName}"; Parameters: "install"; Flags: runhidden waituntilterminated; Tasks: installservice; StatusMsg: "Installing background service..."

; Offer to launch the app after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop and uninstall service if it was installed
Filename: "{app}\{#MyAppSvcName}"; Parameters: "stop";      Flags: runhidden; StatusMsg: "Stopping service..."
Filename: "{app}\{#MyAppSvcName}"; Parameters: "uninstall"; Flags: runhidden; StatusMsg: "Removing service..."

[Code]
// Helper: check whether a path segment is already in the system PATH
function PathNotInPath(const PathToAdd: string): Boolean;
var
  CurrentPath: string;
begin
  if not RegQueryStringValue(HKLM,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', CurrentPath) then
  begin
    Result := True;
    Exit;
  end;
  Result := Pos(LowerCase(PathToAdd), LowerCase(CurrentPath)) = 0;
end;
