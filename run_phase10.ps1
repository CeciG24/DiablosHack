param(
    [ValidateSet('smoke', 'train', 'check', 'simulate')]
    [string]$Action = 'check',
    [string]$Name = 'f10-full',
    [string]$InputFile = 'docs/F10_INPUT_EXAMPLE.json',
    [string]$OutputFile = 'output/f10-simulation.json',
    [string]$Target = 'Extreme Altitude'
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$phase10Python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $phase10Python)) { throw 'Falta .venv y sus dependencias de modelado.' }
if ($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$') { throw 'Nombre de experimento inválido' }
New-Item -ItemType Directory -Path 'output' -Force | Out-Null
switch ($Action) {
    'smoke' { & $phase10Python -m experiments.phase10 --name $Name --smoke }
    'train' { & $phase10Python -m experiments.phase10 --name $Name }
    'check' { & $phase10Python -m experiments.check_phase10 --experiment "artifacts/modeling/$Name/F10" --output "output/$Name-audit.json" }
    'simulate' { & $phase10Python -m experiments.phase10_simulator --experiment "artifacts/modeling/$Name/F10" --input $InputFile --target $Target --output $OutputFile }
}
if ($LASTEXITCODE -ne 0) { throw "Fase 10 falló con código $LASTEXITCODE" }
