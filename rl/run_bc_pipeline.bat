@echo off
cd /d "%~dp0"
echo ===========================================
echo   LESNAR AI: ZURICH-CLASS TRAINING PIPELINE
echo ===========================================
echo.

echo [Preflight] Sanity checks (syntax + AirSim + dataset + 1-epoch BC smoke)...
..\airsim-env\Scripts\python.exe preflight_bc_pipeline.py --steps 300 --out expert_vfh_preflight_300.npz --smoke_outdir runs\bc_smoke --airsim_timeout 3600
if errorlevel 1 goto error
echo.

echo [Phase 1] FEEDING THE BRAIN (Data Collection)
echo Running VFH Expert to generate 50,000 steps of high-quality flight data...
echo.
..\airsim-env\Scripts\python.exe collect_expert.py --steps 50000 --out expert_vfh_50k.npz --no-compress
if errorlevel 1 goto error

echo.
echo [Phase 2] BEHAVIOR CLONING (Supervised Study)
echo Forcing RecurrentPPO to mimic the VFH Expert...
echo.
..\airsim-env\Scripts\python.exe pretrain_bc.py --data expert_vfh_50k.npz --save_path runs/ppo_lesnar_bc_pretrained --epochs 20
if errorlevel 1 goto error

echo.
echo [Phase 3] REINFORCEMENT LEARNING (Fine-Tuning)
echo Starting PPO training from the pre-trained brain...
echo.
echo NOTE: Modifications needed in train_ppo.py to load 'runs/ppo_lesnar_bc_pretrained' !!!
echo for now, just launching data collection and BC.
echo.
echo Done.
exit /b 0

:error
echo.
echo [ERROR] Pipeline failed. Check logs.
exit /b 1
