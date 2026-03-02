# Data Ingestion Manual

## 1. Overview
This document outlines the procedures for acquiring, verifying, and organizing external datasets required for model training and validation within Project Sentinel.

## 2. Dataset Management Utilities

The repository includes Python utilities for automated dataset management:
-   **Location**: `datasets/`
-   **Execution Environment**: any Python env with required deps (legacy default was `legacy/airsim-env`).

### 2.1 Audit & Planning
To verify existing datasets and generate a download plan:

```powershell
& "bin\audit_datasets.bat"
```
*(Note: Ensure python path matches your setup; legacy default is `legacy\airsim-env\Scripts\python.exe`.)*

## 3. Acquisition Protocols

### 3.1 Open Source Datasets
The following datasets are authorized for automated retrieval:
-   **Drone Specific**: VisDrone, UAVDT, Stanford Drone Dataset (SDD).
-   **Synthetic**: TartanAir, AirSim-Synth.

**Command:**
```powershell
python scripts/download_datasets.py --keys visdrone uavdt --dest D:\datasets
```

### 3.2 Restricted Access Datasets
Certain datasets utilize proprietary licenses and require authentication (Cityscapes, Mapillary, Waymo).
1.  Obtain credentials/cookies from the official vendor portal.
2.  Export cookies to `cookies.txt`.
3.  Execute secure download:

```powershell
python scripts/download_datasets.py --profile secure --cookie-file cookies.txt
```

## 4. Directory Structure

Data must be organized according to the following schema to ensure compatibility with training pipelines:

```text
D:\datasets\
├── coco/
├── cityscapes/
│   ├── leftImg8bit/
│   └── gtFine/
├── visdrone/
└── airsim_synth/ (Generated locally)
```

## 5. Troubleshooting

-   **Checksum Mismatch**: Delete the corrupted archive in `_archives/` and retry.
-   **Authentication Failure**: Regenerate `cookies.txt` and verify session validity.
-   **Network Timeout**: The script supports resume capability; re-execute the command.
