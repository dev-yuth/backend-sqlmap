# Runs the Flask app using the project's virtual environment Python
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path $projectRoot  # go up from scripts/ to project root

$venvPython = Join-Path $projectRoot ".venv/Scripts/python.exe"
$appPy = Join-Path $projectRoot "app.py"

if (-not (Test-Path $venvPython)) {
  Write-Error ".venv not found. Please run scripts/install.ps1 first."
}

if (-not (Test-Path $appPy)) {
  Write-Error "app.py not found at $appPy"
}

Write-Host "[run] Starting server..."
& $venvPython $appPy
