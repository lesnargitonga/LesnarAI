param(
  [int]$Port = 14560,
  [string]$RuleName = 'AirSim PX4 UDP 14560'
)

function Test-IsAdmin {
  $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
}

# Ensure admin elevation (needed to create firewall rules)
if (-not (Test-IsAdmin)) {
  Write-Host "[INFO] Elevation required to create firewall rules. Requesting Administrator..."
  $scriptPath = $MyInvocation.MyCommand.Path
  $argList = "-ExecutionPolicy Bypass -File `"$scriptPath`" -Port $Port -RuleName `"$RuleName`""
  Start-Process -FilePath powershell.exe -ArgumentList $argList -Verb RunAs | Out-Null
  return
}

# Check if an inbound UDP rule for the port exists (enabled)
$rule = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Where-Object { $_.Enabled -eq 'True' }
if ($rule) {
  Write-Host "[OK] Firewall rule already present: $RuleName" -ForegroundColor Green
  return
}

Write-Host "[INFO] Creating inbound UDP firewall rule for port $Port ..."
try {
  New-NetFirewallRule -DisplayName $RuleName -Direction Inbound -Action Allow -Protocol UDP -LocalPort $Port -Profile Any | Out-Null
} catch {
  Write-Error "[ERR] Failed to create firewall rule: $($_.Exception.Message)"
  exit 1
}

# Verify creation
$rule = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue | Where-Object { $_.Enabled -eq 'True' }
if ($rule) {
  Write-Host "[OK] Firewall rule created: $RuleName" -ForegroundColor Green
} else {
  Write-Error "[ERR] Firewall rule not found after creation attempt. Try running PowerShell as Administrator."
  exit 1
}
