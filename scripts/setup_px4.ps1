# PowerShell script to setup PX4-Autopilot
$PX4_DIR = Join-Path $PSScriptRoot "..", "..", "PX4-Autopilot"
$PX4_DIR = [System.IO.Path]::GetFullPath($PX4_DIR)

Write-Host "Checking for PX4-Autopilot at: $PX4_DIR"

if (-not (Test-Path $PX4_DIR)) {
    Write-Host "PX4-Autopilot not found. Cloning..."
    try {
        git clone https://github.com/PX4/PX4-Autopilot.git $PX4_DIR --recursive
        if ($LASTEXITCODE -eq 0) {
            Write-Host "PX4-Autopilot cloned successfully." -ForegroundColor Green
        }
        else {
            Write-Error "Failed to clone PX4-Autopilot. Please clone manually to $PX4_DIR."
            exit 1
        }
    }
    catch {
        Write-Error "Failed to execute git. Is git installed?"
        exit 1
    }
}
else {
    Write-Host "PX4-Autopilot already exists." -ForegroundColor Green
}

Write-Host "PX4 Setup Complete."
Write-Host "To run SITL, open WSL and navigate to: $PX4_DIR"
Write-Host "Then run: make px4_sitl gz_x500"
