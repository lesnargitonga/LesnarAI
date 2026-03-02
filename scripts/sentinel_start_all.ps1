param(
  [switch]$SkipSmoke
)

# Orchestrates: AirSim settings -> Firewall -> PX4 SITL (WSL) -> Unreal -> Wait RPC -> Smoke test

$Root = Split-Path -Parent $PSScriptRoot
Write-Host "[INFO] Repo root: $Root"

function Wait-Port {
  param([string]$TargetHost = '127.0.0.1', [int]$Port, [int]$TimeoutSec = 180)
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $client = New-Object System.Net.Sockets.TcpClient
      $iar = $client.BeginConnect($TargetHost, $Port, $null, $null)
      $success = $iar.AsyncWaitHandle.WaitOne(1000)
      if ($success -and $client.Connected) { $client.Close(); return $true }
      $client.Close()
    } catch { }
  }
  return $false
}

# 1) Ensure AirSim settings
Write-Host "[STEP] Installing AirSim settings preset (PX4 UDP)..."
try {
  & "$Root/scripts/install_airsim_settings.ps1" -Preset 'px4_udp'
} catch {
  Write-Error "AirSim settings install failed: $($_.Exception.Message)"; exit 1
}

# Verify settings landed
$settingsPath = Join-Path $env:USERPROFILE 'Documents/AirSim/settings.json'
if (-not (Test-Path $settingsPath)) {
  Write-Error "AirSim settings not found at $settingsPath after install"; exit 1
}

# 2) Ensure Firewall rule (prompts for admin if needed)
Write-Host "[STEP] Ensuring firewall rule for UDP 14560..."
& "$Root/scripts/check_firewall_udp.ps1" -Port 14560
# Verify presence but don't fail the entire flow; user may have added it already
try {
  $fwRule = Get-NetFirewallRule -DisplayName 'AirSim PX4 UDP 14560' -ErrorAction SilentlyContinue | Where-Object { $_.Enabled -eq 'True' }
  if ($fwRule) {
    Write-Host "[OK] Firewall rule present and enabled."
  } else {
    Write-Warning "Firewall rule not confirmed. If AirSim/PX4 can't communicate, re-run firewall task as Administrator."
  }
} catch {
  Write-Warning "Could not verify firewall rule: $($_.Exception.Message)"
}

# 3) Start PX4 SITL (opens new window)
Write-Host "[STEP] Launching PX4 SITL (WSL)..."
& "$Root/scripts/start_px4_sitl_wsl.ps1"

# 4) Open Unreal solution
$cfgPath = Join-Path $Root 'sentinel.config.json'
$unrealSln = $null
if (Test-Path $cfgPath) {
  try { $cfg = Get-Content $cfgPath -Raw | ConvertFrom-Json; $unrealSln = $cfg.unreal_sln } catch { }
}
if (-not $unrealSln) { $unrealSln = 'J:/dronesim/dronesim.sln' }
Write-Host "[STEP] Opening Unreal solution: $unrealSln"
if (Test-Path $unrealSln) {
  Start-Process $unrealSln | Out-Null
} else {
  Write-Warning "Unreal solution not found at $unrealSln. Update sentinel.config.json."
}

Write-Host "[INFO] In Visual Studio, press F5 to launch the Editor, then click Play."

# 5) Wait for AirSim RPC (port 41451)
Write-Host "[STEP] Waiting for AirSim RPC on 127.0.0.1:41451 (up to 180s)..."
if (Wait-Port -Port 41451 -TimeoutSec 180) {
  Write-Host "[READY] AirSim RPC is available." -ForegroundColor Green
} else {
  Write-Warning "AirSim RPC not detected on 127.0.0.1:41451 within timeout. You can continue manually."
}

# 6) Smoke test (optional)
if (-not $SkipSmoke) {
  $venvPy = Join-Path $Root 'airsim-env/Scripts/python.exe'
  $pyExe = if (Test-Path $venvPy) { $venvPy } else { 'python' }
  $smokeScript = Join-Path $Root 'scripts/wait_for_airsim_and_move.py'
  Write-Host "[STEP] Running AirSim smoke test (simple move)..."
  Push-Location $Root
  try {
    & $pyExe $smokeScript --wait 30
  } catch {
    Write-Warning "Smoke test failed: $($_.Exception.Message)"
  } finally {
    Pop-Location
  }
}

Write-Host ""
Write-Host "All steps complete (Start All). Review PX4 and Unreal windows for status." -ForegroundColor Green
Write-Host "If smoke test ran, the drone should have taken off, moved briefly, and landed."
