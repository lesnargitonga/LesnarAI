param(
  [switch]$InvertMask,
  [switch]$UseDepth,
  [int]$Hz = 10,
  [double]$BaseSpeed = 0.8,
  [double]$MinMotion = 0.5,
  [double]$CreepSpeed = 0.5,
  [double]$OpenThresh = 0.55,
  [double]$CommitSecs = 2.5,
  [double]$LookaheadM = 3.5,
  [string]$LogCsv = "",
  [string]$RecordDir = "",
  [switch]$LowImpact,
  [int]$StaggerSeconds = 0
)

# Resolve repo root
$Root = Split-Path -Parent $PSScriptRoot
Write-Host "[INFO] Repo root: $Root"

# Run logs
$logsDir = Join-Path $Root 'logs'
if (!(Test-Path $logsDir)) { New-Item -ItemType Directory -Path $logsDir | Out-Null }
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'

# Helper to start a background process with stdout/stderr redirected to log files
function Start-LoggedProcess {
  param(
    [string]$Title,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory,
    [string]$StdoutPath,
    [string]$StderrPath,
    [switch]$LowPrio
  )

  $startParams = @{
    FilePath               = $FilePath
    ArgumentList           = $ArgumentList
    WorkingDirectory       = $WorkingDirectory
    NoNewWindow            = $true
    RedirectStandardOutput = $StdoutPath
    RedirectStandardError  = $StderrPath
    PassThru               = $true
  }

  $proc = Start-Process @startParams

  if ($LowPrio -and $proc) {
    try { $proc.PriorityClass = 'BelowNormal' } catch { }
  }

  Write-Host "[STARTED] $Title (pid=$($proc.Id))"
  Write-Host "         stdout: $StdoutPath"
  Write-Host "         stderr: $StderrPath"
  return $proc
}

function Tail-Log {
  param([string]$Path, [int]$Lines = 30)
  if (Test-Path $Path) {
    Write-Host "[LOG] Last $Lines lines of $Path" -ForegroundColor Yellow
    Get-Content -Path $Path -Tail $Lines | ForEach-Object { "  $_" } | Write-Host
  }
}

# Simple TCP port waiter
function Wait-Port {
  param([string]$Hostname = '127.0.0.1', [int]$Port, [int]$TimeoutSec = 20)
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $client = New-Object System.Net.Sockets.TcpClient
      $iar = $client.BeginConnect($Hostname, $Port, $null, $null)
      $success = $iar.AsyncWaitHandle.WaitOne(500)
      if ($success -and $client.Connected) { $client.Close(); return $true }
      $client.Close()
    } catch { }
  }
  return $false
}

# Backend
$backendPy = Join-Path $Root 'backend-env/Scripts/python.exe'
$backendExe = if (Test-Path $backendPy) { $backendPy } else { 'python' }
Write-Host "[INFO] Backend Python: $backendExe"

$backendOut = Join-Path $logsDir ("backend_$ts.out.log")
$backendErr = Join-Path $logsDir ("backend_$ts.err.log")

$backendProc = Start-LoggedProcess -Title 'Lesnar AI Backend' -FilePath $backendExe -ArgumentList @('app.py') -WorkingDirectory (Join-Path $Root 'backend') -StdoutPath $backendOut -StderrPath $backendErr -LowPrio:$LowImpact
if ($StaggerSeconds -gt 0) { Start-Sleep -Seconds $StaggerSeconds } else { Start-Sleep -Seconds 2 }

# Wait for backend to listen on 5000 (best-effort, 15s)
if (Wait-Port -Port 5000 -TimeoutSec 15) {
  Write-Host "[READY] Backend listening on http://localhost:5000"
} else {
  Write-Host "[WARN] Backend not confirmed on port 5000." -ForegroundColor Yellow
  Tail-Log -Path $backendErr -Lines 40
  Write-Host "[HINT] If you see missing modules, run setup: .\\setup.bat" -ForegroundColor Yellow
}

# Frontend
$frontendOut = Join-Path $logsDir ("frontend_$ts.out.log")
$frontendErr = Join-Path $logsDir ("frontend_$ts.err.log")

