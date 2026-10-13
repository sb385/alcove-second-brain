# Registers the Windows scheduled task: sync every 2 hours from 08:00 to 20:00
# (08, 10, 12, 14, 16, 18, 20). This PC's clock is IST. The 08:00 run also sends
# the WhatsApp summary. StartWhenAvailable catches up if the PC was off; a run
# that is still going when the next one is due is not doubled up.
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "run_routine_local.ps1"   # API-key mode: run_daily.ps1
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At 8:00AM
$repeat = New-ScheduledTaskTrigger -Once -At 8:00AM -RepetitionInterval (New-TimeSpan -Hours 2) `
    -RepetitionDuration (New-TimeSpan -Hours 12 -Minutes 1)
$trigger.Repetition = $repeat.Repetition
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 90)
Register-ScheduledTask -TaskName "Alcove Second Brain" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Second-brain sync every 2h, 08:00-20:00 IST" -Force
