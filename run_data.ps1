param(
    [ValidateSet('example', 'check', 'prepare', 'tests')]
    [string]$Action = 'example'
)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw 'Falta .venv. Crea el entorno con python -m venv .venv e instala requirements.txt.'
}
$dataPython = $venvPython
switch ($Action) {
    'example' { & $dataPython (Join-Path $projectRoot 'examples\load_training_data.py') }
    'check' { & $dataPython (Join-Path $projectRoot 'scripts\check_data.py') }
    'prepare' { & $dataPython (Join-Path $projectRoot 'scripts\prepare_data.py') }
    'tests' { & $dataPython -m unittest discover -s (Join-Path $projectRoot 'tests') -v }
}
exit $LASTEXITCODE
