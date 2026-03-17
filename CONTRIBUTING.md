# Contributing to Operation Sentinel

Thank you for your interest in contributing. This document outlines the process for reporting bugs, proposing features, and submitting code changes.

## Code of Conduct

All contributors are expected to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## How to Report a Bug

Before opening an issue, search existing issues to avoid duplicates.  
Use the **Bug Report** issue template and include:

- A clear, concise title
- Steps to reproduce the problem
- Expected versus observed behaviour
- Relevant log output (from `logs/`, container stdout, or teacher bridge output)
- Environment: OS, WSL version, PX4-Autopilot commit, Gazebo Harmonic version

## How to Request a Feature

Use the **Feature Request** issue template.  
Describe the problem you are trying to solve; do not assume a specific solution is required.

## Development Workflow

1. **Fork** the repository and create a branch from `main`.
2. Branch names must follow the pattern: `feat/<topic>`, `fix/<topic>`, or `docs/<topic>`.
3. Keep commits focused — one logical change per commit.
4. Follow conventional commit format: `type(scope): short description`
   - Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
5. Run the smoke test before opening a pull request:
   ```bash
   python3 scripts/smoke_runtime.py
   ```
6. Open a pull request against `main`.  
   Fill in the pull request template completely.

## Code Style

- Python: follow PEP 8. Max line length 100 characters.
- React/JS: ESLint rules defined in `frontend/.eslintrc`.
- No dead code, commented-out blocks, or TODO comments in merged changes.

## Security Issues

Do **not** open a public issue for security vulnerabilities.  
See [SECURITY.md](SECURITY.md) for the responsible disclosure process.

## Licence

By contributing, you agree that your contributions will be licensed under the same licence as this repository. See [LICENSE](LICENSE).
