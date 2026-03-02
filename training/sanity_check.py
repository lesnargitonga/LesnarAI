import importlib
import sys

mods = [
    ('numpy', 'numpy.__version__'),
    ('cv2', 'cv2.__version__'),
    ('torch', 'torch.__version__'),
    ('torchvision', 'torchvision.__version__'),
    ('tqdm', 'tqdm.__version__'),
    ('pandas', 'pandas.__version__'),
    ('yaml', 'yaml.__version__ if hasattr(yaml, "__version__") else "(PyYAML)"'),
    ('matplotlib', 'matplotlib.__version__'),
    ('skimage', 'skimage.__version__'),
    ('albumentations', 'albumentations.__version__'),
    ('gymnasium', 'gymnasium.__version__'),
    ('stable_baselines3', 'stable_baselines3.__version__'),
    ('airsim', 'airsim.__version__ if hasattr(airsim, "__version__") else "(airsim)"'),
]

ok = True
print("Sanity import/version check:\n")
for name, ver_expr in mods:
    try:
        m = importlib.import_module(name)
        ver = eval(ver_expr, {name: m})
        print(f"OK {name}: {ver}")
    except Exception as e:
        ok = False
        print(f"FAIL {name}: {e}")

sys.exit(0 if ok else 1)
