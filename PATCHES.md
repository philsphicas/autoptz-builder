# Carried changes

This build-only repo commits nothing from upstream `AutoPTZ/autoptz`. Instead the
workflow checks out upstream at a resolved release commit and applies a small,
auditable set of changes at build time. This file is the provenance ledger: every
carried change, why it exists, and when it can be retired.

There are two ways a change is applied:

- **Scripted edits** (`scripts/apply_edits.py`) — for values computed at build
  time (repo slug, release version, build number) and small dependency pins. Each
  edit asserts it matched exactly once, so any upstream drift fails the build
  loudly instead of silently shipping something wrong.
- **Source patches** (`patches/*.patch`) — for source-code fixes, carried as
  unified diffs and applied with `git apply --check <p> && git apply <p>`
  (depth 1, **no** `--3way`) so a stale patch fails loudly rather than silently
  3-way merging into a signed release. Generate with `git diff` from an upstream
  checkout so the `a/…`,`b/…` paths line up.

## Scripted edits

### Updater redirect

Point the in-app updater at this repo. `checker._repo()` already returns
`os.environ.get("AUTOPTZ_UPDATE_REPO", DEFAULT_REPO)`, so the target is
runtime-configurable without touching upstream's updater logic. `apply_edits.py`
writes a small builder-owned PyInstaller runtime hook
(`packaging/rthook_autoptz_update.py`) that `setdefault`s `AUTOPTZ_UPDATE_REPO`
to this repo, and registers it in the spec's `runtime_hooks` (spec-file builds
ignore the `--runtime-hook` CLI flag, so it must go in the spec). The hook runs
before any `autoptz` import; `setdefault` means a user's own value still wins,
and `checker.py` stays byte-for-byte upstream — nothing to drift against. If
upstream ever populates `runtime_hooks` itself, the `runtime_hooks=[]` token
disappears and the edit fails loudly (switch to appending).

*Lifecycle:* permanent — inherent to a rebuild repo.

### Version stamp

Stamp the computed release version into `autoptz/__init__.py` (`__version__`) and
`packaging/Info.plist` (`CFBundleShortVersionString` = `X.Y.Z`, `CFBundleVersion`
= a monotonic build number). `__version__` is the single source that drives the
DMG filename, the updater's self-version, and the installed package metadata.

*Lifecycle:* permanent — needed for the post-release (`X.Y.Z.postN`) scheme.

### Dependency pins

Upstream leaves `boxmot>=10.0.91` unpinned, so a fresh install resolves the newest
boxmot **major** (they cut breaking majors roughly monthly) and the tracker
crashes: in 22.x, `BotSort`/`ByteTrack`/`DeepOcSort` are no longer re-exported
from `boxmot.trackers`, so the code's `from boxmot.trackers import …` raises
`ImportError`; its fallback then reaches for the top-level `boxmot.BotSort`, which
22.x also dropped → `AttributeError` → hard crash.

We exact-pin `boxmot==19.0.0`. It is the newest boxmot that satisfies **all three**
constraints the build needs (verified by inspecting every major v11–v22):

1. **Import path** — `from boxmot.trackers import BotSort, ByteTrack, DeepOcSort`
   still resolves. (True through v21 too; v22 removed these re-exports.)
2. **Constructor API** — the classes take `reid_model` / `with_reid` /
   `embedding_off` / `cmc_method`, matching the code's calls. (v16–v18 export the
   names but still use the old `reid_weights` kwarg, so they'd `TypeError`.)
3. **Installable on Intel mac** — v19's numpy is unpinned, so it co-installs with
   numpy 1.26.4 + torch 2.2.2. v20 bumped boxmot to `numpy>=2.2.0`, which has no
   valid torch pairing on x86_64 macOS (see below) — so v20/v21, despite matching
   1+2, can't build there.

The classes and constructors are actually still compatible in v20–v22 (only the
*import path* and the numpy floor changed), so the crash is a packaging/re-export
regression, not a tracking-algorithm change — hence the exact pin plus the
defence-in-depth patch below.

boxmot pulls torch, and the numpy/torch compatibility problem is
**macOS-Intel-only**: the last torch x86_64-macOS wheel is 2.2.2 (needs numpy<2),
while numpy-2 support starts at torch 2.3.0 (which dropped Intel-mac wheels). So
the pins split by platform marker — Intel mac gets torch 2.2.2 + numpy 1.26.4;
every other platform keeps numpy 2.2.6 and a modern `torch>=2.3` (the floor
prevents pip backtracking into the numpy-2 ABI trap). Applied to
`requirements/tracking.txt` (boxmot/torch/torchvision) and `requirements/base.txt`
(numpy).

*Lifecycle:* temporary — retire once upstream ships equivalent pins (see the
upstream tracking note at the bottom).

## Source patches

### `0001-track-graceful-degrade-on-incompatible-boxmot.patch`

Hardens `_create_boxmot_tracker()` in `autoptz/engine/pipeline/track.py`. Upstream
tries the `boxmot.trackers` (>=11) API and, on `ImportError`, falls back to the
top-level `boxmot.*` classes — but a boxmot **major** bump removes those top-level
names, so the fallback raises `AttributeError` (uncaught by `except ImportError`)
and, with no ReID, the outer handler re-raises: a hard crash on the first tracked
frame. The patch makes *any* boxmot instantiation failure degrade to the built-in
`_SimpleIoUTracker` (as the "boxmot not installed" path already does), logged
once. It is defence-in-depth on top of the boxmot pin: the pin keeps the tested
API, this keeps the app alive if a future resolve ever drifts.

*Lifecycle:* temporary — retire once the equivalent fix lands upstream.

### `0002-build-macos-retry-codesign-on-timestamp-flake.patch`

Wraps `codesign` in `packaging/build_macos.sh` with a retry helper. codesign's
`--timestamp` step contacts Apple's secure timestamp server, which intermittently
answers "The timestamp service is not available." A build signs 200+ nested
Mach-O binaries, so even a rare per-call flake reliably sinks a build — it already
killed one release-gating x86_64 build while the arm64 build on the same commit
passed, proving it transient. The patch adds `codesign_with_retry()` (5 attempts,
linear backoff) and routes all three executed `--timestamp` sites (nested Mach-O
loop, app bundle, DMG) through it. Retries fire **only** on the timestamp-service
message, so genuine signing errors still fail fast. Mirrors upstream's existing
`create_dmg()` hdiutil retry.

*Lifecycle:* temporary — retire once an equivalent retry lands upstream.

## Upstream tracking

The dependency pins and the graceful-degrade patch are workarounds for upstream
gaps and should be proposed upstream so they can eventually be dropped here:

- pin boxmot (and split torch/numpy by platform marker) in upstream's
  requirements,
- degrade gracefully in `track.py` instead of crashing on an incompatible boxmot,
  and
- retry `codesign` on the transient Apple timestamp-service flake in
  `build_macos.sh` (parallels upstream's existing hdiutil retry).

The updater redirect and version stamp are inherent to a rebuild repo and stay.
