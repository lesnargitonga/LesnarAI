import hashlib
import hmac
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHAIN_FILE = REPO_ROOT / 'docs' / 'security' / 'audit_chain.jsonl'

_chain_lock = threading.Lock()


def _chain_file() -> Path:
    raw = (os.environ.get('LESNAR_AUDIT_CHAIN_FILE') or '').strip()
    return Path(raw) if raw else DEFAULT_CHAIN_FILE


def _chain_key() -> bytes:
    raw = (os.environ.get('LESNAR_AUDIT_CHAIN_KEY') or '').strip()
    if not raw:
        raise RuntimeError(
            'LESNAR_AUDIT_CHAIN_KEY is required for signed audit chain entries. '
            'Use a high-entropy secret and rotate it with standard key management.'
        )
    return raw.encode('utf-8')


def _canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _read_last_hash_and_seq(path: Path) -> tuple[str, int]:
    if not path.exists():
        return ('0' * 64, 0)

    last = ''
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            if line.strip():
                last = line.strip()

    if not last:
        return ('0' * 64, 0)

    try:
        record = json.loads(last)
        prev_hash = str(record.get('entry_hash') or ('0' * 64))
        seq = int(record.get('seq') or 0)
        return (prev_hash, seq)
    except Exception:
        return ('0' * 64, 0)


def append_signed_audit(kind: str, payload: dict) -> dict:
    path = _chain_file()
    path.parent.mkdir(parents=True, exist_ok=True)

    with _chain_lock:
        prev_hash, seq = _read_last_hash_and_seq(path)
        base = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'seq': seq + 1,
            'kind': kind,
            'prev_hash': prev_hash,
            'payload': payload,
        }
        entry_hash = hashlib.sha256(_canonical(base)).hexdigest()
        signature = hmac.new(_chain_key(), _canonical({**base, 'entry_hash': entry_hash}), hashlib.sha256).hexdigest()

        record = {
            **base,
            'entry_hash': entry_hash,
            'signature': signature,
            'algorithm': 'sha256+hmac-sha256',
        }

        with path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, sort_keys=True) + '\n')
            handle.flush()
            os.fsync(handle.fileno())

        return record


def verify_chain(path: Path | None = None) -> dict:
    chain_path = path or _chain_file()
    if not chain_path.exists():
        return {'ok': True, 'entries': 0, 'issues': []}

    issues = []
    expected_prev = '0' * 64
    expected_seq = 1
    entries = 0
    key = _chain_key()

    with chain_path.open('r', encoding='utf-8') as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            entries += 1
            try:
                record = json.loads(line)
            except Exception:
                issues.append(f'line {line_no}: invalid json')
                continue

            if int(record.get('seq') or -1) != expected_seq:
                issues.append(f'line {line_no}: seq mismatch expected={expected_seq} actual={record.get("seq")}')

            if str(record.get('prev_hash') or '') != expected_prev:
                issues.append(f'line {line_no}: prev_hash mismatch')

            base = {
                'ts': record.get('ts'),
                'seq': record.get('seq'),
                'kind': record.get('kind'),
                'prev_hash': record.get('prev_hash'),
                'payload': record.get('payload'),
            }
            recomputed_hash = hashlib.sha256(_canonical(base)).hexdigest()
            if recomputed_hash != record.get('entry_hash'):
                issues.append(f'line {line_no}: entry_hash mismatch')

            expected_sig = hmac.new(key, _canonical({**base, 'entry_hash': record.get('entry_hash')}), hashlib.sha256).hexdigest()
            if expected_sig != record.get('signature'):
                issues.append(f'line {line_no}: signature mismatch')

            expected_prev = str(record.get('entry_hash') or expected_prev)
            expected_seq += 1

    return {'ok': len(issues) == 0, 'entries': entries, 'issues': issues}
