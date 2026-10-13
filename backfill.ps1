# One-time catch-up: read the last N days of Gmail + WhatsApp in 5-day windows,
# oldest first, so later messages can close items opened earlier.
#   powershell -ExecutionPolicy Bypass -File .\backfill.ps1 [-Days 30] [-ChunkDays 5]
# Scheduled syncs pause while this runs (lock file). Progress: logs\backfill.log
param([int]$Days = 30, [int]$ChunkDays = 5)
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
# Keep the PC awake while this runs; Windows releases it when the script exits.
try {
  Add-Type -Namespace SB -Name Power -MemberDefinition '[DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);' -ErrorAction Stop
  [SB.Power]::SetThreadExecutionState(0x80000001) | Out-Null   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
} catch {}
New-Item -ItemType Directory -Force -Path "logs", ".run" | Out-Null
$blog = "logs\backfill.log"
function BLog($m) { $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $m"; $line | Out-File $blog -Append -Encoding utf8; Write-Output $line }

$lock = ".run\backfill.lock"
Set-Content $lock "started $(Get-Date -Format o)"
$end = [DateTimeOffset]::Now
$start = $end.AddDays(-$Days)
$n = [Math]::Ceiling($Days / $ChunkDays)
BLog "backfill start: $($start.ToString('dd MMM')) -> now, $n windows of $ChunkDays days"
try {
  for ($i = 0; $i -lt $n; $i++) {
    $s = $start.AddDays($i * $ChunkDays)
    $u = if ($i -eq $n - 1) { $end } else { $start.AddDays(($i + 1) * $ChunkDays) }
    (Get-Item $lock).LastWriteTime = Get-Date   # keep the lock fresh
    BLog "window $($i + 1)/$n : $($s.ToString('dd MMM HH:mm')) -> $($u.ToString('dd MMM HH:mm'))"
    & powershell -NoProfile -ExecutionPolicy Bypass -File .\run_routine_local.ps1 -Backfill -Since $s.ToString("o") -Until $u.ToString("o")
    BLog "window $($i + 1)/$n done (exit $LASTEXITCODE)"
  }
} finally {
  Remove-Item $lock -ErrorAction SilentlyContinue
  BLog "backfill finished; scheduled syncs resume"
}
