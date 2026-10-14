param([ValidateRange(1, 1000)][int]$MaxLines = 250)
$ErrorActionPreference = 'Stop'
$champFragmentRoot = Split-Path -Parent $PSScriptRoot

# Учебный лимит: физические строки, включая комментарии и пустые строки.
# БД, резервный Vue, документы, зависимости и результаты сборки не входят в учебный маршрут.
$champExcludedFolders = @(
    '.git', '.venv', '.venv-streamlit', 'node_modules', 'bin', 'obj', 'dist', 'runtime',
    '__pycache__', '.pytest_cache', 'TestResults', 'database', 'web'
)
$champCodeExtensions = @(
    '.py', '.cs', '.xaml', '.vue', '.js', '.ts', '.css', '.html', '.ps1', '.cjs', '.mjs'
)

function Get-ChampSourceFiles([string]$Folder) {
    foreach ($champEntry in Get-ChildItem -LiteralPath $Folder) {
        if ($champEntry.PSIsContainer) {
            if ($champEntry.Name -notin $champExcludedFolders) {
                Get-ChampSourceFiles $champEntry.FullName
            }
        }
        elseif ($champEntry.Extension -in $champCodeExtensions) {
            $champEntry
        }
    }
}

$champFragmentRows = @(
    foreach ($champSource in Get-ChampSourceFiles $champFragmentRoot) {
        $champRelative = $champSource.FullName.Substring($champFragmentRoot.Length + 1)
        $champLineCount = [System.IO.File]::ReadAllLines($champSource.FullName).Count
        $champKind = if ($champRelative -match '^backend[\\/]app[\\/]') { 'Python API' }
        elseif ($champRelative -match '^desktop[\\/](tests|checks|checks-wpf)[\\/]') { 'Tests' }
        elseif ($champRelative -match '^(backend|web)[\\/]tests[\\/]') { 'Tests' }
        elseif ($champRelative -match '^desktop[\\/]') { 'WPF' }
        elseif ($champRelative -match '^web_streamlit[\\/]tests[\\/]') { 'Tests' }
        elseif ($champRelative -match '^web_streamlit[\\/]') { 'Streamlit' }
        elseif ($champRelative -match '^web[\\/]src[\\/]' -or $champRelative -match '^web[\\/]index.html$') { 'Web' }
        else { 'Tools' }
        [pscustomobject]@{
            Part = $champKind
            File = $champRelative
            Lines = $champLineCount
            Result = if ($champLineCount -le $MaxLines) { 'OK' } else { 'TOO LONG' }
        }
    }
)

$champFragmentRows | Sort-Object Part, File | Format-Table -AutoSize
$champOversized = @($champFragmentRows | Where-Object Lines -gt $MaxLines)
$champTotalLines = ($champFragmentRows | Measure-Object Lines -Sum).Sum
$champPeakLines = ($champFragmentRows | Measure-Object Lines -Maximum).Maximum
Write-Host "Files: $($champFragmentRows.Count); lines: $champTotalLines; largest: $champPeakLines; limit: $MaxLines."
if ($champOversized.Count -gt 0) {
    Write-Error "$($champOversized.Count) fragment(s) exceed the learning limit of $MaxLines lines."
    exit 1
}
Write-Host 'PASS: every active source fragment fits the limit. SQL and legacy Vue (web/) are excluded.'
