# HDD Project Privacy Matrix

This file summarizes the codebases found under `/mnt/74A0E222A0E1EB16/docs/lesnar` and gives a practical recommendation for whether each should be treated as public, private, or archive-only.

The HDD volume is currently read-only, so missing project docs could not be added in place there. Companion summaries for the missing-doc projects live in this folder.

| Project | Current doc status | What it does | Recommended visibility | Notes |
|---|---|---|---|---|
| Lesnar AI | Has README | UAV autonomy, simulation, control, and training stack | Public flagship | Strongest portfolio repo. |
| Lesnar AI - Copy | Has README | Duplicate or older variant of Lesnar AI | Private/archive | Keep as backup only. |
| Lesnar AI_recovery_git | Has README | Recovery copy of Lesnar AI | Private/archive | Not a public-facing project. |
| MediMatch | Has README | Medical supply redistribution app scaffold | Public candidate | Good product and systems signal. |
| response parser | Has README | MediMatch survey/data-generation and analysis tooling | Public after sanitization | Current HDD copy previously showed local credentials/data artifacts. |
| Campus Map | Missing in-source README on HDD; workspace summary added | Campus navigation, routing, group and safety flows | Public candidate | See `Campus-Map.md`. |
| doc debunker | Has README | Streamlit research report generator | Public candidate | Good applied AI tooling story. |
| e com | Has README | Defender-first e-commerce security assessor | Public candidate | Stronger if framed as safe assessment tooling. |
| Simy | Has README | Secure communications platform rebuild | Public candidate | Strong technical systems signal; review secrets before release. |
| Mel | Missing in-source README on HDD; workspace summary added | Boutique storefront frontend prototype | Public candidate | See `Mel-Fashion-Shop.md`. |
| trader | Has README | Trading dashboard or trading app | Private | Weak public signal, higher risk profile. |
| option trader | Has README | Deriv options trading agent | Private | Financial automation and account-linked workflow. |
| mempool sniper | Has README | Mempool trading bot scaffold | Private | High misuse and reputational risk. |
| proxy | Missing in-source README on HDD; workspace summary added | Browser launcher with proxy and environment overrides | Private | See `Proxy-Launcher.md`. |
| email bypass | Has README | Email security research framework | Private | Too sensitive for a general public portfolio. |

## Suggested Public Set

- Lesnar AI
- MediMatch
- Campus Map
- doc debunker
- e com
- Simy
- Mel

## Suggested Private Or Archive Set

- Lesnar AI - Copy
- Lesnar AI_recovery_git
- trader
- option trader
- mempool sniper
- proxy
- email bypass

## Borderline Set

- response parser

`response parser` can be public if you strip local credentials, generated data, and any project-specific private artifacts. If you do not want to maintain that cleanup, keep it private.
