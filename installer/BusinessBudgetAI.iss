#define MyAppName "Business Budget AI"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Business Budget AI"

[Setup]
AppId={{BUDGET-AI-2026-1001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}

DefaultDirName={autopf}\Business Budget AI
DefaultGroupName={#MyAppName}

OutputDir=output
OutputBaseFilename=BusinessBudgetAISetup

Compression=lzma
SolidCompression=yes
WizardStyle=modern

PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Files]
Source: "..\ai.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\budget.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\desktop_app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\bookkeeping.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\quickbooks.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\shopping_api.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\secure_storage.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\start_budget_ai.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "setup_app.ps1"; Flags: dontcopy

[Icons]
Name: "{autodesktop}\Business Budget AI"; Filename: "{app}\start_budget_ai.bat"
Name: "{group}\Business Budget AI"; Filename: "{app}\start_budget_ai.bat"

[Run]
Filename: "{app}\start_budget_ai.bat"; \
    Description: "Launch Business Budget AI"; \
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