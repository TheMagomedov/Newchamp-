$ErrorActionPreference = 'Stop'
$champRoot = Split-Path -Parent $PSScriptRoot
# Только рабочие исходники. Пустые строки и комментарии входят в Lines.
$champParts = [ordered]@{
    Backend = @(Get-ChildItem (Join-Path $champRoot 'backend/app') -File -Filter '*.py')
    Frontend = @(Get-ChildItem (Join-Path $champRoot 'web_streamlit') -File -Filter '*.py')
    Desktop = @(Get-ChildItem (Join-Path $champRoot 'desktop') -File | Where-Object Extension -in '.cs', '.xaml')
}
$champTotals = foreach ($champPart in $champParts.Keys) {
    $champCounts = foreach ($champFile in $champParts[$champPart]) {
        $champLines = [IO.File]::ReadAllLines($champFile.FullName)
        [pscustomobject]@{
            Lines = $champLines.Count
            NonBlank = @($champLines | Where-Object { $_.Trim().Length -gt 0 }).Count
        }
    }
    [pscustomobject]@{
        Part = $champPart
        Files = $champCounts.Count
        Lines = [int]($champCounts.Lines | Measure-Object -Sum).Sum
        NonBlank = [int]($champCounts.NonBlank | Measure-Object -Sum).Sum
    }
}
$champTotals | Format-Table -AutoSize
Write-Host "Total runtime lines: $(($champTotals.Lines | Measure-Object -Sum).Sum)"
Write-Host 'Excluded: database, tests/checks, launch tools, config, docs, libraries, generated builds and legacy Vue.'
Write-Host 'Physical lines are not equivalent to statements or learning time; some existing lines contain multiple statements.'
