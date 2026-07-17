# autoptz-builder

A standalone build repo that repackages upstream [AutoPTZ](https://github.com/AutoPTZ/autoptz)
releases as **signed, notarized macOS DMGs with the `boxmot` tracking extra bundled**
(BoT-SORT / DeepOCSORT / ByteTrack + OSNet ReID) — the features the default
torch-free upstream DMG omits.

This repo contains **no AutoPTZ source**, only one workflow
([`.github/workflows/build.yml`](.github/workflows/build.yml)). It is **not a fork**,
so there is nothing to sync and no merge conflicts, ever.

## How it works

Daily (and on demand), the workflow:

1. Checks whether upstream has a newer **stable** release than this repo already ships.
2. If so, checks out `AutoPTZ/autoptz` at that release tag and applies two build-time tweaks:
   - installs with `--with-tracking` → **boxmot bundled** into the app;
   - rewrites `DEFAULT_REPO` in `autoptz/update/checker.py` → **this repo**, so the
     installed app's in-app updater pulls future builds from here.
3. Builds `arm64` (Apple Silicon) and `x86_64` (Intel) DMGs, code-signs + notarizes them.
4. Publishes both DMGs plus a `SHA256SUMS` manifest as a release tagged to match upstream.

Install once from this repo's [Releases](../../releases); after that the app
auto-updates itself from here.

## Required secrets

Set on this repo (Settings → Secrets and variables → Actions):

| Secret | Purpose |
| --- | --- |
| `MACOS_CERTIFICATE_P12_BASE64` | base64 of the Developer ID Application `.p12` |
| `MACOS_CERTIFICATE_PASSWORD` | password for that `.p12` |
| `MACOS_SIGN_IDENTITY` | e.g. `Developer ID Application: NAME (TEAMID)` |
| `MACOS_NOTARY_APPLE_ID` | Apple ID used for notarization |
| `MACOS_NOTARY_TEAM_ID` | Apple Developer Team ID |
| `MACOS_NOTARY_PASSWORD` | app-specific password from appleid.apple.com |
