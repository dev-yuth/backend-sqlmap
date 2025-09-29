# Creates a virtual environment and installs dependencies
$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path $projectRoot  # go up from scripts/ to project root

Write-Host "[install] Project root: $projectRoot"

# Create venv if missing
$venvPython = Join-Path $projectRoot ".venv/Scripts/python.exe"
if (-not (Test-Path $venvPython)) {
  Write-Host "[install] Creating virtual environment..."
  python -m venv (Join-Path $projectRoot ".venv")
}

# Install requirements using venv's pip
$req = Join-Path $projectRoot "requirements.txt"
if (-not (Test-Path $req)) {
  Write-Error "requirements.txt not found at $req"
}

Write-Host "[install] Installing dependencies from requirements.txt..."
& $venvPython -m pip install -r $req

Write-Host "[install] Done."
