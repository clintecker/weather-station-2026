#!/bin/sh
# Fetch the pinned KiCadRoutingTools (hardware/bench-breadboard-r0) into vendor/ (git-ignored), with
# its prebuilt router and its own Python environment. Re-running verifies the pins. Not part of
# tools/fetch-vendor.sh: CI does not need it, and the prebuilt binary is for macOS arm64 only.
set -eu
export GIT_NO_REPLACE_OBJECTS=1
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
krt="$root/vendor/KiCadRoutingTools"
venv="$root/vendor/krt-venv"
KRT_URL=https://github.com/drandyhaas/KiCadRoutingTools.git
KRT_TAG=v0.23.1
KRT_COMMIT=295f9ee197517e8323726853361eb137cc08ba9e   # the commit of tag v0.23.1 (tag object a26048ab714e)
ASSET=grid_router-macos-arm64.so
ASSET_SHA256=5f36bd314cfe54c450941d0a3c2a270badca239c5054fe00e627550b42bf0a68   # = the release asset digest on GitHub

if [ "$(uname -s)-$(uname -m)" != "Darwin-arm64" ]; then
  echo "fetch-router: the pinned prebuilt router is for macOS arm64; skipped on $(uname -s)-$(uname -m)"
  exit 0
fi
if [ ! -d "$krt/.git" ]; then
  git clone --quiet --depth 1 --branch "$KRT_TAG" "$KRT_URL" "$krt"
fi
actual=$(git -C "$krt" rev-parse HEAD)
[ "$actual" = "$KRT_COMMIT" ] || { echo "KiCadRoutingTools is at $actual, expected $KRT_COMMIT" >&2; exit 1; }
changes=$(git -C "$krt" status --porcelain --untracked-files=no)
[ -z "$changes" ] || { printf '%s has local changes:\n%s\n' "$krt" "$changes" >&2; exit 1; }

bin="$krt/rust_router/grid_router.so"
if [ ! -f "$bin" ]; then
  curl -fsSL -o "$bin" "https://github.com/drandyhaas/KiCadRoutingTools/releases/download/$KRT_TAG/$ASSET"
fi
sum=$(shasum -a 256 "$bin" | awk '{print $1}')
[ "$sum" = "$ASSET_SHA256" ] || { echo "$ASSET has SHA-256 $sum, expected $ASSET_SHA256" >&2; exit 1; }

if [ ! -x "$venv/bin/python" ]; then
  python3 -m venv "$venv"
fi
"$venv/bin/python" -m pip install --quiet --disable-pip-version-check -r "$root/hardware/bench-breadboard-r0/requirements-router.txt"
echo "ok KiCadRoutingTools $KRT_TAG $KRT_COMMIT, $ASSET $ASSET_SHA256"
