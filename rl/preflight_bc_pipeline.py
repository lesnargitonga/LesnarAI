import argparse
import py_compile
import subprocess
import sys
import time
import socket
from pathlib import Path

import numpy as np


def compile_files(files: list[Path]) -> None:
    for f in files:
        py_compile.compile(str(f), doraise=True)


def _port_open(host: str, port: int, timeout_sec: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def wait_for_airsim(host: str, port: int, timeout_sec: int) -> None:
    deadline = time.time() + float(timeout_sec)
    last_print = 0.0
    while time.time() < deadline:
        if _port_open(host, port):
            return
        now = time.time()
        if now - last_print > 2.0:
            remaining = int(max(0, deadline - now))
            print(f"[PREFLIGHT] Waiting for AirSim RPC at {host}:{port} ({remaining}s left)...")
            last_print = now
        time.sleep(0.5)
    raise TimeoutError(f"AirSim RPC port not reachable at {host}:{port} after {timeout_sec}s")


def check_airsim_connection(host: str = "127.0.0.1", port: int = 41451) -> None:
    import airsim

    last_err: Exception | None = None
    for _ in range(5):
        try:
            try:
                client = airsim.MultirotorClient(ip=host, port=port)
            except TypeError:
                # Older API signature fallback.
                client = airsim.MultirotorClient(ip=host)
            client.confirmConnection()
            # A cheap API call that fails fast if the sim isn't responding.
            _ = client.getMultirotorState()
            return
        except Exception as e:
            last_err = e
            time.sleep(0.5)
    raise RuntimeError(f"AirSim connection check failed: {last_err}")


def run_collect_expert(python_exe: Path, steps: int, out_npz: Path) -> None:
    cmd = [
        str(python_exe),
        str(Path(__file__).with_name("collect_expert.py")),
        "--steps",
        str(steps),
        "--out",
        str(out_npz),
    ]
    subprocess.run(cmd, check=True)


def validate_npz(npz_path: Path) -> None:
    data = np.load(npz_path)
    for key in ("visual", "kinematics", "actions"):
        if key not in data:
            raise ValueError(f"Missing key '{key}' in {npz_path}")

    visual = data["visual"]
    kin = data["kinematics"]
    act = data["actions"]

    if visual.ndim != 3:
        raise ValueError(f"visual expected (N,H,W), got shape {visual.shape}")
    if kin.ndim != 2:
        raise ValueError(f"kinematics expected (N,19), got shape {kin.shape}")
    if act.ndim != 2 or act.shape[1] != 4:
        raise ValueError(f"actions expected (N,4), got shape {act.shape}")

    if kin.shape[1] != 19:
        raise ValueError(f"kinematics dim expected 19, got {kin.shape[1]}")

    n = act.shape[0]
    if visual.shape[0] != n or kin.shape[0] != n:
        raise ValueError(
            f"mismatched N: visual={visual.shape[0]} kin={kin.shape[0]} actions={n}"
        )


def run_bc_smoke(python_exe: Path, data_npz: Path, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    save_path = outdir / "ppo_lesnar_bc_smoke"
    cmd = [
        str(python_exe),
        str(Path(__file__).with_name("pretrain_bc.py")),
        "--data",
        str(data_npz),
        "--save_path",
        str(save_path),
        "--epochs",
        "1",
        "--batch",
        "32",
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--out", type=str, default="expert_vfh_smoke_preflight.npz")
    ap.add_argument("--skip_airsim", action="store_true")
    ap.add_argument("--skip_collect", action="store_true")
    ap.add_argument("--skip_bc", action="store_true")
    ap.add_argument("--smoke_outdir", type=str, default="runs/bc_smoke")
    ap.add_argument("--airsim_host", type=str, default="127.0.0.1")
    ap.add_argument("--airsim_port", type=int, default=41451)
    ap.add_argument(
        "--airsim_timeout",
        type=int,
        default=3600,
        help="Seconds to wait for AirSim before failing (lets you start the pipeline before Unreal)",
    )
    args = ap.parse_args()

    here = Path(__file__).resolve().parent
    python_exe = Path(sys.executable)

    to_compile = [
        here / "airsim_gym_env.py",
        here / "collect_expert.py",
        here / "pretrain_bc.py",
        here / "train_ppo.py",
    ]

    print("[PREFLIGHT] Compiling key RL scripts...")
    compile_files(to_compile)

    if not args.skip_airsim and not args.skip_collect:
        print("[PREFLIGHT] Checking AirSim connectivity...")
        wait_for_airsim(str(args.airsim_host), int(args.airsim_port), int(args.airsim_timeout))
        check_airsim_connection(str(args.airsim_host), int(args.airsim_port))

    out_npz = (here / args.out).resolve()

    if not args.skip_collect:
        print(f"[PREFLIGHT] Collecting {args.steps} expert steps -> {out_npz}")
        run_collect_expert(python_exe, steps=args.steps, out_npz=out_npz)

    if not args.skip_collect:
        print("[PREFLIGHT] Validating dataset shapes...")
        validate_npz(out_npz)

    if not args.skip_bc:
        print("[PREFLIGHT] Running 1-epoch BC smoke train (no AirSim)...")
        run_bc_smoke(python_exe, data_npz=out_npz, outdir=(here / args.smoke_outdir))

    print("[PREFLIGHT] OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
