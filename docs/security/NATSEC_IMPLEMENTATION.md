# National-Security Hardening Implementation (Repository Scope)

This document records the controls implemented directly in this repository.

## Implemented controls

1. Fail-closed API authentication
- Backend now requires both `LESNAR_ADMIN_API_KEY` and `LESNAR_OPERATOR_API_KEY` when `LESNAR_REQUIRE_AUTH=1` (default).
- Startup fails if required keys are missing in enforced mode.

2. Restricted CORS policy
- Backend and Socket.IO now use explicit origin allow-list from `LESNAR_CORS_ORIGINS`.
- Wildcard origin policy is removed.

3. Tamper-evident signed audit chain
- Every command/event audit record is additionally written as a chained, signed entry.
- Location default: `docs/security/audit_chain.jsonl`.
- Signature: HMAC-SHA256 over canonical payload and previous hash.
- Required key: `LESNAR_AUDIT_CHAIN_KEY`.

4. Dataset integrity + signature tooling
- Script `scripts/dataset_integrity.py` creates and verifies signed manifests.
- Per-file metadata includes `sha256`, size, and timestamp.
- Required key: `LESNAR_DATASET_SIGN_KEY`.

5. Expanded security posture checks
- Script `scripts/security_posture_check.py` now checks:
  - localhost-only port binding,
  - loopback API host,
  - auth fail-closed enabled,
  - non-wildcard CORS,
  - required security keys present,
  - weak secrets.

## Operations checklist

1. Export secure runtime secrets

```bash
export LESNAR_REQUIRE_AUTH=1
export LESNAR_ADMIN_API_KEY='<strong-random-value>'
export LESNAR_OPERATOR_API_KEY='<strong-random-value>'
export LESNAR_AUDIT_CHAIN_KEY='<strong-random-value>'
export LESNAR_DATASET_SIGN_KEY='<strong-random-value>'
export LESNAR_CORS_ORIGINS='https://controlplane.example.mil'
```

2. Run baseline checks

```bash
python3 scripts/security_posture_check.py
```

3. Verify audit chain integrity

```bash
python3 scripts/verify_audit_chain.py
```

4. Sign and verify dataset

```bash
python3 scripts/dataset_integrity.py create --dataset-root dataset --manifest docs/security/dataset_manifest.json
python3 scripts/dataset_integrity.py verify --dataset-root dataset --manifest docs/security/dataset_manifest.json
```

## Important boundary

This repository now implements hardening primitives for authentication, auditability, and dataset integrity. Full national-security accreditation still requires external controls outside source code (HSM/KMS custody, host hardening baselines, SIEM/SOC operations, immutable storage policy, and formal compliance evidence).
