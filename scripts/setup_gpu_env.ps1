Param(
    [string]$EnvName = "lesnar-ai-gpu",
    [string]$Workspace = "D:\\docs\\lesnar\\Lesnar AI"
)

Write-Host "Checking for Conda..." -ForegroundColor Cyan
$condaVersion = (conda --version 2>$null)
if (-not $condaVersion) {
    Write-Error "Conda not found. Please install Miniconda/Anaconda and run 'conda init powershell'."
    exit 1
}

$EnvFile = Join-Path $Workspace "scripts/conda-env-windows.yml"
if (-not (Test-Path $EnvFile)) {
    Write-Error "Environment file not found: $EnvFile"
    exit 1
}

# Check if env exists
$envList = conda env list | Out-String
if ($envList -match "\b$EnvName\b") {
    Write-Host "Conda env '$EnvName' already exists. Skipping creation." -ForegroundColor Yellow
} else {
    Write-Host "Creating Conda env '$EnvName' from $EnvFile..." -ForegroundColor Cyan
    conda env create -f "$EnvFile" | Write-Output
}

Write-Host "Verifying CUDA with Torch using 'conda run'..." -ForegroundColor Cyan
conda run -n $EnvName python "$Workspace/scripts/verify_cuda.py"

# Optionally train if dataset exists
$CsvPath = Join-Path $Workspace "dataset/px4_teacher/telemetry_adv.csv"
if (Test-Path $CsvPath) {
    Write-Host "Dataset found: $CsvPath. Starting training..." -ForegroundColor Green
    conda run -n $EnvName python "$Workspace/training/train_student_px4.py" --data "$CsvPath" --epochs 30 --bs 128 --out "$Workspace/models/student_px4.pt"
} else {
    Write-Host "No dataset found at $CsvPath. Run the PX4 collector, then re-run this script to train." -ForegroundColor Yellow
}
