#!/usr/bin/env python3
import argparse
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def collect_files(dataset_root: Path, excluded_rel_paths: set[str] | None = None) -> list[Path]:
    excluded = excluded_rel_paths or set()
    files = []
    for path in dataset_root.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(dataset_root).as_posix()
        if rel in excluded:
            continue
        files.append(path)
    return sorted(files)


def build_manifest(dataset_root: Path, files: list[Path]) -> dict:
    entries = []
    for file_path in files:
        rel = file_path.relative_to(dataset_root).as_posix()
        stat = file_path.stat()
        entries.append({
            'path': rel,
            'size_bytes': stat.st_size,
            'modified_utc': datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            'sha256': sha256_file(file_path),
        })

    return {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'algorithm': 'sha256',
        'dataset_root': str(dataset_root.resolve()),
        'file_count': len(entries),
        'files': entries,
    }


def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode('utf-8')


def sign_manifest(payload: dict, key: str) -> str:
    return hmac.new(key.encode('utf-8'), canonical_bytes(payload), hashlib.sha256).hexdigest()


def write_manifest(manifest_path: Path, signed_payload: dict):
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(signed_payload, indent=2), encoding='utf-8')


def verify_manifest(dataset_root: Path, manifest_payload: dict, excluded_rel_paths: set[str] | None = None) -> tuple[bool, list[str]]:
    issues = []
    files = manifest_payload.get('files') or []
    excluded = excluded_rel_paths or set()

    for item in files:
        rel = item.get('path')
        expected_hash = item.get('sha256')
        expected_size = item.get('size_bytes')
        if not rel or not expected_hash:
            issues.append('manifest entry missing path/hash')
            continue

        file_path = dataset_root / rel
        if not file_path.exists():
            issues.append(f'missing file: {rel}')
            continue

        if file_path.stat().st_size != expected_size:
            issues.append(f'size mismatch: {rel}')

        actual_hash = sha256_file(file_path)
        if actual_hash != expected_hash:
            issues.append(f'hash mismatch: {rel}')

    current_files = {p.relative_to(dataset_root).as_posix() for p in collect_files(dataset_root, excluded)}
    manifest_files = {item.get('path') for item in files if item.get('path')}
    extras = sorted(current_files - manifest_files)
    for rel in extras:
        issues.append(f'untracked file: {rel}')

    return (len(issues) == 0, issues)


def load_key_from_env(env_name: str) -> str:
    key = (os.environ.get(env_name) or '').strip()
    if not key:
        raise RuntimeError(f'{env_name} is required for dataset manifest signing/verification.')
    return key


def run_create(args: argparse.Namespace) -> int:
    dataset_root = Path(args.dataset_root).resolve()
    if not dataset_root.exists() or not dataset_root.is_dir():
        raise RuntimeError(f'Dataset root not found: {dataset_root}')

    manifest_path = Path(args.manifest).resolve()
    excluded = set()
    try:
        excluded.add(manifest_path.relative_to(dataset_root).as_posix())
    except Exception:
        pass

    key = load_key_from_env(args.sign_key_env)
    files = collect_files(dataset_root, excluded)
    manifest = build_manifest(dataset_root, files)
    signature = sign_manifest(manifest, key)

    signed_payload = {
        **manifest,
        'signature': {
            'type': 'hmac-sha256',
            'key_env': args.sign_key_env,
            'value': signature,
        },
    }
    write_manifest(manifest_path, signed_payload)
    print(f'Wrote signed manifest: {args.manifest}')
    print(f'Files: {manifest["file_count"]}')
    return 0


def run_verify(args: argparse.Namespace) -> int:
    dataset_root = Path(args.dataset_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        raise RuntimeError(f'Manifest not found: {manifest_path}')

    excluded = set()
    try:
        excluded.add(manifest_path.relative_to(dataset_root).as_posix())
    except Exception:
        pass

    payload = json.loads(manifest_path.read_text(encoding='utf-8'))
    signature_block = payload.get('signature') or {}
    stored_signature = signature_block.get('value')
    key_env = signature_block.get('key_env') or args.sign_key_env

    if not stored_signature:
        raise RuntimeError('Manifest signature missing.')

    key = load_key_from_env(key_env)
    unsigned_payload = {k: v for k, v in payload.items() if k != 'signature'}
    expected_signature = sign_manifest(unsigned_payload, key)

    if not hmac.compare_digest(stored_signature, expected_signature):
        print('FAIL: manifest signature mismatch')
        return 2

    ok, issues = verify_manifest(dataset_root, unsigned_payload, excluded)
    if not ok:
        print('FAIL: dataset integrity check failed')
        for issue in issues:
            print(f' - {issue}')
        return 3

    print('PASS: signature valid and dataset integrity verified')
    return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description='Signed dataset integrity manifest tooling')
    p.add_argument('--dataset-root', default='dataset', help='Dataset root directory')
    p.add_argument('--manifest', default='docs/security/dataset_manifest.json', help='Manifest path')
    p.add_argument('--sign-key-env', default='LESNAR_DATASET_SIGN_KEY', help='Env var containing signing key')

    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('create', help='Create and sign manifest')
    sub.add_parser('verify', help='Verify manifest signature and dataset integrity')
    return p


def main() -> int:
    args = parser().parse_args()
    if args.command == 'create':
        return run_create(args)
    if args.command == 'verify':
        return run_verify(args)
    raise RuntimeError(f'Unsupported command: {args.command}')


if __name__ == '__main__':
    raise SystemExit(main())
