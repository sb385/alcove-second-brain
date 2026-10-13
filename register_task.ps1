# Registers a Windows scheduled task that runs the job every day at 08:00.
# This PC's clock is on India Standard Time, so 08:00 local = 08:00 IST.
# StartWhenAvailable makes it catch up if the PC was off/asleep at 08:00.
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "run_routine_local.ps1"   # API-key mode: run_daily.ps1
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "Alcove Second Brain" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Daily 08:00 IST second-brain digest" -Force
Write-Host "Registered 'Alcove Second Brain' for 08:00 daily."
