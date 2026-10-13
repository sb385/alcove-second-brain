# Runs the daily second-brain job and appends output to logs\YYYY-MM.log
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
New-Item -ItemType Directory -Force -Path "logs" | Out-Null
$log = Join-Path "logs" ("{0:yyyy-MM}.log" -f (Get-Date))
"`n===== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') =====" | Out-File -FilePath $log -Append -Encoding utf8
& ".\.venv\Scripts\python.exe" -m secondbrain.main *>&1 | Out-File -FilePath $log -Append -Encoding utf8
exit $LASTEXITCODE
