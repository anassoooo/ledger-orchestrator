param(
    [switch]$SkipDocker,
    [switch]$OpenArtifacts
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$outputsRoot = Join-Path $projectRoot 'outputs'

$run = Get-ChildItem -LiteralPath $outputsRoot -Directory |
    Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName 'report.json')) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName 'STAR_consolide.xlsx'))
    } |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $run) {
    throw 'Aucune exécution démontrable contenant report.json et STAR_consolide.xlsx.'
}

$reportPath = Join-Path $run.FullName 'report.json'
$workbookPath = Join-Path $run.FullName 'STAR_consolide.xlsx'
$anomaliesPath = Join-Path $run.FullName 'anomalies.csv'
$reviewPath = Join-Path $run.FullName 'cellules_a_revoir.csv'
$report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json

Write-Host ''
Write-Host 'LedgerOrchestrator - contrôle de démonstration' -ForegroundColor Cyan
Write-Host "Run        : $($report.run_id)"
Write-Host "Entreprise : $($report.company)"
Write-Host "Exercices  : $($report.years -join ', ')"
Write-Host "Unité      : $($report.target_unit)"
Write-Host "Statut     : $($report.status)"
Write-Host "Écritures  : $($report.written_cells)"
Write-Host "Anomalies  : $(@($report.issues).Count)"
Write-Host "À revoir   : $(@($report.review).Count)"

Write-Host ''
Write-Host 'Couverture des cellules cibles' -ForegroundColor Cyan
$coverage = foreach ($item in $report.coverage.summary) {
    [pscustomobject]@{
        Exercice = $item.year
        Feuille = $item.sheet
        Validees = [int]$item.counts.populated_this_run
        Attendues = [int]$item.expected_cells
        A_revoir = [int]$item.counts.missing_or_blocked
    }
}
$coverage | Format-Table -AutoSize

if (-not $SkipDocker) {
    Push-Location $projectRoot
    try {
        docker compose up -d engine gateway | Out-Host
        $health = $null
        for ($attempt = 1; $attempt -le 12; $attempt++) {
            try {
                $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/health' -TimeoutSec 3
                break
            }
            catch {
                Start-Sleep -Seconds 5
            }
        }
        if (-not $health) {
            throw 'API locale non disponible après 60 secondes.'
        }
        Write-Host ''
        Write-Host "API status : $($health.status)" -ForegroundColor Green
        Write-Host "Local only : $($health.local_only)" -ForegroundColor Green
        Write-Host "Report API : http://127.0.0.1:8000/runs/$($report.run_id)/report"
    }
    finally {
        Pop-Location
    }
}

Write-Host ''
Write-Host 'Fichiers de démonstration' -ForegroundColor Cyan
Write-Host "Classeur   : $workbookPath"
Write-Host "Anomalies  : $anomaliesPath"
Write-Host "Revue      : $reviewPath"

if ($OpenArtifacts) {
    Start-Process -FilePath $workbookPath
    Start-Process -FilePath $anomaliesPath
    Start-Process -FilePath $reviewPath
}
