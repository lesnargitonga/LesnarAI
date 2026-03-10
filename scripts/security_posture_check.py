#!/usr/bin/env python3
import json
import os
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DOCKER_COMPOSE = REPO / "docker-compose.yml"
CONFIG = REPO / "config.json"
BACKEND_APP = REPO / "backend" / "app.py"
REPORT_DIR = REPO / "docs" / "security"
REPORT_JSON = REPORT_DIR / "security_posture_report.json"
REPORT_MD = REPORT_DIR / "SECURITY_POSTURE.md"


DEFAULT_SECRETS = {
    "example-password",
    "example-operator-key",
    "example-admin-key",
    "replace-with-strong-random-secret",
    "dev-secret",
    "changeme",
    "password",
}


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def build_report() -> dict:
    compose_text = read_text(DOCKER_COMPOSE)
    app_text = read_text(BACKEND_APP)
    cfg = {}
    try:
        cfg = json.loads(read_text(CONFIG))
    except Exception:
        pass

    findings = []

    localhost_ports = [
        "127.0.0.1:5000:5000",
        "127.0.0.1:5432:5432",
        "127.0.0.1:6379:6379",
        "127.0.0.1:8080:8080",
    ]
    missing_localhost = [p for p in localhost_ports if p not in compose_text]
    if missing_localhost:
        findings.append({
            "level": "high",
            "title": "Service port exposure",
            "detail": f"Missing localhost bind(s): {missing_localhost}",
            "recommendation": "Bind all service ports to 127.0.0.1 unless external access is required.",
        })

    api_host = cfg.get("api_settings", {}).get("host", "")
    if api_host and api_host != "127.0.0.1":
        findings.append({
            "level": "medium",
            "title": "API host not loopback",
            "detail": f"config.json api_settings.host={api_host}",
            "recommendation": "Set API host to 127.0.0.1 for local secure operations.",
        })

    require_auth = os.environ.get("LESNAR_REQUIRE_AUTH", "1").strip()
    if require_auth != "1":
        findings.append({
            "level": "high",
            "title": "Auth fail-closed disabled",
            "detail": "LESNAR_REQUIRE_AUTH is not set to 1",
            "recommendation": "Set LESNAR_REQUIRE_AUTH=1 and configure admin/operator API keys.",
        })

    if "cors_allowed_origins=\"*\"" in app_text or "CORS(app)" in app_text:
        findings.append({
            "level": "high",
            "title": "Permissive CORS policy",
            "detail": "Detected wildcard or unrestricted CORS configuration in backend/app.py",
            "recommendation": "Restrict CORS origins using LESNAR_CORS_ORIGINS to approved control-plane hosts.",
        })

    weak_env = []
    for key in [
        "POSTGRES_PASSWORD",
        "LESNAR_ADMIN_API_KEY",
        "LESNAR_OPERATOR_API_KEY",
        "FLASK_SECRET_KEY",
        "LESNAR_AUDIT_CHAIN_KEY",
        "LESNAR_DATASET_SIGN_KEY",
    ]:
        value = os.environ.get(key, "")
        if value and value.strip().lower() in DEFAULT_SECRETS:
            weak_env.append(key)
    if weak_env:
        findings.append({
            "level": "high",
            "title": "Weak runtime secrets detected",
            "detail": f"Weak values detected for: {weak_env}",
            "recommendation": "Rotate credentials and use strong random values (>=24 chars).",
        })

    missing_required_keys = []
    for key in ["LESNAR_ADMIN_API_KEY", "LESNAR_OPERATOR_API_KEY", "LESNAR_AUDIT_CHAIN_KEY", "LESNAR_DATASET_SIGN_KEY"]:
        if not (os.environ.get(key) or "").strip():
            missing_required_keys.append(key)
    if missing_required_keys:
        findings.append({
            "level": "high",
            "title": "Missing required security keys",
            "detail": f"Unset keys: {missing_required_keys}",
            "recommendation": "Provision secrets from a managed secret store and inject at runtime.",
        })

    status = "pass" if not findings else "needs_attention"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "checks": {
            "localhost_port_binding": len(missing_localhost) == 0,
            "api_host_loopback": (api_host == "127.0.0.1"),
            "weak_runtime_secrets": len(weak_env) == 0,
            "auth_fail_closed": require_auth == "1",
            "non_wildcard_cors": not ("cors_allowed_origins=\"*\"" in app_text or "CORS(app)" in app_text),
            "required_security_keys_present": len(missing_required_keys) == 0,
        },
        "findings": findings,
        "notes": [
            "This is a local security baseline check, not a formal certification.",
            "For stronger security: secret manager, TLS termination, encrypted backups, signed audit logs.",
        ],
    }


def write_reports(report: dict):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = [
        "# Security Posture Report",
        "",
        f"Generated: {report['generated_at']}",
        f"Status: {report['status']}",
        "",
        "## Checks",
    ]

    for key, value in report['checks'].items():
        lines.append(f"- {key}: {value}")

    lines += ["", "## Findings"]

    if not report["findings"]:
        lines.append("- No high-confidence baseline findings.")
    else:
        for item in report["findings"]:
            lines.append(f"- [{item['level'].upper()}] {item['title']}: {item['detail']}")
            lines.append(f"  - Recommendation: {item['recommendation']}")

    lines += ["", "## Notes"] + [f"- {n}" for n in report["notes"]]
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    rep = build_report()
    write_reports(rep)
    print(f"Wrote: {REPORT_JSON}")
    print(f"Wrote: {REPORT_MD}")
