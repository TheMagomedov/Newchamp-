param([switch]$Integration, [switch]$LegacyWeb)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# Keep the learning-sized source fragments within the agreed physical-line limit.
& './scripts/check_fragments.ps1'

# The five competition tests exercise Desktop functions without SQL, HTTP, files or a real clock.
dotnet test desktop/tests/Toir.Desktop.Tests.csproj -c Release -p:RestoreLockedMode=true
if ($LASTEXITCODE -ne 0) { throw 'Модульные тесты WPF не прошли.' }

& '.venv/Scripts/python.exe' -m pytest backend/tests/test_domain.py -q
if ($LASTEXITCODE -ne 0) { throw 'Модульные тесты Python не прошли.' }

if (-not (Test-Path -LiteralPath '.venv-streamlit/Scripts/python.exe')) {
    throw 'Для проверок нового веба сначала выполните ./setup_streamlit.ps1.'
}
& '.venv-streamlit/Scripts/python.exe' -m pytest web_streamlit/tests -q
if ($LASTEXITCODE -ne 0) { throw 'Проверки Streamlit не прошли.' }

if ($LegacyWeb) {
    $champTestPnpm = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    $champFallbackPnpm = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/fallback/pnpm.cmd'
    if ($champTestPnpm) { & $champTestPnpm.Source --dir web test }
    elseif (Test-Path -LiteralPath $champFallbackPnpm) { & $champFallbackPnpm --dir web test }
    else { throw 'Нужен pnpm для проверок резервного Vue.' }
    if ($LASTEXITCODE -ne 0) { throw 'Проверки резервного Vue не прошли.' }
}

if ($Integration) {
    Write-Host 'Интеграционные проверки создают временные записи в настроенной учебной БД и очищают свои фикстуры. Аудит и пропуски номеров могут остаться.'
    & '.venv/Scripts/python.exe' -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Интеграционные проверки Python/API не прошли.' }
}
Write-Host 'Выбранные проверки пройдены. Проверки интерфейса и конкурсная оценка выполняются отдельно.'
