# Cloud mode: upload Wispr Flow data every hour (and at logon) so the 08:00
# cloud routine sees meetings recorded on this PC.
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "wispr_upload.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`"" `
    -WorkingDirectory $PSScriptRoot
$hourly = New-ScheduledTaskTrigger -Once -At (Get-Date).Date.AddHours((Get-Date).Hour + 1) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
$logon = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
Register-ScheduledTask -TaskName "Alcove Second Brain - Wispr upload" -Action $action `
    -Trigger @($hourly, $logon) -Settings $settings -Force | Out-Null
Write-Host "Registered hourly Wispr upload."
