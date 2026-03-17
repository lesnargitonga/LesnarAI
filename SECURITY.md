# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| `main` branch | Yes |

Only the current `main` branch receives security fixes.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

To report a vulnerability, please email the maintainers directly (see the repository contact information) or use GitHub's private security advisory feature:

1. Navigate to the repository on GitHub.
2. Click **Security** → **Advisories** → **New draft security advisory**.
3. Provide a clear description of the vulnerability, steps to reproduce it, and its potential impact.

You will receive an acknowledgement within 72 hours.

## Disclosure Policy

- Vulnerabilities will be assessed and triaged within 7 days of receipt.
- A fix will be developed and tested privately.
- A security advisory will be published once a fix is available and merged to `main`.
- Credit will be given to the reporter unless they request otherwise.

## Scope

The following are in scope:

- Authentication and session handling (`backend/app.py`, `scripts/manage_auth_users.py`)
- API key validation and role enforcement
- Redis command injection
- Secrets exposed in logs or repository

The following are out of scope for this policy:

- Denial-of-service against the local simulator (Gazebo/PX4)
- Simulation-only exploits with no path to production systems
- Issues in third-party dependencies already reported upstream

## Security Hardening Notes

- The backend runs in external-only mode (`LESNAR_EXTERNAL_ONLY=1`) by default.
- API keys are scoped by role and read from `.env` at startup; they are never committed to the repository.
- Session tokens are Postgres-backed with server-side expiry.
- The `audit_chain.py` module maintains an append-only signed event log.
