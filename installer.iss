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
#define MyAppVersion     "1.7.7"
#define MyAppPublisher   "NetSentinel Project"
#define MyAppURL         "https://github.com/ossianericson/netsentinel"
#define MyAppExeName     "NetSentinel.exe"
#define MyAppCliName     "NetSentinel-cli.exe"
#define MyAppSvcName     "NetSentinel-svc.exe"
#define MyAppID          "com.netsentinel.app"
#define OoklaCliId       "Ookla.Speedtest.CLI"

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
PrivilegesRequiredOverridesAllowed = dialog commandline

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
Name: "desktopicon";    Description: "{cm:CreateDesktopIcon}";                              GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath";      Description: "Add NetSentinel CLI to system PATH";                  GroupDescription: "Command line integration"; Flags: checkedonce
Name: "installservice"; Description: "Install NetSentinel as a background Windows service (requires Administrator)"; GroupDescription: "Background monitoring"; Flags: unchecked

; ── Ookla Speedtest CLI task ────────────────────────────────────────────────────────────────
; Checked by default — users who don't want it can uncheck.
; Installed via winget (Ookla.Speedtest.CLI) so no binary redistribution.
; NetSentinel works perfectly without it; this just unlocks 1 Gbps+ test speeds.
Name: "installookla";   Description: "Install Ookla Speedtest CLI (recommended — enables 1 Gbps+ speed tests)"; GroupDescription: "Speed testing"; Flags: checkedonce

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
Name: "{autodesktop}\{#MyAppName}";               Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\NetSentinel.ico"

[Registry]
; Add install dir to system PATH
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Check: PathNotInPath('{app}'); Tasks: addtopath; Flags: preservestringtype

[Run]
; ── Ookla Speedtest CLI install (optional task) ───────────────────────────────────────────────
; Runs: winget install --id Ookla.Speedtest.CLI --silent --accept-package-agreements
; No binary is redistributed — winget downloads directly from Ookla's servers.
; The --source winget flag avoids disambiguation prompts.
; Failure is silently ignored — NetSentinel falls back to its built-in multithreaded
; backend if the CLI is not present.
Filename: "cmd.exe"; \
  Parameters: "/c winget install --id {#OoklaCliId} --source winget --silent --accept-package-agreements --accept-source-agreements 2>nul"; \
  Flags: runhidden waituntilterminated; \
  Tasks: installookla; \
  Check: ShouldInstallOokla; \
  StatusMsg: "Installing Ookla Speedtest CLI (for 1 Gbps+ speed tests)..."

; Install service after copy (optional task)
Filename: "{app}\{#MyAppSvcName}"; Parameters: "install"; Flags: runhidden waituntilterminated; Tasks: installservice; StatusMsg: "Installing background service..."

; Offer to launch the app after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop and uninstall service if it was installed
Filename: "{app}\{#MyAppSvcName}"; Parameters: "stop";      Flags: runhidden; StatusMsg: "Stopping service..."
Filename: "{app}\{#MyAppSvcName}"; Parameters: "uninstall"; Flags: runhidden; StatusMsg: "Removing service..."

; Note: Ookla CLI is NOT uninstalled here — it's a separate package the user may
; want to keep for other uses. Users can uninstall it via:
;   winget uninstall Ookla.Speedtest.CLI

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

// Helper: check if an executable exists anywhere on PATH
function FindProc(const ExeName: String): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/c where ' + ExeName + ' >nul 2>&1', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := Result and (ResultCode = 0);
end;

// Guard: skip Ookla CLI installation during silent/automated runs.
// Winget validation sandboxes run /VERYSILENT — a nested winget call hangs,
// times out, and causes the outer installer to return E_ABORT (0x80004004).
// Interactive users still get the install; headless/CI runs skip it cleanly.
function ShouldInstallOokla(): Boolean;
begin
  Result := not WizardSilent();
end;

// Pre-installation check: warn if winget is missing when Ookla CLI task is selected
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  NeedsRestart := False;

  if not IsTaskSelected('installookla') then Exit;

  // Check common winget location and PATH
  if FileExists(ExpandConstant('{localappdata}\Microsoft\WindowsApps\winget.exe')) then Exit;
  if FindProc('winget') then Exit;

  // winget not found — warn interactively only; silent installs (winget validation) must not block
  if not WizardSilent then
    MsgBox(
      'The Ookla Speedtest CLI could not be automatically installed because winget ' +
      '(Windows Package Manager) was not found on this system.' + #13#10 + #13#10 +
      'NetSentinel will still work — it includes a built-in multithreaded speed test backend.' + #13#10 + #13#10 +
      'To get 1 Gbps+ speed tests later, install the Ookla CLI manually:' + #13#10 +
      '  1. Install winget from the Microsoft Store (App Installer)' + #13#10 +
      '  2. Run: winget install Ookla.Speedtest.CLI' + #13#10 + #13#10 +
      'Or use the "Install via winget" button in the Speed Test page inside NetSentinel.',
      mbInformation, MB_OK
    );
end;
