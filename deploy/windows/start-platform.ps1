param(
    [string]$Address = "0.0.0.0",
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Runtime = Join-Path $ProjectRoot "var\windows"
$Logs = Join-Path $Runtime "logs"
New-Item -ItemType Directory -Force -Path $Logs | Out-Null

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python virtual environment not found: $Python"
}

function Start-ManagedProcess {
    param([string]$Name, [string[]]$Arguments)
    $PidFile = Join-Path $Runtime "$Name.pid"
    if (Test-Path -LiteralPath $PidFile) {
        $ExistingPid = [int](Get-Content -LiteralPath $PidFile -Raw)
        if (Get-Process -Id $ExistingPid -ErrorAction SilentlyContinue) {
            Write-Host "$Name is already running (PID $ExistingPid)."
            return
        }
    }
    $Process = Start-Process -FilePath $Python -ArgumentList $Arguments `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $Logs "$Name.out.log") `
        -RedirectStandardError (Join-Path $Logs "$Name.err.log")
    Set-Content -LiteralPath $PidFile -Value $Process.Id
    Write-Host "$Name started (PID $($Process.Id))."
}

Start-ManagedProcess "sftp-sync" @("scripts/sync_sftp.py")
Start-ManagedProcess "streamlit" @(
    "-m", "streamlit", "run", "app.py",
    "--server.address=$Address", "--server.port=$Port",
    "--server.headless=true", "--browser.gatherUsageStats=false"
)

Write-Host "Platform started. Open http://<Windows-IP>:$Port"