$frontendProc = Start-LoggedProcess -Title 'Lesnar AI Frontend' -FilePath 'cmd.exe' -ArgumentList @('/c', 'npm', 'start') -WorkingDirectory (Join-Path $Root 'frontend') -StdoutPath $frontendOut -StderrPath $frontendErr -LowPrio:$LowImpact
if ($StaggerSeconds -gt 0) { Start-Sleep -Seconds $StaggerSeconds } else { Start-Sleep -Seconds 2 }

if (Wait-Port -Port 3000 -TimeoutSec 25) {
  Write-Host "[READY] Frontend listening on http://localhost:3000"
} else {
  Write-Host "[WARN] Frontend not confirmed on port 3000." -ForegroundColor Yellow
  Tail-Log -Path $frontendErr -Lines 40
  Write-Host "[HINT] If npm dependencies are missing, run: .\\setup.bat" -ForegroundColor Yellow
}

# Choose Python for autonomy: prefer venv under airsim-env
$venvPy = Join-Path $Root 'airsim-env/Scripts/python.exe'
$py = if (Test-Path $venvPy) { "`"$venvPy`"" } else { 'python' }
Write-Host "[INFO] Autonomy Python: $py"

# Lower workload if LowImpact
if ($LowImpact) {
  $Hz = [Math]::Max(5, [int][Math]::Floor($Hz / 2))
  Write-Host "[INFO] LowImpact mode: reducing autonomy Hz to $Hz and setting low process priority"
}

# Build autonomy command
$autoArgs = @(
  "`"$Root/airsim/segmentation_autonomy.py`"",
  "--hz $Hz",
  "--base_speed $BaseSpeed",
  "--min_motion $MinMotion",
  "--creep_speed $CreepSpeed",
  "--open_thresh $OpenThresh",
  "--commit_secs $CommitSecs",
  "--lookahead_m $LookaheadM"
)
if ($InvertMask) { $autoArgs += "--invert_mask" }
if ($UseDepth) { $autoArgs += "--use_depth" }

# Logging and recording paths
if ([string]::IsNullOrWhiteSpace($LogCsv)) {
  $LogCsv = Join-Path $logsDir ("seg_diag_" + $ts + ".csv")
}
$autoArgs += "--log_csv `"$LogCsv`""

if (-not [string]::IsNullOrWhiteSpace($RecordDir)) {
  $autoArgs += "--record `"$RecordDir`""
}

# Ensure AirSim RPC is likely ready (default 127.0.0.1:41451)
if (Wait-Port -Port 41451 -TimeoutSec 20) {
  Write-Host "[READY] AirSim RPC appears available on 127.0.0.1:41451"
} else {
  Write-Host "[WARN] AirSim RPC not confirmed on 127.0.0.1:41451; autonomy may retry/fail"
}

$autoOut = Join-Path $logsDir ("autonomy_$ts.out.log")
$autoErr = Join-Path $logsDir ("autonomy_$ts.err.log")

# Start autonomy via PowerShell so we can pass the python executable cleanly
$autoCmd = "Set-Location '$Root'; $py -u $($autoArgs -join ' ')"
$autoProc = Start-LoggedProcess -Title 'Lesnar AI Autonomy' -FilePath 'powershell.exe' -ArgumentList @('-NoProfile', '-Command', $autoCmd) -WorkingDirectory $Root -StdoutPath $autoOut -StderrPath $autoErr -LowPrio:$LowImpact

Write-Host ""
Write-Host "All components launched:" -ForegroundColor Green
Write-Host "  - Backend   : http://localhost:5000"
Write-Host "  - Frontend  : http://localhost:3000"
Write-Host "  - Autonomy  : logs at $LogCsv"
Write-Host ""
Write-Host "Notes:"
Write-Host "  - Make sure your Unreal + AirSim level is running before autonomy connects."
Write-Host "  - To stop: Stop-Process -Id $($backendProc.Id),$($frontendProc.Id),$($autoProc.Id)"
