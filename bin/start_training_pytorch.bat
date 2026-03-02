@echo off
setlocal
set "PY=%~dp0..\airsim-env\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo Using %PY%

echo Installing PyTorch CUDA 11.8 (if needed)...
"%PY%" -m pip install -r "%~dp0..\training\requirements-pytorch.txt"

echo Quick synthetic train to produce a model...
"%PY%" "%~dp0..\training\pytorch_quick_synth.py" --out "%~dp0..\models\unet_torch_synth" --epochs 1 --samples 64 --size 128 128

echo If you already collected AirSim dataset, start real training:
echo   "%PY%" "%~dp0..\training\pytorch_unet.py" --data "%~dp0..\dataset" --img_size 256 256 --batch 8 --epochs 20 --out "%~dp0..\runs\unet_torch"

endlocal