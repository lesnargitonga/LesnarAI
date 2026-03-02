@echo off
setlocal ENABLEDELAYEDEXPANSION

REM Prefer the workspace venv's python; fallback to system python
set "PYTHON=%~dp0..\airsim-env\Scripts\python.exe"
if not exist "%PYTHON%" (
    set "PYTHON=python"
)

echo Using Python: %PYTHON%

echo Installing training requirements (may take a few minutes)...
"%PYTHON%" -m pip install -r "%~dp0..\training\requirements.txt"
"%PYTHON%" -m pip install tensorflow_hub

echo Exporting TFHub DeepLabV3 model...
"%PYTHON%" "%~dp0..\training\export_tfhub_deeplab.py" --out "%~dp0..\models\deeplabv3_cityscapes"

echo Quick training a small UNet on synthetic blobs...
"%PYTHON%" "%~dp0..\training\quick_train_synth_unet.py" --out "%~dp0..\models\unet_synth" --epochs 2 --samples 64 --size 128 128

echo Models prepared under models/.

endlocal
