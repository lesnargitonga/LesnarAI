# Convenience wrapper to launch backend, frontend, and autonomy with recommended defaults
param(
  [switch]$InvertMask,
  [switch]$UseDepth,
  [switch]$LowImpact,
  [int]$StaggerSeconds = 0
)
$script = Join-Path $PSScriptRoot '../scripts/start_everything.ps1'
if (-not (Test-Path $script)) {
  Write-Error "Launcher not found: $script"
  exit 1
}
# Call the orchestrator directly so switch parameters remain typed
& $script @PSBoundParameters
