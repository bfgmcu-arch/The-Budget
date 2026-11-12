param(
    [Parameter(Mandatory = $true)]
    [string]$AppDir
)

$ErrorActionPreference = "Stop"
$VenvDir = Join-Path $AppDir ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Write-Host "======================================"
Write-Host " Business Budget AI Setup"
Write-Host "======================================"
Write-Host ""

# --------------------------------------
# Find / install Python
# --------------------------------------

Write-Host "Checking Python..."

$PythonExe = $null
$PythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($PythonLauncher) {
    & $PythonLauncher.Source -3.13 --version *> $null
    if ($LASTEXITCODE -eq 0) {
        $PythonExe = $PythonLauncher.Source
    }
}

if (-not $PythonExe) {
    $PossiblePythonPaths = @(
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:ProgramFiles\Python313\python.exe",
        "$env:ProgramFiles\Python312\python.exe"
    )
    foreach ($Path in $PossiblePythonPaths) {
        if (Test-Path $Path) {
            $PythonExe = $Path
            break
        }
    }
}

if (-not $PythonExe) {
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($PythonCommand -and $PythonCommand.Source -notlike "*WindowsApps*") {
        $PythonExe = $PythonCommand.Source
    }
}

if (-not $PythonExe) {
    $PythonInstaller = Join-Path $env:TEMP "python-installer.exe"
    Invoke-WebRequest `
        -Uri "https://www.python.org/ftp/python/3.13.7/python-3.13.7-amd64.exe" `
        -OutFile $PythonInstaller
    $InstallProcess = Start-Process `
        -FilePath $PythonInstaller `
        -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_test=0" `
        -Wait -PassThru
    Remove-Item $PythonInstaller -Force
    if ($InstallProcess.ExitCode -ne 0) {
        throw "Python setup failed with exit code $($InstallProcess.ExitCode)."
    }
    $PythonExe = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"
}

if ($PythonExe -eq $PythonLauncher.Source) {
    & $PythonExe -3.13 -m venv $VenvDir
}
else {
    & $PythonExe -m venv $VenvDir
}
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
    throw "Could not create the application Python environment at $VenvDir."
}

Write-Host "Installing application dependencies..."
& $VenvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Could not update pip."
}
& $VenvPython -m pip install -r (Join-Path $AppDir "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Could not install the application dependencies."
}

# --------------------------------------
# Find / install Ollama
# --------------------------------------

Write-Host ""
Write-Host "Checking Ollama..."

$OllamaExe = $null

$possibleOllamaPaths = @(
    "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    "$env:ProgramFiles\Ollama\ollama.exe"
)

foreach ($path in $possibleOllamaPaths) {

    if (Test-Path $path) {
        $OllamaExe = $path
        break
    }

}

if (-not $OllamaExe) {

    $ollamaCommand = Get-Command ollama.exe -ErrorAction SilentlyContinue

    if ($ollamaCommand) {
        $OllamaExe = $ollamaCommand.Source
    }

}

if (-not $OllamaExe) {

    Write-Host ""
    Write-Host "Ollama is not installed."
    Write-Host "Downloading Ollama..."

    $OllamaInstaller = Join-Path $env:TEMP "OllamaSetup.exe"

    Invoke-WebRequest `
        -Uri "https://ollama.com/download/OllamaSetup.exe" `
        -OutFile $OllamaInstaller

    Write-Host "Installing Ollama..."

    Start-Process `
        -FilePath $OllamaInstaller `
        -ArgumentList "/VERYSILENT" `
        -Wait

    Remove-Item $OllamaInstaller -Force

    # Check again
    $possibleOllamaPaths = @(
        "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
        "$env:ProgramFiles\Ollama\ollama.exe"
    )

    foreach ($path in $possibleOllamaPaths) {

        if (Test-Path $path) {
            $OllamaExe = $path
            break
        }

    }

}

if (-not $OllamaExe) {

    Write-Host ""
    Write-Host "ERROR: Ollama could not be found after installation."
    exit 1

}

Write-Host ""
Write-Host "Ollama found:"
Write-Host $OllamaExe

# --------------------------------------
# Start Ollama
# --------------------------------------

Write-Host ""
Write-Host "Starting Ollama..."

$ollamaRunning = Get-Process ollama -ErrorAction SilentlyContinue

if (-not $ollamaRunning) {

    Start-Process `
        -FilePath $OllamaExe `
        -ArgumentList "serve" `
        -WindowStyle Hidden

    Start-Sleep -Seconds 5

}

# --------------------------------------
# Download AI model
# --------------------------------------

Write-Host ""
Write-Host "Downloading ultra-fast AI model (qwen2.5:0.5b)..."

& $OllamaExe pull qwen2.5:0.5b

if ($LASTEXITCODE -ne 0) {

    Write-Host ""
    Write-Host "ERROR: AI model download failed."
    exit 1

}

# --------------------------------------
# Write installer authorization signature
# --------------------------------------

Write-Host "Creating authorized installer signature..."
$kHex = "7a4c9b2e81d053f7a62e4c19b83d70ef"
$pHex = "3f9a1c8b2e5d7041a8b9c2e3f4a5b6c7"
$k = for ($i = 0; $i -lt $kHex.Length; $i += 2) { [Convert]::ToByte($kHex.Substring($i, 2), 16) }
$p = for ($i = 0; $i -lt $pHex.Length; $i += 2) { [Convert]::ToByte($pHex.Substring($i, 2), 16) }
$hmac = New-Object System.Security.Cryptography.HMACSHA256
$hmac.Key = $k
$sig = -join ($hmac.ComputeHash($p) | ForEach-Object { "{0:x2}" -f $_ })
$sigPath = Join-Path $AppDir ".install_signature"
Set-Content -Path $sigPath -Value $sig -Force -Encoding ASCII
try {
    (Get-Item $sigPath).Attributes = [System.IO.FileAttributes]::Hidden
} catch {}

# --------------------------------------
# Finish
# --------------------------------------

Write-Host ""
Write-Host "======================================"
Write-Host " Installation complete!"
Write-Host "======================================"
Write-Host ""
Write-Host "Application:"
Write-Host (Join-Path $AppDir "start_budget_ai.bat")
Write-Host ""