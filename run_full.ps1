param([string]$RuntimeRoot = 'D:\CodexRuntime\DiablosHack', [int]$ApiPort = 8001, [int]$WebPort = 4200)
$ErrorActionPreference = 'Stop'
$repoRoot = $PSScriptRoot
$frontendRoot = Join-Path $repoRoot 'altura-plus'
$runtimePath = [IO.Path]::GetFullPath($RuntimeRoot)
New-Item -ItemType Directory -Path $runtimePath -Force | Out-Null
foreach ($directory in @('tmp', 'logs', 'frontend', 'angular-cache')) {
    New-Item -ItemType Directory -Path (Join-Path $runtimePath $directory) -Force | Out-Null
}
$env:TEMP = Join-Path $runtimePath 'tmp'
$env:TMP = $env:TEMP
$env:PYTHONPYCACHEPREFIX = Join-Path $runtimePath 'pycache'
$env:NG_CLI_ANALYTICS = 'false'
$env:NG_BUILD_MAX_WORKERS = '2'
$env:DIABLOS_CORS_ORIGINS = "http://127.0.0.1:$WebPort,http://localhost:$WebPort"
if (-not $env:DIABLOS_RUN) {
    $runId = (Get-Content -LiteralPath (Join-Path $repoRoot 'data\CURRENT') -Raw).Trim()
    $env:DIABLOS_RUN = Join-Path $repoRoot "data\runs\$runId"
}
if (-not (Test-Path -LiteralPath (Join-Path $env:DIABLOS_RUN 'pitches.parquet'))) {
    throw 'DIABLOS_RUN no contiene pitches.parquet; restaurar los datos privados verificados.'
}
$dependencyRoot = Join-Path $runtimePath 'frontend'
Copy-Item -LiteralPath (Join-Path $frontendRoot 'package.json'), (Join-Path $frontendRoot 'package-lock.json') -Destination $dependencyRoot
$cli = Join-Path $dependencyRoot 'node_modules\@angular\cli\bin\ng.js'
if (-not (Test-Path -LiteralPath $cli)) {
    & npm.cmd ci --prefix $dependencyRoot --cache (Join-Path $runtimePath 'npm-cache') --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Falló npm ci' }
}
foreach ($link in @(@('node_modules', (Join-Path $dependencyRoot 'node_modules')), @('.angular', (Join-Path $runtimePath 'angular-cache')))) {
    $linkPath = Join-Path $frontendRoot $link[0]
    if (-not (Test-Path -LiteralPath $linkPath)) {
        New-Item -ItemType Junction -Path $linkPath -Target $link[1] | Out-Null
    }
}
$apiUrl = "http://127.0.0.1:$ApiPort"
$webUrl = "http://127.0.0.1:$WebPort"
foreach ($port in @($ApiPort, $WebPort)) {
    $probe = [Net.Sockets.TcpClient]::new()
    try {
        $probe.Connect('127.0.0.1', $port)
        throw "El puerto $port ya está ocupado. Usa otro puerto o detén el proceso anterior."
    } catch [Net.Sockets.SocketException] {
        # Connection refused: this port is available.
    } finally { $probe.Dispose() }
}
$python = Join-Path $repoRoot '.venv\Scripts\python.exe'
$apiProcess = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', "$ApiPort") -WorkingDirectory $repoRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath 'logs\backend.out.log') -RedirectStandardError (Join-Path $runtimePath 'logs\backend.err.log')
$webProcess = $null
try {
    for ($attempt = 0; $attempt -lt 90; $attempt++) {
        if ($apiProcess.HasExited) { throw 'El backend terminó; revisar logs/backend.err.log' }
        try {
            $ready = Invoke-RestMethod "$apiUrl/ready" -TimeoutSec 2
            if ($ready.status -eq 'ready') { break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $ready -or $ready.status -ne 'ready') { throw 'F8/F10 no están listos; revisar los logs.' }
    $pitchers = Invoke-RestMethod "$apiUrl/api/v1/pitchers?min_n=60&limit=1" -TimeoutSec 60
    if (-not $pitchers.records.Count) { throw 'F9 no devuelve pitchers reales; revisar artefactos.' }
    $webProcess = Start-Process -FilePath (Get-Command node.exe).Source -ArgumentList @("`"$cli`"", 'serve', '--host', '127.0.0.1', '--port', "$WebPort", '--no-open') -WorkingDirectory $frontendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimePath 'logs\frontend.out.log') -RedirectStandardError (Join-Path $runtimePath 'logs\frontend.err.log')
    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if ($webProcess.HasExited) { throw 'El frontend terminó; revisar logs/frontend.err.log' }
        try {
            $response = Invoke-WebRequest $webUrl -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) { break }
        } catch { }
        Start-Sleep -Seconds 1
    }
    if (-not $response -or $response.StatusCode -ne 200) { throw 'El frontend no respondió a tiempo.' }
    $state = @{ backend_pid=$apiProcess.Id; frontend_pid=$webProcess.Id; api=$apiUrl; web=$webUrl; data_run=$env:DIABLOS_RUN; started_at=(Get-Date).ToString('o') }
    $state | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtimePath 'session.json')
    $state | ConvertTo-Json
} catch {
    if ($webProcess -and -not $webProcess.HasExited) { Stop-Process -Id $webProcess.Id }
    if (-not $apiProcess.HasExited) { Stop-Process -Id $apiProcess.Id }
    throw
}
