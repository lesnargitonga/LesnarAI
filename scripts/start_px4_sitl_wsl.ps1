param(
  [string]$ConfigPath = (Join-Path (Split-Path -Parent $PSScriptRoot) 'sentinel.config.json'),
  [int]$UdpPort = 14560
)

function Read-Json($path) {
  if (-not (Test-Path $path)) { throw "Config not found: $path" }
  Get-Content $path -Raw | ConvertFrom-Json
}

$cfg = Read-Json $ConfigPath
$px4WinPath = $cfg.px4_path
$wslDistro = $cfg.wsl_distro

if (-not $px4WinPath) { throw "px4_path missing in $ConfigPath" }
if (-not $wslDistro) { $wslDistro = 'Ubuntu-24.04' }

# Convert Windows path to WSL path
function ConvertTo-WSLPath($winPath) {
  if (-not $winPath) { throw 'Empty path provided' }
  $drive = $winPath.Substring(0,1).ToLower()
  $rest = $winPath.Substring(2)
  # Normalize slashes and trim any leading slashes
  $rest = ($rest -replace '\\','/')
  $rest = $rest -replace '^/+',''
  "/mnt/$drive/$rest"
}

$px4WslPath = ConvertTo-WSLPath $px4WinPath
$px4Bin = "$px4WslPath/build/px4_sitl_default/bin/px4"

Write-Host "[INFO] Opening WSL shell for PX4 in distro '$wslDistro' at $px4WslPath" -ForegroundColor Cyan

# Build a bash script that changes to the PX4 dir, prints tips, then turns into an interactive shell
$bashCmd = "cd '$px4WslPath'; echo 'PX4 shell ready.'; echo 'Run:'; echo '  $px4Bin'; echo 'Then at pxh> run:'; echo '  simulator_mavlink start -u $UdpPort'; echo ''; exec bash"

# Open a new PowerShell window and keep it open (-NoExit), invoking WSL directly
$psCmd = "wsl.exe -d `"$wslDistro`" -- bash -lc `"$bashCmd`""
$psArgs = @('-NoExit','-Command', $psCmd)
Start-Process -FilePath 'powershell.exe' -ArgumentList $psArgs -WorkingDirectory (Split-Path -Parent $PSScriptRoot) -WindowStyle Normal | Out-Null

Write-Host "[STARTED] PX4 WSL shell opened. In that window, run the px4 binary shown above; when pxh> appears, type: simulator_mavlink start -u $UdpPort" -ForegroundColor Green
