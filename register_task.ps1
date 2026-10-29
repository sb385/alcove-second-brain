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
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 90)
Register-ScheduledTask -TaskName "Alcove Second Brain" -Action $action -Trigger $trigger `
    -Settings $settings -Description "Second-brain sync every 2h, 08:00-20:00 IST" -Force

# Every 5 minutes: if a site redeploy wiped the dashboard, upload it again.
# No Claude involved; pythonw runs without a console window.
$fill = New-ScheduledTaskAction -Execute (Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe") `
    -Argument "-m secondbrain.publish --if-empty" -WorkingDirectory $PSScriptRoot
$every10 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 5)
$fillSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "Alcove Second Brain - keep site filled" -Action $fill -Trigger $every10 `
    -Settings $fillSettings -Description "Re-upload the dashboard if a redeploy left the site empty" -Force

# Every 30 minutes: read new/changed team tracker files (OneDrive\Alcove Trackers\<Project>).
# Claude is only used when a file actually changed.
$trk = New-ScheduledTaskAction -Execute (Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe") `
    -Argument "-m secondbrain.trackers" -WorkingDirectory $PSScriptRoot
$every30 = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 30)
$trkSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 60)
Register-ScheduledTask -TaskName "Alcove Second Brain - trackers" -Action $trk -Trigger $every30 `
    -Settings $trkSettings -Description "Read new/changed team tracker files into the Tasks sheet" -Force
