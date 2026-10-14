param([ValidateRange(1024,65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe') -or -not (Test-Path -LiteralPath '.env')) {
    throw 'Сначала выполните setup.ps1. Python-окружение или локальные настройки ещё не подготовлены.'
}
$champListener = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
if ($champListener) {
    try {
        $champHealth = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 3
        if ($champHealth.success -and $champHealth.data.status -eq 'ok') {
            Write-Host "ТОиР-Проф уже работает: http://127.0.0.1:$Port. Второй сервер не нужен."
            Write-Host 'После обновления кода остановите прежний сервер Ctrl+C в его терминале и запустите этот скрипт снова.'
            return
        }
    } catch { }
    throw "Порт $Port занят. Не закрывайте неизвестный процесс: выберите другой порт, например ./start.ps1 -Port 8010, и укажите его в WPF."
}
Write-Host "API для WPF/Streamlit: http://127.0.0.1:$Port (без /api); резервный Vue доступен по этому же адресу."
Write-Host "Новый веб: в другом терминале выполните ./start_streamlit.ps1 -ApiPort $Port и откройте http://127.0.0.1:8501."
Write-Host 'Оставьте этот терминал открытым. Для остановки сервера нажмите Ctrl+C.'
& '.venv/Scripts/python.exe' -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $Port
if ($LASTEXITCODE -ne 0) { throw 'API не запустился. Проверьте сообщение выше и доступность SQL Server.' }
