param(
    [ValidateSet('smoke', 'full', 'f1-smoke', 'f1', 'f2-smoke', 'f2', 'f3-smoke', 'f3', 'f4-smoke', 'f4', 'tests', 'contract')]
    [string]$Action = 'smoke'
)
$ErrorActionPreference = 'Stop'
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    throw 'Falta .venv. Crea el entorno con python -m venv .venv e instala requirements.txt.'
}
$modelingPython = $venvPython
Push-Location -LiteralPath $PSScriptRoot
try {
    switch ($Action) {
        'smoke' { & $modelingPython -m modeling.cli smoke }
        'full' { & $modelingPython -m modeling.cli smoke --full }
        'f1-smoke' { & $modelingPython -m modeling.cli train --phase F1 --smoke }
        'f1' { & $modelingPython -m modeling.cli train --phase F1 }
        'f2-smoke' { & $modelingPython -m modeling.cli train --phase F2 --smoke }
        'f2' { & $modelingPython -m modeling.cli train --phase F2 }
        'f3-smoke' { & $modelingPython -m modeling.cli train --phase F3 --smoke }
        'f3' { & $modelingPython -m modeling.cli train --phase F3 }
        'f4-smoke' { & $modelingPython -m modeling.cli train --phase F4 --smoke }
        'f4' { & $modelingPython -m modeling.cli train --phase F4 }
        'tests' { & $modelingPython -m unittest discover -s tests -v }
        'contract' { & $modelingPython scripts/check_modeling_contract.py }
    }
    $modelingExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $modelingExitCode
