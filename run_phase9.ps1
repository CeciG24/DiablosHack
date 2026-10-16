param(
    [ValidateSet('smoke', 'train', 'check', 'predict')]
    [string]$Action = 'check',
    [string]$Name = 'f9-full',
    [string]$InputFile = 'docs/F9_INPUT_EXAMPLE.json',
    [string]$OutputFile = 'output/f9-prediction.json'
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$phase9Python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $phase9Python)) {
    throw 'Falta .venv. Crea el entorno e instala requirements-modeling.txt.'
}
if ($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$') { throw 'Nombre de experimento inválido' }
New-Item -ItemType Directory -Path 'output' -Force | Out-Null
switch ($Action) {
    'smoke' { & $phase9Python -m experiments.phase9 --name $Name --smoke }
    'train' { & $phase9Python -m experiments.phase9 --name $Name }
    'check' { & $phase9Python -m experiments.check_phase9 --experiment "artifacts/modeling/$Name/F9" --output "output/$Name-audit.json" }
    'predict' { & $phase9Python -m experiments.phase9_predict --experiment "artifacts/modeling/$Name/F9" --input $InputFile --output $OutputFile }
}
if ($LASTEXITCODE -ne 0) { throw "Fase 9 falló con código $LASTEXITCODE" }
