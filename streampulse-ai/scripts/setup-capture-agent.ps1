# Creates the capture agent virtualenv and installs Playwright (uses your installed Google Chrome).
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
if (-not (Test-Path ".venv-agent")) { python -m venv .venv-agent }
.\.venv-agent\Scripts\python -m pip install --upgrade pip
.\.venv-agent\Scripts\pip install -r capture\requirements-agent.txt
# Chrome is used via channel="chrome"; install Playwright's Chromium too as a fallback option.
.\.venv-agent\Scripts\python -m playwright install chromium
New-Item -ItemType Directory -Force -Path storage\recordings | Out-Null
Write-Host "Capture agent installed. Next: .venv-agent\Scripts\python -m capture.agent login"
