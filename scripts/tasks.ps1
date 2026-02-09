param(
  [Parameter(Position=0)]
  [ValidateSet("help","install","install-user","test","test-models","test-golden","test-ralph","run-movers","run-watchlist","run-email","smoke")]
  [string]$Task = "help",

  [string]$Date = "2026-02-08",
  [int]$Top = 20,
  [ValidateSet("us","il","uk","eu","crypto")]
  [string]$Region = "us",
  [string]$Watchlist = "watchlist.yaml",
  [string]$Out = "",
  [string]$WatchOut = "runs/watchlist-demo",
  [string]$EmailOut = "runs/email-demo"
)

$ErrorActionPreference = "Stop"

function Get-PythonCmd {
  if (Get-Command py -ErrorAction SilentlyContinue) {
    return @("py", "-3")
  }
  if (Get-Command python -ErrorAction SilentlyContinue) {
    return @("python")
  }
  throw "No Python interpreter found. Install Python 3 and ensure 'py' or 'python' is on PATH."
}

function Run-Py {
  param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
  $py = Get-PythonCmd
  if ($py.Length -eq 1) {
    & $py[0] @Args
  } else {
    & $py[0] $py[1] @Args
  }
}

if (-not $Out) { $Out = "runs/$Date" }

switch ($Task) {
  "help" {
    Write-Host "Tasks:"
    Write-Host "  .\\scripts\\tasks.ps1 install"
    Write-Host "  .\\scripts\\tasks.ps1 install-user"
    Write-Host "  .\\scripts\\tasks.ps1 test"
    Write-Host "  .\\scripts\\tasks.ps1 run-movers -Date 2026-02-08 -Top 20 -Region us -Out runs/2026-02-08"
    Write-Host "  .\\scripts\\tasks.ps1 run-watchlist -Watchlist watchlist.yaml -WatchOut runs/watchlist-demo"
    Write-Host "  .\\scripts\\tasks.ps1 run-email -Date 2026-02-08 -Out runs/email-demo"
    Write-Host "  .\\scripts\\tasks.ps1 smoke"
  }
  "install" {
    Run-Py -m pip install -r requirements.txt -r requirements-dev.txt
  }
  "install-user" {
    Run-Py -m pip install --user -r requirements.txt -r requirements-dev.txt
  }
  "test" {
    Run-Py -m pytest -q -s
  }
  "test-models" {
    Run-Py -m pytest tests/test_models.py -q -s
  }
  "test-golden" {
    Run-Py -m pytest tests/test_golden_run.py -q -s
  }
  "test-ralph" {
    Run-Py -m pytest tests/ralphing_harness.py -q -s
  }
  "run-movers" {
    Run-Py -m daily_movers run --date $Date --mode movers --top $Top --region $Region --out $Out
  }
  "run-watchlist" {
    Run-Py -m daily_movers run --mode watchlist --watchlist $Watchlist --out $WatchOut
  }
  "run-email" {
    Run-Py -m daily_movers run --date $Date --mode movers --top $Top --region $Region --send-email --out $EmailOut
  }
  "smoke" {
    Run-Py -m pytest -q -s
    Run-Py -m daily_movers run --date $Date --mode movers --top $Top --region $Region --out $Out
    Run-Py -m daily_movers run --mode watchlist --watchlist $Watchlist --out $WatchOut
  }
}
