#define MyAppName "Abel"
#define MyAppVersion "3.0.0"
#define MyAppPublisher "Student Led Business Solutions"

[Setup]
AppId={{BUDGET-AI-2026-1001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}

DefaultDirName={autopf}\Abel
DefaultGroupName={#MyAppName}

OutputDir=output
OutputBaseFilename=AbelSetup
SetupIconFile=..\assets\abel_icon.ico

Compression=lzma
SolidCompression=yes
WizardStyle=modern

PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\ai.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\budget.csv"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\budget.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\desktop_app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\bookkeeping.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\quickbooks.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\shopping_api.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\secure_storage.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\security.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\integrity.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\manifest.vault"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\start_abel.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\start_budget_ai.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\abel_icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\assets\abel_logo.png"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "setup_app.ps1"; Flags: dontcopy

[Icons]
Name: "{autodesktop}\Abel"; Filename: "{app}\start_abel.bat"; IconFilename: "{app}\assets\abel_icon.ico"
Name: "{group}\Abel"; Filename: "{app}\start_abel.bat"; IconFilename: "{app}\assets\abel_icon.ico"

[Run]
Filename: "{app}\start_abel.bat"; \
    Description: "Launch Abel"; \
    Flags: postinstall nowait skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
    ResultCode: Integer;
    ScriptPath: String;
    Parameters: String;
begin
    if CurStep = ssPostInstall then
    begin
        ExtractTemporaryFile('setup_app.ps1');
        ScriptPath := ExpandConstant('{tmp}\setup_app.ps1');
        Parameters := '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '" -AppDir "' + ExpandConstant('{app}') + '"';
        if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Parameters, '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
            RaiseException('Could not start the dependency installer.');
        if ResultCode <> 0 then
            RaiseException(Format('Dependency installation failed with exit code %d.', [ResultCode]));
    end;
end;
