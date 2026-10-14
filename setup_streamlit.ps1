$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$champWebPython = Join-Path $PSScriptRoot '.venv-streamlit/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $champWebPython)) {
    $champBasePython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $champBasePython)) {
        throw 'Сначала подготовьте API командой ./setup.ps1.'
    }
    & $champBasePython -m venv .venv-streamlit
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать Python-окружение Streamlit.' }
}
$champWebRequirements = 'web_streamlit/requirements.lock.txt'
if (-not (Test-Path -LiteralPath $champWebRequirements)) {
    $champWebRequirements = 'web_streamlit/requirements.txt'
}
& $champWebPython -m pip install -r $champWebRequirements
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости Streamlit.' }
Write-Host 'Готово. Запустите API: ./start.ps1; затем в другом терминале: ./start_streamlit.ps1.'
