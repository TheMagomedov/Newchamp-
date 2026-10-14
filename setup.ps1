param([switch]$LegacyWeb)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать окружение Python.' }
}
& '.venv/Scripts/python.exe' -m pip install -r backend/requirements.lock.txt
if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости Python.' }
& '.venv/Scripts/python.exe' scripts/setup.py
if ($LASTEXITCODE -ne 0) { throw 'Не удалось подготовить БД.' }
& './setup_streamlit.ps1'
if ($LegacyWeb) {
Push-Location web
try {
    $champPnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    $champBundledPnpm = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm.cmd'
    if ($champPnpm) {
        & $champPnpm.Source install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости web.' }
        & $champPnpm.Source run build
    } elseif (Test-Path -LiteralPath $champBundledPnpm) {
        & $champBundledPnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости web.' }
        & $champBundledPnpm run build
    } else {
        npm.cmd install
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости web. Нужен Node.js с npm или pnpm.' }
        npm.cmd run build
    }
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось собрать web.' }
} finally { Pop-Location }
}
dotnet build desktop/Toir.Desktop.csproj -c Release
if ($LASTEXITCODE -ne 0) { throw 'Не удалось собрать настольное приложение WPF.' }
Write-Host 'Готово. Запустите ./run.ps1 для API и Streamlit вместе.'
