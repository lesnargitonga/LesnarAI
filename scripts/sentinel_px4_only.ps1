param(
  [int]$UdpPort = 14560
)

$Root = Split-Path -Parent $PSScriptRoot
Write-Host "[INFO] Repo root: $Root"

# Install AirSim settings
Write-Host "[STEP] Installing AirSim settings preset (PX4 UDP)..."
& "$Root/scripts/install_airsim_settings.ps1" -Preset 'px4_udp'

# Ensure Firewall rule (may prompt for admin)
Write-Host "[STEP] Ensuring firewall rule for UDP $UdpPort..."
& "$Root/scripts/check_firewall_udp.ps1" -Port $UdpPort

# Open PX4 WSL shell in PX4 dir
Write-Host "[STEP] Opening PX4 shell in WSL..."
& "$Root/scripts/start_px4_sitl_wsl.ps1" -UdpPort $UdpPort

Write-Host "[NEXT] In the new WSL window, run the px4 binary to start SITL, then at pxh> run: simulator_mavlink start -u $UdpPort" -ForegroundColor Yellow
Write-Host "[NEXT] Launch Unreal manually (open your project and click Play)." -ForegroundColor Yellow
