$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $PSScriptRoot
$RequiredFiles = @(
    "ai.py", "app.py", "budget.csv", "budget.py", "bookkeeping.py", "config.py", "desktop_app.py",
    "quickbooks.py", "shopping_api.py", "requirements.txt", "secure_storage.py", "start_budget_ai.bat"
)
foreach ($File in $RequiredFiles) {
    if (-not (Test-Path (Join-Path $AppDir $File))) {
        throw "Required installer source file is missing: $File"
    }
}

$InnoCompilerPath = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $InnoCompilerPath) {
    $InnoPaths = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $InnoCompilerPath = $InnoPaths | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if ($InnoCompilerPath) {
    & $InnoCompilerPath (Join-Path $PSScriptRoot "BusinessBudgetAI.iss")
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup failed with exit code $LASTEXITCODE"
    }
}
else {
    Write-Host "ISCC.exe was not found. Install Inno Setup to build the installer package."
}