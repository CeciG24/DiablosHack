param(
    [ValidateSet('freeze', 'smoke', 'evaluate', 'serve')][string]$Action = 'smoke',
    [string]$Release = 'artifacts/modeling/releases/f8-release-20261013',
    [string]$Name,
    [string]$ReleaseId,
    [switch]$Reproduce,
    [int]$Port = 8765
)
$ErrorActionPreference = 'Stop'
$releasePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Push-Location -LiteralPath $PSScriptRoot
try {
    switch ($Action) {
        'freeze' {
            if (-not $Name) { throw 'Indica -Name para crear un release nuevo antes de abrir test.' }
            & $releasePython -m modeling.phase8 freeze --name $Name
        }
        'smoke' { & $releasePython -m modeling.phase8 smoke --release $Release }
        'evaluate' {
            if (-not $ReleaseId) { throw 'Indica -ReleaseId con el ID de release_lock.json.' }
            $releaseArguments = @('-m', 'modeling.phase8', 'evaluate', '--release', $Release, '--release-id', $ReleaseId)
            if ($Reproduce) { $releaseArguments += '--reproduce' }
            & $releasePython @releaseArguments
        }
        'serve' { & $releasePython -m modeling.api --release $Release --serve --port $Port }
    }
    $releaseExitCode = $LASTEXITCODE
} finally { Pop-Location }
exit $releaseExitCode
