# Proxy Launcher

Source folder: `/mnt/74A0E222A0E1EB16/docs/lesnar/proxy`

## What It Is

Proxy Launcher is a small Node.js browser-session launcher built on Puppeteer Extra and the stealth plugin. The main script creates or reuses a browser profile and supports optional browser-environment controls such as proxy routing, timezone emulation, and geolocation overrides.

## Main Signals

- `launcher.js` is the only meaningful entry point.
- The script uses `puppeteer-extra`, `puppeteer-extra-plugin-stealth`, and `yargs`.
- The code opens a persistent browser profile and applies optional environment overrides at launch time.

## Public Or Private?

Recommended: Private or internal only.

Why:
- It is environment-spoofing and proxy-routing tooling, not a strong public portfolio signal.
- It is easy to misread out of context.
- It adds more reputational risk than upside compared with your product, systems, and governance projects.

Public exception:
- Only publish it if you rewrite the framing around defensive browser QA or controlled environment testing and strip out anything that reads like anti-detection tooling.

## Note

The HDD volume is currently read-only, so this summary lives in the workspace instead of a new `README.md` inside the source folder.
