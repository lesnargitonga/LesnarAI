#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / 'backend'))

from audit_chain import verify_chain


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify signed audit chain integrity')
    parser.add_argument('--chain-file', default=None, help='Optional path to audit chain jsonl file')
    args = parser.parse_args()

    path = Path(args.chain_file).resolve() if args.chain_file else None
    result = verify_chain(path)
    print(json.dumps(result, indent=2))
    return 0 if result.get('ok') else 2


if __name__ == '__main__':
    raise SystemExit(main())
