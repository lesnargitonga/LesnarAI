# Campus Map

Source folder: `/mnt/74A0E222A0E1EB16/docs/lesnar/Campus Map`

## What It Is

Campus Map is a React and TypeScript campus navigation app built around Mapbox and Firebase. Based on the application entry points and component layout, it supports interactive campus mapping, point-of-interest browsing, route planning, group coordination flows, lost-and-found handling, and safety-oriented navigation features such as hazard-aware routing.

## Main Signals

- `src/FreshApp.tsx` contains the main map workflow.
- `src/components/` includes routing, group, lost-and-found, and map panels.
- `package.json` describes the app as `Campus Map Navigator` and uses React, Mapbox, and Firebase.

## Public Or Private?

Recommended: Public candidate.

Why:
- Clear product story.
- Strong student and portfolio signal.
- Easy to explain in demos and interviews.

Before public release:
- Remove `.env` and `node_modules` from the HDD copy.
- Keep only the docs that support the public narrative.
- Add screenshots or a short architecture diagram if you want it to read more professionally.

## Note

The HDD volume is currently read-only, so this summary lives in the workspace instead of a new `README.md` inside the source folder.
