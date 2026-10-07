$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$taskPython = Join-Path $PSScriptRoot '.venv-verificacao\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -m venv .venv-verificacao
    if ($LASTEXITCODE -ne 0) { throw 'Não foi possível criar o ambiente Python.' }
}
$taskLockHash = (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot 'requirements-lock.txt')).Hash
$taskMarker = Join-Path $PSScriptRoot '.venv-verificacao\dependencias.sha256'
if (-not (Test-Path -LiteralPath $taskMarker) -or (Get-Content -LiteralPath $taskMarker -Raw).Trim() -ne $taskLockHash) {
    & $taskPython -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falha na instalação das dependências.' }
    Set-Content -LiteralPath $taskMarker -Value $taskLockHash
}
& $taskPython -m streamlit run interface.py
if ($LASTEXITCODE -ne 0) { throw 'Falha ao iniciar a interface.' }
