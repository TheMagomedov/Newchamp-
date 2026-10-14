param(
    [ValidateRange(1024,65535)][int]$Port = 8501,
    [ValidateRange(1024,65535)][int]$ApiPort = 8000
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$champStreamlitPython = Join-Path $PSScriptRoot '.venv-streamlit/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $champStreamlitPython)) {
    throw 'Сначала выполните ./setup_streamlit.ps1.'
}
if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
    throw "Порт $Port уже занят. Проверьте открытый сайт или задайте другой -Port. Не закрывайте неизвестные процессы."
}
try {
    $champApiHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 5
    if (-not $champApiHealth.success) { throw 'Нет успешного ответа API.' }
} catch {
    throw "API недоступен. В отдельном терминале запустите ./start.ps1 -Port $ApiPort и повторите."
}
$champPreviousApi = $env:TOIR_API_URL
try {
    $env:TOIR_API_URL = "http://127.0.0.1:$ApiPort"
    Write-Host "Streamlit: http://127.0.0.1:$Port; API: $env:TOIR_API_URL. Для остановки веба нажмите Ctrl+C."
    & $champStreamlitPython -m streamlit run web_streamlit/app.py `
        --server.address 127.0.0.1 --server.port $Port --server.headless true `
        --browser.gatherUsageStats false
    if ($LASTEXITCODE -ne 0) { throw 'Streamlit завершился с ошибкой. Проверьте сообщение выше.' }
} finally {
    $env:TOIR_API_URL = $champPreviousApi
}
