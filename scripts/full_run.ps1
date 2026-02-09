<#
.SYNOPSIS
    Complete Daily Movers run: 60 stocks across all markets with SMTP email delivery.

.DESCRIPTION
    This script runs a full pipeline covering:
    - 20 US large-cap stocks
    - 10 Israeli (TASE) stocks
    - 10 UK (London) stocks
    - 10 European stocks
    - 10 Crypto assets

    Outputs:
    - digest.html (opens automatically)
    - report.xlsx
    - digest.eml
    - archive.jsonl
    - run.json + run.log

    Email is sent via Ethereal SMTP using credentials.csv in the project root.

.PARAMETER Top
    Number of symbols to process (default: 60, the full watchlist)

.PARAMETER NoOpen
    If specified, don't auto-open digest.html after the run

.PARAMETER DryRun
    If specified, just print what would be executed without running

.EXAMPLE
    .\scripts\full_run.ps1

.EXAMPLE
    .\scripts\full_run.ps1 -Top 30 -NoOpen
#>

# PSScriptAnalyzer -IgnoreRule PSUseDeclaredVarsMoreThanAssignments

param(
    [int]$Top = 60,
    [switch]$NoOpen,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Paths
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$WatchlistPath = Join-Path $ProjectRoot "watchlist_all_exchanges_60.yaml"
$CredsPath = Join-Path $ProjectRoot "credentials.csv"

# Date (today in UTC)
$Today = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
$Timestamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH-mm-ssZ")
$RunsDir = Join-Path $ProjectRoot "runs"
$OutDir = Join-Path $RunsDir "full-run-$Timestamp"

# Header
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "   Daily Movers - Full Multi-Market Run" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Checking prerequisites..." -ForegroundColor Yellow

# Check watchlist
if (-not (Test-Path $WatchlistPath)) {
    Write-Host "  [ERROR] Watchlist not found: $WatchlistPath" -ForegroundColor Red
    exit 1
}
Write-Host "  [OK] Watchlist: $WatchlistPath" -ForegroundColor Green

# Check credentials.csv for SMTP
$SendEmail = $false
if (-not (Test-Path $CredsPath)) {
    Write-Host "  [WARN] credentials.csv not found - email will NOT be sent" -ForegroundColor Yellow
    Write-Host "         To enable email: download credentials.csv from https://ethereal.email/create" -ForegroundColor Yellow
}
else {
    Write-Host "  [OK] SMTP credentials: $CredsPath" -ForegroundColor Green
    $SendEmail = $true
}

# Count symbols in watchlist
$SymbolCount = (Get-Content $WatchlistPath | Select-String "^\s*-\s+\w").Count
Write-Host "  [OK] Symbols in watchlist: $SymbolCount" -ForegroundColor Green

# Configuration summary
Write-Host ""
Write-Host "Run Configuration:" -ForegroundColor Yellow
Write-Host "  Date:        $Today"
Write-Host "  Mode:        watchlist"
Write-Host "  Watchlist:   watchlist_all_exchanges_60.yaml"
Write-Host "  Top:         $Top"
Write-Host "  Output:      $OutDir"
Write-Host "  Send Email:  $SendEmail"
Write-Host "  Auto-Open:   $(-not $NoOpen)"

if ($DryRun) {
    Write-Host ""
    Write-Host "[DRY RUN] Would execute the above configuration. Exiting." -ForegroundColor Magenta
    exit 0
}

# Environment variables for stability
$env:MAX_WORKERS = "2"
$env:REQUEST_TIMEOUT_SECONDS = "30"
$env:OPENAI_TIMEOUT_SECONDS = "60"
$env:PYTHONUTF8 = "1"

Write-Host ""
Write-Host "Starting pipeline..." -ForegroundColor Yellow
Write-Host "  This may take 2-5 minutes depending on network"
Write-Host ""

# Build command
$PythonArgs = @(
    "-3", "-m", "daily_movers", "run",
    "--date", $Today,
    "--mode", "watchlist",
    "--watchlist", $WatchlistPath,
    "--top", $Top.ToString(),
    "--out", $OutDir
)

if ($SendEmail) {
    # Load SMTP credentials from CSV
    $CsvContent = Import-Csv $CredsPath
    $SmtpRow = $CsvContent | Where-Object { $_.Service -eq "SMTP" } | Select-Object -First 1
    
    if ($SmtpRow) {
        $env:SMTP_HOST = $SmtpRow.Hostname
        $env:SMTP_PORT = $SmtpRow.Port
        $env:SMTP_SSL_PORT = "465"
        $env:SMTP_USERNAME = $SmtpRow.Username
        $env:SMTP_PASSWORD = $SmtpRow.Password
        $env:FROM_EMAIL = $SmtpRow.Username
        $env:SELF_EMAIL = $SmtpRow.Username
        
        $PythonArgs += "--send-email"
        Write-Host "  SMTP configured: $($SmtpRow.Hostname)" -ForegroundColor Cyan
    }
}

if ($NoOpen) {
    $PythonArgs += "--no-open"
}

# Run
$StartTime = Get-Date
Write-Host "----------------------------------------------------------------" -ForegroundColor DarkGray

try {
    & py @PythonArgs
    $ExitCode = $LASTEXITCODE
}
catch {
    Write-Host ""
    Write-Host "[ERROR] Pipeline failed: $_" -ForegroundColor Red
    exit 1
}

Write-Host "----------------------------------------------------------------" -ForegroundColor DarkGray

$EndTime = Get-Date
$Duration = $EndTime - $StartTime

# Summary
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "   Run Complete" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

if ($ExitCode -eq 0) {
    Write-Host ""
    Write-Host "  Status:   SUCCESS" -ForegroundColor Green
}
else {
    Write-Host ""
    Write-Host "  Status:   PARTIAL/FAILED (exit code $ExitCode)" -ForegroundColor Yellow
}

Write-Host "  Duration: $($Duration.Minutes)m $($Duration.Seconds)s"
Write-Host "  Output:   $OutDir"

# List artifacts
if (Test-Path $OutDir) {
    Write-Host ""
    Write-Host "Artifacts:" -ForegroundColor Yellow
    Get-ChildItem -Path $OutDir | ForEach-Object {
        $Size = if ($_.Length -gt 1024) { "{0:N1} KB" -f ($_.Length / 1024) } else { "$($_.Length) B" }
        Write-Host "  - $($_.Name) ($Size)"
    }
}

# Email viewing instructions
if ($SendEmail) {
    Write-Host ""
    Write-Host "Email sent via Ethereal!" -ForegroundColor Green
    Write-Host "  View it at: https://ethereal.email/login" -ForegroundColor Cyan
    Write-Host "  Username:   $($env:SMTP_USERNAME)" -ForegroundColor Cyan
}

Write-Host ""
exit $ExitCode
