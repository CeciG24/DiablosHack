param([int]$Port = 8001, [switch]$Reload)
$ErrorActionPreference = 'Stop'
$backendPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Push-Location -LiteralPath $PSScriptRoot
try {
    $backendArgs = @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', "$Port")
    if ($Reload) { $backendArgs += '--reload' }
    & $backendPython @backendArgs
    $backendExitCode = $LASTEXITCODE
} finally { Pop-Location }
exit $backendExitCode
