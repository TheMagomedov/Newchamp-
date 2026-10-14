param(
    [ValidateRange(1024,65535)][int]$WebPort = 8501,
    [ValidateRange(1024,65535)][int]$ApiPort = 8000
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$champOwnedApi = $null
$champApiAddress = "http://127.0.0.1:$ApiPort"
function Test-ChampApi {
    try {
        $champHealth = Invoke-RestMethod -Uri "$champApiAddress/api/health" -TimeoutSec 2
        return $champHealth.success -and $champHealth.data.status -eq 'ok'
    } catch { return $false }
}
try {
    if (-not (Test-ChampApi)) {
        if (Get-NetTCPConnection -State Listen -LocalPort $ApiPort -ErrorAction SilentlyContinue) {
            throw "Порт API $ApiPort занят неизвестным приложением. Выберите другой -ApiPort."
        }
        $champApiPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
        if (-not (Test-Path -LiteralPath $champApiPython)) {
            throw 'Сначала выполните ./setup.ps1.'
        }
        $champOwnedApi = Start-Process -FilePath $champApiPython -WindowStyle Hidden -PassThru `
            -WorkingDirectory $PSScriptRoot -ArgumentList @(
                '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend',
                '--host', '127.0.0.1', '--port', "$ApiPort", '--no-access-log'
            )
        $champReady = $false
        for ($champAttempt = 0; $champAttempt -lt 15; $champAttempt++) {
            if (Test-ChampApi) { $champReady = $true; break }
            if ($champOwnedApi.HasExited) { break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $champReady) { throw 'API не запустился. Проверьте SQL Server и .env; подробности: runtime/api.log.' }
    }
    Write-Host "Откройте http://127.0.0.1:$WebPort. Терминал оставьте открытым; остановка — Ctrl+C."
    & './start_streamlit.ps1' -Port $WebPort -ApiPort $ApiPort
} finally {
    # Останавливается только процесс, созданный именно этим запуском.
    if ($champOwnedApi -and -not $champOwnedApi.HasExited) {
        Stop-Process -Id $champOwnedApi.Id -ErrorAction SilentlyContinue
    }
}
