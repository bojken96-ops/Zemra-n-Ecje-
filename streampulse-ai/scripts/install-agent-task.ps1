# Registers a Scheduled Task that starts the capture agent when you sign in (interactive session).
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $root ".venv-agent\Scripts\pythonw.exe"
$action = New-ScheduledTaskAction -Execute $python -Argument "-m capture.agent run" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
  -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "StreamPulse Capture Agent" -Action $action -Trigger $trigger `
  -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Registered 'StreamPulse Capture Agent'. It starts at your next sign-in (or: Start-ScheduledTask 'StreamPulse Capture Agent')."
