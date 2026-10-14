param([string]$PlantUmlJar = (Join-Path $PSScriptRoot '../tools/plantuml-1.2026.8.jar'))
$ErrorActionPreference = 'Stop'
$champRoot = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $PlantUmlJar)) {
    throw 'Нужен локальный PlantUML JAR. См. docs/diagrams/README.md. Исходники никуда не отправляются.'
}
$champJar = (Resolve-Path -LiteralPath $PlantUmlJar).Path
$champDiagrams = @('use-cases', 'activity', 'classes') | ForEach-Object {
    Join-Path $champRoot "docs/diagrams/$_.puml"
}
foreach ($champFormat in @('-tsvg', '-tpng')) {
    & java '-Djava.awt.headless=true' '-DPLANTUML_LIMIT_SIZE=12000' -jar $champJar -charset UTF-8 -Playout=smetana -failfast2 $champFormat @champDiagrams
    if ($LASTEXITCODE -ne 0) { throw "Ошибка PlantUML ($champFormat). Проверьте синтаксис диаграмм." }
}
Write-Host 'Три UML-диаграммы экспортированы в SVG и PNG. Проверьте изображения перед сдачей.'
