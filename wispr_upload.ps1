# Uploads new Wispr Flow meetings/notes to the brain-data branch for the cloud routine.
# Logs to logs\wispr-upload.log. Registered hourly by register_wispr_upload.ps1.
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$log = "logs\wispr-upload.log"
function Log($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m" | Out-File $log -Append -Encoding utf8 }

$bash = "C:\Program Files\Git\bin\bash.exe"
& $bash scripts/brain_data.sh pull *>&1 | Out-File $log -Append -Encoding utf8
$env:DATA_DIR = ".brain-data/data"
& ".\.venv\Scripts\python.exe" -m secondbrain.wispr_upload *>&1 | Out-File $log -Append -Encoding utf8
& $bash scripts/brain_data.sh push "wispr upload $(Get-Date -Format 'yyyy-MM-dd HH:mm')" *>&1 | Out-File $log -Append -Encoding utf8
Log "done (exit $LASTEXITCODE)"
