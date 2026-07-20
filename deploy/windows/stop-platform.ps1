$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Runtime = Join-Path $ProjectRoot "var\windows"

foreach ($Name in @("streamlit", "sftp-sync")) {
    $PidFile = Join-Path $Runtime "$Name.pid"
    if (-not (Test-Path -LiteralPath $PidFile)) {
        continue
    }
    $ProcessId = [int](Get-Content -LiteralPath $PidFile -Raw)
    Stop-Process -Id $ProcessId -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $PidFile -Force
    Write-Host "$Name stopped."
}
