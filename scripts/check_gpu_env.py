"""GPU / ML environment diagnostics for Lesnar AI.
Safe to run even if packages are partially installed.
Prints JSON-ish lines so batch scripts can parse if needed.
"""
from __future__ import annotations
import json, sys, platform, importlib, subprocess
from typing import Dict, Any

REPORT: Dict[str, Any] = {
    "python": sys.version.split()[0],
    "platform": platform.platform(),
    "cuda": {
        "nvidia_smi": None,
        "driver_version": None,
    },
    "packages": {}
}

PKGS = [
    ("torch", ["cuda.is_available", "__version__"]),
    ("tensorflow", ["__version__"]),
    ("opencv-python", ["__version__"]),
    ("cv2", ["__version__"]),
    ("numpy", ["__version__"]),
]

# Query nvidia-smi
try:
    smi = subprocess.run(["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                         capture_output=True, text=True, timeout=3)
    if smi.returncode == 0:
        driver = smi.stdout.strip().splitlines()[0] if smi.stdout.strip() else None
        REPORT["cuda"]["nvidia_smi"] = True
        REPORT["cuda"]["driver_version"] = driver
    else:
        REPORT["cuda"]["nvidia_smi"] = False
except Exception:
    REPORT["cuda"]["nvidia_smi"] = False

for mod_name, attrs in PKGS:
    entry: Dict[str, Any] = {"present": False}
    try:
        mod = importlib.import_module(mod_name)
        entry["present"] = True
        # Special handling for torch cuda availability
        if mod_name == "torch" and hasattr(mod, "cuda"):
            try:
                entry["cuda_available"] = bool(mod.cuda.is_available())
            except Exception:
                entry["cuda_available"] = None
        for a in attrs:
            if a == "cuda.is_available":
                continue
            value = None
            part = mod
            for piece in a.split('.'):
                if hasattr(part, piece):
                    part = getattr(part, piece)
                else:
                    part = None
                    break
            if callable(part):
                try:
                    value = part()
                except Exception:
                    value = None
            else:
                value = part
            entry[a.replace('.', '_')] = value
    except Exception as e:
        entry["error"] = str(e)
    REPORT["packages"][mod_name] = entry

print("[GPU_ENV]" + json.dumps(REPORT))

# Simple human readable summary
print("\n=== Lesnar AI GPU / ML Environment ===")
print(f"Python          : {REPORT['python']}")
print(f"Platform        : {REPORT['platform']}")
print(f"nvidia-smi      : {REPORT['cuda']['nvidia_smi']}")
print(f"Driver Version  : {REPORT['cuda']['driver_version']}")

torch_info = REPORT['packages'].get('torch', {})
print(f"PyTorch Present : {torch_info.get('present')}")
print(f"PyTorch Version : {torch_info.get('__version__')}")
print(f"CUDA Available  : {torch_info.get('cuda_available')}")

tf_info = REPORT['packages'].get('tensorflow', {})
print(f"TensorFlow Pres : {tf_info.get('present')}")
print(f"TF Version      : {tf_info.get('__version__')}")

cv_info = REPORT['packages'].get('cv2', {})
print(f"OpenCV Present  : {cv_info.get('present')}")
print(f"OpenCV Version  : {cv_info.get('__version__')}")

np_info = REPORT['packages'].get('numpy', {})
print(f"NumPy Present   : {np_info.get('present')}")
print(f"NumPy Version   : {np_info.get('__version__')}")

print("======================================")
